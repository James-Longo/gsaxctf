"""
LooseListParser - ranked result lines without reliable Hy-Tek column headers.

Covers three families that the column parser can't read:
  1. Hand-typed dual/tri meets:   "Boys 100m" / "1. K. Martin  Traip  11.75  5"
  2. Hand-typed relay carnivals:  "Girls One Mile Relay" / "1 Greely A 16:08.66"
  3. Hy-Tek PDFs whose pdftotext output collapsed to single spaces:
     "Event 2 Boys 4x800 Meter Relay" / "1 Morse High School 'A' 11:16.66 10:47.74 10"

Emits the same nested structure as ColumnStrategyParser.
"""

import re
from .base import BaseParser

EVENT_KEYWORDS = re.compile(
    r'(dash|meter|metre|\bm\b|\d{2,4}\s*m\b|relay|medley|hurdles?|jump|vault|'
    r'shot\s*put|discus|javelin|race\s*walk|\brw\b|mile|run)', re.I)
GENDER_RE = re.compile(r'\b(girls?|boys?|women|men|ladies)\b', re.I)
MARK_RE = re.compile(r"^(\d{1,2}:)?\d{1,3}[:.]\d{1,2}(\.\d+)?$|^\d{1,3}-\d{1,2}(\.\d+)?$|^\d{1,2}'\d{1,2}(\.\d+)?\"?$")
STATUS = {'DQ', 'NH', 'NM', 'DNF', 'DNS', 'FOUL', 'SCR', 'FAIL', 'FS', 'ND', 'NT'}
GRADE_RE = re.compile(r'^(7|8|9|10|11|12|FR|SO|JR|SR)$', re.I)

EVENT_CANON = {
    '100': '100 Meter Dash', '200': '200 Meter Dash', '400': '400 Meter Dash',
    '800': '800 Meter Run', '1600': '1600 Meter Run', '3200': '3200 Meter Run',
    '55': '55 Meter Dash', '100m': '100 Meter Dash', '200m': '200 Meter Dash',
    '400m': '400 Meter Dash', '800m': '800 Meter Run', '1600m': '1600 Meter Run',
    '3200m': '3200 Meter Run', '55m': '55 Meter Dash',
    'rw': '1600 Meter Race Walk', '1600 rw': '1600 Meter Race Walk',
    '800 rw': '800 Meter Race Walk', 'racewalk': '1600 Meter Race Walk',
    '110 hurdles': '110 Meter Hurdles', '100 hurdles': '100 Meter Hurdles',
    '300 hurdles': '300 Meter Hurdles', '55 hurdles': '55 Meter Hurdles',
    'high jump': 'High Jump', 'long jump': 'Long Jump', 'triple jump': 'Triple Jump',
    'pole vault': 'Pole Vault', 'shot put': 'Shot Put', 'shot': 'Shot Put',
    'discus': 'Discus', 'javelin': 'Javelin',
    'one mile relay': '4x400 Meter Relay', 'sprint medley': 'Sprint Medley Relay',
    '4x100': '4x100 Meter Relay', '4x200': '4x200 Meter Relay',
    '4x400': '4x400 Meter Relay', '4x800': '4x800 Meter Relay',
    '400 relay': '4x100 Meter Relay', '1600 relay': '4x400 Meter Relay',
    '3200 relay': '4x800 Meter Relay',
    '110 hh': '110 Meter Hurdles', '100 hh': '100 Meter Hurdles',
    '55 hh': '55 Meter Hurdles', '300 ih': '300 Meter Hurdles',
    '300 lh': '300 Meter Hurdles', '100 dash': '100 Meter Dash',
    '200 dash': '200 Meter Dash', '400 dash': '400 Meter Dash',
    '800 run': '800 Meter Run', '1600 run': '1600 Meter Run',
    '3200 run': '3200 Meter Run', 'race walk': '1600 Meter Race Walk',
    'racewalk': '1600 Meter Race Walk', 'triple': 'Triple Jump',
    'high': 'High Jump', 'long': 'Long Jump', 'pole': 'Pole Vault',
    'jav': 'Javelin', 'disc': 'Discus',
}


def canon_event(name):
    n = re.sub(r'\s+', ' ', name.strip().lower().rstrip(':'))
    n = re.sub(r'^event\s+\d+\s*', '', n)
    n = re.sub(r'(\d),(\d)', r'\1\2', n)         # "3,200" -> "3200"
    n = re.sub(r'(\d)\s*x\s*(\d)', r'\1x\2', n)  # "4 x 800" -> "4x800"
    if n in EVENT_CANON:
        return EVENT_CANON[n]
    return name.strip().rstrip(':')


