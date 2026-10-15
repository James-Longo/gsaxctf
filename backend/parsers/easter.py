"""Randy Easter's XC results pages (Mountain Valley Conference, Leavitt,
Monmouth, Tripp, Oxford Hills ... 2004-2010):

    Leavitt Boys / Sept. 14, 2007 / Sunny, Windy Results by Randy Easter
    PLACE  TEAM                  POINTS  PLACES OF FINISHERS     AVG. TIME  SPREAD
      1   Mt. Blue                 45    1    5   10   14   15   18   38   18:08   2:01
    1. Mt. Blue                                          (per-team detail: skipped)
      390     1  Eric Marceau                16:53    5:27
            TEAM
     PLACE SCORE          FINISHER          TIME    PACE        TEAM
      415    13    13  Tyler Gammon                18:37    6:00  Edward Little
        1     1  Jared Cloutier, 11          17:12    5:33  Lisbon

The overall list is the race: [bib] place [team score] finisher[, grade]
time pace team ("Pace: 6:00 | 7:00 | Top" page links may prefix a row).
The team table at the top lists each team's scoring places, which makes the
race verifiable (an 'xc' block paired by event_idx). The distance is read
off time / pace.
"""
import re
from .base import BaseParser

_SIG = re.compile(r'Results by Randy Easter|PLACES OF FINISHERS', re.I)
_ROW = re.compile(
    r'^\s*(?:Pace:[^A-Za-z]*(?:\|\s*)?Top\s+)?(?P<nums>(?:\d{1,4}\s+){1,3})'
    r'(?P<name>[A-Za-z][^\d:]*?)(?:,\s*(?P<gr>\d{1,2}))?\s+'
    r'(?P<time>\d{1,2}:\d{2}(?:\.\d+)?)\s+(?:(?P<pace>\d{1,2}:\d{2})\s+)?(?P<team>[A-Za-z].*?)\s*$')
_TEAM = re.compile(
    r'^\s*(?P<rank>\d{1,3})\*?\s+(?P<team>[A-Za-z].*?)\s+(?P<pts>\d{1,4})\s+'
    r'(?P<places>(?:\d{1,4}\s+){4,9})(?P<avg>\d{1,2}:\d{2})')


class EasterParser(BaseParser):
    @staticmethod
    def matches(text):
        return bool(text and _SIG.search(text))

    def parse(self, text, meet_url, season_type):
        empty = {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}
        if not self.matches(text):
            return empty
        if '<' in text[:3000]:
            text = re.sub(r'<br\s*/?>|</p>|</tr>', '\n', text, flags=re.I)
            text = re.sub(r'<[^>]+>', ' ', text).replace('&nbsp;', ' ').replace('&amp;', '&')
        lines = [l.rstrip() for l in text.replace('\xa0', ' ').splitlines()]
        parsed = []
        teams = []
        for line in lines:
            m = _TEAM.match(line)
            if m and not _ROW.match(line):
                places = [int(x) for x in m.group('places').split()]
                if sum(places[:5]) == int(m.group('pts')) and \
                        (int(m.group('rank')), m.group('team').strip()) not in \
                        {(t['rank'], t['team']) for t in teams}:   # table printed twice
                    teams.append({'rank': int(m.group('rank')), 'team': m.group('team').strip(),
                                  'score': float(m.group('pts')), 'places': places})
                continue
            r = _ROW.match(line)
            if r:
                parsed.append((r, [int(x) for x in r.group('nums').split()]))
        if not parsed:
            return empty
        bib_col = any(len(n) == 3 for _r, n in parsed)
        rows = {}
        miles = []
        for r, nums in parsed:
            if bib_col:
                if len(nums) < 2:
                    continue
                place, tp = nums[1], (nums[2] if len(nums) == 3 else None)
            else:
                place, tp = nums[0], (nums[1] if len(nums) >= 2 else None)
            row = {'athlete': re.sub(r'\s+', ' ', r.group('name')).strip(' ,'),
                   'school': r.group('team').strip(), 'result': r.group('time'),
                   'grade': '', 'type': 'Finals', 'place': place}
            if tp is not None:
                row['team_place'] = tp
            if r.group('gr'):
                from backend.parser import normalize_grade
                row['grade'] = normalize_grade(r.group('gr'))
            rows.setdefault(place, row)
            if r.group('pace'):
                p = r.group('pace').split(':')
                ps = int(p[0]) * 60 + int(p[1])
                t = [float(x) for x in r.group('time').split(':')]
                if 180 <= ps <= 900:
                    miles.append((t[0] * 60 + t[1]) / ps)
        results = [rows[p] for p in sorted(rows)]
        if len(results) < 3:
            return empty
        head = ' '.join(l for l in lines[:12])
        url = (meet_url or '').lower()
        g = ('Girls' if re.search(r'\bgirls?\b|women', head, re.I) or re.search(r'girl|women|g\d|g[-_.]', url)
             else 'Boys')
        if re.search(r'\bboys?\b', head, re.I) and not re.search(r'\bgirls?\b', head, re.I):
            g = 'Boys'
        from .xcrun import _distance_label
        event = _distance_label(sorted(miles)[len(miles) // 2]) if len(miles) >= 3 else 'Run CC'
        rankings = []
        if teams:
            rankings.append({'kind': 'xc', 'gender': g, 'event_header': event,
                             'event_idx': 0, 'teams': teams})
        title = next((l.strip() for l in lines if l.strip()), None)
        return {'events': [{'event': event, 'gender': g, 'is_relay': False, 'results': results}],
                'date': None, 'meet_name': title, 'team_rankings': rankings}
