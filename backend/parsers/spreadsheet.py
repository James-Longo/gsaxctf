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
ALPHA_CELL = re.compile(r"^[A-Za-z][A-Za-z.',\-/& ]{0,39}$")
# a team cell: a short code (BE, K, TA) or a school name, never a mark
TEAM_CELL = re.compile(r"^[A-Za-z][A-Za-z.'\-/& ]{0,23}$")


def _cells(df):
    """Grid of trimmed strings; NaN becomes ''."""
    out = []
    for row in df.itertuples(index=False):
        out.append(['' if v is None or (isinstance(v, float) and v != v)
                    else re.sub(r'\s+', ' ', str(v)).strip()
                    for v in row])
    return out


def _norm_mark(s):
    """Undo the spreadsheet clock-time artifact: 17:47:00 -> 17:47."""
    m = CLOCK_CELL.match(s)
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
        try:
            from io import StringIO
            tables = pd.read_html(StringIO(text), flavor='lxml')
        except Exception:
            return empty
        if not tables:
            return empty

        gender = self._gender(meet_url, text)
        default_event = '5K Cross Country' if season_type == 'XC' else None

        results = []
        title = None
        for df in tables:
            if df.shape[0] < 3 or df.shape[1] < 2:
                continue
            grid = _cells(df)
            if title is None:
                title = self._title(grid)
            for block in self._blocks(grid, times_only=(season_type == 'XC')):
                results.extend(block)

        if len(results) < 5 or default_event is None:
            # Track meets need an event label per row; without one the rows are
            # unusable, so leave the file for the audit trail rather than
            # inventing an event.
            if default_event is None:
                return empty
        if not results:
            return empty

        seen = set()
        deduped = []
        for r in results:
            k = (r['athlete'], r['school'], r['result'])
            if k in seen:
                continue
            seen.add(k)
            deduped.append(r)

        return {'events': [{'event': default_event, 'gender': gender,
                            'is_relay': False, 'results': deduped}],
                'date': None, 'meet_name': title, 'team_rankings': []}

    # -- helpers ----------------------------------------------------------
    def _gender(self, meet_url, text):
        hay = (os.path.basename(meet_url) + ' ' + text[:3000]).lower()
        if re.search(r'girl|women|female|\bgv\b|\bgirls\b', hay):
            return 'Girls'
        if re.search(r'boy|\bmen\b|male|guys|\bbv\b', hay):
            return 'Boys'
        return 'Boys'

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
            if hits >= 3 and hits / len(vals) >= 0.6:
                mark_cols.append(j)
        if not mark_cols:
            return

        for jm in mark_cols:
            # nearest text column to the left is the name; the one after it the team
            def vals_of(j):
                return [v for v in col(j) if v and v.lower() not in HEADER_WORDS]

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
            alpha = [j for j in range(jm - 1, -1, -1)
                     if score(j, ALPHA_CELL) >= 0.7 and score(j, MARK_CELL) < 0.2]
            if not alpha:
                continue
            jn = max(alpha, key=avg_len)
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

            rows = []
            for r in grid:
                mark = r[jm] if jm < len(r) else ''
                name = r[jn] if jn < len(r) else ''
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
                if team.lower() in HEADER_WORDS:
                    team = ''
                rows.append({'athlete': name, 'school': team, 'result': mark,
                             'grade': '', 'type': 'Finals'})
            if len(rows) >= 3:
                yield rows
