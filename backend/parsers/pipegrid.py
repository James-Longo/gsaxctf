"""
PipeGridParser - OCR'd dual-meet score sheets whose table borders survive as
pipe characters:

    FRYEBURG ACADEMY VS SACOPEE VALLEY VS LAKE REGION-BOYS
    EVENT |1st Place 5 pts Sch 2nd Plac ...
    RW___|HARTWELL- 8:23 SV |ODONNELL, R- 8:35 SV |BLAIS, C- 9:21 SV |...
    HJ    |WINKLER- 5' 4" FA |VERRILL- 5'4" SV |...

Cells are "NAME- mark CODE"; codes resolve against the "A VS B VS C" title.
Relay cells are "CODE- mark". Trailing per-team score columns are ignored
because their cells don't match the entry pattern.
"""

import re
from .base import BaseParser
from .looselist import canon_event, is_mark, _normalize_feet_inch_marks

ENTRY_RE = re.compile(
    r"^([A-Za-z][A-Za-z ,.'’-]{1,28}?)[-–]\s*"      # NAME-
    r"([\d][\d:.'’”\" /]{1,14}?)\s*"                 # mark
    r"([A-Z]{1,3})?\s*$")                                       # school code


class PipeGridParser(BaseParser):
    def parse(self, text, meet_url, season_type):
        from bs4 import BeautifulSoup
        if '<' in text[:2000].lower():
            soup = BeautifulSoup(text, 'html.parser')
            text = soup.get_text('\n')
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        piped = [l for l in lines if l.count('|') >= 2]
        if len(piped) < 5:
            return {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}

        # participating schools from the "A VS B VS C[-BOYS]" title line
        schools = []
        title = None
        for l in lines[:8]:
            if re.search(r'\bvs\b', l, re.I):
                title = l
                clean = re.sub(r'[-–]?\s*(boys|girls)\s*$', '', l, flags=re.I)
                schools = [s.strip(' .') for s in re.split(r'\bvs\.?\b', clean, flags=re.I)
                           if s.strip()]
                break
        gender = ''
        blob = ' '.join(lines[:8]).lower() + ' ' + meet_url.lower()
        if 'girl' in blob:
            gender = 'Girls'
        elif 'boy' in blob:
            gender = 'Boys'

        def resolve(code):
            if not code:
                return 'Unknown'
            cands = [s for s in schools if s.lower().startswith(code.lower())]
            if len(cands) == 1:
                return cands[0].title()
            cands = [s for s in schools
                     if ''.join(w[0] for w in s.split()).lower() == code.lower()]
            if len(cands) == 1:
                return cands[0].title()
            return code

        meet_date = None
        m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', ' '.join(lines[:6]))
        if m:
            yy = m.group(3) if len(m.group(3)) == 4 else '20' + m.group(3)
            meet_date = f'{yy}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}'

        events = []
        for l in piped:
            cells = [c.strip() for c in l.split('|')]
            label = re.sub(r'[_\W]+$', '', cells[0]).strip()
            if not label or re.search(r'event|score|name', label, re.I):
                continue
            # OCR noise guard: the label must actually look like an event
            if not re.match(r'^(4\s*x\s*\d{3}|\d{2,4}\s*m?(h|m|rw)?|rw|hj|lj|tj|pv|sp|shot|disc\w*|jav\w*|high|long|triple|pole|race\s*walk)\b',
                            label, re.I) and not re.search(r'relay|jump|vault|put|hurdle|dash|walk', label, re.I):
                continue
            ev_name = canon_event(label)
            is_relay = bool(re.search(r'relay|4\s*x|4x', label, re.I))
            results = []
            for cell in cells[1:]:
                cell = _normalize_feet_inch_marks(cell.strip())
                if not cell or re.fullmatch(r'[\d\s.]*', cell):
                    continue  # per-team score columns
                m_e = ENTRY_RE.match(cell)
                if not m_e:
                    continue
                who, mark, code = m_e.group(1).strip(), m_e.group(2).strip(), m_e.group(3)
                mark = mark.rstrip(" .'")
                if not is_mark(mark):
                    continue
                if is_relay or (code is None and len(who) <= 3 and who.isupper()):
                    results.append({'school': resolve(who if code is None else who),
                                    'result': mark, 'athletes': [], 'grade': '',
                                    'type': 'Finals'})
                else:
                    results.append({'athlete': who.title() if who.isupper() else who,
                                    'school': resolve(code), 'result': mark,
                                    'grade': '', 'type': 'Finals'})
            if results:
                events.append({'event': ev_name, 'gender': gender or 'Boys',
                               'is_relay': is_relay, 'results': results})
        return {'events': events, 'date': meet_date, 'meet_name': title,
                'team_rankings': []}
