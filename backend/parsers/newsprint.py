"""
Newspaper-style result formats.

AgateParser - championship summaries as one dense paragraph per gender:
    BOYS TRACK
    KVAC CLASS B CHAMPIONSHIPS
    Belfast 104 Leavitt 74.5 Erskine 58 ... MCI 4
    100:1. Biggs (MV) 13.39; 2. Scott (CH) 13.64; ... 200:1. ...
School codes in (parens) resolve against the team-scores line via prefix or
initials.

ParagraphNewsParser - prose blocks with comma-separated entries:
    Girls 4x800 Meter Relay
    1, Greely High School 'A' 9:59.23. 2, Old Town High School 'A' 10:17.97.
    Girls 55 Meter Hurdles Preliminaries
    1, Rawcliffe, MacKenzie, Hampden Acad, 8.99Q. 2, Harrison, Leslie, ...
"""

import re
from .base import BaseParser
from .looselist import canon_event, is_mark

# label followed by ":" (any next entry) or directly by "1." (colon-less dialect)
AGATE_EVENT_RE = re.compile(
    r'(?:^|[.;]\s+)([A-Za-z0-9][\w,.  xX/-]{0,28}?)\s*(?::\s*(?=\d\.\s|[A-Z])|\s+(?=1\.\s))', re.M)
AGATE_ENTRY_RE = re.compile(
    r'(\d)\.\s*(?:\(tie\)\s*)?([^();:]+?)\s*(?:\(([^)]{1,60})\))?[,\s]*'
    r'([\d]{1,2}[:.\-][\d:.\-]+)\s*[;.]')
# comma variant: "Bouchey, SV, 17.7; J. Bagdon, GNG, 18.6" (place number optional)
AGATE_COMMA_RE = re.compile(
    r'(?:\d\.\s*)?([A-Z][^,;:()]{1,30}?),\s*([A-Z][A-Za-z.\-]{0,8}),\s*'
    r'([\d]{1,2}[:.\-][\d:.\-]+)\s*[;.]?')
MARK_TOKEN = re.compile(r'^\d{1,2}[:.\-][\d:.\-]*$')


