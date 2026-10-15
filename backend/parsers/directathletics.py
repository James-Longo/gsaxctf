"""DirectAthletics MeetPro text results (college meets: Maine State
championship, Husson Harrier Invitational, 2017):

    Men's 8000 Meters
       1 Bates                     31       26:08      2:10:39      0:37.4   3    5    6    7    10
    ================================================================
      Pl Athlete                 Yr Team                      Score       Time  Avg. Mile    Avg. kM
    ================================================================
       1 TORDA, Ben              JR Bowdoin                       1   25:25.27     5:06.9     3:10.7
      15 LEVINE, Justin          SO Bates                             26:39.32     5:21.8     3:19.9
      -- MURRAY, Emma            FR Husson                                 DNS        ---        ---

Each "Women's / Men's NNNN Meters" title opens a race; the team table above
the runners lists every team's scoring places (an 'xc' block paired to the
race by event_idx). Runner columns are cut at the header words: the name
from "Athlete", class from "Yr", team from "Team" up to "Score" (the team
place, right-aligned under it), then the time.
"""
import re
from .base import BaseParser, proper_case_name

_SIG = re.compile(r'DirectAthletics|^\s*Pl\s+Athlete\s+Yr\s+Team\s+Score\s+Time', re.I | re.M)
_RACE = re.compile(r"^\s*(Women|Men)'?s\s+(\d{3,5})\s*Meters?\b", re.I)
_TEAM = re.compile(r'^\s*(\d{1,3})\s+(\S.*?)\s+(\d{1,4})\s+\d{1,2}:\d{2}(?:\.\d+)?\s+'
                   r'(?:\d+:)?\d{1,2}:\d{2}(?:\.\d+)?\s+\d{1,2}:\d{2}(?:\.\d+)?\s+((?:\d{1,4}\s+)*\d{1,4})\s*$')
_TIME = re.compile(r'^(?:\d+:)?\d{1,2}:\d{2}(?:\.\d+)?$')


class DirectAthleticsParser(BaseParser):
    @staticmethod
    def matches(text):
        return bool(text and _SIG.search(text[:20000]))

    def parse(self, text, meet_url, season_type):
        empty = {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}
        if '<' in text[:3000]:
            text = re.sub(r'<[^>]+>', '', text).replace('&nbsp;', ' ').replace('&amp;', '&')
        if not self.matches(text):
            return empty
        lines = text.replace('\xa0', ' ').splitlines()
        races = []
        cols = None
        for line in lines:
            m = _RACE.match(line)
            if m:
                g = 'Girls' if m.group(1).lower() == 'women' else 'Boys'
                meters = int(m.group(2))
                event = f'{meters // 1000}k Run CC' if meters % 1000 == 0 else f'{meters} Meter Run CC'
                races.append({'gender': g, 'event': event, 'rows': [], 'teams': []})
                cols = None
                continue
            if not races:
                continue
            if re.match(r'^\s*Pl\s+Athlete\b', line):
                cols = {w: line.index(w) for w in ('Athlete', 'Yr', 'Team', 'Score')
                        if w in line}
                continue
            if cols is None:
                t = _TEAM.match(line)
                if t:
                    places = [int(x) for x in t.group(4).split()]
                    if sum(places[:5]) == int(t.group(3)):
                        races[-1]['teams'].append({'rank': int(t.group(1)), 'team': t.group(2).strip(),
                                                   'score': float(t.group(3)), 'places': places})
                continue
            row = self._row(line, cols)
            if row:
                races[-1]['rows'].append(row)
        events, rankings = [], []
        from backend.parser import normalize_grade
        for r in races:
            if len(r['rows']) < 3:
                continue
            for row in r['rows']:
                row['grade'] = normalize_grade(row['grade'])
            if r['teams']:
                rankings.append({'kind': 'xc', 'gender': r['gender'], 'event_header': r['event'],
                                 'event_idx': len(events), 'teams': r['teams']})
            events.append({'event': r['event'], 'gender': r['gender'], 'is_relay': False,
                           'results': r['rows']})
        if not events:
            return empty
        title = next((l.strip() for l in lines[1:6] if l.strip()), None)
        date = None
        dm = re.search(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', '\n'.join(lines[:6]))
        if dm:
            date = f'{dm.group(3)}-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}'
        return {'events': events, 'date': date, 'meet_name': title, 'team_rankings': rankings}

    @staticmethod
    def _row(line, cols):
        if not all(k in cols for k in ('Athlete', 'Yr', 'Team', 'Score')):
            return None
        pl = line[:cols['Athlete']].strip()
        if not re.fullmatch(r'\d{1,4}', pl):
            return None          # "--" DNS / DNF
        name = line[cols['Athlete']:cols['Yr']].strip()
        yr = line[cols['Yr']:cols['Team']].strip()
        team = line[cols['Team']:cols['Score']].strip()
        rest = line[cols['Score']:].split()
        if not name or not rest:
            return None
        row = {'place': int(pl), 'athlete': proper_case_name(name) if name.split(',')[0].isupper() else name,
               'school': team, 'grade': yr, 'type': 'Finals'}
        if re.fullmatch(r'\d{1,4}', rest[0]) and len(rest) > 1:
            row['team_place'] = int(rest[0])
            rest = rest[1:]
        if not _TIME.match(rest[0]):
            return None
        row['result'] = rest[0]
        return row
