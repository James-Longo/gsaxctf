"""Official cross-country team scores from Hy-Tek result files.

Hy-Tek prints a "Team Scores" block after each XC race:

                                   Team Scores
    =================================================================================
    Rank Team                      Total    1    2    3    4    5   *6   *7   *8   *9
    =================================================================================
       1 Lake Region High School      21    1    2    3    6    9   13   19
          Total Time:  2:00:55.88
             Average:    24:11.18

(newer exports drop the ruler/header rows and star the qualifying teams:
"   *1 Portland High School         75   10   12   16   18   19   29   43").

The places list is each team's finishers' TEAM places (individual places
re-numbered over scoring teams only), so the block can be re-derived from
the race's finish order alone. QAQC does exactly that: it is the gold
standard check that a race was parsed completely and in order.

parse_xc_team_scores() is parser-agnostic: it reads the raw file text, so it
works whichever parser in the chain won the result rows.
"""
import re

_GENDER = {'girls': 'Girls', 'women': 'Girls', 'female': 'Girls', 'woman': 'Girls',
           'boys': 'Boys', 'men': 'Boys', 'male': 'Boys', 'man': 'Boys'}

_SCORES_HDR = re.compile(
    r'^(?:(girls|boys|women|men|female|male)\b[^A-Za-z]*)?(?:[\w&/\-\'’ ]{0,50}\s)?team\s+(?:scores?|results)\s*:?\s*(?:\*\s*[A-Za-z ]{0,40})?$', re.I)
_EVENT_HDR = re.compile(
    r'^\s*(?:Event\s+\d+\s+)?(Girls|Boys|Women|Men|Mixed)\b\s*(.*)$', re.I)
_RESULTS_GENDER = re.compile(r'^\s*Results\s*-\s*(Women|Men|Girls|Boys)\b\s*(.*)$', re.I)
# per-class sections inside one race's block: "CLASS A Results"
# ("Division 2,3, JC Results 5000 Run": a label of several words, then the race)
_SECTION = re.compile(r'^(Class|Division|Section)\s+(\w{1,4}(?:\s*,\s*\w{1,4})*)\s+Results'
                      r'(?:\s*-\s*(Women|Men|Girls|Boys))?(?:\s+\d+\s*\w*\s*Run)?$', re.I)
# rank, team, total, then the team places (up to 9 scorers)
_ROW = re.compile(r'^\s*\*?\s*(\d{1,3})\s+(\S.*?)\s+(\d{1,4})((?:\s+\d{1,4}){0,12})\s*$')


def _html_to_text(text):
    if '<' in text[:3000] and '</' in text.lower():
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, 'html.parser')
            # an HTML table: one line per row, cells apart (else every cell
            # lands on its own line and "Lisbon | 32" is lost)
            flat = 0
            for tr in soup.find_all('tr'):
                cells = [re.sub(r'\s+', ' ', td.get_text(' ')).strip() for td in tr.find_all(['td', 'th'])]
                if len([c for c in cells if c]) >= 2:
                    tr.replace_with('\n' + '   '.join(c for c in cells if c) + '\n')
                    flat += 1
            if flat >= 3 and not soup.find('pre'):
                return soup.get_text('\n')
            if 'schemas-microsoft-com:office' in text[:5000]:
                # Word export: one Hy-Tek line per <p> (see Sub5ColumnParser)
                ps = [re.sub(r'[ \t\r\n]+', ' ', p.get_text()).replace('\xa0', ' ') for p in soup.find_all('p')]
                if sum(1 for x in ps if x.strip()) >= 5:
                    # (a rank in a paragraph of its own: "1" / "Orono High School 46 ...")
                    out = []
                    for x in ps:
                        if out and re.fullmatch(r'\s*\d{1,3}\s*', out[-1]) and re.match(r'\s*[A-Za-z]', x):
                            out[-1] = out[-1].rstrip() + ' ' + x.strip()
                        else:
                            out.append(x)
                    return '\n'.join(out)
            pres = soup.find_all('pre')
            whole = soup.get_text('\n')
            if pres:
                inside = '\n'.join(p.get_text() for p in pres)
                # (a <pre> holding only the page header, the list after it
                # in <p>/<font> lines: the whole page)
                if len(inside.strip()) >= 0.5 * len(whole.strip()) and not (
                        re.search(r'(?i)team\W{0,3}scores?', whole) and not re.search(r'(?i)team\W{0,3}scores?', inside)):
                    return inside
                return whole.replace('\xa0', ' ')
            return whole
        except Exception:
            return re.sub(r'<[^>]+>', '', text)
    return text


def _is_event_header(line):
    s = line.strip()
    if re.match(r'^Event\s+\d+\s+', s, re.I):
        return True
    m = _EVENT_HDR.match(s)
    if m and len(s) < 70 and re.search(
            r'\b(\d+(\.\d+)?\s*(k|km|mile|miles|meter|m)\b|run|cc|xc|cross|varsity|jv|race)',
            m.group(2), re.I) and 'team scores' not in s.lower():
        return True
    return False


# RunScore ("*********** BOYS TEAM SCORE **********"):
#   1. Falmouth
#           3    4    5    6    9  (13) (16) =    27
#        Sean Soucy, Ben Wyman, ...
_RS_HDR = re.compile(r'^\*{3,}\s*(.*?)\s*TEAM\s+SCORES?\s*\*{3,}$', re.I)   # ("WOMEN'S TEAM SCORE")
_RS_TEAM = re.compile(r'^\s*(\d{1,3})\.\s+(\S.*?)\s*$')
_RS_PLACES = re.compile(r'^\s*((?:\(?\d{1,4}\)?(?:\s+|(?<=\))(?=\()))*\(?\d{1,4}\)?)\s*=\s*(\d{1,4})\s*$')
_RS_ONELINE = re.compile(r'^\s*(\d{1,3})\.\s+(\S.*?)\s+((?:\(?\d{1,4}\)?(?:\s+|(?<=\))(?=\()))*\(?\d{1,4}\)?)\s*=\s*(\d{1,4})\s*$')


def parse_runscore_team_scores(text):
    """RunScore team-score sections; each header opens a block whose label
    ("BOYS", "JV GIRLS", "VARSITY") gives gender and division."""
    lines = _html_to_text(text).replace('\xa0', ' ').splitlines()
    # two score tables side by side ("*** BOYS ... ***     *** GIRLS ... ***"):
    # the right-hand table is read after the left one
    hdr2 = re.compile(r"\*{3}\s*[A-Za-z' ]{0,30}TEAM\s+SCORES?\s*\*{3}", re.I)
    for i, l in enumerate(lines):
        ms = list(hdr2.finditer(l))
        if len(ms) == 2:
            cut = ms[1].start()
            while cut > 0 and l[cut - 1] == '*':
                cut -= 1        # (the whole run of stars opens the right table)
            j = i
            while j < len(lines) and j - i < 80 and not (j > i and hdr2.search(lines[j])):
                j += 1
            left, right = [], []
            for x in lines[i:j]:
                # (a row of the right table: "...= 18      1. Cheverus ...")
                mx = list(re.finditer(r'\s{3,}(?=\d{1,3}\.\s+[A-Za-z])', x))
                c = mx[-1].start() if mx and mx[-1].start() > 15 else cut
                left.append(x[:c].rstrip())
                right.append(x[c:])
            lines = lines[:i] + left + right + lines[j:]
            break
    blocks, cur, pend = [], None, None
    for line in lines:
        s = line.strip()
        mh = _RS_HDR.match(s)
        if mh:
            label = mh.group(1).strip()
            if cur is not None and cur['teams'] and cur.get('label') == label and not label:
                continue
            gw = re.search(r'\b(girls|boys|women|men)\b', label, re.I)
            cur = {'kind': 'xc', 'gender': _GENDER.get(gw.group(1).lower()) if gw else None,
                   'event_header': s, 'teams': [], 'label': label}
            div = re.sub(r'\b(girls|boys|women|men)\b', '', label, flags=re.I).strip()
            if div:
                cur['division'] = div.title() if div.isupper() else div
            blocks.append(cur)
            pend = None
            continue
        if cur is None or not s:
            continue
        m1 = _RS_ONELINE.match(line)
        if m1:
            rank, team, pl, tot = m1.groups()
        else:
            mt = _RS_TEAM.match(line)
            if mt and not re.search(r'\d\s*$', mt.group(2)):
                pend = (mt.group(1), mt.group(2))
                continue
            mp = _RS_PLACES.match(line)
            if not (mp and pend):
                continue
            rank, team = pend
            pl, tot = mp.groups()
            pend = None
        places = [int(x) for x in re.findall(r'\d+', pl)]
        cur['teams'].append({'rank': int(rank), 'team': team.strip(), 'score': float(tot),
                             'places': places})
    out = []
    for b in blocks:
        b.pop('label', None)
        t = b['teams']
        good = sum(1 for x in t if len(x['places']) >= 5 and sum(x['places'][:5]) == x['score'])
        if t and (good >= max(1, 0.6 * len(t)) or len(t) == 2 and good == 1):
            out.append(b)
    return out


