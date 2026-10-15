"""Team scores printed as a grid of finish places (Gorham, Wilkinson
Memorial, 2011-2017):

        Girls Cross Country                Gorham   Bonny Eagle   Scarborough
        Friday, October 12, 2012    1st    14       1             5
        at Narragansett School      2nd    17       2             10
                                    ...
                                    TOTAL  96       18            78

    PLACE  Name  School  Time       BOYS TEAM SCORES
      1   Aiden Willey  Bonny Eagle  10:39   SCHOOL  Gorham  Bonny Eagle  Windham
      2   ...                                  1st      3        1           2

Each ordinal row ("1st".."7th") gives every team's n-th scorer; the line
above names the teams, one per column; TOTAL is the score. A team's column
is kept only when its first five places add up to its printed total - the
grid then serves as the race's official team result ('xc' blocks), which
makes these hand-made sheets verifiable.
"""
import re

_ORD = re.compile(r'(?<!\S)([1-9])(?:st|nd|rd|th)(?!\S)', re.I)
_GENDER = re.compile(r"\b(girl'?s?|boy'?s?|women'?s?|men'?s?)\b", re.I)


def _cells(text, x0, overlap=False):
    """[(center x, text)] for 2+-space separated cells right of x0 (or,
    with overlap, ending right of it: "SCHOOL Gorham" over the 1st column)."""
    out = []
    for m in re.finditer(r'\S+(?: \S+)*', text):
        if m.start() >= x0 or overlap and m.end() > x0 + 1 and not re.search(r'\d', m.group()):
            out.append(((m.start() + m.end()) / 2, m.group()))
    return out


def team_grid_blocks(text, file_gender=None):
    lines = (text or '').replace('\xa0', ' ').splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        m = _ORD.search(lines[i])
        if not m or m.group(1) != '1' or i == 0:
            i += 1
            continue
        x_end = m.end()
        h = i - 1
        while h > 0 and not lines[h].strip():
            h -= 1                       # (a double-spaced sheet)
        head = lines[h]
        # the team names: the header line right of the ordinal column ("SCHOOL"
        # labels the ordinal column itself)
        names = []
        for x, t in _cells(head, x_end - 1, overlap=True):
            if re.fullmatch(r'school|teams?', t, re.I):
                continue
            pre = re.match(r'(?:school|teams?)\s+', t, re.I)     # "SCHOOL Gorham"
            if pre:
                x, t = x + len(pre.group()) / 2, t[pre.end():]
            names.append((x, t))
        first_vals = [(x, v) for x, v in _cells(lines[i], x_end) if re.fullmatch(r'\d{1,3}', v)]
        if len(first_vals) > len(names) >= 1:
            # team names set one space apart ("Gorham Bonny Eagle   Cheverus"):
            # a word starting over a value column opens that team, a word one
            # space after another continues it
            starts = [(x - len(v) / 2, x) for x, v in first_vals]
            cols = {x: [] for _s, x in starts}
            prev_end, prev_col = None, None
            for w in re.finditer(r'\S+', head):
                if w.end() <= x_end - 1 or re.fullmatch(r'school|teams?', w.group(), re.I):
                    continue
                on = [x for st, x in starts if abs(st - w.start()) <= 1]
                if on:
                    col = on[0]
                elif prev_col is not None and w.start() - prev_end == 1:
                    col = prev_col
                else:
                    col = min(starts, key=lambda sx: abs(sx[0] - w.start()))[1]
                cols[col].append(w.group())
                prev_end, prev_col = w.end(), col
            if all(cols.values()):
                names = [(x, ' '.join(ws)) for x, ws in cols.items()]
        if len(names) < 2 or any(re.search(r'\d', t) for _x, t in names):
            i += 1
            continue
        places = {t: [] for _x, t in names}
        total = {}
        j = i
        while j < len(lines):
            lj = lines[j]
            mo = _ORD.search(lj)
            mt = re.search(r'(?<!\S)TOTAL(?!\S)', lj, re.I)
            mark = mo if mo and abs(mo.end() - x_end) <= 3 else mt
            if not mark:
                if j > i + 20:
                    break
                j += 1
                continue
            vals = [(x, v) for x, v in _cells(lj, mark.end()) if re.fullmatch(r'\d{1,3}', v)]
            for k, (x, v) in enumerate(vals):
                if len(vals) == len(names):
                    tx, team = names[k]     # a full row: one value per team, in order
                else:
                    tx, team = min(names, key=lambda n: abs(n[0] - x))
                    if abs(tx - x) > 12:
                        continue
                if mark is mt:
                    total[team] = int(v)
                else:
                    places[team].append(int(v))
            if mark is mt:
                break
            j += 1
        teams = []
        for _x, t in names:
            p = places[t]
            if len(p) >= 5 and t in total and sum(p[:5]) == total[t]:
                teams.append({'team': t, 'score': float(total[t]), 'places': p})
        if len(teams) >= 2:
            near = ' '.join(lines[max(0, i - 6):i + 1])
            gm = None
            for gm in _GENDER.finditer(near):
                pass
            g = None
            if gm:
                g = 'Girls' if gm.group(1).lower().startswith(('girl', 'women')) else 'Boys'
            teams.sort(key=lambda t: t['score'])
            for k, t in enumerate(teams):
                t['rank'] = k + 1
            blocks.append({'kind': 'xc', 'gender': g or file_gender,
                           'event_header': 'team place grid', 'teams': teams})
        i = j + 1
    return blocks


