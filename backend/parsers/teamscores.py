"""
teamscores.py - official team scores printed in a track result file.

The score check compares our scoring with the scores the file prints, so
every way a file prints them has to be read. Formats seen on sub5:

  Hy-Tek, end of a results file (two teams per line):
      Women - 2B - Team Rankings - 14 Events Scored
      ====================================================
          1) Old Town High School   111     2) Bangor High School   97

  Hy-Tek "Team Rankings - Through Event 38" (often a separate scores file
  posted next to the results), one table per sex:
                    Female Team Scores
      Place   School                       Points
        1     Brunswick High School   BRU      99
        2     CONY TRACK TEAM         CONY     64 .50      (pdftotext split)
        4     Poland                  POL      6567        (65.67: no decimal point,
                                         Total  637.00       the printed total confirms)

  Hand-made lists ("Team Scores" / "Final Scores" / "TEAM SCORES"):
      Girls                              1 Portland High School -
      1 Greely  133                      162
      Cheverus     93                    (a number on its own line)

    extract_team_scores(text, file_gender=None) -> [
        {'gender': 'Girls'|'Boys'|'Combined', 'events_scored': int|None,
         'teams': [{'rank': int, 'team': str, 'score': float}, ...]}, ...]

One block per gender: a file that prints its standings several times (each
page, or after each event) keeps the last, most complete one.
"""

import re

HEADER = re.compile(r'team\s+(?:rankings|scores)|final\s+scores', re.I)
NOT_HEADER = re.compile(r'\bno\s+team\s+scores\b', re.I)
G_GIRLS = re.compile(r"\b(?:women|girls|female|ladies)'?s?\b", re.I)
G_BOYS = re.compile(r"\b(?:men|boys|male)'?s?\b", re.I)
G_COMB = re.compile(r'\bcombined\b', re.I)
EVENTS_N = re.compile(r'(\d+)\s*Events?\s*Scored', re.I)
THROUGH_N = re.compile(r'Through\s+Event\s+(\d+)', re.I)
STOP = re.compile(r'^\s*(?:Event\s+\d+|EVENTS\b|Results\b|Name\s+Year\s+School)', re.I)
RULE = re.compile(r'^[\s=_-]{5,}$')
COLS = re.compile(r'^\s*(?:Place|Rank)\s+(?:School|Team)\b', re.I)
PAIR_ROW = re.compile(r'(\d+)\)\s+(.*?)\s+(\d{1,4}(?:\.\d+)?)\s*(?=\d+\)\s|$)')
NUM = r'\d{1,5}(?:\s?\.\d{1,2})?'
PLACED_ROW = re.compile(rf'^\s*(\d{{1,2}})[.)]?\s+(.*?[A-Za-z].*?)\s*-?\s+({NUM})\s*$')
BARE_ROW = re.compile(rf'^\s*([A-Za-z][^0-9]*?[A-Za-z.)])\s*-?\s+({NUM})\s*$')
PLACED_NO_SCORE = re.compile(r'^\s*(\d{1,2})[.)]?\s+(.*?[A-Za-z].*?)\s*-?\s*$')
LONE_NUM = re.compile(rf'^\s*({NUM})\s*$')


def _gender(line):
    if G_COMB.search(line):
        return 'Combined'
    g, b = G_GIRLS.search(line), G_BOYS.search(line)
    if g and not b:
        return 'Girls'
    if b and not g:
        return 'Boys'
    return None


def _num(s):
    return float(re.sub(r'\s+', '', s))


def _team(name):
    # a Hy-Tek team code in its own column: "Brunswick High School   BRU"
    # (not "Mt. Desert Island HS", one space before the HS)
    name = re.sub(r'\s{2,}[A-Z0-9]{2,6}\s*$', '', name.rstrip(' -:'))
    return re.sub(r'\s+', ' ', name).strip(' -:')


def _rows(lines, i):
    """Rows of one block starting at line i; returns (rows, next_i, sub)
    where sub is a list of (gender, rows) when the block switches sex."""
    parts = []           # [(gender or None, rows)]
    cur_g, rows = None, []
    junk = 0
    pending = None       # "1 Portland High School -" waiting for its number
    j = i
    while j < len(lines):
        line = lines[j]
        s = line.strip()
        j += 1
        if not s or RULE.match(s) or COLS.match(s):
            continue
        if STOP.match(s) or (HEADER.search(s) and rows):
            j -= 1
            break
        g = _gender(s)
        if g and len(s.split()) <= 4 and not re.search(r'\d', s):
            # "Female Team Scores", "Girls": the next table's sex
            if rows:
                parts.append((cur_g, rows))
                rows = []
            cur_g = g
            continue
        pairs = PAIR_ROW.findall(s)
        if pairs:
            for rank, team, pts in pairs:
                rows.append({'rank': int(rank), 'team': _team(team), 'score': _num(pts)})
            junk = 0
            continue
        if pending is not None:
            m = LONE_NUM.match(s)
            if m:
                rank, team = pending
                rows.append({'rank': rank, 'team': _team(team), 'score': _num(m.group(1))})
                pending = None
                junk = 0
                continue
            pending = None
        m = PLACED_ROW.match(s)
        if m:
            rows.append({'rank': int(m.group(1)), 'team': _team(m.group(2)), 'score': _num(m.group(3))})
            junk = 0
            continue
        m = BARE_ROW.match(s)
        if m and len(m.group(1)) <= 45:
            rows.append({'rank': None, 'team': _team(m.group(1)), 'score': _num(m.group(2))})
            junk = 0
            continue
        m = PLACED_NO_SCORE.match(s)
        if m and len(m.group(2)) <= 45:
            pending = (int(m.group(1)), m.group(2))
            continue
        junk += 1
        if junk >= 2 and (rows or parts):
            break
        if junk >= 4:
            break
    if rows:
        parts.append((cur_g, rows))
    return parts, j