class AgateParser(BaseParser):
    def parse(self, text, meet_url, season_type):
        from bs4 import BeautifulSoup
        if '<' in text[:2000].lower():
            soup = BeautifulSoup(text, 'html.parser')
            pres = soup.find_all('pre')
            text = "\n".join(p.get_text() for p in pres) if pres else soup.get_text(separator='\n')
        text = text.replace('\xa0', ' ')
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return self._empty()

        # Gender sections: "BOYS TRACK" / "GIRLS TRACK" markers split the file
        sections = []
        current_gender = None
        buf = []
        for l in lines:
            m = re.match(r'^(boys?|girls?)\s*(track)?\s*$', l, re.I)
            if m:
                if buf and current_gender:
                    sections.append((current_gender, buf))
                current_gender = 'Girls' if m.group(1).lower().startswith('g') else 'Boys'
                buf = []
            else:
                buf.append(l)
        if buf and current_gender:
            sections.append((current_gender, buf))
        if not sections:
            # fall back to filename gender
            g = 'Girls' if re.search(r'girl|[_\-]g\b', meet_url.lower()) else 'Boys'
            sections = [(g, lines)]

        meet_name = lines[1] if len(lines) > 1 else lines[0]
        events_out = []
        for gender, body in sections:
            schools, score_idx = self._score_line_schools(body)
            blob = ' '.join(l for i, l in enumerate(body) if i != score_idx)
            events_out.extend(self._parse_section(blob, gender, schools))
        if not events_out:
            return self._empty()
        return {'events': events_out, 'date': None, 'meet_name': meet_name,
                'team_rankings': []}

    @staticmethod
    def _empty():
        return {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}

    @staticmethod
    def _score_line_schools(body_lines):
        """Team-scores line: 'Belfast 104 Leavitt 74.5 Erskine 58 ... MCI 4'
        Returns (school_names, line_index_or_None)."""
        for i, l in enumerate(body_lines[:6]):
            pairs = re.findall(r'([A-Z][A-Za-z .\'/-]+?)\s+(\d+(?:\.\d+)?)(?=[,;]?\s+[A-Z]|[,;]?\s*$)', l)
            if len(pairs) >= 3:
                return [p[0].strip() for p in pairs], i
        return [], None

    def _parse_section(self, blob, gender, schools):
        def resolve(code):
            if not code:
                return 'Unknown'
            c = code.strip().lower()
            cands = [s for s in schools if s.lower().startswith(c)]
            if len(cands) == 1:
                return cands[0]
            cands = [s for s in schools
                     if ''.join(w[0] for w in s.split()).lower() == c]
            if len(cands) == 1:
                return cands[0]
            cands = [s for s in schools if s.lower().startswith(c[:3])]
            if len(cands) == 1:
                return cands[0]
            return code.strip()

        # find event markers: label must look like an event
        from .looselist import EVENT_KEYWORDS, EVENT_CANON
        markers = []
        for m in AGATE_EVENT_RE.finditer(blob):
            label = m.group(1).strip()
            low = re.sub(r'\s+', ' ', label.lower())
            if EVENT_KEYWORDS.search(label) or re.match(r'^\d{2,4}\b', label) \
                    or low in EVENT_CANON:
                markers.append((m.start(), m.end(), label))
        events = []
        for i, (s, e, label) in enumerate(markers):
            seg_end = markers[i + 1][0] if i + 1 < len(markers) else len(blob)
            seg = blob[e:seg_end]
            ev_name = canon_event(label)
            is_relay = bool(re.search(r'relay|medley|4x', label, re.I))
            results = []
            for m in AGATE_ENTRY_RE.finditer(seg):
                place, who, code, mark = m.group(1), m.group(2).strip(), m.group(3), m.group(4)
                mark = mark.rstrip('.;')
                who = who.strip(' ,')
                # "A. Healey, SV" without parens: split the code off the name
                if not code and ',' in who:
                    who, maybe_code = [x.strip() for x in who.rsplit(',', 1)]
                    if maybe_code and len(maybe_code) <= 8:
                        code = maybe_code
                if not is_mark(mark) and not re.match(r'^\d+-\d*$', mark):
                    continue
                if is_relay:
                    school = who.strip(' ,')
                    legs = []
                    if code and not MARK_TOKEN.match(code) and len(code.split()) >= 3:
                        legs = code.split()
                    results.append({'school': resolve(school) if len(school) <= 5 else school,
                                    'result': mark, 'athletes': legs,
                                    'grade': '', 'type': 'Finals'})
                else:
                    results.append({'athlete': who, 'school': resolve(code),
                                    'result': mark, 'grade': '', 'type': 'Finals'})
            if not results and not is_relay:
                # comma-separated variant without (parens): "Name, CODE, mark;"
                for m in AGATE_COMMA_RE.finditer(seg):
                    who, code, mark = m.group(1).strip(), m.group(2).strip(), m.group(3).rstrip('.;')
                    if not is_mark(mark) and not re.match(r'^\d+-\d*$', mark):
                        continue
                    results.append({'athlete': who, 'school': resolve(code),
                                    'result': mark, 'grade': '', 'type': 'Finals'})
            if results:
                events.append({'event': ev_name, 'gender': gender,
                               'is_relay': is_relay, 'results': results})
        return events


class MangledStreamParser(BaseParser):
    """Hy-Tek output whose newlines were stripped (email-mangled files): the
    whole meet is one multi-KB line. Events and rows are recovered by regex
    over the character stream."""

    EVENT_RE = re.compile(
        r'(Girls|Boys|Women|Men)\s+([\w .#\'/-]{3,45}?)\s*={10,}')
    ROW_RE = re.compile(
        r'(\d{1,2})\s+([A-Z][\w\'.-]+,\s+[A-Z][\w .\'-]+?)\s{2,}'
        r'((?:\d{1,2}|--|FR|SO|JR|SR)?\s{0,4}[A-Z][\w .&\'/-]*?)\s{2,}'
        r'([\d:.\-]+[QqJj*]?)')
    RELAY_ROW_RE = re.compile(
        r"(\d{1,2})\s+([A-Z][\w .&\'/-]{3,35}?)\s+'?[A-D]'?\s{2,}([\d:.\-]+[QqJj*]?)")

    def parse(self, text, meet_url, season_type):
        from bs4 import BeautifulSoup
        if '<' in text[:2000].lower():
            soup = BeautifulSoup(text, 'html.parser')
            pres = soup.find_all('pre')
            text = "\n".join(p.get_text() for p in pres) if pres else soup.get_text(separator='\n')
        if max((len(l) for l in text.splitlines()), default=0) < 2000:
            return {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}
        stream = re.sub(r'\s*\n\s*', ' ', text)

        meet_name = stream.strip()[:80].split('  ')[0].strip()
        m_date = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', stream[:300])
        date = None
        if m_date:
            mm, dd, yy = m_date.groups()
            date = f'{yy}-{mm.zfill(2)}-{dd.zfill(2)}'

        markers = list(self.EVENT_RE.finditer(stream))
        events = []
        for i, m in enumerate(markers):
            seg_end = markers[i + 1].start() if i + 1 < len(markers) else len(stream)
            seg = stream[m.end():seg_end]
            g = m.group(1).capitalize()
            gender = 'Girls' if g in ('Girls', 'Women') else 'Boys'
            label = m.group(2).strip()
            ev_name = canon_event(label)
            is_relay = bool(re.search(r'relay|medley|4x', label, re.I))
            rtype = 'Prelims' if re.search(r'prelim', seg[:200], re.I) and \
                                 not re.search(r'finals', seg[:60], re.I) else 'Finals'
            results = []
            row_re = self.RELAY_ROW_RE if is_relay else self.ROW_RE
            for r in row_re.finditer(seg):
                if is_relay:
                    results.append({'school': r.group(2).strip(), 'result': r.group(3).rstrip('QqJj*'),
                                    'athletes': [], 'grade': '', 'type': rtype})
                else:
                    school = re.sub(r'^(\d{1,2}|--|FR|SO|JR|SR)\s+', '', r.group(3)).strip()
                    results.append({'athlete': r.group(2).strip(), 'school': school,
                                    'result': r.group(4).rstrip('QqJj*'), 'grade': '',
                                    'type': rtype})
            if results:
                events.append({'event': ev_name, 'gender': gender,
                               'is_relay': is_relay, 'results': results})
        return {'events': events, 'date': date, 'meet_name': meet_name,
                'team_rankings': []}