def _grid_rows(text):
    """Rows of cells: HTML tables cell by cell (blank cells kept), else
    each text line split at 2+ spaces with each cell's centre x."""
    rows = []
    if '<' in text[:3000] and re.search(r'<td', text, re.I):
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, 'html.parser')
            for tr in soup.find_all('tr'):
                cells = [re.sub(r'\s+', ' ', td.get_text(' ')).replace('\xa0', ' ').strip()
                         for td in tr.find_all(['td', 'th'])]
                rows.append([(float(k), c) for k, c in enumerate(cells)])
            return rows, True
        except Exception:
            pass
    for line in (text or '').replace('\xa0', ' ').splitlines():
        rows.append([((m.start() + m.end()) / 2, m.group()) for m in re.finditer(r'\S+(?: \S+)*', line)])
    return rows, False


def vertical_grid_blocks(text, file_gender=None):
    """Team scores as columns of places under a row of team names:

        Falmouth            Lake Region         Waynflete       Yarmouth
        1                   14                                  2
        3                   15                                  4

    (no ordinal column). Each column lists one team's finishers' places;
    its score is the first five. HTML tables are read cell by cell."""
    rows, is_html = _grid_rows(text)
    blocks = []
    i = 0
    while i < len(rows):
        head = [(x, c) for x, c in rows[i] if c]
        names = [(x, c) for x, c in head if re.fullmatch(r"[A-Za-z][A-Za-z .'&/()-]{1,40}|[A-Z]", c)
                 and not re.search(r'(?i)^(place|name|time|team|score|total|grade|school|pts|points)s?$', c)]
        if not is_html and len(names) >= 2:
            # the grid's header may follow a runner header on the same line
            # ("Place Athlete Time School   Scarborough Kennebunk McAuley")
            k0 = next((k for k in range(len(head)) if all(
                re.fullmatch(r"[A-Za-z][A-Za-z .'&/()-]{1,40}|[A-Z]", c) for _x, c in head[k:])), len(head))
            head = head[k0:]
            names = [n for n in names if n in head]
        if is_html and len(names) >= 2:
            # ("Place | Last | First | School | Time | Points | | Portland |
            # Gorham ..."): the grid's names follow the runner list's header
            hw = [k for k, (_x, c) in enumerate(head)
                  if re.search(r'(?i)^(place|name|time|team|score|total|grade|school|pts|points|last|first)s?$', c)]
            if hw and hw[-1] + 2 < len(head):
                head = head[hw[-1] + 1:]
                names = [n for n in names if n in head]
        idx_x = None
        if not is_html and names and i + 1 < len(rows):
            # team names set one space apart ("Marshwood Cheverus Windham"):
            # split the header's words over the number columns below
            nxt = [(x, c) for x, c in rows[i + 1] if x >= min(x - len(c) / 2 for x, c in names) - 6]
            k = len(nxt)
            while k > 0 and re.fullmatch(r'\(?\d{1,3}\)?\*?', nxt[k - 1][1]):
                k -= 1
            numx = [x for x, _c in nxt[k:]]
            # a scorer-number column (1, 2, 3, 4, 5) left of the teams'
            # columns, the names printed off their columns: names in order
            if len(numx) >= 3 and len(numx) > len(names):
                first = []
                for r in rows[i + 1:i + 12]:
                    cs = [c for x, c in r if c and abs(x - numx[0]) <= 2]
                    if not cs or not re.fullmatch(r'\d{1,3}', cs[0]):
                        break
                    first.append(int(cs[0]))
                if len(first) >= 5 and first == list(range(1, len(first) + 1)):
                    idx_x, numx = numx[0], numx[1:]
                    if len(numx) == len(names):
                        names = [(x, c) for x, (_x0, c) in zip(numx, names)]
                        head = names
            if len(numx) >= 2 and len(names) > len(numx) and \
                    all(re.fullmatch(r'\d{1,3}', c) for _x, c in nxt[k:]) and names[-len(numx)][0] > min(numx) - 15 and \
                    all(x < min(numx) - 15 for x, _c in names[:-len(numx)]):
                # (a runner's cells on the header's line, left of the team
                # names: "2 16:37  Nadeau  B   Deering  Scarb.  Sanford  B")
                names = names[-len(numx):]
                head = names
            if len(numx) > len(names):
                words = []
                for line_x, c in names:
                    start = line_x - len(c) / 2
                    for m in re.finditer(r'\S+', c):
                        words.append((start + m.start() + len(m.group()) / 2, m.group()))
                groups = {x: [] for x in numx}
                for wx, w in words:
                    groups[min(numx, key=lambda x: abs(x - wx))].append(w)
                if idx_x is not None and len(words) <= 9:
                    # (names printed off their columns: the words in order,
                    # grouped so the most groups are schools the rows name)
                    import itertools
                    body = ' '.join(c for r in rows for _x, c in r).lower()
                    best = None
                    for cut in itertools.combinations(range(1, len(words)), len(numx) - 1):
                        bounds = (0,) + cut + (len(words),)
                        gs = [' '.join(w for _x, w in words[a:b]) for a, b in zip(bounds, bounds[1:])]
                        sc = sum(body.count(g.lower()) >= 2 for g in gs)
                        if best is None or sc > best[0]:
                            best = (sc, gs)
                    if best and best[0] >= len(numx) - 1:
                        groups = {x: [g] for x, g in zip(numx, best[1])}
                if not all(groups.values()) and len(numx) <= len(words) <= 9 and \
                        all(re.fullmatch(r"[A-Z][A-Z.'&/-]*", w) for _wx, w in words):
                    # (a word nearer the next column: "SANFORD M" over two
                    # columns) - the split of the words, in order, whose
                    # groups sit nearest their columns
                    import itertools
                    best = None
                    for cut in itertools.combinations(range(1, len(words)), len(numx) - 1):
                        bounds = (0,) + cut + (len(words),)
                        gs = [words[a:b] for a, b in zip(bounds, bounds[1:])]
                        cost = sum(abs(sum(wx for wx, _w in g) / len(g) - x) for g, x in zip(gs, sorted(numx)))
                        if best is None or cost < best[0]:
                            best = (cost, gs)
                    groups = {x: [w for _wx, w in g] for x, g in zip(sorted(numx), best[1])}
                if all(groups.values()):
                    names = [(x, ' '.join(ws)) for x, ws in groups.items()]
                    head = names
        if len(names) < 2 or len(names) < len(head) - 1:
            i += 1
            continue
        cols = {x: [] for x, _c in names}
        seen_x, last_row = {}, {}
        totals_row = {}
        xmin = min(x - (0 if is_html else len(c) / 2) for x, c in names) - (0 if is_html else 6)
        j = i + 1
        while j < len(rows):
            # (runner rows may sit left of the grid on the same lines)
            cells = [(x, c) for x, c in rows[j] if c and x >= xmin]
            if not is_html:
                # the trailing run of numbers (a runner's cells may precede it)
                k = len(cells)
                while k > 0 and re.fullmatch(r'\(?\d{1,3}\)?\*?', cells[k - 1][1]):
                    k -= 1
                cells = cells[k:]
            nb = j
            while nb < len(rows) and nb - j < 2 and not [c for _x, c in rows[nb] if c]:
                nb += 1         # (one or two blank lines inside the grid)
            if not cells and not is_html and nb > j and nb < len(rows) and j > i + 1 and rows[nb] and \
                    all(re.fullmatch(r'\(?\d{1,3}\)?\*?', c) for _x, c in rows[nb] if c):
                j = nb
                continue
            if not cells and j == i + 1:
                j += 1          # (the runner list's own header row under the team names)
                continue
            if not cells and is_html and sum(1 for x, c in rows[j] if c and x < xmin) >= 3 and \
                    not any(c for x, c in rows[i] if x < xmin) and sum(1 for v in cols.values() if v) >= 2:
                j += 1          # (a runner beside the grid who scores for no team)
                continue
            if not cells or not all(re.fullmatch(r'\(?\d{1,3}\)?\*?', c) for _x, c in cells):
                break
            cells = [(x, c) for x, c in cells if not (idx_x is not None and abs(x - idx_x) <= 2)]
            # (a full row - one number per team - goes column by column:
            # right-aligned numbers can sit nearer the next team's name)
            in_order = not is_html and len(cells) == len(cols)
            # a totals row inside the grid ("Total:  24  31  0 ...", "103  38
            # 116  28  86"), the 6th/7th runners printed under it: the
            # totals, not places
            if in_order:
                sums = [(nx, int(re.sub(r'\D', '', c))) for nx, (_x, c) in zip(sorted(cols), cells)]
            else:
                sums = [(min(cols, key=lambda cx: abs(seen_x.get(cx, cx) - x)), int(re.sub(r'\D', '', c)))
                        for x, c in cells]
            hit = [(nx, v) for nx, v in sums if len(cols[nx]) >= 5 and v == sum(cols[nx][:5]) and v]
            if len(hit) >= 2 and len(hit) >= 0.5 * sum(1 for nx, _v in sums if cols[nx] and any(cols[nx])):
                totals_row = dict(hit)
                j += 1
                break
            got = {}
            for ci, (x, c) in enumerate(cells):
                # (a partial row in a grid printed off its names: the columns
                # where the full rows above put their numbers)
                nx = sorted(cols)[ci] if in_order else \
                    min(cols, key=lambda cx: abs(seen_x.get(cx, cx) - x))
                if is_html and nx != x:
                    continue
                if not is_html and abs(seen_x.get(nx, nx) - x) > 12 and not in_order:
                    continue
                if in_order:
                    seen_x[nx] = x
                cols[nx].append(int(re.sub(r'\D', '', c)))
                got[nx] = cols[nx][-1]
            last_row = got
            j += 1
        teams = []
        # a totals row under the places: most of its numbers are their
        # column's first-five sums (one may be the sheet's own slip)
        printed = dict(totals_row)
        if last_row and len(last_row) >= 2 and sum(
                1 for x, v in last_row.items() if len(cols[x]) > 5 and v == sum(cols[x][:5])) >= 0.5 * len(last_row):
            for x, v in last_row.items():
                if cols[x] and cols[x][-1] == v and len(cols[x]) > 5:
                    printed[x] = v
                    cols[x] = cols[x][:-1]
        for x, name in names:
            p = cols[x]
            if x not in printed and len(p) > 5 and p[-1] == sum(p[:5]):
                p = p[:-1]               # a totals row under the places
            if re.search(r'(?i)\b(place|score|name|time|school|team|grade|pts|points|bib)\b', name):
                continue       # a results header, not a team
            if len(p) > 7 and all(b - a == 1 for a, b in zip(p, p[1:])):
                continue       # a run of row numbers, not a team's places
            if len(p) >= 5 and all(b > a for a, b in zip(p, p[1:])):
                teams.append({'team': name, 'score': float(printed.get(x, sum(p[:5]))), 'places': p})
        if j - i >= 6 and len(teams) >= 2:
            gw = None
            for r in rows[max(0, i - 4):i + 1]:
                for _x, c in r:
                    m = re.search(r'\b(girls?|boys?|women|men)\b', c, re.I)
                    if m:
                        gw = m.group(1).lower()
            g = ('Girls' if gw and gw.startswith(('girl', 'women')) else
                 'Boys' if gw else file_gender)
            # names carrying a gender each ("Edward Little Girls ... Lewiston Boys")
            by_g = {}
            # two grids side by side ("Lewiston MCI   Lewiston MCI"): a name
            # seen again starts the next race's grid
            part, seen_n = 0, set()
            for t in teams:
                if t['team'] in seen_n:
                    part, seen_n = part + 1, set()
                seen_n.add(t['team'])
                mg = re.search(r'\b(girls?|boys?)\b', t['team'], re.I)
                tg = ('Girls' if mg.group(1).lower().startswith('girl') else 'Boys') if mg else g
                by_g.setdefault((tg, part), []).append(t)
            if len({k[1] for k in by_g}) > 1:
                by_g = {(None if not any(re.search(r'(?i)\b(girls?|boys?)\b', t['team']) for t in ts)
                         else k[0], k[1]): ts for k, ts in by_g.items()}
            for (tg, _part), ts in by_g.items():
                ts.sort(key=lambda t: t['score'])
                for k, t in enumerate(ts):
                    t['rank'] = k + 1
                if len(ts) >= 1:
                    blocks.append({'kind': 'xc', 'gender': tg, 'event_header': 'team place columns',
                                   'teams': ts})
            i = j
        else:
            i += 1
    return blocks
