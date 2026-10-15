"""Fixed-width race results laid out under an "=====" ruler (RunScore and
the timing services that use it: Pine Tree Race Services, 5K Sports,
Granite State, ...), common for Maine middle-school and invitational XC
2015-2025:

                     Cumberland County Middle School XC Festival Meet
                                      2 Miles
                               Co-Ed Junior Varsity
    Place TmPl No.  Name                          G School                    Mtime
    ===== ==== ==== ============================= = ========================= =====
        1    1  738 ANDREW WILSON                 m BRUNSWICK MIDDLE SCHOOL   12:35
        2    2  691 AUSTIN JACKMAN                M BRUNSWICK MIDDLE SCHOOL   13:24

The ruler gives every column's exact span, so rows are cut by position
rather than guessed from spacing; the header names the columns (Place,
TmPl = team place, No. = bib, G = sex, Gr/Yr = grade, Ag = age, School /
Team, Time / Mtime / Ftime). A race with a sex column is split into a
Girls and a Boys race (co-ed JV races, girls running in the boys' race).
Title lines above the header name the meet and the distance.
"""
import re
from .base import BaseParser, proper_case_name, proper_case_team

_RULER = re.compile(r'^\s*=+(?: +=+){3,}\s*$')
_TIME = re.compile(r'^(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d+)?$')
_DIST = re.compile(r'(?<![\d,.\-])(\d+(?:\.\d+)?) ?(K|KM|Kilometers?|Miles?|Mi|Meters?|M)\b(?!\s*sports)', re.I)
_WORDS = {'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5'}


def _spans(ruler):
    return [(m.start(), m.end()) for m in re.finditer(r'=+', ruler)]


def _label(head, a, b):
    return head[a:b].strip().lower().rstrip('.:')


def _distance_event(titles):
    for t in titles:
        t2 = re.sub(r'\b(one|two|three|four|five)\b(?=\s+mile)', lambda m: _WORDS[m.group(1).lower()],
                    t, flags=re.I)
        m = _DIST.search(t2)
        if not m:
            continue
        v, unit = m.group(1), m.group(2).lower()
        if unit.startswith('k'):
            return f'{v}k Run CC'
        if unit.startswith('mi'):
            return f'{v} Mile Run CC'
        if unit.startswith('met') or (unit == 'm' and float(v) >= 1000):
            return f'{v} Meter Run CC'
    return 'Run CC'


