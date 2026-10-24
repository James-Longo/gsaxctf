"""Plain place tables under a one-line column header, with no Hy-Tek event
header to hang them on - the commonest hand-made XC result sheet on sub5
(Mt. Blue Relays, Yarmouth, Gorham, Second Seven, Freeport score sheets...):

    Mt. Blue Relays Boy's Results ~ 2011
    Place Name                             School         Time
        1 Chase Brown                      Boothbay       11:00

    Place   LName           FName       Time    School
     1      Bell            Payton      13:10   Edward Little

    Place Score Name              School Time    Place Score Name    School Time
        1     1 Eastman,Silas     Frye     16:36    46       Simmons,Matt  Fal  21:46

The header names the columns and their order; rows are read cell by cell
(cells are separated by 2+ spaces, the time and the place are typed), so
columns may drift from page to page. A header repeated across the line is
a second column of the same list. The race's gender comes from the title
lines above the header (Boy's / GIRLS RESULTS), else the file name; its
distance from the title ("Course length approximately 2.95 miles").
"""
import re
from .base import BaseParser, proper_case_name, proper_case_team

_PLACE_H = r'(?:place|plc|pl|pos|position|overall|count|ovrallplc)'   # ("ovrallplc  lname  fname  ltime": a timer's field names)
_HEADER = re.compile(r'\b' + _PLACE_H + r'\b', re.I)
_TIME = re.compile(r'^(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d+)?$|^\d{1,2}:\d{2};\d{2}$')
_GENDER = re.compile(r"\b(girl'?s?|boy'?s?|women'?s?|men'?s?|female|male)\b", re.I)
_DIST = re.compile(r'(?<![\d,.\-])(\d+(?:\.\d+)?) ?(k\b|km\b|kilometers?|miles?|mi\b)(?!\s*sports)', re.I)

# header word -> field
_FIELDS = [
    (re.compile(r'^' + _PLACE_H + r'\.?$', re.I), 'place'),
    (re.compile(r'^(score|pts|points|team\s*pl(ace)?|tmpl|tm|tp)\.?$', re.I), 'team_place'),
    (re.compile(r'^scores$', re.I), 'skip'),
    (re.compile(r'^(lname|last(\s*name)?)$', re.I), 'last'),
    (re.compile(r'^(fname|first(\s*name)?)$', re.I), 'first'),
    (re.compile(r'^(name|athlete|runner)$', re.I), 'name'),
    (re.compile(r'^(school|team|club|affiliation|team\s+name|school\s+name)$', re.I), 'school'),
    (re.compile(r'^(time|mark|finish|result|final|ltime)s?$', re.I), 'time'),
    (re.compile(r'^(yr|gr|grade|year|cl)\.?$', re.I), 'grade'),
    (re.compile(r'^(bib#?|no|#)\.?$', re.I), 'bib'),
    (re.compile(r'^order$', re.I), 'skip'),
    (re.compile(r'^(sex|b/g|m/f|gender)\.?$', re.I), 'sex'),
    (re.compile(r'^(pace|avg|gap|behind|age|div|adj|s#|seed|race)\.?$', re.I), 'skip'),
]


# a header word; "First Name" / "Last Name" / "Team Place" are one word
_WORD = r"(?:(?:first|last|team|tm|school) ?(?:name|place|pl)\b|[BbMm]/[GgFf]\b|[A-Za-z#]+)\.?"   # (one space: "School   Name" is two columns)


def _cut_scores(seg):
    """Drop a "TEAM SCORES" table title printed to the right of the header
    - unless "Team" is this table's school column ("Name  Team  Scores")."""
    cut = re.search(r'(?:\b(?:boys|girls|men|women)\s+)?team\s+scores?', seg, re.I)
    if cut and re.search(r'\b(school|club|affiliation|team)\b', seg[:cut.start()], re.I):
        return seg[:cut.start()]
    return seg


