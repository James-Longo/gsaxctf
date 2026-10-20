"""XCRun "OFFICIAL RESULTS" exports (PDF), common for Maine MS/HS dual and
league meets 2016-2025 (Brunswick, Maranacook, Winthrop, Spruce Mountain,
Oxford Hills, MVC, ...):

                                 MARANACOOK MIDDLE SCHOOL
                                          BOYS RACE
                                     OFFICIAL RESULTS
    PLC BIB    PTS   NAME                        TEAM            TIME     PACE
     1   179    1    BRAYDEN DOW            8    WINDSOR       :11:52.8   6:36

Older ones add a class column and a time-behind column:

    PLC   BIB   PLC CLS   NAME               AGE/LOCATION/TEAM     TIME    BEHIND   PACE
     1    227     1 MSB   SATTERFIELD, GRADY  8 MT ARARAT        : 9:53.9   : 0.0     5:29

and some pages run two result columns side by side, so rows are matched
anywhere on a line. The finish is the first time after the team cell; the
per-mile PACE (and BEHIND gap) that follow are what generic parsers took.
The "Place TEAM Points SCORES" table that follows each race lists every
team's scoring places, which makes the race verifiable (kind 'xc' blocks).
"""
import re
from .base import BaseParser, proper_case_name, proper_case_team

_SIG = re.compile(r'PLC\s+BIB\s+(?:PTS|PLC\s+CLS)\s+NAME|PLC\s+NAME\s+LOCATION\s+BIB\s+PLC\s+TEAM')
_GENDER_WORD = re.compile(r'\b(BOYS|GIRLS|MEN|WOMEN|MEN\'S|WOMEN\'S)\b', re.I)
_GMAP = {'boys': 'Boys', 'men': 'Boys', "men's": 'Boys',
         'girls': 'Girls', 'women': 'Girls', "women's": 'Girls'}
_TIME = r'(?::\s?\d{1,2}:\d{2}(?:\.\d+)?|\d{1,2}:\d{2}:\d{2}(?:\.\d+)?|\d{1,2}:\d{2}\.\d+)'
_ROW_PTS = re.compile(
    r'(?<!\S)(?P<place>\d{1,4})\s+(?P<bib>\d{1,5})\s+(?P<pts>\d{1,4})\s+'
    r'(?P<mid>[A-Za-z].*?)\s+(?P<time>' + _TIME + r')(?!\S)')
_ROW_CLS = re.compile(
    r'(?<!\S)(?P<place>\d{1,4})\s+(?P<bib>\d{1,5})\s+(?P<pts>\d{1,4})\s+(?P<cls>[A-Z]{1,4})\s+'
    r'(?P<mid>[A-Za-z].*?)\s+(?P<time>' + _TIME + r')(?!\S)')
# "PLC NAME LOCATION BIB OA-PLC TEAM TIME BEHIND" (St. Dom's, Tripp, Brunswick
# 2017-2023), split into "HSG - H.S. GIRLS" sections
_ROW_OA = re.compile(
    r'(?<!\S)(?P<place>\d{1,4})\s+(?P<name>[A-Za-z][^\d:]*?)\s+(?P<bib>\d{1,5})\s+(?P<pts>\d{1,4})\s+'
    r'(?P<mid>[A-Za-z].*?)\s+(?P<time>' + _TIME + r')(?!\S)')
_SECTION = re.compile(r'^\s+([A-Z]{2,4})\s+-\s+(\S.*?)\s*(?:\d+/\d+)?\s*$')
_SCORES_HDR = re.compile(r'Place\s+TEAM\s+Points', re.I)
_SCORE_ROW = re.compile(
    r'^\s*(?P<rank>\d{1,3})\s+(?P<team>\S.*?)\s+(?P<score>\d{1,4})\s+'
    r'(?P<places>(?:\d{1,4}\s+){4,}\d{1,4})(?=\s+:|\s+\d+:|\s*$)')