_SIDE_ROW = re.compile(r"\s{3,}(\d{1,2})\s+([A-Za-z][\w/ .'&-]*?)\s+((?:\(?\d{1,3}\)?,\s*)+\(?\d{1,3}\)?)\s+(\d{1,3})\s*$")


def _side_score_rows(lines):
    """A score table printed to the right of the runner rows ("...  GHCA  -
    Team Scores" / "...  Boys" / "...  1  PIMS  2, 4, 5, 8, 9, (10, 11)  28",
    "36 ...   Girls Team Scores" / "...  1st - South Portland 1-3-4-5-6
    (7 & 9)  19"): its rows, as lines of their own after the page."""
    extra = []
    hdr = re.compile(r'(?:\S|^[ \t]{27})[ \t]{3,}((?:[A-Za-z’\']+[ \t]+){0,2}team[ \t]+scor(?:es?|ing))[ \t]*$', re.I)
    used = set()
    start = re.compile(r'[A-Za-z]|\d{1,2}(?:st|nd|rd|th)?[ \t]*[-–.)]|\d{1,2}[ \t]{2,}[A-Za-z]')
    done = -1
    for i, l in enumerate(lines):
        mh = hdr.search(l)
        if not mh or i <= done:
            continue
        col = mh.start(1)

        def gender_of(txt, g0):
            gw = re.search(r'(?i)\b(boys|girls|men|women)\b', txt)
            return _GENDER[gw.group(1).lower()] if gw else g0
        g = gender_of(mh.group(1), None)
        out, head = [], f'{g or ""} Team Scores'.strip()
        blank = 0
        span = [i]
        left_rows = 0
        for j, r in enumerate(lines[i + 1:i + 60], i + 1):
            if j - i > 16 and sum(1 for x in lines[i + 1:j] if x.strip()) > 15:
                break
            done = j
            span.append(j)
            m2 = hdr.search(r)
            gaps = [m for m in re.finditer(r'(?:^|[ \t]{3,})', r)
                    if col - 35 <= m.end() <= col + 5 and start.match(r[m.end():])]
            if gaps:
                # (the start nearest the title from the left; a rank just
                # before it opens the row: "1      PIMS  2, 4, ...")
                g0 = gaps[-1]
                rk = [m for m in gaps if m.end() >= g0.end() - 20 and
                      re.match(r'\d{1,2}(?:st|nd|rd|th)?[ \t]*[-–.)]|\d{1,2}[ \t]{2,}[A-Za-z]', r[m.end():])]
                gaps = [rk[0] if rk else g0]
            tail = r[gaps[0].end():].strip() if gaps else ''
            mg = re.fullmatch(r'(?i)(boys|girls|men|women)', tail)
            if m2 or mg:
                # (a new table title: "Boys Team Scoring", a bare "Girls")
                g = gender_of(m2.group(1) if m2 else tail, None if m2 else g)
                head = f'{g or ""} Team Scores'.strip()
                blank = 0
                continue
            if not r.strip():
                continue
            if not tail:
                blank += 1
                if blank >= (2 if out else 4):
                    break
                continue
            blank = 0
            if head:
                out += ['', head]
                head = None
            out.append(tail)
            if re.search(r'\d{1,2}[:;.]\d{2}', r[:gaps[0].end()]):
                left_rows += 1          # (a runner row on its left)
        if len(out) >= 3 and (l[:col].strip() or left_rows):
            extra += out
            used |= set(span)
    return extra, used


def _team_lists(lines):
    """Per-team runner lists beside the finish list ("Team Score" /
    "Bangor (18)" / "Name  Points" / "Jonathon Stanhope  2" ... /
    "Total  26"): one block per heading, each team with its places."""
    blocks = []
    hdr = re.compile(r'(?i)team\s+scores?\s*$')
    i = 0
    while i < len(lines):
        mh = hdr.search(lines[i])
        if not mh or mh.start() < 25:
            i += 1
            continue
        x = mh.start() - 15
        teams, cur = [], None
        j = i + 1
        while j < len(lines) and j - i < 90:
            r = lines[j]
            if hdr.search(r) and hdr.search(r).start() >= 25:
                break
            m = re.search(r'(?<![A-Za-z])[A-Za-z]', r[x:]) if len(r) > x else None
            seg = r[x + m.start():].strip() if m else ''
            seg = re.sub(r'(?i)^points?\s{2,}(?=[A-Za-z])', '', seg)     # (the list's own Points header)
            j += 1
            if not seg or re.match(r'(?i)name\s+points?$', seg):
                continue
            mt = re.match(r'(?i)total\s+(\d{1,3}|n/?s)\s*$', seg)
            mr = re.match(r"^([A-Za-z][A-Za-z .'\-]*?[A-Za-z.])\s{2,}(\d{1,3}|-+)\s*$", seg)
            mn = re.match(r"^([A-Za-z][A-Za-z .'/&\-]*?[A-Za-z.])\s*(?:\((\d{1,3}|N/?S)\))?\s*$", seg)
            if mt:
                if cur is not None:
                    cur['total'] = mt.group(1)
                    teams.append(cur)
                cur = None
            elif mr and cur is not None:
                if mr.group(2).isdigit():
                    cur['places'].append(int(mr.group(2)))
            elif mn and (cur is None or not cur['places']):
                cur = {'team': mn.group(1), 'places': [], 'total': mn.group(2)}
        good = []
        for t in teams:
            if t['total'] and t['total'].isdigit() and len(t['places']) >= 5:
                good.append({'rank': None, 'team': t['team'], 'score': float(t['total']),
                             'places': sorted(t['places'])})
        if len(good) >= 2 and sum(1 for t in good if sum(t['places'][:5]) == t['score']) >= 0.6 * len(good):
            good.sort(key=lambda t: t['score'])
            for k, t in enumerate(good):
                t['rank'] = k + 1
            blocks.append({'kind': 'xc', 'gender': None, 'event_header': lines[i].strip()[-80:], 'teams': good})
        i = j
    return blocks


