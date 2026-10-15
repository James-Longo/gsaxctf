"""XC "OFFICIAL MEET REPORT" exports (RunScore-style, e.g. Brewer Timing).

    Race #1
    MEN (Varsity) • 5 Kilometers (3.11 Miles)                     Final Results
   TEAM SCORING SUMMARY
   Final Standings          Score   Scoring Order          Total     Avg.   Spread
     1   Orono High School    39     1-5-8-11-14(26)(36)    1:25:29 17:06   1:12.5
   INDIVIDUAL RESULTS
   Athlete                  YR Team                 Score   Time     Avg. Mile  Avg. kM
     1   ARSENAULT, Ben     SR Orono High School       1    16:24.37 5:16.5     3:16.9

Pages are often laid out in two columns (team summary beside individual
results, or two columns of individuals), so rows are matched anywhere on a
line rather than by column position, then put back in place order per race.
The finish time is the first time after the team-score cell; the paces that
follow it (per mile / per km) were what earlier parsers stored.

Official team standings come with each team's scoring places, so every race
is verifiable by QAQC (kind 'xc' blocks, paired to their race by event_idx).
"""
import re
from .base import BaseParser, proper_case_name, proper_case_team

_SIG = re.compile(r'INDIVIDUAL RESULTS', re.I)
_SIG2 = re.compile(r'TEAM SCORING SUMMARY|OFFICIAL MEET REPORT|Race\s*#\s*\d', re.I)
_RACE = re.compile(r'^\s*Race\s*#\s*(\d+)', re.I)
_TITLE = re.compile(
    r'^\s*(?P<g>MEN|WOMEN|BOYS|GIRLS|MALE|FEMALE)?\'?S?\s*(?:\((?P<div>[^)]*)\))?\s*'
    r'(?P<div2>[A-Za-z][A-Za-z ./&-]*?)?\s*•\s*(?P<dist>[^•]+?)(?:\s{2,}|$)', re.I)
_GENDER = {'men': 'Boys', 'boys': 'Boys', 'male': 'Boys',
           'women': 'Girls', 'girls': 'Girls', 'female': 'Girls'}
_W = r"[A-Za-z][\w'\-.]*"
_IND = re.compile(
    r'(?<!\S)(?P<place>\d{1,4})\s+'
    r'(?P<name>' + _W + r"(?: [\w'\-.]+)*\s?,(?:\s?[\w'\-.]+(?: [\w'\-.]+)*?)?"
    r"(?: \([\w'\-. ]{1,12}\))?"   # nickname: "YANUSH, Charles (CJ)"
    r'|' + _W + r"(?: [\w'\-.]+)*? [A-Z][A-Z'\-]+(?:(?: | - )[A-Z][A-Z'\-]+)*"  # "ALVAREZ - BACK"
    r'(?: \((?P<yr2>FR|SO|JR|SR|GR|5Y|\d{1,2})\))?'
    # plain "Jesse Orach": only when a YR cell follows, else ambiguous
    r'|' + _W + r"(?: [\w'\-.]+)+(?=\s+(?:FR|SO|JR|SR|GR|5Y)\s))"
    r'(?:\s+(?P<yr>FR|SO|JR|SR|GR|5Y|\d{1,2}))?'
    # the team cell never holds a scoring order ("4-5-6") or a time: that
    # is a team-summary row sitting beside the athlete column
    r'\s+(?P<team>(?:(?!\d-\d|\d:\d)\S)(?:(?!\d-\d|\d:\d).)*?)\s+(?P<score>-|\(\d+\)|\d+)\s+'
    r'(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)(?!\S)')
_TEAM = re.compile(
    r'(?<!\S)(?P<rank>\d{1,3})\s+(?P<team>\S.*?)\s+(?P<score>\d{1,4})\s+'
    r'(?P<order>\d{1,4}(?:-\d{1,4}){4,})(?P<disp>(?:\(\d{1,4}\))*)(?!\S)')


def _event_name(dist, div):
    d = dist.strip()
    km = re.search(r'(\d+(?:\.\d+)?)\s*(?:Kilometers?|km|k)\b', d, re.I)
    mi = re.search(r'(\d+(?:\.\d+)?)\s*Miles?\b', d, re.I)
    m_ = re.search(r'(\d{3,5})\s*(?:Meters?|m)\b', d, re.I)
    # the first-named unit is the race's own ("2.1 Miles (3.38 Kilometers)")
    cands = [(x.start(), x) for x in (km, mi, m_) if x]
    if not cands:
        base = d
    else:
        first = min(cands, key=lambda c: c[0])[1]
        if first is km:
            base = f'{first.group(1)}k Run CC'
        elif first is mi and float(first.group(1)) >= 1000:
            # "5000 Miles (8046.7 Kilometers)": a mistyped unit (Thomas
            # College 2018, women's times are 5,000 m times)
            v = int(float(first.group(1)))
            base = f'{v // 1000}k Run CC' if v % 1000 == 0 else f'{v} Meter Run CC'
        elif first is mi:
            base = f'{first.group(1)} Mile Run CC'
        else:
            base = f'{first.group(1)} Meter Run CC'
    return f'{base} {div}'.strip() if div else base