_DIST = re.compile(r'(?<![\d,.\-])(\d+(?:\.\d+)?) ?(K|KM|MILES?|MI)\b(?!\s*sports)', re.I)
# per-mile PACE after the finish (an optional ": 0.0" BEHIND gap between)
_PACE_AFTER = re.compile(r'(?:\s+:\s?\d{0,2}:?\d{1,2}\.\d)?\s+(\d{1,2}):(\d{2})(?!\S)')
_MS_TITLE = re.compile(r'JUNIOR\s+HIGH|MIDDLE\s+SCHOOL|\bMS\b|\bJH\b|\bJR\.?\s+HIGH|'
                       r'ELEMENTARY|\b[5-8](?:TH)?\s*(?:&|-|/)\s*[6-8]', re.I)


def _secs(t):
    parts = [float(x) for x in t.split(':')]
    v = 0.0
    for x in parts:
        v = v * 60 + x
    return v


def _distance_label(miles):
    """Course length the timer configured, read off time / PACE. Standard
    lengths get their usual names; anything else is reported in miles so a
    short middle-school course is never filed as the default 5K."""
    for km in (5, 4, 3, 6, 8):
        if abs(miles - km / 1.609344) <= 0.02 * km / 1.609344:
            return f'{km}k Run CC'
    for mi in (1.0, 1.5, 2.0, 2.5, 3.0):
        if abs(miles - mi) <= 0.02 * mi:
            return f'{mi:g} Mile Run CC'
    return f'{miles:.1f} Mile Run CC'


def _clean_time(t):
    t = re.sub(r'\s', '', t).lstrip(':')
    if re.match(r'^0:\d{2}:', t):
        t = t[2:].lstrip('0') or '0'
        if t.startswith(':'):
            t = '0' + t
    return t


def _split_mid(mid):
    """'SAM BELLOWS-HASKINS     7   MT. ARARAT' -> (name, grade, team)."""
    parts = [p for p in re.split(r'\s{2,}', mid.strip()) if p]
    grade = ''
    if len(parts) >= 3 and re.fullmatch(r'\d{1,2}', parts[1]):
        return parts[0], parts[1], ' '.join(parts[2:])
    if len(parts) == 2:
        name, team = parts
        m = re.match(r'^(\d{1,2})\s+(\S.*)$', team)
        if m:
            grade, team = m.group(1), m.group(2)
        else:
            m = re.match(r'^(.*\S)\s+(\d{1,2})$', name)
            if m:
                name, grade = m.group(1), m.group(2)
        return name, grade, team
    if len(parts) == 1:
        m = re.match(r'^(.*?\S)\s+(\d{1,2})\s+(\S.*)$', parts[0])
        if m:
            return m.group(1), m.group(2), m.group(3)
    if len(parts) > 2:
        return parts[0], grade, ' '.join(parts[1:])
    return None