def _indented_team_lists(lines):
    """"Team Scores   Scores" over "  Cony   35" and its scorers indented
    under it ("    Casey Gallant   2"), and by-team runner listings closed
    by "TEAM SCORE -> 35" under each team's scorers."""
    teams = []
    row = re.compile(r"^(\s*)([A-Za-z][A-Za-z .'/&\-]*?[A-Za-z.])\s{3,}(\d{1,3})\s*$")
    for i, l in enumerate(lines):
        if not re.match(r'(?i)\s*team\s+scores?\s{3,}scores?\s*$', l):
            continue
        cur = None
        for r in lines[i + 1:i + 80]:
            m = row.match(r)
            if not m:
                if r.strip() and not re.match(r'(?i)\s*(?:boys|girls)?\s*team\s+scores?', r):
                    break
                continue
            ind = len(m.group(1))
            if cur is None or ind <= cur['ind']:
                cur = {'ind': ind, 'team': m.group(2), 'score': float(m.group(3)), 'places': []}
                teams.append(cur)
            else:
                cur['places'].append(int(m.group(3)))
        break
    arrow = re.compile(r'(?i)^\s*team\s+score\s*-+>\s*(\d{1,3})\s*$')
    rrow = re.compile(r'^\s*\d{1,3}\s+\d{1,4}\s+\S.*?\s{2,}([A-Za-z][\w.\-]*)\s+\d{1,2}\s+[\d:.]+\s+(\d{1,3})\s*$')
    for i, l in enumerate(lines):
        ma = arrow.match(l)
        if not ma:
            continue
        got = []
        for r in lines[max(0, i - 8):i][::-1]:
            mr = rrow.match(r)
            if not mr:
                if r.strip():
                    break
                continue
            got.append((mr.group(1), int(mr.group(2))))
        schools = {g for g, _p in got[:5]}
        if len(got) >= 5 and len(schools) == 1:
            teams.append({'team': got[0][0], 'score': float(ma.group(1)),
                          'places': sorted(p for _g, p in got[:5])})
    teams = [dict(t, rank=None) for t in teams if len(t['places']) >= 5]
    for t in teams:
        t.pop('ind', None)
        t['places'] = sorted(t['places'])
    if len(teams) < 2 or sum(1 for t in teams if sum(t['places'][:5]) == t['score']) < 0.6 * len(teams):
        return []
    teams.sort(key=lambda t: t['score'])
    for k, t in enumerate(teams):
        t['rank'] = k + 1
    return [{'kind': 'xc', 'gender': None, 'event_header': 'Team Scores', 'teams': teams}]


def _html_scores_grid(text):
    """An HTML sheet with a SCORES column beside the runners: a team's name
    in one row, its places and total in the next ("Bonny Eag le" / "1 7 14
    24 25 71 4")."""
    if not re.search(r'(?i)<table', text or ''):
        return []
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, 'html.parser')
    except Exception:
        return []
    blocks = []
    for table in soup.find_all('table'):
        rows = [[td.get_text(' ', strip=True) for td in tr.find_all(['td', 'th'])] for tr in table.find_all('tr')]
        for hi, h in enumerate(rows):
            c = next((k for k, v in enumerate(h) if re.fullmatch(r'(?i)(?:team\s+)?scores?', v)), None)
            if c is None:
                continue
            gw = re.search(r'(?i)\b(boys|girls|men|women)\b', ' '.join(h[:c]))
            g = _GENDER[gw.group(1).lower()] if gw else None
            teams, pend = [], None
            for r in rows[hi + 1:hi + 60]:
                tail = [v for v in r[c:] if v]
                if len(tail) == 1 and re.search(r'[A-Za-z]{2}', tail[0]) and not re.search(r'\d', tail[0]):
                    pend = re.sub(r'\s+', ' ', tail[0])
                    continue
                if pend and len(tail) >= 6 and all(re.fullmatch(r'\d{1,3}', v) for v in tail):
                    nums = [int(v) for v in tail]
                    k = next((k for k in range(5, len(nums)) if nums[k] == sum(nums[:5])), None)
                    if k is not None:
                        teams.append({'rank': None, 'team': pend, 'score': float(nums[k]), 'places': nums[:k]})
                    pend = None
            if len(teams) >= 2:
                teams.sort(key=lambda t: t['score'])
                for k, t in enumerate(teams):
                    t['rank'] = k + 1
                blocks.append({'kind': 'xc', 'gender': g, 'event_header': 'SCORES', 'teams': teams})
            break
    return blocks


