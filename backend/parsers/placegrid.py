"""
PlaceGridParser - dual-meet results published as an Event x Place matrix:

    Event         1st                 2nd                 3rd
    4x800         Massabesic 11:02    Kennebunk           McAuley 11:12.7
                                      11:08.8
    110 Hurdles   Sither S 17.4       Heinbach K 18.5     Salamone Mc 18.9

Individual cells are "Lastname CODE mark" with 1-3 letter school codes; relay
cells use full school names, which lets the parser build the code->school map
per file (code is a prefix of a full name).
"""

import re
from .base import BaseParser
from .looselist import canon_event, is_mark

HEADER_RE = re.compile(r'^\s*(?:girls|boys)?\s*events?\s+(1st(?:\s+place)?|first)\b', re.I)
PLACE_RE = re.compile(r'\b(1st|2nd|3rd|4th|5th|6th|first|second|third|fourth|fifth|sixth)\b', re.I)


class PlaceGridParser(BaseParser):
    def parse(self, text, meet_url, season_type):
        from bs4 import BeautifulSoup
        if '<' in text[:2000].lower():
            soup = BeautifulSoup(text, 'html.parser')
            pres = soup.find_all('pre')
            text = "\n".join(p.get_text() for p in pres) if pres else soup.get_text(separator='\n')
        lines = text.replace('\xa0', ' ').splitlines()

        header_idx = None
        for i, l in enumerate(lines):
            if HEADER_RE.match(l):
                header_idx = i
                break
        if header_idx is None:
            # two-line header variant: a "1st  2nd  3rd..." line adjacent to
            # a line containing "Event"
            for i, l in enumerate(lines):
                if len(PLACE_RE.findall(l)) >= 3 and 'event' in \
                        (lines[i - 1] + ' ' + l + ' ' + (lines[i + 1] if i + 1 < len(lines) else '')).lower():
                    header_idx = i
                    break
        if header_idx is None:
            return {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}

        header = lines[header_idx]
        try:
            ev_col = header.lower().index('event')
        except ValueError:
            ev_col = 0
        cols = [ev_col]
        for m in PLACE_RE.finditer(header):
            cols.append(m.start())
        spans = [(cols[i], cols[i + 1] if i + 1 < len(cols) else 10 ** 6)
                 for i in range(len(cols))]

        # Build rows: a line with text in the Event column starts a new row;
        # otherwise its column slices append to the previous row's cells.
        # "Team:" / "Time:" / "Mark:" sub-rows carry the schools and marks for
        # the names accumulated above them (Wiscasset-style sheets).
        rows = []          # simple cells rows
        subrow_events = [] # (event_label, names[], schools[], marks[]) tuples
        current_sub = None
        has_subrows = any(re.match(r'\s*(team|school)s?:', l, re.I) for l in lines)
        for l in lines[header_idx + 1:]:
            if not l.strip() or HEADER_RE.match(l):
                continue
            cells = [l[s:e].strip() for s, e in spans]
            if has_subrows:
                label = cells[0].lower().rstrip(':')
                if label in ('team', 'teams', 'school', 'schools'):
                    if current_sub:
                        current_sub[2] = [(a + ' ' + b).strip() for a, b in
                                          zip(current_sub[2], cells[1:])] if current_sub[2] else cells[1:]
                    continue
                if label in ('time', 'times', 'mark', 'marks', 'distance', 'dist', 'height'):
                    if current_sub:
                        current_sub[3] = cells[1:]
                    continue
                if cells[0] and (current_sub is None or current_sub[3]):
                    # a new event starts only after the previous one's marks
                    current_sub = [cells[0], cells[1:], [], []]
                    subrow_events.append(current_sub)
                elif current_sub:
                    # continuation: wrapped event label and/or wrapped names
                    if cells[0]:
                        current_sub[0] = (current_sub[0] + ' ' + cells[0]).strip()
                    current_sub[1] = [(a + ' ' + b).strip() for a, b in
                                      zip(current_sub[1], cells[1:])]
                continue
            if cells[0]:
                rows.append(cells)
            elif rows:
                for k in range(1, len(cells)):
                    if cells[k]:
                        rows[-1][k] = (rows[-1][k] + ' ' + cells[k]).strip()

        # Legend codes: "At Traip (T) – With Freeport (FP), Fryeburg (FA)..."
        legend = {}
        for l in lines[:6]:
            for m in re.finditer(r'([A-Z][A-Za-z .\'-]{2,30}?)\s*\(([A-Z]{1,3})\)', l):
                legend[m.group(2)] = m.group(1).strip().lstrip('With ').strip()

        # Gender from filename
        url_low = meet_url.lower()
        gender = 'Girls' if re.search(r'girl|women|[_\-]?g\.(pdf|htm)|\dg\b', url_low) else \
                 'Boys' if re.search(r'boy|men|[_\-]?b\.(pdf|htm)|\db\b', url_low) else 'Girls'

        # First pass: collect relay school full names for the code map
        full_schools = set()
        for cells in rows:
            if re.search(r'relay|medley|4x', cells[0], re.I):
                for cell in cells[1:]:
                    toks = cell.split()
                    if not toks:
                        continue
                    words = [t for t in toks if not is_mark(t)]
                    if len(words) >= 1 and all(len(w) > 1 for w in words):
                        full_schools.add(' '.join(words))

        def resolve_code(code):
            if code in legend:
                return legend[code]
            matches = [s for s in full_schools
                       if s.lower().startswith(code.lower())]
            if len(matches) == 1:
                return matches[0]
            # typo variants of the same school ("Masssabesic"/"Massabesic")
            if matches and len({m.lower()[:4] for m in matches}) == 1:
                return min(matches, key=len)
            return code

        events = []
        for label, names, schools, marks in subrow_events:
            ev_name = canon_event(label)
            is_relay = bool(re.search(r'relay|medley|4\s*x', label, re.I))
            results = []
            for k in range(max(len(names), len(marks))):
                name = names[k].strip() if k < len(names) else ''
                school = schools[k].strip() if k < len(schools) else ''
                mark = (marks[k].split()[0] if k < len(marks) and marks[k] else '')
                mark = re.sub(r'\(tie.*$', '', mark).strip()
                if not mark or not is_mark(mark):
                    continue
                if is_relay or not name:
                    if school or name:
                        results.append({'school': school or name, 'result': mark,
                                        'athletes': [], 'grade': '', 'type': 'Finals'})
                else:
                    results.append({'athlete': name, 'school': school or 'Unknown',
                                    'result': mark, 'grade': '', 'type': 'Finals'})
            if results:
                events.append({'event': ev_name, 'gender': gender or 'Boys',
                               'is_relay': is_relay, 'results': results})

        for cells in rows:
            label = cells[0].replace('\x00', '').strip()
            ev_name = canon_event(label)
            is_relay = bool(re.search(r'relay|medley|4x', label, re.I))
            results = []
            for cell in cells[1:]:
                # paired-rows cells look like "Simonds T | 16.9"
                if ' | ' in cell:
                    who, pmark = cell.rsplit(' | ', 1)
                    pmark = pmark.strip()
                    ptoks = who.split()
                    if not ptoks or not is_mark(pmark):
                        continue
                    if is_relay:
                        results.append({'school': resolve_code(' '.join(ptoks)),
                                        'result': pmark, 'athletes': [], 'grade': '',
                                        'type': 'Finals'})
                    elif len(ptoks) >= 2 and ptoks[-1] in legend:
                        results.append({'athlete': ' '.join(ptoks[:-1]),
                                        'school': legend[ptoks[-1]], 'result': pmark,
                                        'grade': '', 'type': 'Finals'})
                    else:
                        results.append({'athlete': ' '.join(ptoks), 'school': 'Unknown',
                                        'result': pmark, 'grade': '', 'type': 'Finals'})
                    continue
                toks = cell.split()
                if not toks:
                    continue
                mark = None
                for i in range(len(toks) - 1, -1, -1):
                    if is_mark(toks[i]):
                        mark = toks[i].rstrip('*qQjJ')
                        head = toks[:i]
                        tail = [t for t in toks[i + 1:] if not is_mark(t)]
                        break
                if mark is None or not (head or tail):
                    continue
                if is_relay:
                    school = ' '.join(head) or ' '.join(tail)
                    results.append({'school': school, 'result': mark,
                                    'athletes': [], 'grade': '', 'type': 'Finals'})
                else:
                    # school may be a trailing code before the mark, or the
                    # words AFTER the mark ("Nicole Kirschner 10:59.4 Cony")
                    if tail:
                        school = ' '.join(tail)
                        name = ' '.join(head)
                    elif len(head) >= 2 and len(head[-1]) <= 3:
                        school = resolve_code(head[-1])
                        name = ' '.join(head[:-1])
                    else:
                        school = ''
                        name = ' '.join(head)
                    if name:
                        results.append({'athlete': name, 'school': school or 'Unknown',
                                        'result': mark, 'grade': '', 'type': 'Finals'})
            if results:
                events.append({'event': ev_name, 'gender': gender,
                               'is_relay': is_relay, 'results': results})

        # meta
        meet_name = None
        meet_date = None
        for l in lines[:header_idx]:
            s = l.strip()
            if s and meet_name is None:
                meet_name = s
            m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', s)
            if m:
                mm, dd, yy = m.groups()
                if len(yy) == 2:
                    yy = '20' + yy
                meet_date = f'{yy}-{mm.zfill(2)}-{dd.zfill(2)}'
        return {'events': events, 'date': meet_date, 'meet_name': meet_name,
                'team_rankings': []}