class VerticalTokensParser(BaseParser):
    """Hy-Tek exported via Word/Excel where every value sits on its own line:

        Event 1  Girls 4x800 Meter Relay
        ... Team / Relay / Finals ...
        1
        Belfast Area High School
        A
        10:12.09
        8          <- points (optional)
        2
        ...
    """
    EVENT_RE = re.compile(r'^Event\s+\d+\s+(Girls|Boys|Women|Men)\s+(.+)$', re.I)

    def parse(self, text, meet_url, season_type):
        from bs4 import BeautifulSoup
        from .looselist import is_mark, _normalize_feet_inch_marks, GRADE_RE
        if '<' in text[:2000].lower():
            soup = BeautifulSoup(text, 'html.parser')
            text = soup.get_text('\n')
        text = text.replace('\xa0', ' ').replace('�', ' ')
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        # this format is overwhelmingly 1-2 tokens per line
        if not lines or sum(1 for l in lines if len(l.split()) <= 2) / len(lines) < 0.6:
            return {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}

        # Word exports may split the event header itself across lines:
        # "Event" / "31" / "Girls" / "Pole Vault" -> reassemble
        joined = []
        i = 0
        while i < len(lines):
            if lines[i].lower() == 'event' and i + 3 < len(lines) and \
                    re.fullmatch(r'\d{1,3}', lines[i + 1]) and \
                    re.match(r'^(girls|boys|women|men)$', lines[i + 2], re.I):
                joined.append(f'Event {lines[i+1]} {lines[i+2]} {lines[i+3]}')
                i += 4
            else:
                joined.append(lines[i])
                i += 1
        lines = joined

        meet_name = lines[0] if lines else None
        date = None
        m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', ' '.join(lines[:8]))
        if m:
            date = f'{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}'

        events = []
        current = None
        record = None  # accumulating [rank, fields...]
        for l in lines:
            l = _normalize_feet_inch_marks(l)
            m_ev = self.EVENT_RE.match(l)
            if m_ev:
                if current and current['results']:
                    events.append(current)
                g = m_ev.group(1).capitalize()
                label = m_ev.group(2).strip()
                current = {'event': canon_event(label),
                           'gender': 'Girls' if g in ('Girls', 'Women') else 'Boys',
                           'is_relay': bool(re.search(r'relay|medley|4x', label, re.I)),
                           'results': []}
                record = None
                continue
            if current is None:
                continue
            if re.fullmatch(r'\d{1,2}', l):
                if record is None or len(record) > 1:
                    record = [l]      # new rank (or points line consumed as rank reset)
                continue
            m_glued = re.match(r'^(\d{1,2})\s+([A-Za-z].*)$', l)
            if m_glued and (record is None or len(record) > 1) and \
                    not is_mark(m_glued.group(2).split()[0]):
                record = [m_glued.group(1), m_glued.group(2)]  # "1 Abby"
                continue
            if record is None:
                continue
            if is_mark(l) and len(record) >= 2:
                fields = [f for f in record[1:] if not re.fullmatch(r"[A-D]|'[A-D]'", f)]
                if not fields:
                    record = None
                    continue
                if current['is_relay']:
                    current['results'].append({'school': fields[0], 'result': l.rstrip('qQjJ*'),
                                               'athletes': [], 'grade': '', 'type': 'Finals'})
                else:
                    # the grade may sit alone or glued to the school
                    # ("SO Orono"); name is every field before it
                    grade = ''
                    name = fields[0]
                    school = ' '.join(fields[1:])
                    for idx in range(1, len(fields)):
                        mg = re.match(r'^(FR|SO|JR|SR|7|8|9|10|11|12)\b\s*(.*)$',
                                      fields[idx], re.I)
                        if mg:
                            grade = mg.group(1).upper()
                            name = ' '.join(fields[:idx])
                            school = ' '.join(
                                x for x in [mg.group(2)] + fields[idx + 1:] if x)
                            break
                    current['results'].append({'athlete': name,
                                               'school': school or 'Unknown',
                                               'result': l.rstrip('qQjJ*'),
                                               'grade': grade, 'type': 'Finals'})
                record = None
                continue
            if len(record) < 6 and len(l) < 45 and not re.search(r'record|kvac|finals|prelim', l, re.I):
                record.append(l)
            else:
                record = None

        if current and current['results']:
            events.append(current)
        return {'events': events, 'date': date, 'meet_name': meet_name,
                'team_rankings': []}