def parse_xc_team_scores(text):
    """Return a list of team-score blocks:
        [{'kind': 'xc', 'gender': 'Girls'|'Boys'|None, 'event_header': str|None,
          'teams': [{'rank', 'team', 'score', 'places': [int, ...]}, ...]}]
    Only blocks that carry per-team places (the XC signature) are kept."""
    if not text or not (re.search(r'team(?:<[^>]{0,200}>|&nbsp;|[^\w<&]){0,400}scores?', text, re.I) or
                        _TEAM_RESULTS.search(text) or _INLINE_SCORES.search(text)):
        return []
    if re.search(r"\*{3}\s*[A-Za-z' ]{0,30}TEAM\s+SCORES?\s*\*{3}", text, re.I):
        rs = parse_runscore_team_scores(text)
        if rs:
            return rs
        # ("******* Team Scores *******" over "1. Bonny Eagle 35 4-5-6-7-13-[17-20]")
        text = re.sub(r'(?im)^[ \t]*\*{3,}[ \t]*((?:[A-Za-z]+[ \t]+){0,3}TEAM[ \t]+SCORES?)[ \t]*\*{3,}[ \t]*$', r'\1', text)
    lines = _split_side_tables(re.sub(r'(?i)\bteam[ \t]*\n[ \t]*(scores?)[ \t]*$', r'Team \1',
                                      _html_to_text(text).replace('\xa0', ' '), flags=re.M).splitlines())
    # (a rank on a line of its own, its team's row on the next: "   1 " /
    # "Mount Desert Island HS   23   2   3 ...")
    for k in range(len(lines) - 1):
        if re.fullmatch(r'\s*\d{1,3}\s*', lines[k]):
            j = k + 1
            while j < len(lines) and j - k <= 2 and not lines[j].strip():
                j += 1
            if j < len(lines) and re.match(r"\s*[A-Za-z][A-Za-z .'&/()-]*\s{2,}\d{1,3}(?:\s+\d{1,3}){4,}\s*$", lines[j]):
                lines[j] = lines[k].rstrip() + ' ' + lines[j].strip()
                lines[k] = ''
    orig_lines = list(lines)
    side, used = _side_score_rows(lines)
    if side:
        # (the side table's lines are read from its own column only)
        lines = [l if k not in used else re.sub(r'[ \t]{3,}.*$', '', l) if not _SCORES_HDR.match(l.strip()) else ''
                 for k, l in enumerate(lines)] + side
    blocks = []
    cur = None
    rs_pend = None
    pending_split = False
    last_event, last_gender = None, None
    for li, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        mh = _SCORES_HDR.match(s)
        if mh:
            # "Varsity Boys Three Mile Run Team Scores": gender anywhere
            gw = re.search(r'\b(girls|boys|women|men)\b', s, re.I)
            g = _GENDER.get((mh.group(1) or (gw.group(1) if gw else '')).lower()) or last_gender
            # a page break can repeat the header inside one block
            if cur is not None and cur['event_header'] == last_event and not cur['teams']:
                continue
            if cur is not None and cur['event_header'] == last_event and cur['teams'] \
                    and g == cur['gender']:
                continue
            cur = {'kind': 'xc', 'gender': g, 'event_header': last_event, 'teams': []}
            blocks.append(cur)
            continue
        mg = _RESULTS_GENDER.match(s)
        if mg:
            last_gender = _GENDER[mg.group(1).lower()]
            label = mg.group(2).strip()
            if re.search(r'(?i)\d|\b(?:run|mile|miles|meters?|km)\b', label):
                label = ''          # ("Results - Women 2.6Mile Mile Run": the race, no division)
            if cur is not None and label:
                # "Results - Men Large School" / "... Small School": one
                # block per division inside one Team Scores section
                if cur['teams']:
                    cur = {'kind': 'xc', 'gender': last_gender,
                           'event_header': cur['event_header'], 'teams': []}
                    blocks.append(cur)
                cur['gender'] = last_gender
                cur['division'] = label
                continue
            if cur is not None and not cur['teams']:
                # "Team Scores / ==== / Rank Team ... / Results - Women":
                # the block's own gender line, its rows follow
                cur['gender'] = last_gender
                continue
            if cur is not None and cur['teams'] and cur['gender'] and last_gender != cur['gender']:
                # one Team Scores section ranking a Mixed race's men, then
                # its women ("Results - Men" rows ... "Results - Women")
                cur = {'kind': 'xc', 'gender': last_gender,
                       'event_header': cur['event_header'], 'teams': []}
                blocks.append(cur)
                continue
            last_event = s
            cur = None
            continue
        if _is_event_header(s):
            m = _EVENT_HDR.match(re.sub(r'^Event\s+\d+\s+', '', s, flags=re.I))
            if m:
                last_gender = _GENDER.get(m.group(1).lower(), last_gender)
            last_event = s
            cur = None
            continue
        # a bare "Results" line between two teams lists opens the next
        # race's block (Word exports lose the second "Team Scores" title)
        # (a page header "Results" inside one list continues it: split only
        # when the list restarts at rank 1)
        if s == 'Results' and cur is not None and cur['teams']:
            pending_split = True
            continue
        msec = _SECTION.match(s)
        if msec:
            label = f"{msec.group(1).capitalize()} {msec.group(2)}"
            if cur is not None:
                if cur['teams']:
                    cur = {'kind': 'xc', 'gender': cur['gender'],
                           'event_header': cur['event_header'], 'teams': []}
                    blocks.append(cur)
                cur['section'] = label
                cur['division'] = label
                if msec.group(3):
                    cur['gender'] = _GENDER[msec.group(3).lower()]
            continue
        if cur is None:
            continue
        # RunScore's two-line rows without its starred title: "1. YORK" /
        # "2  4  5  6  9 (11) (12) =  26"
        mrt = _RS_TEAM.match(line)
        if mrt and not re.search(r'\d\s*$', mrt.group(2)) and not re.search(r'\d', mrt.group(2)):
            rs_pend = (int(mrt.group(1)), mrt.group(2).strip())
            continue
        mrp = _RS_PLACES.match(line)
        if mrp and rs_pend:
            places = [int(x) for x in re.findall(r'\d+', mrp.group(1))]
            cur['teams'].append({'rank': rs_pend[0], 'team': rs_pend[1], 'score': float(mrp.group(2)),
                                 'places': places})
            rs_pend = None
            continue
        # "1.   Bonny Eagle   35   4-5-6-7-13-[17-20]" / "1st - South Portland
        # 1 2 3 4 5 [6 7]  15" / "1   Lincolnville   26   1-4-6-7-8"
        line = re.sub(r'^(\s*\*?\s*\d{1,3})(?:\.|st|nd|rd|th)?(?:\s*[-–—]\s+|\.?(?=\s))', r'\1 ', line, count=1)
        line = re.sub(r'(?<=\d)\s*=\s*(\d{1,3})\s*$', r'  \1', line)       # "1-3-4-5-7=20"
        if re.search(r'\d-\[?\d|\[\d', line):
            line = re.sub(r'(?<=\d)-(?=\[?\d)|-?\[|\]', ' ', line)
            line = re.sub(r'\((\d{1,3})(?:\s*&\s*(\d{1,3}))?\)', r' \1 \2 ', line)   # "(7 & 9)"
        # "1   GHCA. 29   3, 4, 5, 6, 11, (13), (15)": comma places, displacers in ()
        if re.search(r'\d,\s*\(?\d', line):
            line = re.sub(r'\(((?:\d{1,4},\s*)*\d{1,4})\)', r'\1', line).replace(',', ' ')
            line = re.sub(r'(?<=[A-Za-z])\.(?=\s+\d)', '', line)
        m = _ROW.match(line)
        if not m:
            continue
        team = m.group(2).strip()
        if re.match(r'^(total|average|rank)\b', team, re.I) or ':' in team:
            continue
        if not pending_split and int(m.group(1)) == 1 and cur['teams'] and \
                (cur['teams'][-1].get('rank') or 0) >= 2:
            # a second table under the first with no title of its own: its
            # ranks start over ("1. Bonny Eagle 35 ..." below "5. Windham 103")
            pending_split = True
        if pending_split:
            pending_split = False
            if int(m.group(1)) == 1 and cur['teams']:
                cur = {'kind': 'xc', 'gender': cur['gender'],
                       'event_header': cur['event_header'], 'teams': []}
                blocks.append(cur)
        nums = [int(m.group(3))] + [int(x) for x in m.group(4).split()]
        # a team name can end in digits ("Brunswick CC 2010"): the total is
        # the number that equals the sum of the five places after it
        k = next((i for i in range(len(nums) - 5)
                  if nums[i] == sum(nums[i + 1:i + 6])), 0)
        if k:
            team = f"{team} {' '.join(str(n) for n in nums[:k])}"
        places = nums[k + 1:]
        if not k and len(nums) >= 6 and nums[0] != sum(nums[1:6]) and abs(nums[-1] - sum(nums[:5])) <= 10 and \
                (nums[-1] > nums[-2] or nums[-1] == sum(nums[:5])) and all(b > a for a, b in zip(nums[:-1], nums[1:-1])):
            # places first, the total last: "1  PIMS  2, 4, 5, 8, 9, (10, 11)  28"
            places, k = nums[:-1], len(nums) - 1
        elif not k and len(nums) >= 5 and nums[0] != sum(nums[1:6]) and \
                all(b > a for a, b in zip(nums, nums[1:])):
            # the total wrapped onto the next line ("1 – Gorham 1-4-5-8-10-[13-16]"
            # / "   st      28"): places only on this one
            nx = next((x for x in lines[li + 1:li + 3] if x.strip()), '')
            mt = re.match(r'^\s*(?:st|nd|rd|th)?\s*(\d{1,3})\s*$', nx)
            if mt and int(mt.group(1)) == sum(nums[:5]):
                nums = nums + [int(mt.group(1))]
                places, k = nums[:-1], len(nums) - 1
        entry = {'rank': int(m.group(1)), 'team': team, 'score': float(nums[k])}
        # a fixed-width export cuts the last column ("... 33 34 3" for 35):
        # a final place shorter than, and below, the one before is cut off
        if len(places) > 5 and places[-1] < places[-2] and \
                len(str(places[-1])) < len(str(places[-2])):
            places = places[:-1]
            entry['truncated'] = True
        # (an export glitch repeats the first places in the *8 *9 columns:
        # "45  4 5 8 12 16 20 22  4 5")
        for k in range(5, 8):
            if len(places) > k and len(places) - k <= 4 and places[k:] == places[:len(places) - k]:
                places = places[:k]
                break
        entry['places'] = places
        cur['teams'].append(entry)
    out = []
    for b in blocks:
        teams = b['teams']
        if not teams:
            continue
        # XC signature: most teams list >= 5 scoring places that add up
        good = sum(1 for t in teams if len(t['places']) >= 5
                   and sum(t['places'][:5]) == t['score'])
        # (two teams, one hand-totalled wrong: "Caribou 45  2 3 6 11 12 13")
        if good >= max(1, len(teams) * 0.6) or len(teams) == 2 and good == 1:
            out.append(b)
    if not out:
        out = _html_scores_grid(text)
    if not out:
        out = _team_lists(orig_lines)
    if not out:
        out = _indented_team_lists(orig_lines)
    if not out:
        out = parse_team_totals(text)
    return out