def _inline(line):
    """Scores printed on the header line itself:
    "Girls Team Scores: York 116, CE 46.5" / "final scores Gorham 108 Thornton 88.5"."""
    m = HEADER.search(line)
    rest = line[m.end():] if m else ''
    rest = re.split(r'\s{4,}(?:Event|event)\b', rest)[0]   # the results grid after it
    rest = re.sub(r'^\s*[:-]?\s*', '', rest)
    out, prev = [], 0
    for m in re.finditer(r'(?<![\d.])(\d{1,3}(?:\.\d{1,2})?)(?![\d.])', rest):
        name = re.sub(r'\s+', ' ', rest[prev:m.start()]).strip(' ,;:-')
        prev = m.end()
        if not re.search(r'[A-Za-z]', name) or len(name) > 40:
            return None
        out.append({'rank': None, 'team': _team(name), 'score': float(m.group(1))})
    return out if len(out) >= 2 else None


def extract_team_scores(text, file_gender=None):
    lines = (text or '').splitlines()
    found = {}           # gender -> (order key, block)
    order = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if not HEADER.search(line) or NOT_HEADER.search(line):
            i += 1
            continue
        hg = _gender(line)
        # a division scored on its own: "Men - Junior Division - Team Rankings"
        md = re.search(r"(?i)\b(?:women|men|girls|boys|female|male)'?s?\b\s*-?\s*(.*?)\s*-?\s*team\s+(?:rankings|scores)", line)
        div = re.sub(r'\s+', ' ', md.group(1)).strip(' -') if md else ''
        mn, mt = EVENTS_N.search(line), THROUGH_N.search(line)
        n = int(mn.group(1)) if mn else int(mt.group(1)) if mt else None
        inline = _inline(line)
        if inline:
            # "Girls Team Scores: York 116, CE 46.5, LR 37.5"
            parts, i = [(None, inline)], i + 1
        else:
            parts, i = _rows(lines, i + 1)
        for g, rows in parts:
            g = g or hg or file_gender
            # (one team is a real block only under a Hy-Tek "Team Rankings" header:
            # "Women - 6th grade - Team Rankings" with "1) Lyman Moore 69")
            if not g or len(rows) < 2 and not (len(rows) == 1 and rows[0].get('rank') == 1
                                                and re.search(r'(?i)team\s+rankings', line)):
                continue
            teams = [r for r in rows if r['team'] and not re.match(r'(?i)totals?$|points$|place$', r['team'])]
            if any(r['score'] >= 1000 for r in teams):
                # "Poland POL 6567 ... Total 637.00": points printed without their decimal point
                # (WMC indoor 2008-09); read as hundredths only when the printed total agrees
                tot = [r['score'] for r in rows if re.match(r'(?i)totals?$', r['team'] or '')]
                fixed = [r['score'] / 100 if r['score'] >= 1000 else r['score'] for r in teams]
                if tot and abs(sum(fixed) - tot[-1]) < 0.05:
                    for r, v in zip(teams, fixed):
                        r['score'] = round(v, 2)
                else:
                    teams = [r for r in teams if r['score'] < 1000]
            # unplaced lists rank by score
            if any(r['rank'] is None for r in teams):
                teams.sort(key=lambda r: -r['score'])
                for k, r in enumerate(teams):
                    r['rank'] = k + 1
            order += 1
            key = ((n or 0), order)
            fk = (g, div)
            if fk not in found or key >= found[fk][0]:
                blk = {'gender': g, 'events_scored': n, 'teams': teams}
                if div:
                    blk['division'] = div
                found[fk] = (key, blk)
    return [b for _, b in sorted(found.values(), key=lambda x: (x[1]['gender'], x[1].get('division', '')))]


def file_text(path):
    """Plain text of a result file for score reading: pdftotext -layout for
    a PDF; for HTML, the text with every line break the markup implies
    (<br>, </p>, </tr>, </pre>), tags spanning lines and all."""
    import subprocess
    if path.lower().endswith('.pdf'):
        try:
            return subprocess.run(['pdftotext', '-layout', path, '-'], capture_output=True,
                                  text=True, timeout=60).stdout
        except (OSError, subprocess.SubprocessError):
            return ''
    from bs4 import BeautifulSoup
    with open(path, encoding='utf-8', errors='ignore') as f:
        html = f.read()
    html = re.sub(r'(?i)<br\s*/?>|</p>|</tr>|</h\d>|</div>', '\n', html)
    if 'schemas-microsoft-com:office' in html[:5000]:
        # Word exports wrap one printed line over several source lines
        html = re.sub(r'(?i)<p\b', '\n<p', re.sub(r'[\r\n]+', ' ', html))
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    # a score table (Word / Excel export) reads as one line per row
    rows = ['   '.join(re.sub(r'\s+', ' ', c.get_text(' ')).strip() for c in tr.find_all(['td', 'th']))
            for tr in soup.find_all('tr') if tr.find('tr') is None]   # (innermost rows)
    if rows:
        text += '\n' + '\n'.join(rows)
    return text.replace('\xa0', ' ')
