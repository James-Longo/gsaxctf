"""
SpreadsheetTableParser - results exported to HTML from a spreadsheet.

Coaches often post results straight out of Excel, OpenOffice or LibreOffice
("Save as Web Page"). The markup is a real <table>, but it carries none of the
structure the other table parsers key on: no event labels, no consistent
header, blank spacer rows and columns everywhere, and often several
independent result blocks laid side by side across one sheet.

Rather than pattern-match the markup, this parser reads the grid with
pandas.read_html and identifies columns by their *content*: the column that
holds marks is the anchor, and the name / team / place columns are located
relative to it. That makes the parser indifferent to column order, to spacer
columns and to whether a header row exists at all.

Last in the parser chain: it only sees files every other parser gave up on.
"""

import os
import re

from .base import BaseParser
from .looselist import canon_event, is_mark

# a time (17:47, 4:55.2), a feet-inches distance (16-01.50) or a plain
# sprint/field mark (12.34) - the same shapes is_mark() accepts
MARK_CELL = re.compile(r'^\d{1,2}:\d{2}(\.\d+)?$|^\d{1,3}-\d{1,2}(\.\d+)?$|^\d{1,3}\.\d{1,2}$')
# a spreadsheet stores 17:47 as a clock time and exports it as "17:47:00"
CLOCK_CELL = re.compile(r'^(\d{1,2}):(\d{2}):(\d{2})$')
HEADER_WORDS = {'name', 'athlete', 'runner', 'school', 'team', 'place', 'pl',
                'time', 'mark', 'result', 'points', 'pts', 'grade', 'yr',
                'bib', 'finish', 'affiliation'}
# a person's name: letters plus a comma or space separating the parts
NAME_CELL = re.compile(r"^[A-Za-z][A-Za-z.'\-]*(?:[,\s]+[A-Za-z][A-Za-z.'\-]*)+$")
# any alphabetic cell - some sheets list surnames only ("Shafer", "Becker")
ALPHA_CELL = re.compile(r"^[A-Za-z][A-Za-z.',’\-/& ]{0,39}$")
# a team cell: a short code (BE, K, TA) or a school name, never a mark
TEAM_CELL = re.compile(r"^[A-Za-z][A-Za-z.'\-/& ]{0,23}$")


class _Cell(str):
    """A cell's text, with the place typed in front of a name kept aside."""
    place = None


def _cell(v):
    if v is None or (isinstance(v, float) and v != v):
        return ''
    t = re.sub(r'\s+', ' ', str(v).replace('\ufffd', ' ')).strip()
    # "34. Zielinski": a place typed into the name cell
    m = re.match(r'^(?:(\d{1,3})\.\s*|\*+)(?=[A-Za-z])', t)
    if not m:
        return t
    c = _Cell(t[m.end():])
    if m.group(1):
        c.place = int(m.group(1))
    return c


def _cells(df):
    """Grid of trimmed strings; NaN becomes ''."""
    return [[_cell(v) for v in row] for row in df.itertuples(index=False)]


def _norm_mark(s):
    """Undo the spreadsheet clock-time artifact: 17:47:00 -> 17:47."""
    s = re.sub(r'^(\d{1,2}:\d{2}(?:[.:]\d+)?)\s*[*#+]+$', r'\1', s.strip())   # "15:45*" (record mark)
    m = CLOCK_CELL.match(s)
    if m and m.group(1) in ('0', '00'):  # h:mm:ss with no hours: 0:23:27
        return f'{m.group(2)}:{m.group(3)}'
    if m and m.group(3) == '00' and int(m.group(1)) < 60:
        return f'{m.group(1)}:{m.group(2)}'
    return s


def _is_mark_cell(s, times_only=False):
    """times_only rejects bare decimals. A distance-race sheet has no sprint
    marks, so a column of "22.0"/"43.0" there is team points, not results."""
    s = _norm_mark(s)
    if not s or not MARK_CELL.match(s):
        return False
    if ':' in s or '-' in s:
        return True
    if times_only:
        return False
    try:
        v = float(s)
    except ValueError:
        return False
    # points are written as whole numbers; a real sprint mark rarely is
    return 5.0 <= v <= 99.99 and v != int(v)