# -- team totals ------------------------------------------------------------
# Hand-made sheets print only each team's total, in many shapes:
#     Team Scores                        1st Scarborough   34      Orono 32
#     1   Yarmouth   26                  LEE ACADEMY - 39        Lisbon 32*
#     "18:12 Morse 36" beside the runners    "Team scores- Matt 17 , Schenck 38"
#     "Scarborough 1-3-4-5-7-[8-10]  20"  (places too: a full block)
#     "Team Score: 20 / Team Name: FALMOUTH" (one section per team)
_TOT_HDR = re.compile(r'(?i)\b(?:(girls?|boys?|women|men)\W*)?(?:[\w&/-]+\s+){0,3}?team\s*(?:scores?|score)\b')
# "Boys Scores: Messalonskee 21, Cony 35" (a line of its own)
_INLINE_SCORES = re.compile(r'(?im)^[ \t]*(?:(?:boys|girls|men|women)[ \t]+)?scores?[ \t]*:[ \t]*(?=[A-Za-z][^\n]*\d)')
# "Girls Varsity Team Results" over "Washington Academy - 21" lines
_TEAM_RESULTS = re.compile(r'(?im)^[ \t]*(?:(?:girls?|boys?|women|men)[ \t]+)?(?:varsity[ \t]+|jv[ \t]+)?'
                           r'(?:(?:girls?|boys?)[ \t]+)?team[ \t]+results[ \t]*$')
_TIME_TOK = re.compile(r'\d{1,2}[:;.’]\d{1,2}(?:[.:;]\d{1,2})?h?')   # ("19.3": a sheet's 19:30)
_NAME = r"[A-Za-z][A-Za-z .'&/()-]{0,40}?[A-Za-z.)]"   # (bounded: no runaway backtracking)
_TOT_LINE = re.compile(r'^\s*(?:\(?(\d{1,2})(?:st|nd|rd|th)?(?:\.\)\s*|[.),:]\s*|\s+))?(' + _NAME + r')(?:\s*[-:=–—]\s*|\s+)(\d{1,3}|NS|ns|Ns|inc|INC)\*?(?:\s{2,}\d(?:st|nd|rd|th)\s*[-:]?\s*\d{1,3}|\s+(?:finished|won|lost|wins|on|by)\b[a-z0-9 ,.]*)?\s*$')
_NAME1 = r"[A-Za-z][A-Za-z.'&/()-]*(?: [A-Za-z.'&/()-]+){0,5}"   # single-spaced words
_TOT_TAIL = re.compile(r'(?<!\S)(?:' + _TIME_TOK.pattern + r'|[1-5]\d[0-5]\d(?=\s{2,}))(?:.*\s{2,}|\s+(?:\S{1,3}\s+){0,2}?)(' + _NAME1 +
                       r')\s+(\d{1,3}|NS|ns|Ns)\*?\s*$')
_RANK_SCORE_TEAM = re.compile(r'^\s*(\d{1,2})\s+(\d{1,3})\s+(' + _NAME + r')\s*$')
_DASH_LIST = re.compile(r'(' + _NAME + r')\s+(\d{1,3})\s*[-–—:]?\s*((?:\d{1,3},\s*){4,}\d{1,3}),?(?:\s*/\s*((?:\d{1,3},\s*)*\d{1,3}))?\s*$')
_PLUS = re.compile(r'(' + _NAME + r')\s*-\s*(\d{1,3})\s+((?:\d{1,3}\+){4,}\d{1,3})\s*$')
# "Holbrook   5  6  7  8  9  13  20   35": a team's places, then its total
_PLACE_SPACE = re.compile(r'^\s*(' + _NAME + r')\s+((?:\d{1,3}\s+){4,8})(\d{1,3})\s*$')
_PLACE_DASH = re.compile(r'(' + _NAME + r')\s+((?:\d{1,3}-){4}\d{1,3}(?:-\[\d{1,3}(?:-\d{1,3})*\])?)\s+(\d{1,3})\s*$')


def _team_entry(rank, team, score):
    team = re.sub(r'\s+', ' ', team).strip(' -:')
    if not re.search(r'[A-Za-z]{2}', team) or re.match(r'(?i)^(place|team|score|total|name|school|time|pace)s?$', team):
        return None
    if re.match(r'(?i)^(ns|inc)$', score):
        return {'rank': None, 'team': team, 'score': None, 'places': []}
    return {'rank': int(rank) if rank else None, 'team': team, 'score': float(score), 'places': []}


def _team_name_sections(lines):
    """'Team Score: 29' / 'Team Name: FREEPORT' (either order) per team."""
    teams = []
    for i, l in enumerate(lines):
        ms = re.match(r'^\s*Team\s+Score:\s*(\d{1,3})\s*$', l, re.I)
        if not ms:
            continue
        name = None
        for j in (i - 1, i + 1, i - 2, i + 2):
            if 0 <= j < len(lines):
                mn = re.match(r'^\s*Team\s+Name:\s*(\S.*?)\s*$', lines[j], re.I)
                if mn:
                    name = mn.group(1)
                    break
        if name:
            teams.append({'rank': None, 'team': name, 'score': float(ms.group(1)), 'places': []})
    return teams


_ORD_PLACE = re.compile(r'\b(FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH)\s+PLACE:', re.I)


def _place_sections(lines):
    """'FIRST PLACE: / Camden Hills / Jamie Conkling  3 / ... / Total: 45',
    two teams side by side: each team's runners with their places."""
    teams = []
    i = 0
    while i < len(lines):
        heads = [(m.start(), m.group(1)) for m in _ORD_PLACE.finditer(lines[i])]
        if not heads:
            i += 1
            continue
        xs = [x for x, _w in heads]

        def col(x):
            return min(range(len(xs)), key=lambda k: abs(xs[k] - x) if x >= xs[k] - 4 else 10 ** 6)
        cur = [{'team': None, 'places': [], 'score': None} for _x in xs]
        j = i + 1
        while j < len(lines) and not _ORD_PLACE.search(lines[j]):
            cells = []
            for m in re.finditer(r'(\S+(?: \S+)*)', lines[j]):
                k = col(m.start())
                # ("Jamie Conkling     3": the place cell joins its name)
                if cells and cells[-1][1] == k and re.fullmatch(r'\d{1,3}', m.group(1)) and \
                        not re.search(r'\d$', cells[-1][0]):
                    cells[-1] = (cells[-1][0] + ' ' + m.group(1), k)
                else:
                    cells.append((m.group(1), k))
            for cell, k in cells:
                mt = re.match(r'(?i)total:\s*(\d{1,3})$', cell)
                mr = re.match(r"^([A-Za-z][A-Za-z .'-]+?)\s+(\d{1,3})$", cell)
                if mt:
                    cur[k]['score'] = float(mt.group(1))
                elif cur[k]['team'] is None and re.fullmatch(r"[A-Za-z][A-Za-z .'&-]+:?", cell):
                    cur[k]['team'] = cell.rstrip(':')
                elif mr and cur[k]['team']:
                    cur[k]['places'].append(int(mr.group(2)))
            j += 1
        for t in cur:
            if t['team'] and t['score'] is not None and len(t['places']) >= 5:
                teams.append(dict(t, rank=None))
        i = j
    # (a total that is not its five places' sum is the sheet's own slip;
    # most must add up)
    if sum(1 for t in teams if sum(sorted(t['places'])[:5]) == t['score']) < max(2, 0.6 * len(teams)):
        return []
    return teams


def _gender_columns(lines):
    """'place school  girls team score  boys team score  combined team
    score': one totals block per gender column."""
    for i, l in enumerate(lines):
        mg = re.search(r'(?i)\bgirls\b[^\n]*?\bscore', l)
        mb = re.search(r'(?i)\bboys\b[^\n]*?\bscore', l)
        if not (mg and mb):
            continue
        cols = {'Girls': mg.start(), 'Boys': mb.start()}
        mc = re.search(r'(?i)\bcombined\b', l)
        if mc:
            cols['Combined'] = mc.start()
        out = {'Girls': [], 'Boys': []}
        for r in lines[i + 1:i + 60]:
            mr = re.match(r'^\s*(\d{1,2})\s+([A-Za-z][A-Za-z .\'&-]*?[A-Za-z.])(?=\s{2,}|\s*$)', r)
            if not mr:
                if r.strip() and not re.match(r'^\s*$', r):
                    continue
                continue
            for m in re.finditer(r'(?<!\S)\d{1,3}(?!\S)', r[mr.end():]):
                x = mr.end() + m.start() + len(m.group()) / 2
                g = min(cols, key=lambda k: abs(cols[k] + 8 - x))
                if g in out:
                    out[g].append({'rank': None, 'team': mr.group(2).strip(), 'score': float(m.group()), 'places': []})
        blocks = []
        for g, teams in out.items():
            if len(teams) >= 2:
                teams.sort(key=lambda t: t['score'])
                for k, t in enumerate(teams):
                    t['rank'] = k + 1
                blocks.append({'kind': 'xc', 'gender': g, 'event_header': l.strip()[:80], 'teams': teams,
                               'totals_only': True})
        return blocks
    return []


