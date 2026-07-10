"""
XCDualSheetParser - classic cross-country dual/tri meet summaries:

    PLACE  TEAM        POINTS  PLACES OF FINISHERS   AVG. TIME  SPREAD
      1   Boothbay       31    1 4 6 9 11 22 23      19:58      2:50
    ...
    Individuals
    1. Boothbay
        1  Chase Brown        18:29   5:58
        4  Matt Forgues       19:28   6:17
    2. Monmouth
        ...

Individual rows carry overall place, name, finish time, and pace; the school
comes from the numbered team subsection header. Gender from the filename.
The single implicit event is 5K Cross Country.
"""

import re
from .base import BaseParser
from .looselist import is_mark

ROW_RE = re.compile(r'^\s*(\d{1,3})\s+([A-Za-z][A-Za-z .,\'-]{2,30}?)\s{2,}(\d{1,2}:\d{2}(?:\.\d+)?)(?:\s+(\d{1,2}:\d{2}))?\s*$')
TEAM_HDR_RE = re.compile(r'^\s*\d{1,2}[.)]\s+([A-Za-z][A-Za-z .\'/&-]{2,35})\s*$')


class XCDualSheetParser(BaseParser):
    def parse(self, text, meet_url, season_type):
        from bs4 import BeautifulSoup
        if '<' in text[:2000].lower():
            soup = BeautifulSoup(text, 'html.parser')
            pres = soup.find_all('pre')
            text = "\n".join(p.get_text() for p in pres) if pres else soup.get_text('\n')
        if not re.search(r'PLACES OF FINISHERS|AVG\.?\s*TIME', text, re.I):
            return {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}
        lines = [l.rstrip() for l in text.replace('\xa0', ' ').splitlines()]

        url_low = meet_url.lower()
        gender = 'Girls' if re.search(r'girl|women', url_low) else \
                 'Boys' if re.search(r'boy|men', url_low) else 'Boys'

        date = None
        for l in lines[:8]:
            m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', l)
            if m:
                yy = m.group(3) if len(m.group(3)) == 4 else '20' + m.group(3)
                date = f'{yy}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}'
                break

        results = []
        current_team = None
        in_individuals = False
        for l in lines:
            s = l.strip()
            if not s:
                continue
            if re.match(r'^individuals?\b', s, re.I):
                in_individuals = True
                continue
            if not in_individuals:
                continue
            m_team = TEAM_HDR_RE.match(s)
            if m_team and not re.search(r'\d:\d', s):
                current_team = m_team.group(1).strip()
                continue
            m_row = ROW_RE.match(l)
            if m_row and current_team:
                name = m_row.group(2).strip()
                mark = m_row.group(3)
                if is_mark(mark):
                    results.append({'athlete': name, 'school': current_team,
                                    'result': mark, 'grade': '', 'type': 'Finals'})

        if not results:
            return {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}
        meet_name = next((l.strip() for l in lines[:4] if l.strip()), None)
        return {'events': [{'event': '5K Cross Country', 'gender': gender,
                            'is_relay': False, 'results': results}],
                'date': date, 'meet_name': meet_name, 'team_rankings': []}