def is_mark(tok):
    t = tok.strip().rstrip('*qQjJhH')
    return bool(MARK_RE.match(t)) or t.upper() in STATUS


def _normalize_feet_inch_marks(s):
    """Convert feet/inch marks written with quotes (or encoding-mangled
    quote characters) to F-II.II: "16' 1 1/2\"" / "16� 1 1/2�" -> 16-01.50."""
    def repl(m):
        feet = int(m.group(1))
        whole = int(m.group(2)) if m.group(2) else 0
        frac = 0.0
        if m.group(3) and m.group(4):
            try:
                frac = int(m.group(3)) / int(m.group(4))
            except ZeroDivisionError:
                frac = 0.0
        return f'{feet}-{whole + frac:05.2f}'
    return re.sub(
        r"(\d{1,2})\s*[�'’]\s*(?:(\d{1,2})\s*)?(?:(\d)/(\d))?\s*[�\"”]?",
        repl, s)


class LooseListParser(BaseParser):
    def parse(self, text, meet_url, season_type):
        from bs4 import BeautifulSoup
        if '<' in text[:2000].lower():
            soup = BeautifulSoup(text, 'html.parser')
            pres = soup.find_all('pre')
            text = "\n".join(p.get_text() for p in pres) if pres else soup.get_text(separator='\n')
        lines = [l.rstrip() for l in text.replace('\xa0', ' ').splitlines()]

        # Default gender from the filename (…girls…, …_g.pdf, …4_26b.pdf)
        url_low = meet_url.lower()
        default_gender = ''
        if re.search(r'girl|women|[_\-]g(irls)?[\W_]|g\.(pdf|htm)', url_low):
            default_gender = 'Girls'
        elif re.search(r'boy|men|[_\-]b(oys)?[\W_]|b\.(pdf|htm)', url_low):
            default_gender = 'Boys'

        meet_name, meet_date = self._meta(lines, meet_url)

        # Team-scores lines ("YORK 105, WELLS 95, CAPE 42") let 1-2 letter
        # school codes resolve to real names. Scores may span several lines.
        schools = []
        for l in lines[:15]:
            s = l.strip()
            if EVENT_KEYWORDS.search(s):
                continue
            for name, _pts in re.findall(
                    r'([A-Za-z][A-Za-z .\'/-]+?)\s+(\d+(?:\.\d+)?)(?=[,;]?\s+[A-Za-z]|[,;]?\s*$)', s):
                name = name.strip().title()
                if 2 < len(name) <= 25 and name not in schools:
                    schools.append(name)
        self._schools = schools if len(schools) >= 2 else []

        events = []
        current = None
        section_gender = default_gender
        in_scores = False

        for line in lines:
            s = line.strip()
            if not s:
                continue
            # Hy-Tek team-score blocks ("*1 Portland High School  75  10 12 ..."
            # then "Average: 17:45.74") look like result rows; skip them up to
            # the next event header
            if re.match(r'^team\s+scores?\b', s, re.I):
                in_scores = True
                continue
            if s.count('|') >= 2:
                continue  # OCR'd table grid — PipeGridParser territory

            # Section markers: "GIRLS RESULTS", "BOYS TRACK MEET AT YORK"
            m_sec = re.match(r'^(girls?|boys?|women|men)\s*(results)?\s*$', s, re.I)
            if not m_sec and re.match(r'^(girls?|boys?|women|men)\b', s, re.I) and \
                    re.search(r'track|meet|results', s, re.I) and \
                    not EVENT_KEYWORDS.search(re.sub(r'track|meet|results', '', s, flags=re.I)):
                m_sec = re.match(r'^(girls?|boys?|women|men)', s, re.I)
            if m_sec:
                g = m_sec.group(1).lower()
                section_gender = 'Girls' if g.startswith(('g', 'w', 'l')) else 'Boys'
                continue

            # Event header?
            header = self._event_header(s, section_gender)
            if header:
                if current and current['results']:
                    events.append(current)
                gender, ev_name = header
                in_scores = False
                current = {
                    'event': canon_event(ev_name),
                    'gender': gender or section_gender or 'Girls',
                    # ("4 X 400": a relay by its canonical name too)
                    'is_relay': bool(re.search(r'relay|medley|4x', ev_name, re.I)
                                     or re.search(r'relay|medley', canon_event(ev_name), re.I)),
                    'results': [],
                }
                continue

            if in_scores and (
                    re.search(r'\b(Place|Pl|Name)\b.*\b(Name|School|Team)\b', s, re.I)
                    or re.match(r'^\d{1,3}[.)]?\s+[A-Za-z].*\d:\d\d', s)):
                # a results ruler or a timed place row ends the scores block
                # (team-score rows carry no times; small meets print the
                # scores FIRST: "Team Scores / Lisbon 35 ... / Place Name ...")
                in_scores = False
            if current is None or in_scores:
                continue

            row = self._parse_row(s, current['is_relay'])
            if row is None:
                row = self._parse_unranked_row(s, current['is_relay'])
            if row:
                current['results'].append(row)

        if current and current['results']:
            events.append(current)

        return {'events': events, 'date': meet_date, 'meet_name': meet_name,
                'team_rankings': []}

    # ------------------------------------------------------------------
    def _meta(self, lines, meet_url):
        meet_name = None
        meet_date = None
        for l in lines[:25]:
            s = l.strip()
            if not s:
                continue
            if meet_name is None and len(s) > 5 and not s[0].isdigit():
                meet_name = s
            m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', s)
            if m and not meet_date:
                mm, dd, yy = m.groups()
                if len(yy) == 2:
                    yy = '20' + yy
                meet_date = f'{yy}-{mm.zfill(2)}-{dd.zfill(2)}'
            m2 = re.search(r'([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4})', s)
            if m2 and not meet_date:
                months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                          'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
                mon = months.get(m2.group(1).lower()[:3])
                if mon:
                    meet_date = f'{m2.group(3)}-{mon:02d}-{int(m2.group(2)):02d}'
        return meet_name, meet_date

    def _event_header(self, s, section_gender):
        """Return (gender_or_None, event_name) if s is an event header."""
        # column captions typed on the header's own line ("DISCUS   HAND
        # FAT   PT", APRIL-15-AT-YORK.pdf): not part of the event name
        # ("4 X 800   TM P MARK", york_may3.pdf)
        cap = r'(?:HAND|FAT|PTS?|PLC?|PLACE|TIME|MARKS?|SEED|FINALS?|SCHOOL|TEAM|NAME|TM|P)'
        s = re.sub(r'\s{2,}%s(?:\s+%s)*\s*$' % (cap, cap), '', s, flags=re.I) or s
        # ... but a line that is all captions is a column-title row ("Team
        # Relay   Finals" over a Hy-Tek relay, smaa-1-1.pdf), not an event
        if re.match(r'^\s*(?:team|name|school|place|pl|lane|heat|bib)\b', s, re.I):
            return None
        if len(s) > 70 or is_mark(s.split()[-1] if s.split() else ''):
            return None
        m = re.match(r'^Event\s+\d+\s+(Girls|Boys|Women|Men)\s+(.+)$', s, re.I)
        if m:
            g = m.group(1).capitalize()
            return ('Girls' if g in ('Girls', 'Women') else 'Boys', m.group(2))
        # "EVENT #4      JV BOYS 5K RUN CC": numbered, gender anywhere
        m = re.match(r'^Event\s*#\s*\d+\s+(.+)$', s, re.I)
        if m:
            gw = re.search(r'\b(girls|boys|women|men)\b', m.group(1), re.I)
            g = gw.group(1).lower() if gw else ''
            return ('Girls' if g in ('girls', 'women') else 'Boys' if g else None,
                    re.sub(r'\s+', ' ', m.group(1)).strip())
        m = re.match(r'^(Girls|Boys|Women|Men)[:\s]+(.+)$', s, re.I)
        # ("Boys 4 x 100": a relay with no keyword, April 11 meet at York)
        if m and (EVENT_KEYWORDS.search(m.group(2)) or re.fullmatch(r'\d\s*x\s*\d{2,4}', m.group(2).strip(), re.I)) \
                and not re.match(r'^\d+[.)]', m.group(2)):
            g = m.group(1).capitalize()
            return ('Girls' if g in ('Girls', 'Women') else 'Boys', m.group(2))
        # bare event header: "100m", "Shot Put", "1600 RW", "4x100"
        low = re.sub(r'\s+', ' ', s.lower().rstrip(':'))
        low = re.sub(r'(\d)\s*x\s*(\d)', r'\1x\2', low)   # "4 X100"
        if low in EVENT_CANON:
            return (None, s)
        # "800 WC": a wheelchair race
        m = re.fullmatch(r'(100|200|400|800|1500|1600)\s*m?\s*wc', low)
        if m:
            return (None, f"{m.group(1)} Meter {'Dash' if int(m.group(1)) <= 400 else 'Run'} Wheelchair")
        # a bare distance under a division or sex: "SR. GIRLS 400", "JR.
        # BOYS 200", "GIRLS 800" (DEC 20 YORK V TRAIP.pdf; the bare "400" is
        # already a header above)
        m = re.fullmatch(r'(?:(?:sr|jr|jv|varsity|frosh|freshmen|freshman)\.?\s*)?'
                         r'((?:girls?|boys?|women|men)\s*)?(55|60|100|200|300|400|500|600|800|1000|1500|1600|3000|3200)'
                         r'(?:\s*(?:m|meters?|y|yards?))?', low)
        if m and (m.group(1) or low.split()[0] != m.group(2)):
            g = (m.group(1) or '').strip()
            return ('Girls' if g.startswith(('g', 'w')) else 'Boys' if g else None, s)
        # (a USATF division phrase doesn't count toward the length: "4x100
        # Meter Relay 17-18 Division Men", 2016 Resultsmaine.htm; "4x100 Meter
        # Relay Intermediate Girls", 2004 meusatf19june04.htm)
        core = re.sub(r'\s*\b(?:(?:\d+\s*&\s*(?:under|over)|\d{1,2}-\d{2}|bantam|midget|youth|intermediate|young)'
                      r'\s+division|(?:bantam|midget|youth|intermediate|young)\s+(?:girls|boys|men|women))\b', '', s, flags=re.I)
        if len(core) < 35 and EVENT_KEYWORDS.search(s) and not re.search(r'\d[:.]\d', s) \
                and not re.match(r'^\d+[.)]\s', s) and not re.search(r'record|school|results|scores', s, re.I):
            return (None, s)
        return None

    def _resolve_school(self, code):
        schools = getattr(self, '_schools', [])
        if not schools or len(code) > 3:
            return code
        cands = [s for s in schools if s.lower().startswith(code.lower())]
        if len(cands) == 1:
            return cands[0]
        cands = [s for s in schools
                 if ''.join(w[0] for w in s.split()).lower() == code.lower()]
        return cands[0] if len(cands) == 1 else code

    def _parse_unranked_row(self, s, is_relay):
        """Rows without place numbers: "McFarland S 9:47" / "Scarborough 9:12.5".
        Only inside an event block; the trailing mark anchors the match."""
        if len(s) > 60:
            return None
        s = _normalize_feet_inch_marks(s)
        toks = s.split()
        if not (2 <= len(toks) <= 6):
            return None
        mark = toks[-1].rstrip('*qQjJ')
        if not is_mark(mark):
            return None
        head = toks[:-1]
        if any(is_mark(t) for t in head):
            return None
        # an exhibition relay: "x   YORK B         Y    54.34" (APR-14-RESULTS.pdf)
        exhib = is_relay and len(head) >= 2 and head[0] in ('x', 'X')
        if exhib:
            head = head[1:]
            if len(head) >= 2 and re.fullmatch(r'[A-Z]{1,3}', head[-1]):
                head = head[:-1]            # (the team's code after its name)
            if len(head) >= 2 and re.fullmatch(r'[A-D]', head[-1]):
                head = head[:-1]            # (the relay letter)
        if is_relay or len(head) == 1:
            school = ' '.join(head)
            if not school or school[0].islower():
                return None
            row = {'school': self._resolve_school(school), 'result': mark, 'athletes': [],
                   'grade': '', 'type': 'Finals'}
            if exhib:
                row['exhibition'] = True
            return row
        # "Name [Name] CODE mark" — school code is a short trailing token
        if len(head) >= 2 and len(head[-1]) <= 3 and head[-1][0].isupper():
            return {'athlete': ' '.join(head[:-1]), 'school': self._resolve_school(head[-1]),
                    'result': mark, 'grade': '', 'type': 'Finals'}
        return None

    def _parse_row(self, s, is_relay):
        # 3-digit places: big XC fields run past 99, and Hy-Tek then drops
        # the leading space ("100 Gideon Walters ...")
        m = re.match(r'^(\d{1,3})[.)]?\s+(.+)$', s)
        if not m:
            return None
        rest = m.group(2).strip()
        rest = re.sub(r'^#\s*\d+\s+', '', rest)  # bib numbers: "1 # 278 Jane Doe ..."
        rest = _normalize_feet_inch_marks(rest)   # 16' 1/2" (or mangled quotes)
        rest = re.sub(r'(\d)-{1,2}tie\b', r'\1', rest, flags=re.I)   # "11.6--tie"
        # a typed half inch: "32-2 ½", "17- ½"
        rest = re.sub(r'(?<![\d.])(\d{1,3})-\s*½', r'\1-0.5', rest)
        rest = re.sub(r'(?<![\d.])(\d{1,3}-\d{1,2})\s*½', r'\1.5', rest)

        # Preferred: 2+ space column split  "K. Martin    Traip    11.75    5"
        parts = [p for p in re.split(r'\s{2,}', rest) if p.strip()]
        if is_relay and len(parts) == 2 and is_mark(parts[1]):
            school = re.sub(r"\s+['\"]?[A-D]['\"]?$", '', parts[0]).strip()
            if school and not school.replace('.', '').isdigit():
                return {'school': school, 'result': parts[1].rstrip('*qQjJ'),
                        'athletes': [], 'grade': '', 'type': 'Finals'}
        # "LASSARD    TH 11:36.0": the code typed one space from the mark
        if not is_relay and len(parts) == 2 and re.fullmatch(r'[A-Z]{1,3} \S+', parts[1]) \
                and is_mark(parts[1].split()[1]) and re.search(r'[A-Za-z]{2}', parts[0]):
            code, mark = parts[1].split()
            return {'athlete': parts[0], 'school': self._resolve_school(code),
                    'result': mark.rstrip('*qQjJ'), 'grade': '', 'type': 'Finals'}
        if len(parts) >= 3:
            mark_idx = None
            for i in range(len(parts) - 1, 0, -1):
                if is_mark(parts[i].split()[0]) or is_mark(parts[i]):
                    mark_idx = i
                    break
            if mark_idx and mark_idx >= 1:
                mark = parts[mark_idx].split()[0].rstrip('*qQjJ')
                if is_relay:
                    school = re.sub(r"\s+['\"]?[A-D]['\"]?$", '', parts[0]).strip()
                    return {'school': self._resolve_school(school), 'result': mark, 'athletes': [],
                            'grade': '', 'type': 'Finals'}
                if mark_idx >= 2:
                    name = parts[0]
                    school = ' '.join(parts[1:mark_idx])
                    grade = ''
                    g = re.match(r'^(7|8|9|10|11|12|FR|SO|JR|SR)\s+(.*)$', school, re.I)
                    if g:
                        grade, school = g.group(1), g.group(2)
                    # dual-meet sheets put the points column (1-6) between
                    # school and mark: "K. Parker  W  6  55.1" (a code's
                    # winner scores 8 in a tri meet: "Y    8   54.0")
                    pts = re.match(r'^(.*\S)\s+[1-6]$', school) or re.match(r'^([A-Z]{1,3})\s+[1-9]$', school)
                    if pts:
                        school = pts.group(1)
                    return {'athlete': name, 'school': self._resolve_school(school), 'result': mark,
                            'grade': grade, 'type': 'Finals'}

        # Fallback: single-space tokens (collapsed pdftotext output)
        toks = rest.split()
        if len(toks) < 3:
            return None
        # rightmost mark token, skipping trailing small-int points
        mark_idx = None
        for i in range(len(toks) - 1, 0, -1):
            if is_mark(toks[i]):
                mark_idx = i
                break
        if mark_idx is None or mark_idx < 1:
            return None
        mark = toks[mark_idx].rstrip('*qQjJ')
        # earlier mark tokens (seed) get excluded from the school text
        first_mark = mark_idx
        while first_mark - 1 > 0 and is_mark(toks[first_mark - 1]):
            first_mark -= 1
        head = toks[:first_mark]
        # a points cell after the school code ("Kayla Gray  L  8 8.36.6",
        # "NYA  NY 8 47.8"): not a grade, not part of the name
        if len(head) >= 2 and re.fullmatch(r'[1-9]|10', head[-1]) and re.fullmatch(r'[A-Z]{1,3}', head[-2]):
            head = head[:-1]
            if is_relay and len(head) >= 2:
                head = head[:-1]    # (the team's code after its name)

        if is_relay:
            school = ' '.join(head)
            school = re.sub(r"\s+['\"]?[A-D]['\"]?$", '', school).strip()
            if not school:
                return None
            return {'school': self._resolve_school(school), 'result': mark, 'athletes': [],
                    'grade': '', 'type': 'Finals'}

        grade_idx = None
        for i, t in enumerate(head):
            if i >= 1 and GRADE_RE.match(t):
                grade_idx = i
                break
        if grade_idx:
            name = ' '.join(head[:grade_idx])
            school = ' '.join(head[grade_idx + 1:])
            grade = head[grade_idx].upper()
        else:
            # no grade token: assume 2-token name, rest school
            if len(head) < 3:
                return None
            name = ' '.join(head[:2])
            school = ' '.join(head[2:])
            grade = ''
        pts = re.match(r'^(.*\S)\s+[1-6]$', school)  # trailing points column
        if pts:
            school = pts.group(1)
        if not name or not school:
            return None
        return {'athlete': name, 'school': self._resolve_school(school), 'result': mark,
                'grade': grade, 'type': 'Finals'}