_SIDE_HDR = re.compile(r"(?i)\b(?:(girls?|boys?|women|men)['’]?s?\W{0,3}(?:varsity\s+)?team\W{0,3}scores?:?|"
                       r"(girls?|boys?|women|men)['’]?s?\s+teams\b)")
_PAIR = r"([A-Za-z][A-Za-z .'&/()-]{0,40}?[A-Za-z.)])\s*[-:]?\s+(\d{1,3}|NS|ns|-)\*?"


def _split_side_tables(lines):
    """Two team-score tables printed side by side ("Girls Team Scores
    Boys Team Scores" over "Erskine Academy:  44   Erskine Academy:  31"):
    each column read as its own table, under its own heading."""
    out, i = [], 0
    pair2 = re.compile(r'^\s*' + _PAIR + r'\s{5,}' + _PAIR + r'\s*$')
    while i < len(lines):
        l = lines[i]
        # "See below team scores:" over two unlabelled columns ("Erskine
        # Academy:  28        Erskine Academy:  15"): one table each
        if re.search(r'(?i)team\s+scores?', l) and not _SIDE_HDR.search(l):
            nxt = [k for k in range(i + 1, min(len(lines), i + 14)) if lines[k].strip()]
            two = [k for k in nxt if pair2.match(lines[k])]
            if len(two) >= 3 and not any(_ORD_PLACE.search(lines[k]) for k in nxt):
                left, right = ['Team Scores'], ['Team Scores']
                last = two[-1]
                for k in range(two[0], last + 1):
                    mm = pair2.match(lines[k])
                    if mm:
                        left.append(f'{mm.group(1)}  {mm.group(2)}')
                        right.append(f'{mm.group(3)}  {mm.group(4)}')
                    elif lines[k].strip():
                        mo = re.match(r'^\s*' + _PAIR + r'\s*$', lines[k])
                        if mo:
                            (left if len(lines[k]) - len(lines[k].lstrip()) < 20 else right).append(
                                f'{mo.group(1)}  {mo.group(2)}')
                # (a lone last team on the right: "                Nokomis:  NS")
                k = last + 1
                while k < len(lines) and k <= last + 2:
                    mo = re.match(r'^(\s*)' + _PAIR + r'\s*$', lines[k])
                    if mo and len(mo.group(1)) >= 20:
                        right.append(f'{mo.group(2)}  {mo.group(3)}')
                    k += 1
                out += [l, ''] + left + [''] + right + ['']
                i = last + 1
                continue
        # (tables apart, not one header row "school  girls team score boys team score")
        hs = [m for m in _SIDE_HDR.finditer(l) if m.start() == 0 or re.search(r'(?:^|\s{3})\s*$', l[:m.start()])]
        if len(hs) < 2:
            out.append(l)
            i += 1
            continue
        xs = [m.start() for m in hs]
        heads = []
        for m in hs:
            g = (m.group(1) or m.group(2)).lower()
            g = 'girls' if g.startswith('girl') or g == 'women' else 'boys'
            heads.append(f'{g.capitalize()} Team Scores')
        cols = [[h] for h in heads]
        extra = [[] for _h in heads]       # (a column's own second column of teams)
        j, n = i + 1, 0
        while j < len(lines) and n <= 30:
            r = lines[j]
            if not r.strip():
                j += 1
                continue
            n += 1
            if re.search(r'\d{1,2}:\d{2}', r) or _SIDE_HDR.search(r):
                # (the last team beside the first runner: "York  115     1 101 Hadley ...")
                mp = re.match(r'^(\s*)' + _PAIR + r'(?=\s{3,})', r)
                if mp and not _SIDE_HDR.search(r) and not re.search(r'\d:\d', mp.group(0)):
                    cols[0].append(f'{mp.group(2)}  {mp.group(3)}')
                    lines[j] = ' ' * len(mp.group(0)) + r[len(mp.group(0)):]
                break
            cuts = [0]
            for x in xs[1:]:
                gaps = [m.end() for m in re.finditer(r'\s{2,}', r)
                        if abs(m.end() - x) <= 24 and re.match(r'[A-Za-z]|\d{1,2}(?:[.)]|st|nd|rd|th)\s', r[m.end():])]
                cuts.append(min(gaps, key=lambda e: abs(e - x)) if gaps else None)
            if r.strip() and all(c is None for c in cuts[1:]):
                # one cell only: the column its text starts under
                st = len(r) - len(r.lstrip())
                k = max(k for k, x in enumerate(xs) if x <= st + 6) if st + 6 >= xs[0] else 0
                # (a team the column already lists is the other column's)
                nm = re.match(r'\s*([A-Za-z][A-Za-z .\'&/-]*?)\s*:?\s+\d', r)
                if nm:
                    have = [kk for kk in range(len(cols)) if any(
                        re.match(r'\s*' + re.escape(nm.group(1)) + r'\s*:?\s+\d', c) for c in cols[kk][1:])]
                    if k in have and len(have) < len(cols):
                        k = next(kk for kk in range(len(cols)) if kk not in have)
                cuts = [0 if kk == k else None for kk in range(len(xs))]
                parts = {k: r}
            else:
                parts = {}
                bounds = [c for c in cuts if c is not None]
                for k, c in enumerate(cuts):
                    if c is None:
                        continue
                    nxt = [b for b in bounds if b > c]
                    parts[k] = r[c:nxt[0] if nxt else len(r)]
            for k, txt in parts.items():
                mm = re.match(r'^\s*' + _PAIR + r'\s{2,}' + _PAIR + r'\s*$', txt)
                if mm:
                    cols[k].append(f'{mm.group(1)}  {mm.group(2)}')
                    extra[k].append(f'{mm.group(3)}  {mm.group(4)}')
                else:
                    cols[k].append(txt)
            j += 1
        for k in range(len(cols)):
            out += cols[k] + extra[k] + ['']
        i = j
    return out