class SpreadsheetTableParser(BaseParser):
    def parse(self, text, meet_url, season_type):
        empty = {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}
        if '<table' not in text.lower():
            return empty
        try:
            import pandas as pd
        except ImportError:
            return empty
        from io import StringIO
        gender = self._gender(meet_url, text)
        # (no distance on the sheet: unknown, not assumed 5K - middle-school
        # 2-mile races and relay legs come as sheets too)
        default_event = 'Run CC' if season_type == 'XC' else None
        if default_event is None:
            # Track meets need an event label per row; without one the rows are
            # unusable, so leave the file for the audit trail rather than
            # inventing an event.
            return empty

        # Each workbook sheet is exported as its own <table> under an
        # "<H1>Sheet 1: <EM>Ind. Boys</EM></H1>" heading: a sheet (and each
        # side-by-side block in it) is its own race, gendered by its heading.
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, 'lxml')
        except Exception:
            return empty
        events = []
        title = None
        seen, seen_names = set(), set()
        for tag in soup.find_all('table'):
            try:
                # the first frame is this table itself (nested tables come
                # after it and are visited as their own tags)
                tables = pd.read_html(StringIO(str(tag)), flavor='lxml')[:1]
            except Exception:
                continue
            h = tag.find_previous(['h1', 'h2', 'h3'])
            hg = self._heading_gender(h.get_text(' ') if h else '')
            for df in tables:
                if df.shape[0] < 3 or df.shape[1] < 2:
                    continue
                grid = _cells(df)
                if title is None:
                    title = self._title(grid)
                ev_name = self._distance_event(grid) or default_event
                for seg_gender, seg in self._sections(grid):
                    events.extend(self._races(seg, season_type, seen, seen_names, {
                        'event': ev_name, 'gender': seg_gender or hg or gender,
                        'is_relay': False}))
        if not events:
            return empty
        return {'events': events, 'date': None, 'meet_name': title, 'team_rankings': []}

    # -- helpers ----------------------------------------------------------
    def _gender(self, meet_url, text):
        hay = (os.path.basename(meet_url) + ' ' + text[:3000]).lower()
        if re.search(r'girl|women|female|\bgv\b|\bgirls\b', hay):
            return 'Girls'
        if re.search(r'boy|\bmen\b|male|guys|\bbv\b', hay):
            return 'Boys'
        return 'Boys'

    def _races(self, grid, season_type, seen, seen_names, template):
        """The races in one sheet section: one per block of columns, except
        that a long list wrapped into side-by-side columns (places 46-90
        beside 1-45) continues its race. Rows already read from an earlier
        sheet (team / summary sheets repeat them) are skipped."""
        races, prev = [], None
        blocks = []
        for block in self._blocks(grid, times_only=(season_type == 'XC')):
            # a column block holding two races one under the other (varsity,
            # then "JV girls" from 28:00 after a 35:15 last varsity runner):
            # the finish order starts over where the time drops
            # (only under a race heading between them - "JV girls", "Varsity
            # Boys": a by-team listing or a typo restarts too, and is no race)
            def headed(k):
                (ra, jm), (rb, _j) = block[k - 1]['_at'], block[k]['_at']
                # (or the list's own header printed again over the next race:
                # "Place | Score | Name | Team | Time")
                return any(re.search(r'\b(boys?|girls?|men|women|jv|varsity|junior|freshm\w*|frosh|'
                                     r'middle|race|heat|division|section|novice|reserve)\b', c, re.I)
                           for row in grid[ra + 1:rb] for c in row[max(0, jm - 4):jm + 1] if c) or \
                    any(sum(1 for c in row[max(0, jm - 4):jm + 1] if re.fullmatch(r'(?i)place|name|time', c or '')) >= 2
                        for row in grid[ra + 1:rb]) and long_run(k)

            def long_run(k):
                # (a by-team summary repeats the header over each team's
                # few runners: only a full list of 15+ is a race)
                n = 1
                while k + n < len(block) and self._secs(block[k + n]['result']) >= self._secs(block[k + n - 1]['result']) - 30:
                    n += 1
                return n >= 15
            cut = [0] + [k for k in range(1, len(block))
                         if self._secs(block[k]['result']) < self._secs(block[k - 1]['result']) - 30
                         and headed(k)] + [len(block)]
            top = 0
            for a, b in zip(cut, cut[1:]):
                run = block[a:b]
                # its gender: a heading over its columns since the last run
                # ("VARSITY GIRLS" | "VARSITY BOYS" side by side, "JV girls")
                r0, jm = run[0]['_at']
                g = None
                for ri in range(r0 - 1, top - 1, -1):
                    cells = grid[ri][max(0, jm - 4):jm + 1]
                    hits = {self._heading_gender(c) for c in cells if c} - {None}
                    if len(hits) == 1:
                        g = hits.pop()
                        break
                top = run[-1]['_at'][0] + 1
                blocks.append((run, g))
        for block, run_g in blocks:
            col = block[0]['_at'][1] if block and '_at' in block[0] else None
            for r in block:
                r.pop('_at', None)
            keys = [(r['result'], self._surname(r['athlete'])) for r in block]
            names = [r['athlete'].lower() for r in block]
            if sum(1 for k in keys if k in seen) >= 0.5 * len(keys) or \
                    sum(1 for n in names if n in seen_names) >= 0.5 * len(names):
                continue
            seen_names.update(names)
            rows = [r for r, k in zip(block, keys) if k not in seen]
            seen.update(keys)
            if len(rows) < 3:
                continue
            # a block that starts faster than the previous one ended is
            # another race; otherwise it continues the list
            if prev is not None and self._secs(rows[0]['result']) >= \
                    self._secs(prev['results'][-1]['result']):
                prev['results'].extend(rows)
                continue
            # a second column holding the middle of the list (1-52 | 53-104,
            # then 105-133 back under the first): it fits in one time gap
            if prev is not None and run_g in (None, prev.get('gender')):
                pr = prev['results']
                t0, t1 = self._secs(rows[0]['result']), self._secs(rows[-1]['result'])
                gap = next((k for k in range(len(pr) - 1)
                            if self._secs(pr[k]['result']) <= t0 and t1 <= self._secs(pr[k + 1]['result'])
                            and self._secs(pr[k + 1]['result']) - self._secs(pr[k]['result']) >= 0.5 * (t1 - t0)), None)
                if gap is not None and len(rows) >= 5 and \
                        sorted(rows, key=lambda r: self._secs(r['result'])) == rows:
                    prev['results'][gap + 1:gap + 1] = rows
                    continue
            # a list wrapped into a column to the right of an earlier race
            # (each division's 1-46 | 47-92): the race whose last time it
            # follows within seconds
            cont = [r0 for r0 in races if r0.get('_col') is not None and col is not None and r0['_col'] < col
                    and not r0.get('_cont') and run_g in (None, r0.get('gender'))
                    and 0 <= self._secs(rows[0]['result']) - self._secs(r0['results'][-1]['result']) <= 20]
            if len(cont) == 1 and len(rows) >= 5:
                cont[0]['results'].extend(rows)
                cont[0]['_cont'] = True
                continue
            prev = dict(template, results=rows)
            prev['_col'] = col
            if run_g:
                prev['gender'] = run_g
            races.append(prev)
        for r0 in races:
            r0.pop('_col', None)
            r0.pop('_cont', None)
        return races

    @staticmethod
    def _sections(grid):
        """Split a sheet at gender heading rows ("GIRLS", "Boys Results"):
        hand-made sheets stack the boys' and girls' races in one grid.
        Yields (gender or None, rows)."""
        out, cur, g = [], [], None
        for row in grid:
            filled = [c for c in row if c]
            hg = None
            if 1 <= len(filled) <= 3 and len(set(filled)) == 1 and len(filled[0]) <= 30:
                hg = SpreadsheetTableParser._heading_gender(filled[0])
            if hg and hg != g and any(any(MARK_CELL.match(_norm_mark(c)) for c in r) for r in cur):
                out.append((g, cur))
                cur = []
            if hg:
                g = hg
            cur.append(row)
        out.append((g, cur))
        return out

    @staticmethod
    def _distance_event(grid):
        """'Distance: 2.75 miles' / '3.1 Mile Course' / '5K' in the sheet's
        title rows names the race; otherwise the caller's default."""
        for row in grid[:8]:
            for c in row:
                if not c or MARK_CELL.match(c):
                    continue
                m = re.search(r'(\d+(?:\.\d+)?)\s*(miles?|mi\b|km\b|k\b)', c, re.I)
                if m and 1.0 <= float(m.group(1)) <= 10:
                    unit = m.group(2).lower()
                    return (f"{m.group(1)}k Run CC" if unit.startswith('k')
                            else f"{m.group(1)} Mile Run CC")
        return None

    @staticmethod
    def _surname(name):
        n = (name or '').strip().lower()
        if ',' in n:
            return n.split(',')[0].strip()
        return n.split()[-1] if n.split() else n

    @staticmethod
    def _secs(mark):
        v = 0.0
        try:
            for x in str(mark).split(':'):
                v = v * 60 + float(x)
        except ValueError:
            return 0.0
        return v

    @staticmethod
    def _heading_gender(head):
        h = head.lower()
        b = re.search(r'\b(boys?|men|male)\b', h)
        g = re.search(r'\b(girls?|women|female)\b', h)
        if b and not g:
            return 'Boys'
        if g and not b:
            return 'Girls'
        return None

    def _title(self, grid):
        for row in grid[:3]:
            filled = [c for c in row if c]
            if len(filled) == 1 and len(filled[0]) > 8 and \
                    not MARK_CELL.match(filled[0]):
                return filled[0]
        return None

    def _blocks(self, grid, times_only=False):
        """Yield result rows for each independent block of columns in a sheet.

        A block is anchored on a column whose cells are mostly marks; the name
        and team columns are the nearest text columns to its left.
        """
        ncol = max(len(r) for r in grid)
        col = lambda j: [r[j] if j < len(r) else '' for r in grid]

        mark_cols = []
        for j in range(ncol):
            vals = [v for v in col(j) if v]
            if len(vals) < 3:
                continue
            hits = sum(1 for v in vals if _is_mark_cell(v, times_only))
            # a "TIME OUT" column of 0:00:00 start times is no finish column
            marks = [_norm_mark(v) for v in vals if _is_mark_cell(v, times_only)]
            if marks and max(marks.count(m) for m in set(marks)) >= 0.8 * len(marks):
                continue
            if hits >= 3 and hits / len(vals) >= 0.6:
                mark_cols.append(j)
        if not mark_cols:
            return

        for jm in mark_cols:
            # nearest text column to the left is the name; the one after it the team
            # judge columns by this block's data rows only (rows with a mark
            # in its mark column): a team-score table stacked below the
            # results shares the columns but is not part of the block
            data_rows = [r for r in grid if jm < len(r) and _is_mark_cell(r[jm], times_only)]

            def vals_of(j):
                return [r[j] for r in data_rows if j < len(r) and r[j]
                        and r[j].lower() not in HEADER_WORDS]

            def score(j, pat):
                vals = vals_of(j)
                if len(vals) < 3:
                    return 0.0
                return sum(1 for v in vals if pat.match(v)) / len(vals)

            def avg_len(j):
                vals = vals_of(j)
                return sum(len(v) for v in vals) / len(vals) if vals else 0.0

            # Columns of words, not marks or numbers, to the left of the marks.
            # The name column is the wordiest of them; the team column is a
            # shorter one beside it (a code like "BE", or a school name).
            # (only back to the previous block's mark column: side-by-side
            # races each own the columns since the last mark column)
            lo = max([c for c in mark_cols if c < jm], default=-1)
            alpha = [j for j in range(jm - 1, lo, -1)
                     if score(j, ALPHA_CELL) >= 0.7 and score(j, MARK_CELL) < 0.2]
            if not alpha:
                continue
            # names barely repeat, schools do: among columns whose values are
            # mostly distinct take the wordiest ("Zielinski" | "Presque Isle")
            def distinct_ratio(j):
                v = vals_of(j)
                return len(set(v)) / len(v) if v else 0.0
            pool = [j for j in alpha if distinct_ratio(j) >= 0.8] or alpha
            jn = max(pool, key=avg_len)
            if avg_len(jn) < 3:
                continue
            jt = None
            best = -1.0
            for j in alpha:
                if j == jn or avg_len(j) > avg_len(jn):
                    continue
                sc = score(j, TEAM_CELL) + (0.25 if abs(j - jn) == 1 else 0.0)
                if sc > best and score(j, TEAM_CELL) >= 0.6:
                    best, jt = sc, j

            # Last / First in two one-word columns beside a longer team
            # column ("1 | Miller | Levi | Belfast 'A' | 10:13"): the wordiest
            # column is then the TEAM, and the name is the pair. The column
            # whose values repeat more is the first name.
            split_name = None

            def one_word(j):
                vals = vals_of(j)
                return vals and sum(1 for v in vals if ' ' not in v.strip()) / len(vals) >= 0.9

            if jn is not None:
                # First | Last in two one-word columns that are themselves
                # the wordiest ("Jeremiah | Sands | Fal"): the column of
                # known first names is the first name
                from .namegender import first_name, BOYS, GIRLS

                def fn_share(c):
                    v = vals_of(c)
                    return sum(1 for x in v if x.lower() in BOYS or x.lower() in GIRLS) / len(v)
                def mostly_one_word(c):  # title rows sit in these columns too
                    v = vals_of(c)
                    return v and sum(1 for x in v if ' ' not in x.strip()) / len(v) >= 0.8

                for j in (jn - 1, jn + 1):
                    if j in alpha and mostly_one_word(j) and mostly_one_word(jn):
                        a, b = fn_share(jn), fn_share(j)
                        if max(a, b) >= 0.35 and abs(a - b) >= 0.25:
                            first, last = (jn, j) if a > b else (j, jn)
                            split_name = (last, first)
                            rest = [c for c in alpha if c not in (j, jn)]
                            jt = max(rest, key=lambda c: score(c, TEAM_CELL) + (
                                0.25 if min(abs(c - j), abs(c - jn)) == 1 else 0), default=None)
                            if jt is not None and score(jt, TEAM_CELL) < 0.6:
                                jt = None
                            jn = None
                            break
            for j in (alpha if split_name is None else []):
                if j + 1 in alpha and one_word(j) and one_word(j + 1) and \
                        jn not in (j, j + 1) and avg_len(jn) > max(avg_len(j), avg_len(j + 1)):
                    def distinct(c):
                        v = vals_of(c)
                        return len(set(v)) / len(v)
                    last, first = (j, j + 1) if distinct(j) >= distinct(j + 1) else (j + 1, j)
                    split_name = (last, first)
                    jt, jn = jn, None
                    break


            rows = []
            dup_left = False
            if not split_name and jn is not None and jn >= 1:
                pairs = [(r[jn - 1], r[jn]) for r in data_rows if jn < len(r) and r[jn]]
                dup_left = len(pairs) >= 5 and sum(1 for a, b in pairs if a == b) >= 0.8 * len(pairs)
            for ri, r in enumerate(grid):
                mark = r[jm] if jm < len(r) else ''
                if split_name:
                    last = r[split_name[0]] if split_name[0] < len(r) else ''
                    first = r[split_name[1]] if split_name[1] < len(r) else ''
                    name = f'{last}, {first}' if last and first else (last or '')   # ("Cloutier |  |  M")
                else:
                    name = r[jn] if jn < len(r) else ''
                    if not name and jn >= 1 and dup_left and jn - 1 < len(r):
                        # (a name cell spanning two columns, read twice, typed
                        # into one of them on this row: "Jay Grant | ''")
                        name = r[jn - 1]
                if not _is_mark_cell(mark, times_only) or not name:
                    continue
                if name.lower() in HEADER_WORDS or not ALPHA_CELL.match(name):
                    continue
                if _is_mark_cell(name, times_only):
                    continue
                mark = _norm_mark(mark)
                if not is_mark(mark):
                    continue
                team = (r[jt] if jt is not None and jt < len(r) else '') or ''
                team = re.sub(r"\s*'[A-Z]'$", '', team)  # relay squad: "Belfast 'A'"
                if team.lower() in HEADER_WORDS:
                    team = ''
                row = {'athlete': str(name), 'school': team, 'result': mark,
                       'grade': '', 'type': 'Finals', '_at': (ri, jm)}
                if getattr(name, 'place', None):
                    row['_pl'] = name.place

                rows.append(row)
            # (a Place column left of the name, "1 | Olivia Tiner": the
            # leftmost all-number column that runs in order)
            run_places = False
            if rows and not any(r.get('_pl') for r in rows):
                left = min(split_name) if split_name else jn
                for pc in range(max(0, (left or 0) - 4), left if left is not None else 0):
                    vals = [grid[r['_at'][0]][pc] if pc < len(grid[r['_at'][0]]) else '' for r in rows]
                    if all(re.fullmatch(r'\d{1,3}(?:\.0)?', v or '') for v in vals):
                        nums = [int(float(v)) for v in vals]
                        # (runs of consecutive places: each column of a
                        # wrapped list, each race of a stacked sheet)
                        runs, a0 = [], 0
                        for k in range(1, len(nums) + 1):
                            if k == len(nums) or nums[k] != nums[k - 1] + 1:
                                runs.append((a0, k))
                                a0 = k
                        if sum(b - a for a, b in runs if b - a >= 3) >= 0.9 * len(nums):
                            run_places = True
                            for a, b in runs:
                                if b - a >= 3:
                                    for r, n in zip(rows[a:b], nums[a:b]):
                                        r['_pl'] = n
                            break
            # (places typed into the name cells, "1. Seekins": kept when they
            # run in order)
            pl = [r.get('_pl') for r in rows]
            pls = [x for x in pl if x]
            keep = len(rows) >= 3 and (run_places or all(pl) and all(b > a or b == 1 for a, b in zip(pls, pls[1:])))
            for r in rows:
                p_ = r.pop('_pl', None)
                if keep:
                    r['place'] = p_
            if len(rows) >= 3:
                yield rows
