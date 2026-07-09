"""
HtmlTableParser - meet results stored in real HTML <table> grids.

Two sub-formats:
  A. Dual-meet place grid (2004-2013):
       header: [Event] | 1st | 2nd | ... [| team-points columns]
       cells:  "D. Belanger B 15.3"  (Name Code Mark), relays "BE 9:10.4"
     The meet title carries the participating schools, gender, and date:
       "Bonny Eagle, Massabesic, Thornton Academy at Biddeford - Boys - May 21, 2004"
  B. Labeled row table (2016+):
       Place | Athlete | Team | Event | Min/Ft | Sec/Inchs | Points

Files whose grid has no event labels at all (e.g. 2004 SMAA championship
matrix) are left unparsed for the audit trail.
"""

import re
from .base import BaseParser
from .looselist import canon_event, is_mark

MONTHS = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
          'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
FIELD_EVENT = re.compile(r'jump|vault|shot|put|discus|javelin|throw', re.I)


class HtmlTableParser(BaseParser):
    def parse(self, text, meet_url, season_type):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, 'html.parser')
        tables = soup.find_all('table')
        if not tables:
            return {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}

        title, gender, date = self._meta(soup, meet_url)

        all_events = []
        racetab_event = None  # last-seen "Girls 4x800 Meter Relay" title table
        for tbl in tables:
            rows = [[c.get_text(' ', strip=True) for c in tr.find_all(['td', 'th'])]
                    for tr in tbl.find_all('tr')]
            rows = [r for r in rows if any(x for x in r)]
            if not rows:
                continue
            # RaceTab: single-cell event title table, then Place|Bib|Name|Affiliation|Time
            flat = ' '.join(rows[0])
            m_ev = re.match(r'^(Girls|Boys|Women|Men)\s+(.{3,50})$', flat)
            if m_ev and len(rows) <= 2:
                g = m_ev.group(1).capitalize()
                racetab_event = ('Girls' if g in ('Girls', 'Women') else 'Boys',
                                 m_ev.group(2).strip())
                continue
            if len(rows) < 2:
                continue
            header0 = [c.lower() for c in rows[0]]
            if racetab_event and 'place' in header0 and \
                    ('affiliation' in header0 or 'bib number' in header0):
                all_events.extend(self._racetab_rows(rows, header0, racetab_event))
                continue
            # side-by-side event columns: [Event, School, Perf., '', Event, School, Perf.]
            h0 = [c.lower().strip() for c in rows[0]]
            if 'school' in h0 and any(c.startswith('perf') for c in h0):
                all_events.extend(self._event_column_pairs(rows, gender))
                continue
            # headerless variant: event names in row 0, (name|code|mark) triples below
            if len(rows) > 2 and any(re.search(r'jump|vault|shot|put', c, re.I) for c in rows[0]):
                from .looselist import _normalize_feet_inch_marks
                data = rows[1]
                marks_at = [j for j, c in enumerate(data)
                            if c and is_mark(_normalize_feet_inch_marks(c).split()[0] if c.split() else '')]
                if marks_at:
                    all_events.extend(self._loose_column_pairs(rows, marks_at, gender))
                    continue

            # the header row may sit below a title row inside the table
            header_idx = None
            for i in range(min(8, len(rows))):
                h = [c.lower().strip() for c in rows[i]]
                if ('athlete' in h and 'event' in h) or \
                        any(re.match(r'1st\b', x) for x in h) or \
                        (h and h[0].startswith('event') and len(h) > 3):
                    header_idx = i
                    break
            if header_idx is None:
                continue
            rows = rows[header_idx:]
            header = [h.lower() for h in rows[0]]
            if 'athlete' in header and 'event' in header:
                all_events.extend(self._labeled_rows(rows, header, gender))
            elif header[0].strip().startswith('event') and len(rows) > 2 and \
                    ('1st' in ' '.join(header) or
                     '1st' in ' '.join(c.lower() for c in rows[1])):
                # triple layout header may be one row (EVENT | 1st Place...) or two
                start = 1 if '1st' in ' '.join(header) else 2
                all_events.extend(self._event_triples(rows, gender, start))
            elif any(re.match(r'1st\b', h.strip()) for h in header):
                all_events.extend(self._place_grid(rows, header, gender, title))
        # merge duplicate event blocks
        merged = {}
        for ev in all_events:
            key = (ev['gender'], ev['event'], ev['is_relay'])
            if key in merged:
                merged[key]['results'].extend(ev['results'])
            else:
                merged[key] = ev
        return {'events': list(merged.values()), 'date': date,
                'meet_name': title, 'team_rankings': []}

    # ------------------------------------------------------------------
    def _meta(self, soup, meet_url):
        title = None
        for el in soup.find_all(['title', 'h1', 'h2', 'b', 'p']):
            t = el.get_text(' ', strip=True)
            if t and len(t) > 8:
                title = t
                break
        gender = ''
        blob = f'{title or ""} {meet_url}'.lower()
        if re.search(r'girl|women|[_\-]g\b|\dg\.htm', blob):
            gender = 'Girls'
        elif re.search(r'boy|men|[_\-]b\b|\db\.htm', blob):
            gender = 'Boys'
        date = None
        m = re.search(r'([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})', title or '')
        if m and m.group(1).lower()[:3] in MONTHS:
            date = f'{m.group(3)}-{MONTHS[m.group(1).lower()[:3]]:02d}-{int(m.group(2)):02d}'
        m2 = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', title or '')
        if m2 and not date:
            mm, dd, yy = m2.groups()
            if len(yy) == 2:
                yy = '20' + yy
            date = f'{yy}-{mm.zfill(2)}-{dd.zfill(2)}'
        return title, gender, date

    # ------------------------------------------------------------------
    @staticmethod
    def _decimal_feet_mark(mark):
        """Jump-meet marks encode feet-inches as decimals: 20.0700 -> 20-07.00"""
        m = re.match(r'^(\d{1,2})\.(\d{2})(\d{0,2})$', mark.strip())
        if m:
            frac = m.group(3) or '00'
            return f'{int(m.group(1))}-{m.group(2)}.{frac}'
        return mark.strip()

    def _loose_column_pairs(self, rows, marks_at, default_gender):
        """Headerless jump-meet grid: row 0 holds event names, data rows hold
        (name | school-code | mark) triples at each mark column."""
        from .looselist import _normalize_feet_inch_marks
        events = {}
        current = {}
        for j in marks_at:
            if j < 2:
                continue
            label = next((rows[0][i].strip() for i in (j - 2, j - 1, j)
                          if i < len(rows[0]) and rows[0][i].strip()), '')
            current[j] = label
        for r in rows[1:]:
            for j in list(current.keys()):
                if j >= len(r) or j < 2:
                    continue
                name, school, mark = r[j - 2].strip(), r[j - 1].strip(), r[j].strip()
                if name and not school and not mark and \
                        re.search(r'jump|vault|shot|put|hurdle|dash', name, re.I):
                    current[j] = name
                    continue
                if not name or not mark:
                    continue
                mark = _normalize_feet_inch_marks(mark).split()[0]
                if not is_mark(mark):
                    continue
                label = current.get(j) or ''
                m_g = re.match(r'^(girls?|boys?)\s+(.*)$', label, re.I)
                gender = ('Girls' if m_g.group(1).lower().startswith('g') else 'Boys') \
                    if m_g else (default_gender or 'Boys')
                ev_label = m_g.group(2) if m_g else label
                if not ev_label:
                    continue
                key = (gender, canon_event(ev_label))
                ev = events.setdefault(key, {'event': key[1], 'gender': gender,
                                             'is_relay': False, 'results': []})
                ev['results'].append({'athlete': name, 'school': school or 'Unknown',
                                      'result': mark, 'grade': '', 'type': 'Finals'})
        return list(events.values())

    def _event_column_pairs(self, rows, default_gender):
        """USM jump meet tables: groups of (Name | School | Perf.) columns side
        by side; new event headers appear mid-table in the name column."""
        header = [c.lower().strip() for c in rows[0]]
        groups = []
        for i in range(len(header) - 2):
            if header[i + 1].startswith('school') and header[i + 2].startswith('perf'):
                groups.append(i)
        if not groups:
            return []
        events = {}
        current = {}
        for i in groups:
            label = rows[0][i].strip()
            if label:
                current[i] = label
        for r in rows[1:]:
            for i in groups:
                if i + 2 >= len(r):
                    continue
                name, school, mark = r[i].strip(), r[i + 1].strip(), r[i + 2].strip()
                if not name:
                    continue
                if school.lower() == 'school' or re.search(
                        r'jump|vault|shot|put|discus|javelin|hurdle|dash|relay', name, re.I) and not mark:
                    current[i] = name
                    continue
                if not mark or mark.lower() in ('nm', 'nh', 'x', 'scr', 'dns'):
                    continue
                label = current.get(i)
                if not label:
                    continue
                m_g = re.match(r'^(girls?|boys?)\s+(.*)$', label, re.I)
                gender = ('Girls' if m_g.group(1).lower().startswith('g') else 'Boys') \
                    if m_g else (default_gender or 'Boys')
                ev_label = m_g.group(2) if m_g else label
                key = (gender, canon_event(ev_label))
                ev = events.setdefault(key, {'event': key[1], 'gender': gender,
                                             'is_relay': False, 'results': []})
                ev['results'].append({'athlete': name, 'school': school or 'Unknown',
                                      'result': self._decimal_feet_mark(mark),
                                      'grade': '', 'type': 'Finals'})
        return list(events.values())

    # ------------------------------------------------------------------
    def _event_triples(self, rows, gender, start=2):
        """Gorham-style grid: each event spans 3 rows -
        [EVENT, name1..name5, pts...], [school1..school5], [mark1..mark5]."""
        events = []
        i = start
        while i < len(rows):
            r = rows[i]
            label = r[0].strip()
            if not label or not re.search(
                    r'hurdle|dash|meter|relay|jump|vault|shot|discus|javelin|walk|\d{2,4}', label, re.I):
                i += 1
                continue
            names = [c.strip() for c in r[1:6]]
            schools = [c.strip() for c in rows[i + 1][:5]] if i + 1 < len(rows) else []
            marks_row = None
            for j in (i + 2, i + 1):
                if j < len(rows):
                    cand = [c.strip() for c in rows[j][:5]]
                    if sum(1 for c in cand if c and is_mark(c)) >= 2:
                        marks_row = cand
                        break
            if marks_row is None:
                i += 1
                continue
            ev_name = canon_event(label)
            is_relay = bool(re.search(r'relay|medley|4\s*x', label, re.I))
            results = []
            for k in range(5):
                name = names[k] if k < len(names) else ''
                school = schools[k] if k < len(schools) else ''
                mark = marks_row[k] if k < len(marks_row) else ''
                if not name or not mark or not is_mark(mark):
                    continue
                if is_relay:
                    results.append({'school': name, 'result': mark, 'athletes': [],
                                    'grade': '', 'type': 'Finals'})
                else:
                    results.append({'athlete': name, 'school': school or 'Unknown',
                                    'result': mark, 'grade': '', 'type': 'Finals'})
            if results:
                events.append({'event': ev_name, 'gender': gender or 'Boys',
                               'is_relay': is_relay, 'results': results})
            i += 3
        return events

    # ------------------------------------------------------------------
    def _racetab_rows(self, rows, header, racetab_event):
        """Hy-Tek RaceTab _full.htm: Place | Bib Number | Name | Affiliation | Time/Mark"""
        gender, ev_label = racetab_event
        name_i = header.index('name') if 'name' in header else 2
        aff_i = header.index('affiliation') if 'affiliation' in header else 3
        mark_i = len(header) - 1
        ev_name = canon_event(ev_label)
        is_relay = bool(re.search(r'relay|medley|4\s*x', ev_label, re.I))
        results = []
        for r in rows[1:]:
            if len(r) <= mark_i:
                continue
            name = r[name_i].strip()
            aff = r[aff_i].strip()
            mark = r[mark_i].strip()
            if not name or not mark or not (is_mark(mark) or mark.upper() in
                                            ('DQ', 'DNF', 'DNS', 'NH', 'NM', 'FOUL', 'SCR')):
                continue
            if is_relay:
                results.append({'school': name, 'result': mark, 'athletes': [],
                                'grade': '', 'type': 'Finals'})
            else:
                results.append({'athlete': name, 'school': re.sub(r'\s+[A-D]$', '', aff),
                                'result': mark, 'grade': '', 'type': 'Finals'})
        if not results:
            return []
        return [{'event': ev_name, 'gender': gender, 'is_relay': is_relay,
                 'results': results}]

    # ------------------------------------------------------------------
    def _labeled_rows(self, rows, header, default_gender):
        """Format B: Place | Athlete | Team | Event | Min/Ft | Sec/Inchs"""
        idx = {name: header.index(name) for name in
               ('place', 'athlete', 'team', 'event') if name in header}
        min_i = next((i for i, h in enumerate(header) if 'min' in h or 'ft' in h), None)
        sec_i = next((i for i, h in enumerate(header) if 'sec' in h or 'inch' in h), None)
        events = {}
        for r in rows[1:]:
            if len(r) <= max(idx.values()):
                continue
            athlete = r[idx['athlete']].strip()
            team = r[idx['team']].strip() if 'team' in idx else ''
            ev_name = r[idx['event']].strip()
            if not athlete or not ev_name:
                continue
            a = r[min_i].strip() if min_i is not None and min_i < len(r) else ''
            b = r[sec_i].strip() if sec_i is not None and sec_i < len(r) else ''
            mark = self._combine_mark(ev_name, a, b)
            if not mark:
                continue
            key = canon_event(ev_name)
            is_relay = bool(re.search(r'relay|medley|4\s*x', ev_name, re.I))
            ev = events.setdefault(key, {'event': key, 'gender': default_gender or 'Boys',
                                         'is_relay': is_relay, 'results': []})
            if is_relay:
                ev['results'].append({'school': athlete if not team else team,
                                      'result': mark, 'athletes': [], 'grade': '',
                                      'type': 'Finals'})
            else:
                ev['results'].append({'athlete': athlete, 'school': team,
                                      'result': mark, 'grade': '', 'type': 'Finals'})
        return list(events.values())

    @staticmethod
    def _combine_mark(ev_name, a, b):
        a = a.replace(',', '.')
        b = b.replace(',', '.')
        if not a and not b:
            return None
        try:
            if FIELD_EVENT.search(ev_name):
                if a and b:
                    return f'{int(float(a))}-{float(b):05.2f}'
                return None
            if a and b:
                sec = float(b)
                return f'{int(float(a))}:{sec:05.2f}'
            if b:
                return f'{float(b):.2f}'
            return None
        except ValueError:
            return None

    # ------------------------------------------------------------------
    def _place_grid(self, rows, header, default_gender, title):
        """Format A: [Event] | 1st | 2nd ... with 'Name Code Mark' cells."""
        first_place_col = next(i for i, h in enumerate(header) if h in ('1st', '2nd'))
        has_event_col = first_place_col > 0
        if not has_event_col:
            return []  # matrix without event labels: leave for the audit
        last_place_col = max(i for i, h in enumerate(header)
                             if h in ('1st', '2nd', '3rd', '4th', '5th', '6th'))

        # participating schools from the title: "A, B, C at D - Boys - ..."
        schools = set()
        host = None
        m = re.match(r'^(.*?)\s+at\s+([A-Za-z .\'-]+?)\s*[-–]', title or '')
        if m:
            for part in m.group(1).split(','):
                if part.strip():
                    schools.add(part.strip())
            host = m.group(2).strip()
            schools.add(host)

        def resolve(code):
            cands = [s for s in schools if s.lower().startswith(code.lower())]
            if len(cands) == 1:
                return cands[0]
            # multi-letter codes are usually initials: BE = Bonny Eagle
            cands = [s for s in schools
                     if ''.join(w[0] for w in s.split()).lower() == code.lower()]
            if len(cands) == 1:
                return cands[0]
            # single-letter codes conventionally mean the host school
            if len(code) == 1 and host and host.lower().startswith(code.lower()):
                return host
            cands = [s for s in schools if s.lower()[0] == code.lower()[0]]
            return cands[0] if len(cands) == 1 else code

        events = []
        for r in rows[1:]:
            ev_label = r[0].strip()
            if not ev_label or is_mark(ev_label):
                continue
            ev_name = canon_event(ev_label)
            is_relay = bool(re.search(r'relay|medley|4\s*x', ev_label, re.I))
            results = []
            for cell in r[first_place_col:last_place_col + 1]:
                cell = cell.strip()
                if not cell:
                    continue
                toks = cell.split()
                mark = None
                for i in range(len(toks) - 1, -1, -1):
                    if is_mark(toks[i]):
                        mark = toks[i].rstrip('*qQjJ')
                        head = toks[:i]
                        break
                if mark is None or not head:
                    continue
                if is_relay:
                    results.append({'school': resolve(' '.join(head)), 'result': mark,
                                    'athletes': [], 'grade': '', 'type': 'Finals'})
                else:
                    if len(head) >= 2 and len(head[-1]) <= 3:
                        school = resolve(head[-1])
                        name = ' '.join(head[:-1])
                    else:
                        school, name = '', ' '.join(head)
                    if name:
                        results.append({'athlete': name, 'school': school or 'Unknown',
                                        'result': mark, 'grade': '', 'type': 'Finals'})
            if results:
                events.append({'event': ev_name, 'gender': default_gender or 'Boys',
                               'is_relay': is_relay, 'results': results})
        return events