def parse_team_totals(text):
    """[{'kind': 'xc', 'totals_only': True, 'gender', 'teams': [...]}] for
    each team-score heading followed by team totals; place lists printed
    as "1-3-4-5-7-[8-10]" make a regular block."""
    plain = _html_to_text(text).replace('\xa0', ' ').replace('\ufffd', ' ')
    plain = re.sub('[\u2010-\u2012]', '-', plain.replace('\xad', '-'))   # (typeset hyphens: "Massabesic\u2010 19")
    plain = re.sub(r'(?<=[A-Za-z])-{2,}(?=\s*\d)', '-', plain)               # ("Scarborough-\xad\u2010 15")
    plain = re.sub(r'(?im)(?<=[A-Za-z.)])\s*(?:[-–—]\s*)?(\d{1,3})\s+points?[ \t]*$', r' - \1', plain)   # "Orono – 25 points"
    # "1.) JB: First Place, 26" / "7.) GSA: NO SCORE"
    plain = re.sub(r'(?i):\s*(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|'
                   r'eleventh|twelfth)\s+place\s*[,-]\s*(?=\d)', ' ', plain)
    plain = re.sub(r'(?i)(?<=[A-Za-z.])\s*[-:]?\s+no\s+score\b', ' NS', plain)
    plain = re.sub(r'(?i)\bteam[ \t]*\n[ \t]*(scores?)\b', r'Team \1', plain)
    # comma lists wrapped over lines ("..., Leavitt \n 55, Brunswick 60,")
    plain = re.sub(r',[ \t]*\n[ \t]*(?=[A-Za-z])', ', ', plain)
    plain = re.sub(r'([A-Za-z.])[ \t]*\n[ \t]*(\d{1,3}\*?\s*,)', r'\1 \2', plain)
    # a team list wrapped mid-name ("Hermon\nHigh School NS,")
    plain = re.sub(r'(?i)(team\s+scores?\s*[-–—:][^\n]*,\s*[A-Za-z .]*)\n([A-Za-z])', r'\1 \2', plain)
    lines = _split_side_tables(plain.splitlines())
    gcols = _gender_columns(lines)
    if gcols:
        return gcols
    placed = _place_sections(lines)
    if len(placed) >= 2:
        placed.sort(key=lambda t: t['score'])
        for k, t in enumerate(placed):
            t['rank'] = k + 1
        return [{'kind': 'xc', 'gender': None, 'event_header': 'PLACE: sections', 'teams': placed}]
    named = _team_name_sections(lines)
    if len(named) >= 2:
        named.sort(key=lambda t: t['score'])
        for k, t in enumerate(named):
            t['rank'] = k + 1
        return [{'kind': 'xc', 'gender': None, 'event_header': 'Team Name / Team Score sections',
                 'teams': named, 'totals_only': True}]
    heads = [i for i, l in enumerate(lines) if _TOT_HDR.search(l) or _TEAM_RESULTS.fullmatch(l.strip())
             or _INLINE_SCORES.match(l)]
    blocks = []
    file_g = None
    for hi, i in enumerate(heads):
        end = heads[hi + 1] if hi + 1 < len(heads) else len(lines)
        hm = _TOT_HDR.search(lines[i]) or _TEAM_RESULTS.search(lines[i]) or _INLINE_SCORES.match(lines[i])
        # (a gender word in another cell of the row - "JV girls | ... |
        # Team scores- Matt 17" - names the list beside it, not this one)
        own = re.split(r'\s{3,}|\|', lines[i][:hm.end()])[-1] + lines[i][hm.end():]
        gw = re.search(r'\b(girls?|boys?|women|men)\b', own, re.I)
        g = _GENDER.get(gw.group(1).lower().rstrip('s') + 's') if gw else None
        if gw and gw.group(1).lower() in ('women', 'men'):
            g = _GENDER[gw.group(1).lower()]
        if g is None:
            # ("BOYS" / "Place Team Score": a bare gender line just above)
            prev = [l.strip() for l in lines[max(0, i - 12):i] if l.strip()][-2:]
            for l in prev[::-1]:
                mb = re.fullmatch(r'(?i)(boys|girls|men|women)', l)
                if mb:
                    g = _GENDER[mb.group(1).lower()]
                    break
        teams, miss = [], 0
        # inline: "Team scores- Matt 17 , Schenck 38" / "Team Scores: Fort Kent 25, ..."
        tail = lines[i][hm.end():]
        # ("1-LEW 24   2 LEAV 41   3 POL 65 ...   TEAM SCORE": the ranked
        # list before its own title)
        _ht = re.search(r'(?i)team\s*scores?', lines[i])
        head_pairs = re.findall(r'(?<!\S)(\d{1,2})\s*-?\s*([A-Z][A-Za-z.]{1,6})\s+(\d{1,3})(?!\S)',
                                lines[i][:_ht.start() if _ht else hm.start()])
        if len(head_pairs) >= 2 and [int(r) for r, _t, _s in head_pairs] == list(range(1, len(head_pairs) + 1)):
            for r, tm, sc in head_pairs:
                e = _team_entry(r, tm, sc)
                if e:
                    teams.append(e)
        mgt = re.match(r'(?i)\s*:?\s*(boys|girls)\s*:', tail)
        if mgt:
            # ("Team Scores: Girls:  JB 25, Her 30")
            g = g or _GENDER[mgt.group(1).lower()]
            tail = ':' + tail[mgt.end():]
        for part in re.split(r'[,;]', tail):
            m = re.match(r'^\s*[-:–—]?\s*(' + _NAME + r')\s*[-:]?\s+(\d{1,3}|NS|ns)\*?\s*$', part)
            if m:
                e = _team_entry(None, m.group(1), m.group(2))
                if e:
                    teams.append(e)
        if not teams and re.match(r'\s*:\s*\d', tail):
            # "Team Score: 32 Hermon, 34 Schenck, 63 Lee." (the total first)
            for m in re.finditer(r"(\d{1,3})\s+([A-Za-z][A-Za-z .'&/-]{0,30}?[A-Za-z])\s*(?=,|\.?\s*$)", tail):
                e = _team_entry(None, m.group(2), m.group(1))
                if e:
                    teams.append(e)
        if not teams and re.match(r'\s*[:\-–]\s*(?:(?:boys|girls)\s*:\s*)?[A-Za-z]', tail, re.I) and \
                len(re.findall(r'[A-Za-z]\s*[-:]?\s*\d{1,3}\b', tail)) >= 2:
            # "Team scores: Lee 23  Schenck 30  Central 68", "Girls: JB 25, Her 30",
            # "Boys  Bangor-43; Erskine Academy - 59; ..."
            body = re.sub(r'(?i)^\s*[:\-–]?\s*(?:(?:boys|girls)\s*:\s*)?', '', tail)
            body = re.split(r'\s{3,}(?=\d)', body)[0]      # (a runner row beside it)
            for m in re.finditer(r"([A-Za-z][A-Za-z .'&/-]{0,30}?[A-Za-z.])\s*[-:]?\s*(\d{1,3}|NS)\b(?![:.]\d)", body):
                e = _team_entry(None, m.group(1), m.group(2))
                if e:
                    teams.append(e)
        if not teams and re.match(r'\s*:', tail):
            # "Team Scores: Deering: 15    Portland: 52 Cheverus: 59"
            for m in re.finditer(r"([A-Za-z][A-Za-z .'&/-]{0,30}?[A-Za-z.])\s*:\s*(\d{1,3}|NS)\b", tail[tail.index(':') + 1:]):
                e = _team_entry(None, m.group(1), m.group(2))
                if e:
                    teams.append(e)
        groups = []          # (gender, teams) when the table names its races
        for line in [lines[i]] + lines[i + 1:min(end, i + 160)]:
            s = line.strip()
            if not s:
                continue
            mg = re.search(r'(?:^|\s)(Boys|Girls|Men|Women|BOYS|GIRLS|MEN|WOMEN)\s*$', s)
            if mg and not _TOT_LINE.match(line):
                if teams:
                    groups.append((g, teams))
                    teams = []
                g = _GENDER[mg.group(1).lower()]
                miss = 0
                continue
            if line is lines[i] or len(line) > 400:
                continue
            # "Boys   Bangor-43; Erskine Academy - 59; Winslow-63; ..." (one
            # gender's list on a line)
            mgl = re.match(r'(?i)^\s*(boys|girls)\s+(.*[;,].*)$', line)
            if mgl:
                prs = [re.match(r"^\s*([A-Za-z][A-Za-z .'&/-]{0,30}?[A-Za-z.])\s*[-:]?\s*(\d{1,3}|NS)\s*$", x)
                       for x in re.split(r'[;,]', mgl.group(2)) if x.strip()]
                if len(prs) >= 2 and all(prs):
                    if teams:
                        groups.append((g, teams))
                    g = _GENDER[mgl.group(1).lower()]
                    teams = [x for x in (_team_entry(None, m.group(1), m.group(2)) for m in prs) if x]
                    miss = 0
                    continue
            e = None
            mpl = _PLUS.search(line)
            mp = _PLACE_DASH.search(line)
            mdl = _DASH_LIST.search(line)
            mrs = _RANK_SCORE_TEAM.match(line)
            msp = _PLACE_SPACE.match(line)
            # "Gorham (1-2-3-5-7)17-18   18", "South Portland(4-6-8-12-13) 14-18  43"
            mpd = re.search(r"(?:^|\s{2,})([A-Za-z][A-Za-z .'&/-]{1,30}?)\s*\(((?:\d{1,3}-){4}\d{1,3})\)\s*[\d-]*\s+(\d{1,3})\s*$", line)
            if mpd and sum(int(x) for x in mpd.group(2).split('-')) == int(mpd.group(3)):
                teams.append({'rank': None, 'team': mpd.group(1).strip(), 'score': float(mpd.group(3)),
                              'places': [int(x) for x in mpd.group(2).split('-')]})
                miss = 0
                continue
            # a totals table left of the runner rows ("YORK   23     41  Daniel Menz  C  19:10",
            # "Brunswick Jr. High: 17     33. Kieran Davidson Br 25:13")
            mlp = re.match(r"^\s{0,3}([A-Z][A-Za-z .'&/-]{1,30}?):?\s+(\d{1,3}|NS)(?![\d:])\s{5,}\d{1,3}\.?\s+[A-Za-z]", line)
            # the total first: "26    York    1st", "15   Orono"
            msf = re.match(r"^\s*(\d{1,3})\s{2,}([A-Za-z][A-Za-z.'&/-]*(?: [A-Za-z.'&/-]+){0,4})(?:\s{2,}\d{1,2}(?:st|nd|rd|th))?\s*$", line)
            if mlp and not _TOT_LINE.match(line) and re.search(r'\d[:;]\d\d', line):
                e = _team_entry(None, mlp.group(1), mlp.group(2))
            elif msf and not _TIME_TOK.search(line) and int(msf.group(1)) >= 10 and (
                    re.search(r'\d(?:st|nd|rd|th)\s*$', line) or
                    re.search(r'(?i)team\s+scores?\s{2,}team\b', lines[i])):
                e = _team_entry(None, msf.group(2), msf.group(1))
            elif msp and sum(sorted(int(x) for x in msp.group(2).split())[:5]) == int(msp.group(3)):
                e = {'rank': None, 'team': msp.group(1).strip(), 'score': float(msp.group(3)),
                     'places': [int(x) for x in msp.group(2).split()]}
            elif mdl:
                pl = [int(x) for x in re.findall(r'\d+', mdl.group(3))] + \
                     [int(x) for x in re.findall(r'\d+', mdl.group(4) or '')]
                # (the team is the last cell: a runner's row may run beside it)
                e = {'rank': None, 'team': re.split(r'\s{2,}', mdl.group(1).strip())[-1],
                     'score': float(mdl.group(2)), 'places': pl}
            elif mrs and int(mrs.group(2)) >= 10:
                e = _team_entry(mrs.group(1), mrs.group(3), mrs.group(2))
            elif mpl:
                e = {'rank': None, 'team': mpl.group(1).strip(), 'score': float(mpl.group(2)),
                     'places': [int(x) for x in mpl.group(3).split('+')]}
            elif mp:
                places = [int(x) for x in re.findall(r'\d+', mp.group(2))]
                e = {'rank': None, 'team': mp.group(1).strip(), 'score': float(mp.group(3)), 'places': places}
            else:
                mt = _TOT_TAIL.search(line)
                if mt and teams and teams[-1].get('_plain') and teams[-1]['score'] is not None and \
                        re.fullmatch(r'\d+', mt.group(2)) and int(mt.group(2)) < teams[-1]['score']:
                    break           # (a plain list ended: the runner rows begin, "... Cape  9")
                if mt:
                    e = _team_entry(None, mt.group(1), mt.group(2))
                elif not _TIME_TOK.search(line):
                    m = _TOT_LINE.match(line)
                    if m:
                        e = _team_entry(m.group(1), m.group(2), m.group(3))
                        if e:
                            e['_plain'] = True
                    # inline list lines: "Monmouth 22, Boothbay 41, Winthrop 72"
                    elif ',' in line:
                        parts = [re.match(r'^\s*(' + _NAME + r')\s+(\d{1,3}|NS|ns)\*?\s*$', p) for p in line.split(',')]
                        if parts and all(parts):
                            for p in parts:
                                x = _team_entry(None, p.group(1), p.group(2))
                                if x:
                                    teams.append(x)
                            miss = 0
                            continue
            if e:
                teams.append(e)
                miss = 0
            elif teams:
                miss += 1
                if miss > 12:
                    break
        if not teams and re.search(r'(?i)\bname\b', lines[i]):
            # the header is the runner list's column row ("Name  Team  ...
            # Place  Team Score"): the totals sit above it ("   GHCA   35")
            above = []
            for l in lines[max(0, i - 12):i]:
                ma = re.search(r"(?:^|\s{3,})([A-Z][A-Za-z .'&/-]{1,30}?)\s{3,}(\d{1,3})\s*$", l)
                if ma and not re.search(r'\d[:;]\d', l):
                    above.append(_team_entry(None, ma.group(1), ma.group(2)))
            teams = [t for t in above if t]
        groups.append((g, teams))
        for g, teams in groups:
            blk = _totals_block(g, teams, lines[i])
            if blk:
                blocks.append(blk)
    if not blocks and heads:
        # the totals typed as one list elsewhere on the page ("York 21,
        # Freeport 48, Gray-NG 71, Richmond 111" under the meet title)
        for l in lines:
            nm = r"[A-Za-z][A-Za-z.'&/-]*(?: [A-Za-z.'&/-]+)*?"
            m = re.match(r"^\s*((?:" + nm + r"\s+\d{1,3}\s*,\s*){2,}" + nm + r"\s+(?:\d{1,3}|ns|NS))(?=\s{3,}|\s*$)", l)
            if m:
                teams = [x for x in (_team_entry(None, *re.match(r'\s*(.*?)\s+(\d{1,3}|ns|NS)\s*$', part).groups())
                                     for part in m.group(1).split(',')) if x]
                blk = _totals_block(None, teams, l)
                if blk:
                    blocks.append(blk)
                    break
    return blocks