class ParagraphNewsParser(BaseParser):
    HEADER_RE = re.compile(r'^(Girls|Boys|Women|Men)\s+(.{3,60})$', re.I)
    RELAY_ENTRY = re.compile(r"^(\d+|--)[,.]\s*(.+?)\s+'?([A-D])'?\s+([\dO:.]+|DNF|DQ|DNS)$")
    INDIV_ENTRY = re.compile(r'^(\d+|--)[,.]\s*(.+)$')

    def parse(self, text, meet_url, season_type):
        from bs4 import BeautifulSoup
        if '<' in text[:2000].lower():
            soup = BeautifulSoup(text, 'html.parser')
            pres = soup.find_all('pre')
            text = "\n".join(p.get_text() for p in pres) if pres else soup.get_text(separator='\n')
        lines = [l.rstrip() for l in text.replace('\xa0', ' ').splitlines()]

        meet_name = next((l.strip() for l in lines[:8] if l.strip()), None)
        date = None
        for l in lines[:8]:
            m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', l)
            if m:
                mm, dd, yy = m.groups()
                if len(yy) == 2:
                    yy = '20' + yy
                date = f'{yy}-{mm.zfill(2)}-{dd.zfill(2)}'
                break

        # group lines into event blocks
        blocks = []
        current = None
        for l in lines:
            s = l.strip()
            if not s:
                continue
            m = self.HEADER_RE.match(s)
            if m and not s[0].isdigit() and re.search(
                    r'dash|meter|relay|hurdle|jump|vault|put|discus|javelin|walk|mile|run|medley',
                    m.group(2), re.I):
                g = m.group(1).capitalize()
                gender = 'Girls' if g in ('Girls', 'Women') else 'Boys'
                current = {'gender': gender, 'label': m.group(2).strip(), 'text': []}
                blocks.append(current)
            elif current is not None:
                current['text'].append(s)

        events = []
        for b in blocks:
            blob = ' '.join(b['text'])
            # entries are separated by ". " followed by "N," or "--,"
            entries = re.split(r'(?<=[.\d])\.\s+(?=(?:\d+|--),)', blob)
            label = re.sub(r'\s*(preliminaries|prelims|finals)\s*$', '', b['label'], flags=re.I)
            is_prelim = bool(re.search(r'prelim', b['label'], re.I))
            ev_name = canon_event(label)
            is_relay = bool(re.search(r'relay|medley|4x', label, re.I))
            results = []
            for entry in entries:
                entry = entry.strip().rstrip('.')
                if is_relay:
                    m = self.RELAY_ENTRY.match(entry)
                    if m:
                        mark = m.group(4).replace('O', '0')
                        results.append({'school': m.group(2).strip(), 'result': mark,
                                        'athletes': [], 'grade': '',
                                        'type': 'Prelims' if is_prelim else 'Finals'})
                    continue
                m = self.INDIV_ENTRY.match(entry)
                if not m:
                    continue
                parts = [p.strip() for p in m.group(2).split(',')]
                if len(parts) < 3:
                    continue
                mark = parts[-1].rstrip('Qq.')
                if not is_mark(mark):
                    continue
                if len(parts) >= 4:
                    name = f'{parts[1]} {parts[0]}'
                    school = ', '.join(parts[2:-1])
                else:
                    name = parts[0]
                    school = parts[1]
                results.append({'athlete': name, 'school': school, 'result': mark,
                                'grade': '', 'type': 'Prelims' if is_prelim else 'Finals'})
            if results:
                events.append({'event': ev_name, 'gender': b['gender'],
                               'is_relay': is_relay, 'results': results})
        return {'events': events, 'date': date, 'meet_name': meet_name,
                'team_rankings': []}