class XCRunParser(BaseParser):
    @staticmethod
    def matches(text):
        return bool(text and _SIG.search(text))

    def parse(self, text, meet_url, season_type):
        empty = {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}
        if not self.matches(text):
            return empty
        cls_layout = bool(re.search(r'PLC\s+CLS', text))
        oa_layout = bool(re.search(r'PLC\s+NAME\s+LOCATION', text))
        row_re = _ROW_CLS if cls_layout else _ROW_OA if oa_layout else _ROW_PTS
        # class layout: first PLC is the place within the class/division,
        # the second (headed "OA") the overall place, which orders the race
        place_group = 'pts' if cls_layout else 'place'
        lines = text.splitlines()
        races = []

        def new_race():
            races.append({'gender': None, 'title': None, 'rows': {}, 'teams': []})

        new_race()
        mode = None
        for i, line in enumerate(lines):
            if 'OFFICIAL RESULTS' in line or re.search(r'(?:^|\s{3,})RESULTS\s*$', line):
                # every header opens a race; continuation pages (DNF rows,
                # the team-score page) are folded back below
                if races[-1]['rows'] or races[-1]['teams']:
                    new_race()
                race = races[-1]
                race['gender'] = race['title'] = None  # a header-only page: read anew
                for near in lines[max(0, i - 4):i + 3]:
                    if _GENDER_WORD.search(near) and not row_re.search(near):
                        g = _GENDER_WORD.search(near).group(1).lower()
                        if race['gender'] is None:
                            race['gender'] = _GMAP.get(g)
                            race['title'] = near.strip()
                mode = None
                continue
            if _SIG.search(line):
                mode = 'rows'
                continue
            ms = _SECTION.match(line) if oa_layout else None
            if ms and mode in ('rows', 'dnf'):
                # a section of the list: its own race ("HSB - H.S. BOYS");
                # "Did Not Finish" rows are no finishers
                if re.search(r'not\s+finish|dnf|disq', ms.group(2), re.I):
                    mode = 'dnf'
                    continue
                if races[-1]['rows']:
                    new_race()
                gm = _GENDER_WORD.search(ms.group(2))
                races[-1]['gender'] = _GMAP.get(gm.group(1).lower()) if gm else None
                races[-1]['title'] = races[-1]['title'] or ms.group(2).strip()
                races[-1]['section'] = ms.group(1)
                mode = 'rows'
                continue
            if _SCORES_HDR.search(line):
                mode = 'scores'
                # a second race's score page before its results ("BOYS"
                # scores right after the girls' page): a race of its own,
                # folded onto its results below
                if races[-1]['teams']:
                    new_race()
                    for near in lines[max(0, i - 3):i]:
                        gm = _GENDER_WORD.search(near)
                        if gm:
                            races[-1]['gender'] = _GMAP.get(gm.group(1).lower())
                            races[-1]['title'] = near.strip()
                continue
            race = races[-1]
            if race['gender'] is None:
                m = re.search(r'\s/\s+(.*?\b(BOYS|GIRLS|MEN|WOMEN)\b.*?)(?:\s{2,}|$)', line)
                if m:
                    race['gender'] = _GMAP.get(m.group(2).lower())
                    race['title'] = race['title'] or m.group(1).strip()
            if mode == 'rows':
                for m in row_re.finditer(line):
                    split = _split_mid(m.group('mid')) if not oa_layout else \
                        (m.group('name').strip(), '', m.group('mid').strip())
                    if not split:
                        continue
                    name, grade, team = split
                    if not re.search(r'[A-Za-z]', team):
                        continue
                    # keyed by (place, bib): judged ties share a place
                    row = race['rows'].setdefault((int(m.group(place_group)), int(m.group('bib'))), {
                        'athlete': proper_case_name(name.strip()),
                        'school': proper_case_team(team.strip()),
                        'result': _clean_time(m.group('time')),
                        'grade': grade, 'type': 'Finals'})
                    if cls_layout:
                        # class / division ("MSB"; "WCH" entries score apart)
                        row['division'] = m.group('cls')
                    elif oa_layout:
                        row['place'] = int(m.group('place'))   # (the OA place spans sections)
                        if race.get('section'):
                            row['division'] = race['section']
                    else:
                        # PTS: the runner's team-score place, 0 = not scoring
                        row['place'] = int(m.group('place'))
                        if int(m.group('pts')):
                            row['team_place'] = int(m.group('pts'))
                    mp = _PACE_AFTER.match(line, m.end())
                    if mp:
                        pace = int(mp.group(1)) * 60 + int(mp.group(2))
                        if 180 <= pace <= 900:
                            race.setdefault('miles', []).append(
                                _secs(row['result']) / pace)
            elif mode == 'scores':
                m = _SCORE_ROW.match(line)
                if m:
                    race['teams'].append({
                        'rank': int(m.group('rank')), 'team': m.group('team').strip(),
                        'score': float(m.group('score')),
                        'places': [int(x) for x in m.group('places').split()]})
        # a division printed on its own page ("WHEELCHAIR DIVISION") repeats
        # the race header: fold it back when its places don't collide
        merged = []
        for r in races:
            prev = merged[-1] if merged else None
            same_g = prev and (r['gender'] or prev['gender']) == (prev['gender'] or r['gender'])
            if same_g and not r['rows']:
                prev['teams'] = prev['teams'] or r['teams']
                continue
            if same_g and not prev['rows']:  # score page printed first
                r['teams'] = r['teams'] or prev['teams']
                r['gender'] = r['gender'] or prev['gender']
                r['title'] = r['title'] or prev['title']
                merged[-1] = r
                continue
            if prev and r['rows'] and prev['rows'] \
                    and (r['gender'] or prev['gender']) == (prev['gender'] or r['gender']) \
                    and not {p for p, _ in r['rows']} & {p for p, _ in prev['rows']}:
                prev['rows'].update(r['rows'])
                prev['teams'] = prev['teams'] or r['teams']
                continue
            merged.append(r)
        races = merged
        # a division section printed last ("WCH - Wheelchair Divison", one
        # runner) catches the score page that belongs to the race above it
        for k in range(1, len(races)):
            r, prev = races[k], races[k - 1]
            if r['teams'] and not prev['teams'] and len(r['rows']) <= 3 < len(prev['rows']) \
                    and (r['gender'] or prev['gender']) == (prev['gender'] or r['gender']):
                prev['teams'], r['teams'] = r['teams'], []
        fname = (meet_url or '').lower()
        file_gender = ('Girls' if re.search(r'girl|women', fname)
                       else 'Boys' if re.search(r'boy|\bmen', fname) else None)
        from backend.parser import normalize_grade
        events, rankings = [], []
        for r in races:
            if not r['rows']:
                continue
            gender = r['gender'] or file_gender or 'Boys'
            dm = _DIST.search(r['title'] or '')
            if dm:
                unit = dm.group(2).lower()
                event = (f"{dm.group(1)}k Run CC" if unit.startswith('k')
                         else f"{dm.group(1)} Mile Run CC")
            elif len(r.get('miles', [])) >= 3:
                ms = sorted(r['miles'])
                event = _distance_label(ms[len(ms) // 2])
            else:
                event = 'Run CC'
            results = [r['rows'][p] for p in sorted(r['rows'])]
            # the cell after NAME is the grade in school meets but the AGE in
            # some ("CAMILA CIEMBRONIEWICZ  16", 0 = not entered): an age
            # column is never read as grades
            nums = [int(x['grade']) for x in results if str(x['grade']).isdigit()]
            is_age = any(13 <= n <= 25 for n in nums)
            for row in results:
                row['grade'] = '' if is_age else normalize_grade(row['grade'])
            events.append({'event': event, 'gender': gender, 'is_relay': False,
                           'results': results})
            if r['teams']:
                rankings.append({'kind': 'xc', 'gender': gender, 'event_header': r['title'],
                                 'event_idx': len(events) - 1, 'teams': r['teams']})
        date = None
        dm = re.search(r'RESULTS[\s\S]{0,200}?(\d{2})/(\d{2})/(\d{4})', text)
        if dm:
            date = f'{dm.group(3)}-{dm.group(1)}-{dm.group(2)}'
        title = next((l.strip() for l in lines if l.strip()
                      and not re.fullmatch(r'(?:OFFICIAL\s+)?RESULTS', l.strip())), None)
        # venue (XC course identity): "LOC: UM at Augusta Course", or the
        # left cell of the line carrying the race id ("Readfield, ME   MAR-MS-2")
        venue = None
        for l in lines[:15]:
            m = re.match(r'^\s*LOC:\s*(\S.*?)\s*$', l)
            if m:
                venue = m.group(1)
                break
            m = re.match(r'^\s*(\S.*?)\s{3,}(?:RACE ID:\s*)?[A-Z0-9][A-Z0-9-]*\d-\d\s*$', l)
            if m and not re.search(r'RESULTS|RACE\b', m.group(1)):
                venue = m.group(1)
                break
        out = {'events': events, 'date': date, 'meet_name': title, 'venue': venue,
               'team_rankings': rankings}
        # junior-high / middle-school meets ("BRUNSWICK JUNIOR HIGH XC")
        if _MS_TITLE.search(title or '') or any(_MS_TITLE.search(r['title'] or '')
                                                for r in races):
            out['meet_level'] = 'ms'
        return out


# XCRun's team pages posted without the overall list ("BOYS SCORES" files):
# the "Place TEAM Points SCORES" table, then each team's runners under a
# "TEAM   Places: 105" header, two teams side by side:
#
#       BOOTHBAY                  Places: 105                             MONMOUTH                      Places: 109
# 1     ROBERT CAMPBELL      11      0:19:06        6:09        5         BEN BAILEY              11       0:19:27     6:16
# 17    BAYLY                 9      0:21:29         6:55        10        DIEGO VILLAMARIN      12       0:20:12     6:31
#       GAUGHAN-CARRASCO                                         18        ROBERT SHELLEY        11       0:21:29     6:56
#
# Every finisher is listed under his team with his overall place, so the
# race is the union of the team lists in place order (a long name wraps onto
# the next line in its own column).
_TEAM_HDR = re.compile(r'(?P<team>[A-Za-z][^:]*?)\s+Places:\s*(?P<pl>\d+)')
_TEAM_ROW = re.compile(
    r'(?<!\S)(?P<place>\d{1,4})\s+(?P<name>[A-Za-z][^\d:]*?)\s+(?:(?P<grade>\d{1,2})\s+)?'
    r'(?P<time>\d{1,2}:\d{2}:\d{2}(?:\.\d+)?|:\d{1,2}:\d{2}(?:\.\d+)?)'
    r'(?:\s+(?P<pace>\d{1,2}:\d{2}))?(?!\S)')


class XCRunTeamPagesParser(BaseParser):
    @staticmethod
    def matches(text):
        return bool(text and _SCORES_HDR.search(text) and re.search(r'Places:\s*\d', text)
                    and not _SIG.search(text))

    def parse(self, text, meet_url, season_type):
        empty = {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}
        if not self.matches(text):
            return empty
        lines = text.splitlines()
        races = []
        mode = None
        for i, line in enumerate(lines):
            if _SCORES_HDR.search(line):
                gender = title = None
                for near in reversed(lines[max(0, i - 3):i]):
                    m = _GENDER_WORD.search(near)
                    if m:
                        gender, title = _GMAP.get(m.group(1).lower()), near.strip()
                        break
                races.append({'gender': gender, 'title': title, 'teams': [], 'rows': [],
                              'cols': [], 'team_at': {}, 'last': {}})
                mode = 'scores'
                continue
            if not races:
                continue
            race = races[-1]
            hdrs = list(_TEAM_HDR.finditer(line))
            taken, seen = [], set()
            if hdrs:
                mode = 'teams'
                for h in hdrs:
                    col = h.start('team')
                    if not any(abs(col - c) <= 4 for c in race['cols']):
                        race['cols'].append(col)
                        race['cols'].sort()
                    b = self._block(race['cols'], col)
                    race['team_at'][b] = h.group('team').strip()
                    race['last'][b] = ('team', col)
                    taken.append((h.start(), h.end()))
                    seen.add(b)
                # (the next team's first runner may share the header's line)
                line = ''.join(' ' if any(a <= k < z for a, z in taken) else ch
                               for k, ch in enumerate(line))
            if mode == 'scores':
                m = _SCORE_ROW.match(line)
                if m and re.search(r'[A-Za-z]', m.group('team')):
                    race['teams'].append({
                        'rank': int(m.group('rank')), 'team': m.group('team').strip(),
                        'score': float(m.group('score')),
                        'places': [int(x) for x in m.group('places').split()]})
                continue
            if mode != 'teams':
                continue
            for m in _TEAM_ROW.finditer(line):
                b = self._block(race['cols'], m.start())
                team = race['team_at'].get(b)
                if not team:
                    continue
                row = {'athlete': m.group('name').strip(), 'school': team,
                       'result': _clean_time(m.group('time')), 'grade': m.group('grade') or '',
                       'type': 'Finals', 'place': int(m.group('place'))}
                if m.group('pace'):
                    pace = int(m.group('pace')[:-3]) * 60 + int(m.group('pace')[-2:])
                    if 180 <= pace <= 900:
                        race.setdefault('miles', []).append(_secs(row['result']) / pace)
                race['rows'].append(row)
                race['last'][b] = ('row', m.start('name'), row)
                seen.add(b)
                taken.append((m.start(), m.end()))
            # a name (or a team name) wrapped onto the next line, in its column
            for s in re.finditer(r'\S(?:\S| (?=\S))*', line):
                if any(a <= s.start() < z for a, z in taken) or re.search(r'\d', s.group()):
                    continue
                b = self._block(race['cols'], s.start())
                last = race['last'].get(b)
                if b in seen or not last:
                    continue
                if last[0] == 'row' and abs(s.start() - last[1]) <= 3:
                    last[2]['athlete'] += ' ' + s.group()
                elif last[0] == 'team' and abs(s.start() - last[1]) <= 3:
                    t = race['team_at'][b]
                    race['team_at'][b] = t + s.group() if re.search(r'[-/]', t) else t + '/' + s.group()
                race['last'][b] = ('done',)
                seen.add(b)
            for b in range(len(race['cols'])):
                if b not in seen and race['last'].get(b, ('',))[0] == 'row':
                    race['last'][b] = ('done',)     # (a wrap only on the very next line)
        fname = (meet_url or '').lower()
        file_gender = ('Girls' if re.search(r'girl|women', fname)
                       else 'Boys' if re.search(r'boy|\bmen', fname) else None)
        from backend.parser import normalize_grade
        events, rankings = [], []
        for r in races:
            if len(r['rows']) < 3:
                continue
            rows = sorted(r['rows'], key=lambda x: x['place'])
            for x in rows:
                x['athlete'] = proper_case_name(x['athlete'])
                x['school'] = proper_case_team(x['school'])
            nums = [int(x['grade']) for x in rows if str(x['grade']).isdigit()]
            is_age = any(13 <= n <= 25 for n in nums)
            for x in rows:
                x['grade'] = '' if is_age else normalize_grade(x['grade'])
            if len(r.get('miles', [])) >= 3:
                ms = sorted(r['miles'])
                event = _distance_label(ms[len(ms) // 2])
            else:
                event = 'Run CC'
            gender = r['gender'] or file_gender or 'Boys'
            events.append({'event': event, 'gender': gender, 'is_relay': False, 'results': rows})
            if r['teams']:
                rankings.append({'kind': 'xc', 'gender': gender, 'event_header': r['title'],
                                 'event_idx': len(events) - 1, 'teams': r['teams']})
        date = None
        dm = re.search(r'(?m)^\s*(\d{2})/(\d{2})/(\d{4})\b', text)
        if dm:
            date = f'{dm.group(3)}-{dm.group(1)}-{dm.group(2)}'
        title = next((l.strip() for l in lines if l.strip()), None)
        out = {'events': events, 'date': date, 'meet_name': title, 'team_rankings': rankings}
        if _MS_TITLE.search(title or ''):
            out['meet_level'] = 'ms'
        return out

    @staticmethod
    def _block(cols, col):
        """The side-by-side column a cell starting at `col` sits in: a team's
        places print a few columns left of its header."""
        b = 0
        for k, c in enumerate(cols):
            if col >= c - 12:
                b = k
        return b