def _table_text(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    for tr in soup.find_all('tr'):
        cells = [re.sub(r'\s+', ' ', td.get_text(' ')).replace('\xa0', ' ').strip()
                 for td in tr.find_all(['td', 'th'])]
        line = ''.join(c[:28].ljust(30) for c in cells).rstrip()
        tr.replace_with('\n' + line + '\n')
    return soup.get_text('\n')


def _secs(t):
    v = 0.0
    for x in t.split(':'):
        v = v * 60 + float(x)
    return v


def _field(word):
    for pat, f in _FIELDS:
        if pat.match(word):
            return f
    return None


def _header_fields(seg):
    """['place', 'name', 'school', 'time'] for a header segment, or None."""
    seg = _cut_scores(seg)
    seg = re.sub(r'(?i)\b(boys|girls)\s+(?=first|last)', '', seg)     # "BOYS FIRST  BOYS LAST"
    words = re.findall(_WORD, seg, re.I)
    fields = []
    for w in words:
        f = _field(w.strip())
        if f == 'bib' and fields and fields[-1] == 'bib':
            continue            # "Bib #"
        if f is None:
            rest = seg[seg.find(w.strip()):] if w.strip() in seg else ''
            if 'place' in fields and 'time' in fields and ('name' in fields or 'last' in fields) and (
                    re.search(r'\s{8,}' + re.escape(w.strip()), seg) and
                    not any(_field(x.strip()) in ('school', 'name', 'time', 'place')
                            for x in re.findall(_WORD, rest, re.I)) or
                    # ("TIME      MA 31 (only 1 full team)": a team score)
                    re.search(r'\s{4,}' + re.escape(w.strip()) + r'\s+\d', seg)):
                break           # (a side table's cells set apart on the header row)
            return None
        if f == 'school' and 'school' in fields and re.match(r'(?i)team$', w.strip()):
            f = 'team_place'        # ("place time name school team": the team column holds points)
        fields.append(f)
    if 'place' not in fields or 'time' not in fields or not (
            'name' in fields or 'last' in fields):
        return None
    return fields


def _norm_header(line):
    """("First NameLast Name ... Split": glued header words - the glue
    takes the place of the space - and a sheet's only time column called
    Split.)"""
    line = re.sub(r'(?i)(?<=name)(?=last\b)', ' ', line)
    # ("Boys   Time   Name   Team": the race's gender heads its place column)
    line = re.sub(r'(?i)^(\s*)(boys|girls)(?=\s+time\s+name\b)', lambda m: m.group(1) + 'Pl'.ljust(len(m.group(2))), line)
    # ("Finish Order  BIB#  Name  School  Wave  Finish Time  Points": the
    # place and the time each in two words, kept in their columns)
    line = re.sub(r'(?i)\bfinish order\b', 'Place       ', line)
    line = re.sub(r'(?i)\bfinish time\b', 'Time       ', line)
    line = re.sub(r'(?i)\bwave\b', 'Pace', line)

    if re.search(r'(?i)\bsplit\s*$', line) and not re.search(r'(?i)\b(time|mark|finish|result|final)s?\b', line):
        line = re.sub(r'(?i)\bsplit(\s*)$', r'Time \1', line)
    return line


def _header_positions(seg):
    """Start column of each header word in the segment (same order as
    _header_fields)."""
    seg = _norm_header(_cut_scores(seg))
    return [m.start() for m in re.finditer(_WORD, seg, re.I)]


class HeaderTableParser(BaseParser):
    @staticmethod
    def _headers(line):
        """Header segments on a line: [(start, fields)] (two for a list
        printed in two columns)."""
        line = _norm_header(line)
        # "FINISH  ATHLETE  SCHOOL  TIME": with a time column beside it,
        # the finish column is the place
        if not _HEADER.search(line) and re.search(r'\btime\b', line, re.I):
            line = re.sub(r'\bfinish\b', 'PLACE ', line, count=1, flags=re.I)
        # "      First Name Last Name   School   TIME" / "Name  School  Time"
        # over numbered rows: the unlabelled first column is the place
        if not _HEADER.search(re.sub(r'^\s*Pl\b', '', line)) and re.search(r'\btime\b', line, re.I) and \
                re.search(r'\bname\b', line, re.I) and not re.search(r'\d', line):
            lead = len(line) - len(line.lstrip())
            if re.match(r'\s*Pl\b', line):
                # ("Girls  Time  Name  Team  |  Time  Name  Team": the second
                # list's place cell is the blank one before its Time)
                fn = re.search(r'\bname\b', line, re.I)
                mt2 = re.search(r'\btime\b', line[fn.end():], re.I) if fn else None
                if mt2:
                    t2 = fn.end() + mt2.start()
                    p0 = t2 - 30
                    if p0 > fn.end() and not line[p0:t2].strip():
                        line = line[:p0] + 'PLACE' + line[p0 + 5:]
            elif lead >= 6:
                line = 'PLACE' + line[5:]
            elif re.match(r'\s*name\b', line, re.I):
                line = re.sub(r'^\s*', lambda m: m.group() + 'PLACE ', line, count=1)
            # (a second list beside the first: "Time      Name  School  Time")
            for m in list(re.finditer(r'(?<=\s{8})(?:first\s+)?name\b', line, re.I))[::-1]:
                if re.search(r'\btime\b', line[:m.start()], re.I) and not re.match(r'\s*Pl\b', line):
                    line = line[:m.start() - 7] + 'PLACE  ' + line[m.start():]

        starts = [m.start() for m in _HEADER.finditer(line)
                  if not re.search(r'(?i)\b(team|tm) $', line[:m.start()])]   # ("Team Place", one space)
        if not starts:
            return []
        out = []
        for k, a in enumerate(starts):
            b = starts[k + 1] if k + 1 < len(starts) else len(line)
            f = _header_fields(line[a:b])
            if f is None:
                # a second column cut off by the PDF column splitter
                return out
            out.append((a, f))
        return out

    def parse(self, text, meet_url, season_type):
        empty = {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}
        if season_type != 'XC':
            return empty
        table_mode = False
        if '<' in text[:2000]:
            if re.search(r'<tr\b', text, re.I) and not re.search(r'<pre\b', text, re.I):
                # an HTML table: one line per row, each cell in a fixed-width
                # slot so a header's columns line up with its rows'
                text = _table_text(text)
                table_mode = True
            else:
                text = re.sub(r'<[^>]+>', ' ', text).replace('&nbsp;', ' ').replace('&amp;', '&')
        # (a hand-typed sheet's tabs: columns sit at the tab stops - "Kari
        # Harris<tab>Lee Academy" under "NAME<tab><tab>SCHOOL" - so the
        # header's offsets only hold with the tabs expanded)
        if not table_mode and '\t' in text:
            text = '\n'.join(l.expandtabs(8) if '<' not in l else l for l in text.split('\n'))
        lines = self._unwrap([l.rstrip() for l in text.replace('\xa0', ' ').splitlines()])
        url_low = (meet_url or '').lower()
        file_g = ('Girls' if re.search(r'girl|women|_g\b|g\.(pdf|htm)', url_low)
                  else 'Boys' if re.search(r'boy|\bmen|_b\b|b\.(pdf|htm)', url_low) else None)
        races = []
        titles = []
        skip_team = False
        cur = None      # {'gender', 'titles', 'rows': {place: row}, 'segs'}
        for li, line in enumerate(lines):
            s = line.strip()
            if not s:
                continue
            hs = self._headers(line)
            mgh = re.match(r'(?i)^\s*(boys|girls)\s+time\s+name\b', line)
            if hs and mgh:
                titles.append(mgh.group(1))     # ("Girls  Time  Name  Team": its race)
            if hs and titles and re.match(r'^Team:\s*\S', titles[-1]):
                # a per-team summary table ("Team: Freeport" / Place Score
                # Name Time): the runners again, ranked within the team
                cur, titles = None, []
                skip_team = True
                continue
            if hs:
                skip_team = False
                g = self._title_gender(titles) or (cur['gender'] if cur else None) or file_g
                pos = [_header_positions(line[a:(hs[k + 1][0] if k + 1 < len(hs) else len(line))])
                       for k, (a, _f) in enumerate(hs)]
                if cur is None or (g and cur['gender'] and g != cur['gender']):
                    cur = {'gender': g, 'titles': list(titles), 'rows': {}, 'segs': hs, 'pos': pos}
                    races.append(cur)
                else:
                    cur['segs'], cur['pos'] = hs, pos
                    cur['reheaded'] = True
                    cur['next_gender'] = self._title_gender(titles) or file_g
                    cur['next_titles'] = list(titles)
                    cur['titles'] = cur['titles'] + [t for t in titles if t not in cur['titles']]
                    if g and not cur['gender']:
                        cur['gender'] = g
                # a team-score table printed beside the list ("SCHOOL   TEAM
                # SCORES"): the rows end where its column starts
                mcut = re.search(r'(?i)\bteam\s+scores?\b', line)
                if mcut and not re.search(r'(?i)\b(school|club|affiliation|team)\b', line[:mcut.start()]):
                    mcut = None     # "Name  Team  Scores": Team is the school column
                cur['cut'] = mcut.start() if mcut and mcut.start() > hs[-1][0] else None
                titles = []
                continue
            if skip_team and re.match(r'^\d{1,4}[.)]?\s', s):
                continue
            if cur is not None and (re.match(r'^\d{1,4}[.)]?\s', s) or len(cur['segs']) > 1 and any(
                    re.match(r'^\s*\d{1,4}[.)]?\s', line[max(0, a - 3):]) for a, _f in cur['segs'][1:])):
                got = False
                segs = cur['segs']
                for k, (a, fields) in enumerate(segs):
                    lo = max(0, a - 3)
                    hi = segs[k + 1][0] - 3 if k + 1 < len(segs) else len(line)
                    if k + 1 == len(segs) and cur.get('cut') and cur['cut'] < hi and line[cur['cut'] - 1:cur['cut']] == ' ' \
                            and re.match(r'\s*[A-Za-z].*\s\d{1,4}(?:\.\d+)?\s*$', line[cur['cut']:]):
                        hi = cur['cut']
                    st = [x + a - lo for x in cur['pos'][k]]
                    row = self._row(line[lo:hi], fields) or \
                        self._row_fixed(line[lo:hi], fields, st) or \
                        self._row_by_position(line[lo:hi], fields, st)
                    if row and k == 0 and row['place'] == 1 and cur['rows'] and cur.get('reheaded'):
                        # the list starts over under a repeated header: the
                        # next race (the other gender's page)
                        cur = {'gender': cur.get('next_gender'), 'titles': cur.get('next_titles') or [],
                               'rows': {}, 'segs': cur['segs'], 'pos': cur['pos']}
                        races.append(cur)
                    if row:
                        cur['reheaded'] = False
                    side = cur.get('side', {}).get(k)
                    if row and k > 0 and (side or row['place'] in cur['rows'] and row['place'] == 1):
                        # a second list beside the first that starts at 1:
                        # its own race ("Girls Results      Boys Results")
                        if side is None:
                            g2 = None
                            for t in lines[max(0, li - 8):li][::-1]:
                                for gm in _GENDER.finditer(t):
                                    if gm.start() >= a - 8:
                                        w = gm.group(1).lower()
                                        g2 = 'Girls' if w.startswith(('girl', 'women', 'female')) else 'Boys'
                                        break
                                if g2:
                                    break
                            side = {'gender': g2, 'titles': [], 'rows': {}, 'segs': cur['segs'],
                                    'pos': cur['pos']}
                            races.append(side)
                            cur.setdefault('side', {})[k] = side
                        side['rows'].setdefault(row['place'], row)
                        got = True
                        continue
                    if row and row['place'] in cur['rows'] and k == 0 and \
                            cur['rows'][row['place']].get('athlete') != row.get('athlete') and \
                            cur['rows'][row['place']].get('result') == row.get('result'):
                        # a judged tie ("13 Prashaw 17:38" / "13 Ross 17:38")
                        key = row['place'] + 0.01
                        while key in cur['rows']:
                            key += 0.01
                        cur['rows'][key] = row
                        got = True
                    elif row and row['place'] in cur['rows'] and k == 0 and row['place'] + 1 not in cur['rows'] and \
                            cur['rows'][row['place']].get('athlete') != row.get('athlete') and \
                            (_secs(row.get('result')) or 0) > (_secs(cur['rows'][row['place']].get('result')) or 1e9):
                        # the same place typed twice ("8 Jon Perry 9:19" / "8 Liam Alexander 9:21"): the slower is next
                        row['place'] += 1
                        cur['rows'][row['place']] = row
                        got = True
                    elif row and row['place'] not in cur['rows']:
                        cur['rows'][row['place']] = row
                        got = True
                if got:
                    continue
                # finishers listed past the last time with no time ("42
                # ANDREW RUSSELL   MATTANAWCOOK"): they still took places
                ur = self._untimed(line, cur)
                if ur:
                    cur['rows'][ur['place']] = ur
                    continue
            # a non-finisher printed under the list, the status in the place
            # column ("DNF      Isabella Cote     Skowhegan"): a row, no title
            md = re.match(r'^(DNF|DNS|DQ)\s{2,}(\S.*?)\s{2,}(\S.*)$', s) if cur is not None else None
            if md and not re.search(r'\d', md.group(2)):
                nm = md.group(2)
                cur.setdefault('dnf', []).append(
                    {'athlete': proper_case_name(nm) if nm.isupper() else nm,
                     'school': proper_case_team(md.group(3)) if md.group(3).isupper() else md.group(3),
                     'result': md.group(1), 'grade': '', 'type': 'Finals', 'place': None})
                continue
            if len(s) < 160:
                titles.append(s)
                # a gender title between lists starts a new race
                tg = self._title_gender([s])
                if cur is not None and tg and cur['gender'] and tg != cur['gender'] \
                        and not re.search(r'\d:\d\d', s):
                    cur = dict(cur, gender=tg, titles=[s], rows={})
                    races.append(cur)
        from backend.parser import normalize_grade
        # a roster listed by bib or name ("Count  Last Name ...") beside the
        # finish lists is no race: its times run in no order
        def unsorted(r):
            ts = [_secs(x['result']) for _p, x in sorted(r['rows'].items()) if x.get('result')]
            # (a hand-timed list a few seconds out of order is still a
            # list: "20:35, 20:56, 20:28" - spliced columns jump by minutes)
            return len(ts) >= 5 and sum(1 for a, b in zip(ts, ts[1:]) if b < a - 1) > 0.2 * len(ts) and \
                sum(1 for a, b in zip(ts, ts[1:]) if b < a - 60) > 0.05 * len(ts)
        if any(not unsorted(r) for r in races if len(r['rows']) >= 5):
            races = [r for r in races if not unsorted(r)]
        # a list repeated by team ("YHS: 1 Becker 20:11, 3 Teare ...") is
        # the same runners again, not a race
        seen, kept = set(), []
        for r in races:
            pairs = {(x.get('athlete'), x.get('result')) for x in r['rows'].values()}
            if pairs and len(pairs & seen) >= 0.8 * len(pairs):
                continue
            seen |= pairs
            kept.append(r)
        races = kept
        # a list that starts over with nothing naming its gender: the
        # other gender's race (two lists, boys and girls)
        prev_g = None
        for r in races:
            if r['gender'] is None and r['rows'] and prev_g:
                r['gender'] = 'Girls' if prev_g == 'Boys' else 'Boys'
            prev_g = r['gender'] or (file_g or 'Boys') if r['rows'] else prev_g
        # a "B/G" column: the row's sex is its race's gender
        split = []
        for r in races:
            sexes = {x.get('sex') for x in r['rows'].values()} - {None}
            if len(sexes) > 1:
                for g in sorted(sexes):
                    split.append(dict(r, gender=g, rows={p: x for p, x in r['rows'].items()
                                                         if x.get('sex') == g}))
            else:
                if sexes:
                    r['gender'] = sexes.pop()
                split.append(r)
        races = split
        events = []
        for r in races:
            if len(r['rows']) < 3:
                continue
            rows = [r['rows'][p] for p in sorted(r['rows'])] + list(r.get('dnf', []))
            for x in rows:
                x.pop('sex', None)
            # a name's last word pushed into the school ("Amanda St." |
            # "Jeanos Sanford"): the school the other rows spell is the school
            from collections import Counter
            cnt = Counter(x['school'] for x in rows if x.get('school'))
            known = sorted((sc for sc, n in cnt.items() if n >= 2), key=len, reverse=True)
            # a row cut at the header's school column on a page set further
            # left ("ole Creamer Woolwi" | "ch"): cut where a school the race's
            # other rows spell begins
            for x in [x for _pass in range(2) for x in rows]:
                # (two passes: a row repaired on the first lends its school
                # to the rows above it on the second)
                raw = x.get('_raw')
                if raw is None:
                    continue
                clean = sorted({y['school'] for y in rows if y.get('school') and not y.get('_raw')
                                and re.match(r'[A-Z]', y['school'])} | set(known), key=len, reverse=True)
                sc0 = x.get('school') or ''
                if not (re.match(r'[a-z]', x.get('athlete') or '') or re.match(r'[a-z]', sc0) or
                        # (single-spaced text cut at the header's column:
                        # "Dalayna | Mincey GHCA")
                        sc0 not in clean and any(sc0.endswith(' ' + k) for k in clean)):
                    x.pop('_raw', None)
                    continue
                flat_raw = re.sub(r'\s+', ' ', re.sub(r'([a-z])\d{1,2}([A-Z])', r'\1 \2', raw))
                for k in clean:
                    if re.match(r'[a-z]', k):
                        continue
                    mk = re.search(r'(?<=[a-z ])' + re.escape(k) + r'(?![a-z])', flat_raw)
                    if mk and re.search(r'[A-Za-z]{2}', flat_raw[:mk.start()]):
                        x['athlete'] = re.sub(r'\s+', ' ', flat_raw[:mk.start()]).strip()
                        x['school'] = k
                        x.pop('_raw', None)
                        break
            for x in rows:
                x.pop('_raw', None)
            for x in rows:
                sc = x.get('school') or ''
                # "Chelsea Wocko | murkaMed": a long name ran into a cut-off
                # team ("Med" of Medomak) and the column cut fell inside it
                mg = re.fullmatch(r'([a-z]+)([A-Z][a-z]{2,})', sc)
                if cnt.get(sc, 0) == 1 and mg:
                    kn = next((k for k in known if k.startswith(mg.group(2))), None)
                    if kn:
                        x['athlete'] = x['athlete'] + mg.group(1)
                        x['school'] = kn
                        continue
                if cnt.get(sc, 0) == 1 and len(sc) >= 3:
                    # a school cut short by the column ("Med" for Medomak)
                    pre = [k for k in known if k.startswith(sc) and k != sc]
                    if len(pre) == 1:
                        x['school'] = pre[0]
                        continue
                if cnt.get(sc, 0) == 1:
                    # ("Hunter  Burkhardt  LIS": a name typed with two
                    # spaces; a one-word athlete takes any school a clean
                    # row spells)
                    alls = known + sorted((k for k, n in cnt.items() if n == 1 and ' ' not in k and k != sc
                                           and ' ' not in (x.get('athlete') or ' ')), key=len, reverse=True)
                    for kn in alls:
                        if sc.endswith(' ' + kn) and len(sc) > len(kn) + 1:
                            x['athlete'] = (x['athlete'] + ' ' + sc[:-len(kn)].strip()).strip()
                            x['school'] = kn
                            break
            for row in rows:
                row['grade'] = normalize_grade(row.get('grade', ''))
            dm = None
            for t in r['titles']:
                if re.search(r'\d:\d\d', t):
                    continue        # a row, not a title
                dm = _DIST.search(t)
                if dm:
                    break
            miles = []
            for row in rows:
                pace = row.pop('_pace', None)
                if pace:
                    ps = _secs(pace)
                    if 180 <= ps <= 900:
                        miles.append(_secs(row['result']) / ps)
            if dm:
                unit = dm.group(2).lower()
                event = (f'{dm.group(1)}k Run CC' if unit.startswith('k')
                         else f'{dm.group(1)} Mile Run CC')
            elif len(miles) >= 3:
                from .xcrun import _distance_label
                event = _distance_label(sorted(miles)[len(miles) // 2])
            else:
                event = 'Run CC'
            events.append({'event': event, 'gender': r['gender'] or 'Boys',
                           'is_relay': False, 'results': rows})
        if not events:
            return empty
        # (a single-spaced page cut at the header's columns slices names
        # mid-word: "ea Ro" / "ss GHCA" - not a reading of it)
        flat = [x for e in events for x in e['results']]
        if sum(1 for x in flat if re.match(r'[a-z]', x.get('athlete') or '') or
               re.match(r'[a-z]{1,3} ', x.get('school') or '')) > 0.3 * len(flat):
            return empty
        if table_mode:
            # (a table read row by row must account for its timed rows - a
            # sheet the spreadsheet reader handles is left to it)
            timed = sum(len(re.findall(r'(?<![\d:.])\d{1,2}[:.]\d{2}(?![\d])', l)) for l in lines
                        if re.match(r'^\s*\d{1,4}[.)]?\s', l))
            if sum(len(e["results"]) for e in events) < timed - 1:
                return empty
        title = next((l.strip() for l in lines if l.strip() and not self._headers(l)
                      and not re.match(r'^\s*(?:\d|(?:DNF|DNS|DQ)\s{2,})', l)), None)
        return {'events': events, 'date': None, 'meet_name': title, 'team_rankings': []}

    @staticmethod
    def _untimed(line, cur):
        segs = cur['segs']
        if len(segs) != 1 or len(cur['rows']) < 5 or 'time' not in segs[0][1]:
            return None
        fields = [f for f in segs[0][1][:segs[0][1].index('time')]
                  if f in ('name', 'school', 'last', 'first')]
        cells = [c.strip() for c in re.split(r'\s{2,}', line.strip()) if c.strip()]
        m = re.fullmatch(r'(\d{1,4})[.)]?', cells[0]) if cells else None
        if not m or not 2 <= len(cells) <= len(fields) + 1 or fields[:1] not in (['name'], ['last']):
            return None
        place = int(m.group(1))
        if place != int(max(cur['rows'])) + 1 or any(
                re.search(r'\d|^(DNF|DNS|DQ|NT)$', c, re.I) for c in cells[1:]):
            return None
        if int(max(cur['rows'])) > len(cur['rows']) + 2:
            return None     # (only a list complete to its last timed place)
        vals = dict(zip(fields, cells[1:]))
        if 'last' in vals or 'first' in vals:
            name = ', '.join(x for x in (vals.get('last', ''), vals.get('first', '')) if x)
        else:
            name = vals.get('name', '')
        if not re.search(r'[A-Za-z]{2}', name):
            return None
        return {'place': place, 'type': 'Finals', 'grade': '', 'result': '',
                'athlete': proper_case_name(name) if name.isupper() else name,
                'school': proper_case_team(vals.get('school', ''))}

    @staticmethod
    def _unwrap(lines):
        """A long name wraps the rest of its row to the next line:
              5     Elizabeth Morrissette
                               Waterville Junior High School     13:16.88   5
        lay the continuation over the row (columns keep their x)."""
        out = []
        tm = re.compile(r'\d{1,2}:\d{2}|(?<![\d.])\d{1,2}\.\d{1,2}\s*$')    # (or a sheet's "13.52")
        for l in lines:
            prev = out[-1] if out else ''
            # (the rest of the row may be only grade, sex and time:
            #  "      6      M      15:55.6")
            cont = not re.match(r'^\s*\d', l) or \
                re.fullmatch(r'\s*(?:\d{1,2}\s+)?(?:[MFBGW]\s+)?\d{1,2}:\d{2}(?:\.\d+)?\s*', l)
            if out and l.strip() and cont and tm.search(l) and \
                    re.match(r'^\s*\d{1,4}[.)]?\s+[A-Za-z]', prev) and not tm.search(prev):
                lead = len(l) - len(l.lstrip())
                if lead >= len(prev.rstrip()):
                    out[-1] = prev.rstrip().ljust(lead - 1) + ' ' + l.lstrip()
                else:          # the name ran past the school's column
                    out[-1] = prev.rstrip() + '   ' + l.lstrip()
                continue
            out.append(l)
        return out

    @staticmethod
    def _title_gender(titles):
        for t in reversed(titles):
            m = _GENDER.search(t)
            if m:
                w = m.group(1).lower()
                return 'Girls' if w.startswith(('girl', 'women', 'female')) else 'Boys'
            m = re.search(r'(female|male)\b', t, re.I)   # "DivisionFemale"
            if m:
                return 'Girls' if m.group(1).lower() == 'female' else 'Boys'
        return None

    @classmethod
    def _row_by_position(cls, seg, fields, starts):
        """Cells matched to the header word nearest their start column -
        for rows with an empty cell ("2  Pauline  Nadeau-Miller      Boothbay")."""
        if len(starts) != len(fields):
            return None
        cells = [(m.start(), m.group()) for m in re.finditer(r'\S+(?: \S+)*', seg)]
        if not cells or not re.fullmatch(r'\d{1,4}[.)]?', cells[0][1]):
            return None
        vals = {}
        for x, v in cells[1:]:
            if _TIME.match(v):
                vals.setdefault('time', v)
                continue
            k = min(range(len(fields)), key=lambda i: abs(starts[i] - x))
            f = fields[k]
            if f in ('place', 'time', 'skip', 'bib'):
                continue
            vals[f] = (vals[f] + ' ' + v) if f in vals else v
        if 'time' not in vals:
            return None
        ti = fields.index('time') if 'time' in fields else len(fields)
        order = (['place'] + [f for f in fields[1:ti] if f in vals] + ['time'] +
                 [f for f in fields[ti + 1:] if f in vals and f != 'time'])
        line = '  '.join([cells[0][1].rstrip('.)')] + [vals[f] for f in order[1:]])
        return cls._row(line, order)

    @classmethod
    def _row_fixed(cls, seg, fields, starts):
        """Fixed-width Hy-Tek individual reports run the name into the
        school with one space or none ("Regan Billings Skowhegan Middle
        School", "Miranda SullivanWaterville"): the school starts at its
        header's column."""
        nf = 'name' if 'name' in fields else 'first' if 'first' in fields and 'last' in fields else None
        if not nf or 'school' not in fields or len(starts) != len(fields):
            return None
        if nf == 'first' and fields.index('last') > fields.index('school'):
            return None
        nx, sx = starts[fields.index(nf)], starts[fields.index('school')]
        if not 0 < nx < sx or len(seg) <= sx:
            return None
        m = re.match(r'^\s*(\d{1,4})[.)]?\s', seg)
        t = re.search(r'(?<!\S)(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d+)?(?!\S)', seg[sx:])
        if not m or not t or m.end() > nx + 1:
            return None
        # (a school set a column early: "Billings Skowhegan" with the S one
        # left of the header's column)
        if seg[sx - 1:sx].isalpha() and seg[sx - 2:sx - 1] == ' ':
            sx -= 1
        name = re.sub(r'\s+', ' ', seg[nx:sx]).strip()
        school = re.sub(r'\s+', ' ', seg[sx:]).strip()
        t = re.search(r'(?<!\S)(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d+)?(?!\S)', school)
        if not t:
            return None
        rest = school[t.end():]
        school = school[:t.start()].strip()
        school = re.sub(r'(?:\s+(?:\d{1,2}|[MFBGW]))+$', '', school)    # (grade / sex cells before the time)
        if not re.search(r'[A-Za-z]{2}', name) or not re.search(r'[A-Za-z]{2}', school):
            return None
        line = '  '.join([m.group(1), name, school, t.group()] + rest.split())
        f = ['place', 'name', 'school', 'time'] + [x for x in fields[fields.index('time') + 1:]] \
            if 'time' in fields else None
        row = cls._row(line, f) if f else None
        if row:
            row['_raw'] = seg[m.end():]     # (re-cut later against the race's own schools)
        return row

    @staticmethod
    def _row(seg, fields):
        cells = [c.strip() for c in re.split(r'\s{2,}', seg.strip()) if c.strip()]
        if not cells:
            return None
        m = re.match(r'^(\d{1,4})[.)]?(?:\s+(.*))?$', cells[0])
        if not m:
            return None
        place = int(m.group(1))
        rest = ([m.group(2)] if m.group(2) else []) + cells[1:]
        rest = [c for c in rest if re.search(r'\w', c)]    # a "." placeholder cell
        rest = [re.sub(r'^(\d{1,2}:\d{2}(?:[.:]\d+)?)\s*[*#+]+(?=\s|$)', r'\1', c) for c in rest]   # "15:45*" record
        # a long name run up to its time ("Z. Chase-Donaghue 20:45")
        if not any(_TIME.match(c.split()[0]) or re.fullmatch(r'\d{1,2}\.\d{1,2}', c) for c in rest):
            for i, c in enumerate(rest):
                mt = re.match(r'^(.*[A-Za-z.]\d?)\s((?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d+)?|\d{1,2}\.\d{1,2})$', c)
                if mt:
                    rest[i:i + 1] = [mt.group(1), mt.group(2)]
                    break
        # the time cell anchors the row: "13:10" (or "18:42 Y": time, code)
        tpos = next((i for i, c in enumerate(rest) if _TIME.match(c.split()[0])), None)
        if tpos is None:
            # a spreadsheet's minutes.seconds ("10.02", "11.3" = 11:30,
            # "17.59.47" = 17:59.47)
            t_first = fields.index('time') == 1 if 'time' in fields else False
            tpos = next((i for i, c in enumerate(rest) if (i or t_first) and re.fullmatch(
                r'\d{1,2}\.\d{1,2}(?:\.\d{1,2})?', c.split()[0])), None)
            if tpos is None:
                return None
            tok = rest[tpos].split()[0]
            mm, ss = tok.split('.')[:2]
            hh = tok.split('.')[2] if tok.count('.') == 2 else None
            rest = list(rest)
            rest[tpos] = f'{int(mm)}:{ss.ljust(2, "0")}' + (f'.{hh}' if hh else '') + rest[tpos][len(tok):]
        row = {'place': place, 'type': 'Finals', 'grade': ''}
        f_before = fields[1:fields.index('time')]
        f_after = fields[fields.index('time') + 1:]
        before, after = rest[:tpos], rest[tpos + 1:]
        tcell = rest[tpos].split()
        row['result'] = re.sub(r'^(\d{1,2}:\d{2}):00$', r'\1', tcell[0])   # spreadsheet clock time
        # a timer's clock reading with a zero hour ("00:21:23.00")
        mz = re.fullmatch(r'0{1,2}:(\d{2}):(\d{2}(?:\.\d+)?)', row['result'])
        if mz:
            row['result'] = f'{int(mz.group(1))}:{mz.group(2)}'
        # "19:01:18" / "22:24;95": minutes:seconds:hundredths (no 4+ hour XC race)
        mh = re.fullmatch(r'(\d{1,2}):(\d{2})[:;](\d{2})', row['result'])
        if mh and int(mh.group(1)) >= 4:
            row['result'] = f'{mh.group(1)}:{mh.group(2)}.{mh.group(3)}'
        if len(tcell) > 1:
            after = [' '.join(tcell[1:])] + after
        vals = {}
        # leading integer cells (score / bib) are typed by the header
        b = list(before)
        fb = [f for f in f_before]
        while fb and fb[0] in ('team_place', 'bib') and b and re.fullmatch(r'\d{1,4}', b[0].split()[0]):
            tok = b[0].split()
            if fb[0] == 'team_place':
                vals['team_place'] = int(tok[0])
            b[0] = ' '.join(tok[1:])
            if not b[0]:
                b.pop(0)
            fb.pop(0)
        # a bib / points column inside the cells, every cell present
        # ("Cummings  Calvin  11  Boys  Gorham  105  16:57.0")
        if len(b) == len(fb) and any(f in ('team_place', 'bib') for f in fb):
            keep = [(f, c) for f, c in zip(fb, b)
                    if not (f in ('team_place', 'bib') and re.fullmatch(r'\d{1,5}', c))]
            if len(keep) == len([f for f in fb if f not in ('team_place', 'bib')]):
                fb, b = [f for f, _c in keep], [c for _f, c in keep]
        # (a bib column last before the time, a cell short elsewhere in the
        # row: "Sirois  Andrew  Boys  BE  165  17:32" with no grade)
        fb2 = list(fb)
        while fb2 and fb2[-1] == 'skip':
            fb2.pop()
        if fb2 and fb2[-1] == 'bib' and b and re.fullmatch(r'\d{2,5}', b[-1]) and len(b) < len(fb2):
            b, fb = b[:-1], fb2[:-1]
        fb = [f for f in fb if f not in ('team_place', 'bib')]
        # "11 SP": grade and team in one cell under "YR TEAM"
        if 'grade' in fb and fb.index('grade') + 1 < len(fb) and fb[fb.index('grade') + 1] == 'school':
            for i, c in enumerate(b):
                mg = re.match(r'^(\d{1,2}|FR|SO|JR|SR)\s+([A-Za-z].*)$', c)
                if mg and i == fb.index('grade') and len(b) < len(fb):
                    b[i:i + 1] = [mg.group(1), mg.group(2)]
                    break
        if 'sex' in fb and len(b) == len(fb):
            sx = b[fb.index('sex')]
            if re.fullmatch(r'(?i)boys?|girls?|[MFBGW]', sx):
                row['sex'] = 'Girls' if sx[0].upper() in 'GFW' else 'Boys'
        while len(b) < len(fb) and 'skip' in fb:
            fb.remove('skip') if fb[-1] != 'skip' else fb.pop()   # (a blank unused column)
        if len(b) == len(fb) - 1 and 'grade' in fb and not any(
                re.fullmatch(r'\d{1,2}|FR|SO|JR|SR', c, re.I) for c in b):
            fb = [f for f in fb if f != 'grade']     # an empty grade column
        if len(b) == len(fb) - 1 and fb[:2] == ['last', 'first'] and len(b[0].split()) == 2:
            b = b[0].split() + b[1:]    # ("D'ALESSANDRO MEGAN": one space between the two)
        if len(b) == len(fb):
            vals.update(zip(fb, b))
        elif len(b) == 1 and fb[:2] == ['name', 'school'] and re.fullmatch(r'[A-Za-z.]{1,8}', b[0]) and \
                re.search(r'\d\s{12,}' + re.escape(b[0]) + r'\s', seg):
            # a finisher the sheet left unnamed ("21  20      Yar  15:46"):
            # the place and the team still count
            vals['name'], vals['school'] = '', b[0]
            row['_nameless'] = True
        elif len(b) == 1 and fb[:2] == ['name', 'school'] and \
                re.fullmatch(r'(\S+ \S*[a-z]{3})([A-Z][A-Za-z]{2,}(?: [A-Z][A-Za-z]+)*)', b[0]) and \
                not re.search(r'(?:^|[\s-])(?:Mc|Mac|De|Di|Da|La|Le|Van|Von)$',
                              re.fullmatch(r'(\S+ \S*[a-z]{3})([A-Z][A-Za-z]{2,}(?: [A-Z][A-Za-z]+)*)', b[0]).group(1)):
            # a long name run into its school ("Jackson Lawler-SidellCarrabec")
            mg = re.fullmatch(r'(\S+ \S*[a-z]{3})([A-Z][A-Za-z]{2,}(?: [A-Z][A-Za-z]+)*)', b[0])
            vals['name'], vals['school'] = mg.group(1), mg.group(2)
        elif len(b) == 1 and fb[:2] == ['name', 'school']:
            # one-space columns: the last word is the school code
            w = b[0].split()
            if len(w) < 3:
                return None
            vals['name'], vals['school'] = ' '.join(w[:2]), ' '.join(w[2:])
        elif len(b) > len(fb) and fb and fb[-1] == 'school':
            vals.update(zip(fb[:-1], b[:len(fb) - 1]))
            vals['school'] = ' '.join(b[len(fb) - 1:])
        else:
            return None
        # after the time: typed cells (pace, grade, score) may share a cell
        # with the next or be blank ("5:19 12     Falmouth", "5:34   Wells")
        toks = []
        for c in after:
            if 'team_place' in f_after:
                c = re.sub(r'(?<=[A-Za-z])(\d{1,3})$', r' \1', c)     # ("MOUNTAIN VALLEY0": points run into the team)
            parts = c.split()
            while parts and (re.fullmatch(r'\d{1,2}:\d{2}(?:\.\d+)?|\d{1,3}|FR|SO|JR|SR', parts[0])):
                toks.append(parts.pop(0))
            tail = []
            # ("MOUNTAIN VALLEY 32": the team's points one space after it)
            while 'team_place' in f_after and len(parts) > 1 and re.fullmatch(r'\d{1,3}', parts[-1]):
                tail.insert(0, parts.pop())
            if parts:
                toks.append(' '.join(parts))
            toks += tail
        for f in f_after:
            if not toks:
                break
            t = toks[0]
            if f == 'skip':
                if re.fullmatch(r'\d{1,2}:\d{2}(?:\.\d+)?|\d{1,3}', t):
                    if ':' in t:
                        vals['_pace'] = toks[0]  # per-mile pace: sizes the course
                    toks.pop(0)
            elif f == 'grade':
                if re.fullmatch(r'\d{1,2}|FR|SO|JR|SR', t, re.I):
                    vals['grade'] = toks.pop(0)
            elif f == 'team_place':
                if re.fullmatch(r'\d{1,3}', t):
                    vals['team_place'] = int(toks.pop(0))
            elif f == 'bib':
                if re.fullmatch(r'\d{1,5}', t):
                    toks.pop(0)
            elif f in ('school', 'name', 'last', 'first') and re.search(r'[A-Za-z]', t):
                if vals.get(f):
                    break       # "TEAM SCORES" printed beside the list
                vals[f] = toks.pop(0)
        if 'last' in vals or 'first' in vals:
            name = ', '.join(x for x in (vals.get('last', '').strip(), vals.get('first', '').strip()) if x)
        else:
            name = vals.get('name', '')
        name = re.sub(r',(?=\S)', ', ', name.strip())
        school = (vals.get('school') or '').strip()
        if not re.search(r'[A-Za-z]{2}', name) and not row.pop('_nameless', False):
            return None
        if 'school' in fields and not school and len(re.findall(r'[A-Za-z]+', name)) >= 4:
            return None     # (the school run into the name cell: left to the fixed-width reading)
        if vals.get('team_place'):      # (0: a runner who does not score)
            row['team_place'] = vals['team_place']
        if '_pace' in vals:
            row['_pace'] = vals['_pace']
        g = vals.get('grade', '')
        if g and re.fullmatch(r'\d{1,2}|FR|SO|JR|SR', g, re.I):
            row['grade'] = g.upper()
        # a grade cell run into the school ("Searsport 8",
        # "Lincolnville8Central School": the grade inside a wrapped cell)
        mgs = re.fullmatch(r'(.*[A-Za-z])\s?(\d{1,2})(?:([A-Z][A-Za-z ]+))?', school)
        if mgs and 3 <= int(mgs.group(2)) <= 12 and not row.get('grade'):
            school = mgs.group(1) + (' ' + mgs.group(3).strip() if mgs.group(3) else '')
            row['grade'] = mgs.group(2)
        row['athlete'] = proper_case_name(name) if name.isupper() else name
        row['school'] = proper_case_team(school)
        return row


class PlaceLaterTableParser(BaseParser):
    """Hand-made sheets whose place column is not the first one, which the
    header-table reader (rows start with their place) passes over:

        First       Last       School   Place        Score        Time         Score
        Taylor      Dundas     C                 1            1   17:21   C       31
                             NAME       C       TEAM   TIME IN   PLACE
        Sam Sheehan                             CAR     15:05      1
        Name         Time             Place      Team
        Raymond               20:54           1 BE                BE

    Cells are typed (the time, whole numbers, words) and matched to the
    header's fields of the same type in order, before and after the time;
    what follows the last field (a team-score table beside the list) is
    dropped."""

    _INT = ('place', 'team_place', 'bib')
    _TEXT = ('name', 'first', 'last', 'school')

    @staticmethod
    def _header(line):
        seg = re.sub(r'(?i)\btime\s+in\b', 'Time   ', line)
        words = re.findall(_WORD, seg, re.I)
        fields = []
        for w in words:
            f = _field(w.strip())
            if f is None and re.fullmatch(r'(?i)c', w.strip()):
                f = 'skip'          # (an empty one-letter column: "NAME  C  TEAM")
            if f is None:
                if 'place' in fields and 'time' in fields:
                    break           # (a table set beside the list)
                return None
            if f == 'school' and 'school' in fields:
                f = 'team_place'
            fields.append(f)
        if 'place' not in fields or 'time' not in fields or fields[0] == 'place' or \
                not ('name' in fields or 'last' in fields):
            return None
        return fields

    def parse(self, text, meet_url, season_type):
        empty = {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}
        if season_type != 'XC':
            return empty
        if '<' in text[:2000]:
            if re.search(r'<tr\b', text, re.I) and not re.search(r'<pre\b', text, re.I):
                text = _table_text(text)
            else:
                text = re.sub(r'<[^>]+>', ' ', text).replace('&nbsp;', ' ').replace('&amp;', '&')
        lines = [l.rstrip() for l in text.replace('\xa0', ' ').splitlines()]
        url_low = (meet_url or '').lower()
        file_g = ('Girls' if re.search(r'girl|women|_g\b|g\.(pdf|htm)', url_low)
                  else 'Boys' if re.search(r'boy|\bmen|_b\b|b\.(pdf|htm)', url_low) else None)
        races, titles, cur = [], [], None
        for line in lines:
            if not line.strip():
                continue
            fields = self._header(line)
            if fields:
                cur = {'fields': fields, 'rows': {}, 'titles': list(titles),
                       'gender': HeaderTableParser._title_gender(titles) or file_g}
                races.append(cur)
                titles = []
                continue
            row = self._row(line, cur['fields']) if cur else None
            if row:
                if row['place'] not in cur['rows']:
                    cur['rows'][row['place']] = row
                continue
            if len(line.strip()) < 160:
                titles.append(line.strip())
        events = []
        for r in races:
            if len(r['rows']) < 5:
                continue
            rows = [r['rows'][p] for p in sorted(r['rows'])]
            ts = [_secs(x['result']) for x in rows]
            if sum(1 for a, b in zip(ts, ts[1:]) if b < a - 1) > 0.2 * len(ts):
                continue        # (not a finish list)
            dm = next((m for m in (_DIST.search(t) for t in r['titles']) if m), None)
            if dm:
                unit = dm.group(2).lower()
                event = f'{dm.group(1)}k Run CC' if unit.startswith('k') else f'{dm.group(1)} Mile Run CC'
            else:
                event = 'Run CC'
            events.append({'event': event, 'gender': r['gender'] or 'Boys', 'is_relay': False,
                           'results': rows})
        if not events:
            return empty
        title = next((l.strip() for l in lines if l.strip()), None)
        return {'events': events, 'date': None, 'meet_name': title, 'team_rankings': []}

    @classmethod
    def _row(cls, line, fields):
        cells = []
        for c in re.split(r'\s{2,}', line.strip()):
            mt = re.match(r'^(\S+) (\S.*)$', c)
            # ("16:11 Cheverus": a team-score table set one space from the time)
            cells += [mt.group(1), mt.group(2)] if mt and _TIME.match(mt.group(1)) else [c] if c else []
        ti = next((i for i, c in enumerate(cells) if _TIME.match(c)), None)
        if ti is None or ti == 0 and fields[0] != 'time':
            return None
        k = fields.index('time')
        result = re.sub(r'^(\d{1,2}:\d{2}):00$', r'\1', cells[ti])
        mh = re.fullmatch(r'(\d{1,2}):(\d{2})[:;](\d{2})', result)
        if mh and int(mh.group(1)) >= 4:
            result = f'{mh.group(1)}:{mh.group(2)}.{mh.group(3)}'     # (minutes:seconds:hundredths)

        def typed(cs):
            ints, words = [], []
            for c in cs:
                for tok in re.findall(r'\d+(?![\w:.])|[^\d\s](?:[^\s]| (?=\D))*', c):
                    (ints if tok.isdigit() else words).append(tok.strip())
            return ints, [w for w in words if re.search(r'[A-Za-z]', w)]

        vals = {}
        for before, fs, cs in ((True, fields[:k], cells[:ti]), (False, fields[k + 1:], cells[ti + 1:])):
            ints, words = typed(cs)
            # (after the time only the place: a score there is a team-score
            # table's, printed beside the list)
            ifs = [f for f in fs if f in cls._INT and (before or f == 'place')]
            tfs = [f for f in fs if f in cls._TEXT]
            for f, v in zip(ifs, ints):
                vals.setdefault(f, int(v))
            if not tfs:
                continue
            if len(words) > len(tfs) and tfs[-1] == 'school' and before:
                words = words[:len(tfs) - 1] + [' '.join(words[len(tfs) - 1:])]
            elif len(words) < len(tfs) and tfs[-1] == 'school' and len(words) >= 2:
                vals.setdefault('school', words[-1])
                words, tfs = words[:-1], tfs[:-1]
            for f, v in zip(tfs, words):
                vals.setdefault(f, v)
        if not vals.get('place'):
            return None
        if 'last' in vals or 'first' in vals:
            name = ', '.join(x for x in (vals.get('last', ''), vals.get('first', '')) if x)
        else:
            name = vals.get('name', '')
        if not re.search(r'[A-Za-z]{2}', name):
            return None
        row = {'place': vals['place'], 'type': 'Finals', 'grade': '', 'result': result,
               'athlete': proper_case_name(name) if name.isupper() else name,
               'school': proper_case_team(vals.get('school', ''))}
        if vals.get('team_place'):
            row['team_place'] = vals['team_place']
        return row