class RulerTableParser(BaseParser):
    @staticmethod
    def matches(text):
        lines = (text or '').splitlines()
        for a, b in zip(lines, lines[1:]):
            if _RULER.match(b) and re.search(r'\bName\b', a, re.I) and re.search(r'\bPl(ace)?\b', a, re.I):
                return True
        return False

    def parse(self, text, meet_url, season_type):
        empty = {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}
        if '<' in text[:2000]:
            text = re.sub(r'<[^>]+>', '', text)
            text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        lines = text.replace('\xa0', ' ').splitlines()
        if not self.matches('\n'.join(lines)):
            return empty
        sections = []          # {'titles': [...], 'rows': [...]}
        cols = None
        titles = []
        for i, line in enumerate(lines):
            if i + 1 < len(lines) and _RULER.match(lines[i + 1]) and re.search(r'\bName\b', line, re.I):
                spans = _spans(lines[i + 1])
                cols = self._columns(line, spans)
                sections.append({'titles': [t for t in titles if t], 'rows': [],
                                 'cols': cols})
                titles = []
                continue
            if _RULER.match(line):
                continue
            s = line.strip()
            if not s:
                continue
            if cols is not None and re.match(r'^\d{1,4}\s', s):
                row = self._row(line, sections[-1]['cols']) or \
                    self._row(line, self._shifted(line, sections[-1]['cols']))
                if row:
                    sections[-1]['rows'].append(row)
                    continue
            # a title line (meet, distance, race) or page furniture
            if not re.match(r'^page\s+\d+$', s, re.I) and len(s) < 90:
                titles.append(s)
        if not sections:
            return empty
        # page breaks repeat the titles and ruler: places carry on
        races = []
        for sec in sections:
            if not sec['rows']:
                continue
            prev = races[-1] if races else None
            if prev and sec['rows'][0]['place'] > 1 and \
                    sec['rows'][0]['place'] > prev['rows'][-1]['place'] and \
                    (not sec['titles'] or set(sec['titles']) <= set(prev['titles']) or
                     # (a page 2 whose header differs - "2.0 Miles" for "1.9" -
                     # but whose places carry straight on)
                     sec['rows'][0]['place'] == prev['rows'][-1]['place'] + 1 and
                     not re.search(r'(?i)\b(girls?|boys?|women|men)\b', ' '.join(sec['titles']))):
                prev['rows'].extend(sec['rows'])
                continue
            races.append({'titles': sec['titles'] or (prev['titles'] if prev else []),
                          'rows': list(sec['rows'])})
        from backend.parser import normalize_grade
        url_low = (meet_url or '').lower()
        file_gender = ('Girls' if re.search(r'girl|women', url_low)
                       else 'Boys' if re.search(r'boy|\bmen', url_low) else None)
        events = []
        for r in races:
            title_text = ' '.join(r['titles'])
            tg = ('Girls' if re.search(r'\b(girls?|women)\b', title_text, re.I)
                  else 'Boys' if re.search(r'\b(boys?|men)\b', title_text, re.I) else None)
            event = _distance_event(r['titles'])
            by_g = {}
            from .namegender import name_gender
            for row in r['rows']:
                sex = row.pop('sex', None)
                g = sex or tg or file_gender or 'Boys'
                # a sex cell typed wrong ("ISAAC SHEAN  F" / "KENZIE SHEAN  M",
                # siblings swapped): a decisive first name wins - over a
                # sex cell only, never over the race's own gender
                ng = name_gender(row['athlete'], strict=True)
                if sex and ng and ng != g and not row.get('team_place'):
                    g = ng
                row['grade'] = normalize_grade(row.get('grade', ''))
                by_g.setdefault(g, []).append(row)
            # (both halves of a co-ed field carry one id: its team scores
            # may have been figured on the whole field)
            mid = len(events)
            for g in ('Girls', 'Boys'):
                if by_g.get(g):
                    ev = {'event': event, 'gender': g, 'is_relay': False, 'results': by_g[g]}
                    if len(by_g) > 1:
                        ev['mixed_race'] = mid
                    events.append(ev)
        meet_name = races[0]['titles'][0] if races and races[0]['titles'] else None
        date = None
        dm = re.search(r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b', '\n'.join(lines[:30]))
        if dm:
            y = dm.group(3) if len(dm.group(3)) == 4 else '20' + dm.group(3)
            date = f'{y}-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}'
        return {'events': events, 'date': date, 'meet_name': meet_name, 'team_rankings': []}

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _columns(head, spans):
        """Name each ruler span from the header text above it."""
        cols = []
        for k, (a, b) in enumerate(spans):
            # header words may start a little left of their ruler (right-
            # aligned numbers) - read up to the next span's start
            lo = a if k == 0 else max(spans[k - 1][1], a - 2)
            hi = spans[k + 1][0] if k + 1 < len(spans) else len(head)
            # (a header typed a column left of its ruler, "No. Name" over
            # "==== ====": a word cut at either end belongs to its neighbour)
            if 0 < hi < len(head) and head[hi - 1] != ' ' and head[hi] != ' ':
                h2 = hi
                while h2 > lo and head[h2 - 1] != ' ':
                    h2 -= 1
                if head[lo:h2].strip():
                    hi = h2
            if 0 < lo < len(head) and head[lo - 1] != ' ' and head[lo] != ' ' and k > 0:
                l2 = lo
                while l2 < hi and head[l2] != ' ':
                    l2 += 1
                # the cut word starts in the previous span: keep it whole here
                # only when this span has nothing else
                if head[l2:hi].strip():
                    lo = l2
                else:
                    while lo > 0 and head[lo - 1] != ' ':
                        lo -= 1
            lab = _label(head, lo, hi)
            cols.append((a, b, lab))
        return cols

    @staticmethod
    def _shifted(line, cols):
        """A name holding a character the export counted as several bytes
        ("Dickson\u2010Smith") pulls the rest of its row left: re-anchor the
        columns after the name on where the row's time actually starts."""
        tcol = next((c for c in cols if c[2] in ('time', 'mtime', 'ftime', 'final', 'finals',
                                                 'net', 'gun', 'chip', 'nettime')), None)
        m = list(re.finditer(r'(?<!\S)(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d+)?(?!\S)', line))
        if not tcol or not m:
            return cols
        delta = min((x.start() - tcol[0] for x in m), key=abs)
        if not delta or abs(delta) > 4:
            return cols
        out, after = [], False
        for a, b, lab in cols:
            if after:
                a, b = a + delta, b + delta
            out.append((a, b, lab))
            if lab == 'name':
                after = True
        return out

    def _row(self, line, cols):
        cells = {}
        order = []
        # a row typed one column left of the ruler ("431 RYAN" over
        # "==== ====="): a cut that leaves a word's first letter or two in
        # the cell before moves back to the word's start
        starts = [a for a, _b, _l in cols]
        for k in range(1, len(starts)):
            a = starts[k]
            if 0 < a < len(line) and line[a - 1] != ' ' and line[a] != ' ':
                t0 = a
                while t0 > 0 and line[t0 - 1] != ' ':
                    t0 -= 1
                if a - t0 <= 2 and t0 > starts[k - 1] and line[t0:a].isalpha() and line[a].isalpha():
                    starts[k] = t0
        cols = [(starts[k], b, lab) for k, (a, b, lab) in enumerate(cols)]
        for k, (a, b, lab) in enumerate(cols):
            hi = cols[k + 1][0] if k + 1 < len(cols) else len(line)
            v = line[a:hi].strip()
            order.append((lab, v, a))
        # a long name pushes "SO CHRHS" right: the grade ends the name cell,
        # the school's first letters sit in the grade cell
        labs = [o[0] for o in order]
        gi = next((i for i, l in enumerate(labs) if l in ('gr', 'yr', 'grade', 'grd', 'cl')), None)
        ni = labs.index('name') if 'name' in labs else None
        if gi is not None and ni is not None and gi == ni + 1 and gi + 1 < len(order) and \
                order[gi + 1][0] in ('school', 'team', 'club', 'affiliation', 'school/club'):
            mg = re.match(r'^(.*\S)\s+(FR|SO|JR|SR|\d{1,2})$', order[ni][1])
            if mg and not re.fullmatch(r'(?i)FR|SO|JR|SR|\d{1,2}', order[gi][1]):
                a_g, a_s = order[gi][2], order[gi + 1][2]
                hi = next((c[0] for c in cols if c[0] > a_s), len(line))
                order[ni] = ('name', mg.group(1), order[ni][2])
                order[gi] = (order[gi][0], mg.group(2), a_g)
                order[gi + 1] = (order[gi + 1][0], re.sub(r'\s+', ' ', line[a_g:hi].strip()), a_s)
        place = None
        row = {'type': 'Finals'}
        name = school = mark = None
        one_letter = []
        for lab, v, a in order:
            if lab in ('place', 'pl', 'plc', 'pos', 'overall') and place is None:
                if not re.fullmatch(r'\d{1,4}', v):
                    return None
                place = int(v)
            elif lab in ('tmpl', 'tm pl', 'tpl', 'team pl'):
                if re.fullmatch(r'\d{1,4}', v):
                    row['team_place'] = int(v)
            elif lab == 'name':
                name = v
            elif lab in ('school', 'team', 'club', 'affiliation', 'city', 'school/club'):
                school = v
            elif lab in ('time', 'mtime', 'ftime', 'final', 'finals', 'net', 'gun', 'chip', 'jv', 'nettime'):
                # (a cell cut out of the middle of a number is a shifted row;
                # a school run up to the time - "PORTLAND10:15" - is not)
                if _TIME.match(v) and not (a > 0 and re.match(r'[\d:.]', line[a - 1:a]) and line[a:a + 1].strip()):
                    mark = v
            elif lab in ('gr', 'yr', 'grade', 'grd', 'cl'):
                if re.fullmatch(r'\d{1,2}|FR|SO|JR|SR', v, re.I):
                    row['grade'] = v.upper()
            elif len(lab) == 1 or lab in ('sex', 'gen', 'g/a'):
                one_letter.append(v)
        # single-letter columns: M/F is the sex, a number the grade
        for v in one_letter:
            if v.upper() in ('M', 'F', 'B', 'G', 'W') and 'sex' not in row:
                row['sex'] = 'Girls' if v.upper() in ('F', 'G', 'W') else 'Boys'
            elif re.fullmatch(r'\d{1,2}', v) and not row.get('grade'):
                row['grade'] = v
        if place is None or not name or not mark or not re.search(r'[A-Za-z]', name):
            return None
        row['place'] = place
        row['athlete'] = proper_case_name(name) if name.isupper() else name
        row['school'] = proper_case_team(school or '')
        row['result'] = mark
        row.setdefault('grade', '')
        return row