class MeetReportParser(BaseParser):
    @staticmethod
    def matches(text):
        return bool(text and _SIG.search(text) and _SIG2.search(text))

    def parse(self, text, meet_url, season_type):
        empty = {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}
        if not self.matches(text):
            return empty
        races = {}      # race no -> {'gender', 'event', 'rows': {place: row}, 'teams': {}}
        order = []
        cur = None
        pending_title = False
        for line in text.splitlines():
            m = _RACE.match(line)
            if m:
                cur = int(m.group(1))
                if cur not in races:
                    races[cur] = {'gender': None, 'event': None, 'rows': {}, 'teams': {}}
                    order.append(cur)
                pending_title = True
                continue
            if pending_title and line.strip():
                pending_title = False
                t = _TITLE.match(line)
                if t and cur is not None:
                    r = races[cur]
                    if r['event'] is None:
                        g = (t.group('g') or '').lower()
                        r['gender'] = _GENDER.get(g)
                        div = (t.group('div') or t.group('div2') or '').strip()
                        r['event'] = _event_name(t.group('dist'), div)
                        if r['gender'] is None:
                            low = line.lower()
                            if re.search(r'\b(women|girls)\b', low):
                                r['gender'] = 'Girls'
                            elif re.search(r'\b(men|boys)\b', low):
                                r['gender'] = 'Boys'
                    continue
            if cur is None:
                continue
            race = races[cur]
            for tm in _TEAM.finditer(line):
                places = [int(x) for x in tm.group('order').split('-')]
                places += [int(x) for x in re.findall(r'\((\d+)\)', tm.group('disp'))]
                race['teams'].setdefault(int(tm.group('rank')), {
                    'rank': int(tm.group('rank')), 'team': tm.group('team').strip(),
                    'score': float(tm.group('score')), 'places': places})
            # a typed double quote for an apostrophe: 'O"Dea, Katie'
            line = re.sub(r'(?<=[A-Za-z])"(?=[A-Za-z])', "'", line)
            for im in _IND.finditer(line):
                team = im.group('team').strip()
                # a team-summary row never parses as an athlete: guard anyway
                if re.search(r'\d-\d', team):
                    continue
                name = im.group('name').strip()
                name = re.sub(r'\s*\([^)]*\)$', '', name)  # (SR) or (CJ)
                name = re.sub(r'\s+,', ',', name)            # "LAAM , Nina"
                yr = im.group('yr') or im.group('yr2') or ''
                if not yr:
                    # first name truncated away: "KUNGXAT-FACENDA, JR Thomas"
                    m2 = re.match(r'^(.*,)\s*(FR|SO|JR|SR|GR)$', name)
                    if m2:
                        name, yr = m2.group(1), m2.group(2)
                if not yr:
                    # name ran into the YR cell: "ALONSO, Angel Mend      SO"
                    m2 = re.match(r'^(\S.*?)\s+(FR|SO|JR|SR|GR)\s+(\S.*)$', team)
                    if m2 and not re.match(r'^\d+$', m2.group(1)):
                        name = f'{name} {m2.group(1)}'.strip()
                        yr, team = m2.group(2), m2.group(3)
                # bib-number column between YR and team: "SR   159   Clark"
                team = re.sub(r'^\d{1,5}\s+', '', team)
                # DirectAthletics "Team (Team Place)": "Maine (1)" -> "Maine"
                team = re.sub(r'\s*\(\d{1,3}\)$', '', team)
                place = int(im.group('place'))
                row = race['rows'].setdefault(place, {
                    'athlete': proper_case_name(name),
                    'school': proper_case_team(team),
                    'result': im.group('time'),
                    'grade': yr,
                    'type': 'Finals',
                    'place': place,
                })
                # Score: the team-score place, "(7)" a displacer, "-" none
                sc = re.sub(r'[()]', '', im.group('score'))
                if sc.isdigit():
                    row['team_place'] = int(sc)
        events, rankings = [], []
        for no in order:
            r = races[no]
            if not r['rows']:
                continue
            gender = r['gender'] or 'Boys'
            results = [r['rows'][p] for p in sorted(r['rows'])]
            from backend.parser import normalize_grade
            for row in results:
                row['grade'] = normalize_grade(row['grade'])
            events.append({'event': r['event'] or 'Run CC', 'gender': gender,
                           'is_relay': False, 'results': results})
            if r['teams']:
                rankings.append({'kind': 'xc', 'gender': gender,
                                 'event_header': r['event'],
                                 'event_idx': len(events) - 1,
                                 'teams': [r['teams'][k] for k in sorted(r['teams'])]})
        date = None
        dm = re.search(r'(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})', text)
        if dm:
            from datetime import datetime
            try:
                date = datetime.strptime(dm.group(1), '%B %d, %Y').strftime('%Y-%m-%d')
            except ValueError:
                date = None
        first = next((l.strip() for l in text.splitlines() if l.strip()), '')
        meet_name = re.split(r'\s{2,}', first)[0] if first else None
        return {'events': events, 'date': date, 'meet_name': meet_name,
                'team_rankings': rankings}