def _totals_block(g, teams, head):
    for t in teams:
        t.pop('_plain', None)
    if True:
        teams = [t for t in teams if not re.fullmatch(r'(?i)st|nd|rd|th|place|places|page|sheet', t['team'])
                 and not re.search(r'(?i)\b(?:race|results?)\b', t['team'])]   # ("YORK GIRLS RACE 41": a title)
        scored = [t for t in teams if t['score'] is not None]
        if len(scored) < 2 and not (len(scored) == 1 and len(teams) >= 2):
            return None
        # totals rise with rank (ties allowed); at least 10 (4-runner meets)
        sc = [t['score'] for t in scored]
        # (a runner list "Andrew Poland 12 / Zach Mullin 13 / ...": places)
        if len(sc) >= 3 and sum(1 for a, b in zip(sc, sc[1:]) if b - a == 1) >= max(2, 0.6 * (len(sc) - 1)):
            return None
        # (teams listed in any order are fine when each total is its own
        # five places' sum: "Massabesic 16 1,2,3,4,6,7,8 / Noble 110 ...")
        summed = all(len(t['places']) >= 5 and sum(sorted(t['places'])[:5]) == t['score'] for t in scored)
        if min(sc) < 10 or len(sc) > 2 and not summed and \
                sum(1 for a, b in zip(sc, sc[1:]) if b < a) > max(1, 0.2 * (len(sc) - 1)):
            return None
        blk = {'kind': 'xc', 'gender': g, 'event_header': head.strip()[:80], 'teams': scored}
        if all(len(t['places']) >= 5 for t in scored):
            pass                                  # a full block
        else:
            blk['totals_only'] = True
            for t in scored:
                t['places'] = t['places'] if len(t['places']) >= 5 else []
        for k, t in enumerate(scored):
            t['rank'] = k + 1
        return blk
