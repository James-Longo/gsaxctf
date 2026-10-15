"""Hand-typed cross-country place lists with no event header and no column
ruler - the long tail of school-posted results on sub5 (2003-2024):

    Boys XC @ Cape Elizabeth (Gull Crest Course)          (name, code, time)
    1. Rand              CE     15:39
    1. Michaela Swiatek 18:42 Y          36. Stella Fillmore 26:07 LR
    1. Molly Peverada (HA) ..........16:38                (agate school)
    1 Butler, Braden         M    17:47    Marshwood        34
    1. Levi Miller (Bel) 15:56; 2. Joey Dewitt (Ell) 16:17; 3. ...

Rows are found anywhere on a line (lists are often printed in two or three
columns, or run together as a paragraph): a place number starts a row and
the row's time anchors it. Columns are merged when their places continue
(1-35 | 36-70); a column that restarts at 1 is the other race (a "Girls
Results / Boys Results" page). Race gender comes from the nearest gender
title, else the file name; the distance from a title line.

XC only, and last in the chain: it sees only files every structured parser
gave up on.
"""
import re
from .base import BaseParser, proper_case_name, proper_case_team

_TIME = re.compile(r'(?<![\d:.])(\d{1,2}[:;]\d{2}(?:\.\d{1,2}|:00)?)(?![\d:])')   # "20;03": a typo; "23:07:00": a clock
_START = re.compile(r'(?:(?<=\s)|^)(\d{1,3})(?:\.\)\s*|[.)]\s*|:\s+|\s+\.\s+|\s+)(?=[A-Za-z(]|[)’\']+[A-Za-z])')   # "2.Jason", "48: B. Taylor", "31. )’Louglin" too
_GENDER = re.compile(r"\b(girl'?s?|boy'?s?|women'?s?|men'?s?)\b", re.I)
_DIST = re.compile(r'(?<![\d,.\-])(\d+(?:\.\d+)?) ?(k\b|km\b|miles?|mi\b)(?!\s*sports)', re.I)   # not "Sawyer-7   K\"
_COMBINED = re.compile(r'all\s+classes\s+combined|combined\s+results|cominbined|'
                       r'new\s+england\s+qualif|combined\s+state\s+meet|'
                       r'grade[\s_-]+list|results\s+by\s+grade', re.I)   # (re-rankings of a race)
_NOISE = re.compile(r'\b(?:record(?!,)|scores?|points|total|average|weather|conditions|'
                    r'distance|course|site|date|place\s+name)\b|\bteams?:', re.I)   # (not "Sabine Sites")


def _secs(t):
    if not t:
        return None     # a time cut short at the source ("16:2"): no time
    p = [float(x) for x in t.split(':')]
    return p[0] * 60 + p[1] if len(p) == 2 else p[0] * 3600 + p[1] * 60 + p[2]


def _gender_of(text):
    m = None
    for m in _GENDER.finditer(text):
        pass
    if not m:
        return None
    w = m.group(1).lower()
    return 'Girls' if w.startswith(('girl', 'women')) else 'Boys'


class XCListParser(BaseParser):
    def parse(self, text, meet_url, season_type):
        empty = {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}
        if season_type != 'XC' or not text:
            return empty
        if '<' in text[:3000]:
            # (an Excel page's style sheet and comments are no rows)
            text = re.sub(r'(?is)<(style|script|head)\b.*?</\1>|<!--.*?-->', ' ', text)
            if not re.search(r'<pre\b', text, re.I):
                # (source line wraps are HTML whitespace: "Fox\nIsland  15:24")
                text = re.sub(r'[\r\n]+', ' ', text)
            if re.search(r'(?i)<t[dh]\b[^>]*>\s*time\s*</t[dh]>', text):
                # (a Time cell typed "16 51": minutes and seconds)
                text = re.sub(r'(?i)(<td\b[^>]*>)\s*([1-5]?\d) ([0-5]\d)\s*(</td>)', r'\1\2:\3\4', text)
                # (a Time cell typed "2128" among "17:54" or none: the colon left out)
                text = re.sub(r'(?i)(<td\b[^>]*>)\s*((?:[89]|[1-5]\d))([0-5]\d)\s*(</td>)', r'\1\2:\3\4', text)
            text = re.sub(r'<br\s*/?>|</p>|</tr>|<tr\b[^>]*>|</div>|</h\d>|</li>', '\n', text, flags=re.I)
            # (inline tags inside a cell are no word break: "Coll<span>ier</span>")
            text = re.sub(r'(?i)</?(?:span|font|b|i|u|em|strong)\b[^>]*>', '', text).replace('\ufffd', ' ')
            text = re.sub(r'<[^>]+>', ' ', text).replace('&nbsp;', ' ').replace('&amp;', '&')
        # a timer's "18m 4s 980ms"
        text = re.sub(r'\b(\d{1,2})m\s+(\d{1,2})s\s+(\d{1,3})ms\b',
                      lambda m: f'{m.group(1)}:{int(m.group(2)):02d}.{m.group(3).rjust(3, "0")[:2]}', text)
        # minutes and seconds in two columns ("Min Sec" / "17 31.4"), a
        # sex column before the name ("1   B   McClintock, Matt")
        if re.search(r'(?im)\bmin\s+sec\b', text):
            text = re.sub(r'(?<=\s)(\d{1,2})\s+([0-5]\d\.\d{1,2})(?=\s|$)', r'\1:\2', text)
            if re.search(r'(?im)\bgender\s+name\b', text):
                text = re.sub(r'(?m)^(\s*\d{1,3})\s+[BGMF]\s{2,}(?=[A-Za-z])', r'\1   ', text)
        # "First  Last  Grade  Gender  Team  Finals  Points" with the points
        # column the finish position and no place column
        mh = re.search(r'(?im)^\s*first\s+last\b.*\bteam\s+(?:finals|time)\s+points\s*$', text)
        if mh:
            fl = re.compile(r"(?m)^(\s*)([A-Za-z][\w'.-]*)\s+([A-Za-z][\w'.-]*(?: [A-Za-z][\w'.-]*)?)\s+(?:\d{1,2}\s+)?[MFBG]\s+"
                            r"(\S.*?)\s+(\d{1,2}:\d{2}(?:\.\d+)?)\s+(\d{1,3})\s*$")
            text = text[:mh.end()] + fl.sub(lambda m: f"{m.group(1)}{m.group(6)}. {m.group(2)} {m.group(3)}   "
                                                      f"{m.group(4).strip()}   {m.group(5)}", text[mh.end():])
        # Zone4 print: the team on the line under the runner, after a bib
        # ("1   Teanne Ewings      20:40.6" / "    6 Houlton/GHCA")
        zl = text.split('\n')
        zrow = re.compile(r'^(\s*\d{1,3}\s+[A-Za-z][^\d\n]*?)\s{2,}(\d{1,2}:\d{2}(?:\.\d{1,2})?)\s*$')
        zteam = re.compile(r'^\s+\d{1,4}\s+([A-Za-z][^\d\n]*?)\s*$')
        if sum(1 for a, b in zip(zl, zl[1:]) if zrow.match(a) and zteam.match(b)) >= 5:
            out, k = [], 0
            while k < len(zl):
                ma = zrow.match(zl[k])
                mb = zteam.match(zl[k + 1]) if ma and k + 1 < len(zl) else None
                if ma and mb:
                    out.append(f'{ma.group(1)}   {mb.group(1)}   {ma.group(2)}')
                    k += 2
                    continue
                out.append(zl[k])
                k += 1
            text = '\n'.join(out)
        # RunScore rows without their header: "  1    1  255 Alec Troxell
        # M Deering   16:31" (place, team place, bib, name, sex, team)
        rs_row = re.compile(r'(?m)^(\s*)(\d{1,3})\s+(\d{1,3})?\s+\d{1,4}\s+([A-Z][^\d\n]*?)\s{2,}([MFBGW])\s([A-Z][^\n]*?)\s{2,}(\d{1,2}:\d{2}(?:\.\d+)?)\s*$')
        # Hy-Tek "Place Comp# Name School Time" rows, the bib before a
        # "Last, First" name ("1   113  Sholl, Bethany   Scarborough ...")
        hy_row = re.compile(r"(?m)^(\s*)(\d{1,3})\s+\d{1,4}\s+([A-Z][A-Za-z'.-]+,\s?[A-Za-z][^\d\n]*?)\s{2,}"
                            r"([A-Z][^\d\n]*?)\s{2,}(\d{1,2}:\d{2}(?:\.\d+)?)((?:\s+\d{1,3})?)\s*$")
        # "1    13 Sam Wilson   16:26.34 5:18 Greely   12": place, bib, name,
        # time, pace, team, grade (two lists side by side keep their columns)
        pb_row = re.compile(r"(?<![\S])(\d{1,3})\s+\d{1,4}\s+([A-Z][^\d\n:]*?)\s+(\d{1,2}:\d{2}\.\d{1,2})"
                            r"\s+\d{1,2}:\d{2}\s+([A-Z][A-Za-z'.\-/ ]*?)\s+(\d{1,2})(?=\s|$)")
        # "14:11   Addison Coty   1   Calais": time, name, place, team
        tf_row = re.compile(r"(?m)^[ \t`']*(\d{1,2}[:;]\d{2}(?:\.\d{1,2})?)[ \t]+([A-Za-z][^\d\n]*?)[ \t]{2,}(\d{1,3})"
                            r"[ \t]{2,}([A-Za-z][^\d\n]*?)[ \t]*$")
        if len(tf_row.findall(text)) >= 10:
            text = tf_row.sub(lambda m: f"{m.group(3)}. {m.group(2).strip()}   {m.group(4).strip()}   "
                                        f"{m.group(1).replace(';', ':')}", text)
        # "13:11   1    4     Ewings, Teanne   GHCA   1": time, place, bib, name,
        # team, points (two lists side by side keep their columns)
        tpb_row = re.compile(r"(?<!\S)(\d{1,2}:\d{2}(?:\.\d{1,2})?)[ \t]+(\d{1,3})[ \t]+\d{1,4}[ \t]+([A-Z][^\d\n:]*?)[ \t]{2,}"
                             r"([A-Z][A-Za-z/.'\- ]*?)[ \t]+(?:\d{1,3}|-)(?=[ \t]|$)", re.M)
        if len(tpb_row.findall(text)) >= 10:
            text = tpb_row.sub(lambda m: f"{m.group(2)}. {m.group(3).strip()}   {m.group(4).strip()}   "
                                         f"{m.group(1)}".ljust(len(m.group(0))), text)
        # "  2   2  M Holt-Andrews, Joe   T  1   0:18:03 0:05:49": overall
        # place, place within the sex, sex, name, team, score, time, pace
        ops_row = re.compile(r"(?m)^[ \t]*\d{1,3}[ \t]+(\d{1,3})[ \t]+[MFBG][ \t]+([A-Z][^\d\n]*?)[ \t]{2,}"
                             r"([A-Za-z]{1,4})[ \t]+(?:(\d{1,3})[ \t]+)?0?:?(\d{1,2}:\d{2})[ \t]+\d{1,2}:\d{2}(?::\d{2})?[ \t]*$")
        if len(ops_row.findall(text)) >= 10:
            text = ops_row.sub(lambda m: f"{m.group(1)}. {m.group(2).strip()}   {m.group(3)}   {m.group(5)}"
                                         + (f"   {m.group(4)}" if m.group(4) else ''), text)
        # "Cole Winslow  GHCA  40  0:01:00  0:20:22.5  0:19:22.5   1   1":
        # name, team, bib, start, clock, elapsed, place, team place
        ntb_row = re.compile(r"(?m)^[ \t]*([A-Z][^\d\n]*?)[ \t]{2,}([A-Za-z][A-Za-z/.]{0,5})[ \t]+\d{1,4}[ \t]+"
                             r"\d:\d{2}:\d{2}[ \t]+\d:\d{2}:\d{2}(?:\.\d)?[ \t]+0?:?(\d{1,2}:\d{2}(?:\.\d)?)[ \t]+"
                             r"(\d{1,3})(?:[ \t]+(\d{1,3}))?[ \t]*$")
        if len(ntb_row.findall(text)) >= 10:
            text = ntb_row.sub(lambda m: f"{m.group(4)}. {m.group(1).strip()}   {m.group(2)}   {m.group(3)}"
                                         + (f"   {m.group(5)}" if m.group(5) else ''), text)
        if len(pb_row.findall(text)) >= 10:
            text = pb_row.sub(lambda m: f"{m.group(1)}. {m.group(2).strip()}   {m.group(4).strip()}   "
                                        f"{m.group(3)}".ljust(len(m.group(0))), text)
        if len(hy_row.findall(text)) >= 10:
            text = hy_row.sub(lambda m: f"{m.group(1)}{m.group(2)}. {m.group(3).strip()}   {m.group(4).strip()}   "
                                        f"{m.group(5)}{m.group(6)}", text)
        if len(rs_row.findall(text)) >= 10:
            text = rs_row.sub(lambda m: f"{m.group(1)}{m.group(2)}. {m.group(4).strip()}   {m.group(6).strip()}   "
                                        f"{m.group(7)}" + (f"   {m.group(3)}" if m.group(3) else ''), text)
        # a PDF word ending in a tab breaks its line ("7 Serena\t" /
        # "   Blasios   17:18   Medomak"): the row goes on
        text = re.sub(r'\r(?!\n)', ' ', text)          # (a lone CR inside a row: "Serena\t\r Blasios")
        text = re.sub(r'(?<=\S)( *)\t[ \t]*\n[ \t\xa0]*(?=\S)', lambda m: m.group(1) or ' ', text)
        # a first name alone on the place's line, the rest of the row on
        # the next ("2.   Natalie" / "     Coleman   Bucksport   20:29")
        # ("9. Violet Mahar" / "   Mahar-Little  MSSM  24:10": the wrap
        # repeats the cut word - "Jeannelle" / "elle Ross", "Cars" / "Carson")
        lone = r'\s*\d{1,3}\.\s+[A-Za-z][\w\'-]*(?: [A-Za-z][\w\'-]*){0,2}\s*'
        if re.search(r'(?m)^' + lone + '$', text):
            ls = text.split('\n')
            out, k = [], 0
            while k < len(ls):
                l = ls[k]
                if re.fullmatch(lone, l):
                    j = k + 1
                    while j < len(ls) and not ls[j].strip():
                        j += 1
                    if j < len(ls) and re.match(r'^\s*[A-Za-z]', ls[j]) and _TIME.search(ls[j]) and \
                            not re.match(r'^\s*\d', ls[j]):
                        head, nxt = l.rstrip(), ls[j].strip()
                        a = head.split()[-1]
                        b = nxt.split()[0]
                        if len(head.split()) >= 2 and len(a) >= 3 and len(b) >= 3:
                            if b.startswith(a):
                                head = head[:-len(a)].rstrip()
                            elif a.endswith(b):
                                nxt = nxt[len(b):].lstrip()
                        out.append(head + ' ' + nxt)
                        k = j + 1
                        continue
                out.append(l)
                k += 1
            text = '\n'.join(out)
        # seconds only under a full time ("18:01" then ":10", ":18"): the
        # minutes carry down the list
        if len(re.findall(r'(?<=\s):\d\d(?=\s|$)', text, re.M)) >= 5:
            out, last = [], None
            for l in text.split('\n'):
                mm = re.search(r'(?<![\d:])(\d{1,2}):\d\d(?![\d:])', l)
                if mm:
                    last = mm.group(1)
                elif last:
                    l = re.sub(r'(?<=\s):(\d\d)(?=\s|$)', lambda m: f'{last}:{m.group(1)}', l, count=1)
                out.append(l)
            text = '\n'.join(out)
        # a sheet typed with decimal points for colons ("16.04", "17.3" =
        # 17:30, "17.59.47"), and no colon time anywhere
        if len(re.findall(r'\d:\d\d', text)) <= 3:     # (a course record in the header)
            dots = re.compile(r'(?<![\d.])([1-5]\d|[5-9])\.(\d{1,2})(\.\d{1,2})?(?![\d.])(?!\s*(?:mi|k\b|km|miles?))', re.I)
            if len(dots.findall(text)) >= 10:
                text = dots.sub(lambda m: f'{m.group(1)}:{m.group(2).ljust(2, "0")}' + (m.group(3) or ''), text)
        # times typed as bare digits ("01 GREEN   Y   1610" = 16:10): on a
        # page with no colon time, a 3-4 digit cell after a code that rises
        # down the list is mm:ss
        if len(re.findall(r'\d:\d\d', text)) <= 3:
            bare = re.compile(r'(?<=[A-Za-z.]\s)(\s*)([1-5]?\d)([0-5]\d)(?=\s{2,}|\s*$)', re.M)
            vals = [int(m.group(2)) * 60 + int(m.group(3)) for m in bare.finditer(text)]
            if len(vals) >= 15 and len(set(vals)) >= 0.6 * len(vals) and \
                    sum(1 for a, b in zip(vals, vals[1:]) if b >= a) >= 0.7 * (len(vals) - 1) \
                    and all(360 <= v <= 3600 for v in vals):
                text = bare.sub(lambda m: f'{m.group(1)}{int(m.group(2))}:{m.group(3)}', text)
        # "Name  School  Place  Time  Score" (GNG meet sheets): the place
        # after the school - set it first, keep the team points
        raw = text.splitlines()
        hdr = [i for i, l in enumerate(raw) if re.search(r'(?i)\bname\b.*\bschool\s+place\s+time\b', l)]
        if hdr:
            row = re.compile(r'^\s*(\S.*?\S)\s{2,}(\d{1,3})\s+(\d{1,2}:\d{2}(?:\.\d+)?)(?:\s+(\d{1,3})(?!\S))?')
            last = 0
            for i in range(hdr[0] + 1, len(raw)):
                if re.search(r'(?i)\bname\b.*\bschool\s+place\s+time\b', raw[i]):
                    last = 0            # (the next race's sheet)
                mr = row.match(raw[i])
                if mr:
                    cells = re.split(r'\s{2,}', mr.group(1))
                    name, school = ' '.join(cells[:-1]) if len(cells) > 1 else cells[0], cells[-1] if len(cells) > 1 else ''
                    # (a place typed twice - "2", "2" for 2, 3 - is the row's turn)
                    pl = int(mr.group(2))
                    pl = pl if pl > last else last + 1
                    last = pl
                    raw[i] = f"{pl}. {name}  {school}  {mr.group(3)}" + (f"  {mr.group(4)}" if mr.group(4) else '')
            text = '\n'.join(raw)
        # a list typed without places, one runner a line in finish order
        # ("H Pierce-M- 20:12", "Roberge-28:07", "Cost -M- 19:00"): the
        # line's position is its place
        raw = text.splitlines()
        unnum = re.compile(r"^\s*([A-Za-z][A-Za-z .,'’]{0,30}?)\s*(?:[-,]+\s*([A-Z][A-Za-z]{0,3})\s*-?\s*|[-,]\s*|\s+)"
                           r"(\d{1,2}:\d{2}(?:\.\d{1,2})?)\s*$")
        # ("Dunn         K          17:27": the code in a column of its own)
        unnum2 = re.compile(r"^\s*([A-Za-z][A-Za-z .,'’-]{0,30}?)\s{2,}([A-Z][A-Za-z]{0,3})\s{2,}"
                            r"(\d{1,2}:\d{2}(?:\.\d{1,2})?)\s*$")
        if not any(re.match(r'^\s*\d{1,3}[.)]?\s+[A-Za-z]', l) for l in raw):
            hits = [i for i, l in enumerate(raw) if unnum.match(l) and '-' in l or unnum2.match(l)]
            if len(hits) >= 10 and hits[-1] - hits[0] < 1.3 * len(hits):
                k = 0
                codes = sorted({m.group(2) for l in raw for m in [unnum2.match(l)] if m}, key=len, reverse=True)
                for i in range(hits[0], hits[-1] + 1):
                    mu = unnum2.match(raw[i]) or unnum.match(raw[i])
                    if mu:
                        k += 1
                        raw[i] = f"{k}. {mu.group(1).strip(' ,')}  {mu.group(2) or ''}  {mu.group(3)}"
                        continue
                    # a name run into its code ("Walker-EldersC   23:38")
                    mg = re.match(r'^\s*([A-Za-z][A-Za-z .,\'’-]*[a-z])([A-Z][A-Za-z]{0,3})\s+(\d{1,2}:\d{2}(?:\.\d{1,2})?)\s*$', raw[i])
                    if mg and mg.group(2) in codes:
                        k += 1
                        raw[i] = f"{k}. {mg.group(1)}  {mg.group(2)}  {mg.group(3)}"

                text = '\n'.join(raw)
        # (pdftotext ends each page with a form feed: columns unfold per page)
        lines = [l.rstrip() for page in text.replace('\xa0', ' ').split('\f')
                 for l in self._unfold_columns(page.splitlines())]
        # an "all classes combined" / New England qualifier list re-ranks
        # runners whose class races are posted separately: not a race
        if not getattr(self, 'allow_aggregate', False) and (
                _COMBINED.search(' '.join(lines[:20])) or re.search(r'combined|grade[-_]list', meet_url or '', re.I)):
            return empty
        # per-team score sheets ("Team: Freeport" / Place Score Name Time)
        # repeat the runners of the results file beside them
        if sum(1 for l in lines if re.match(r'^\s*Team:\s*\S', l)) >= 2:
            return empty
        url_low = (meet_url or '').lower()
        file_g = ('Girls' if re.search(r'girl|women', url_low)
                  else 'Boys' if re.search(r'boy|\bmen', url_low) else None)
        races = []                  # {'gender', 'cols': {col: {place: row}}, 'titles'}
        pending = []
        titles = []
        title_genders = []          # gender words of the current title block, in order

        def new_race(g):
            races.append({'gender': g, 'cols': {}, 'titles': list(titles), 'tg': list(title_genders)})

        for line in lines:
            s = line.strip()
            if not s:
                continue
            rows = self._rows(line)
            if not rows:
                if len(s) < 120:
                    titles.append(s)
                    g = _gender_of(s)
                    if g and not _TIME.search(s):
                        gs = [_gender_of(m.group(0)) for m in _GENDER.finditer(s)]
                        # "Girls Results            Boys Results": two races side by side
                        title_genders = gs if len(gs) > 1 else [g]
                        if races and any(races[-1]['cols'].values()):
                            new_race(g)
                        elif races:
                            races[-1]['gender'] = g
                continue
            if not races:
                new_race(title_genders[0] if title_genders else None)
            race = races[-1]
            for col, place, row in rows:
                colmap = race['cols'].setdefault(col, {})
                if col == 0 and place == 1 and colmap:
                    # the list restarts: the next race (gender from the
                    # titles since, else the other one)
                    new_race(None)
                    race = races[-1]
                    colmap = race['cols'].setdefault(col, {})
                seen = {k: v for c, m in race['cols'].items() if c != col for k, v in m.items()}
                seen.update(colmap)
                prev = max((k for k in seen if k < place), default=None)
                if place in seen and place not in colmap or \
                        prev is not None and row['result'] and seen[prev]['result'] and \
                        _secs(row['result']) < _secs(seen[prev]['result']) - 90:
                    # faster than the place before it: another race's rows
                    # printed beside this one (the boys' 37-44 next to the
                    # girls' list) - placed once every race is read
                    pending.append((colmap, row))
                    continue
                colmap.setdefault(place, row)
            titles = []
        for home, row in pending:
            p, t = row['place'], _secs(row['result'])
            for r in reversed(races) if t is not None else []:
                allrows = {k: v for c in r['cols'].values() for k, v in c.items()}
                if p in allrows:
                    continue
                lo = max((k for k in allrows if k < p), default=None)
                hi = min((k for k in allrows if k > p), default=None)
                if lo is None or (_secs(allrows[lo]['result']) or 0) > t + 5 or \
                        hi is not None and (_secs(allrows[hi]['result']) or 1e9) < t - 5:
                    continue
                col = next(c for c, m in r['cols'].items() if lo in m)
                r['cols'][col][p] = row
                break
            else:
                home.setdefault(p, row)    # nowhere better: a typo, keep it
        # a page break repeats the race's title: places that carry on
        # (50 | Page 2 / Boys / 51 ...) are the same race
        merged = []
        for r in races:
            prev = merged[-1] if merged else None
            places = [p for c in r['cols'].values() for p in c]
            pprev = [p for c in prev['cols'].values() for p in c] if prev else []
            if prev and places and pprev and r['gender'] in (prev['gender'], None) and \
                    0 < min(places) - max(pprev) <= 3:
                for c, m in r['cols'].items():
                    prev['cols'].setdefault(c, {}).update(m)
                continue
            merged.append(r)
        races = merged
        # merge columns: continuing places join, a restart is another race
        out = []
        for r in races:
            cols = [r['cols'][c] for c in sorted(r['cols']) if r['cols'][c]]
            if not cols:
                continue
            groups = [dict(cols[0])]
            for c in cols[1:]:
                if min(c) > max(groups[-1]) or min(c) > 1 and not set(c) & set(groups[-1]):
                    groups[-1].update(c)
                else:
                    groups.append(dict(c))
            tg = r.get('tg') or []
            for gi, grp in enumerate(groups):
                # ("Boys Individual ...   Girls Individuals ...": a list per
                # gender side by side, in the title's order)
                g = tg[gi] if len(tg) == len(groups) > 1 and len(set(tg)) > 1 else r['gender']
                out.append({'gender': g, 'titles': r['titles'], 'rows': grp,
                            'col_index': gi})
        # genders: explicit, else alternate from a two-gender title, else file
        events = []
        prev_g = None
        all_titles = ' '.join(l for l in lines[:40])
        order = [_gender_of(m.group(0)) for m in _GENDER.finditer(all_titles)]
        guessed = set()
        for k, r in enumerate(out):
            g = r['gender']
            if g is None:
                guessed.add(k)
                if prev_g and any(re.match(r'(race|heat|section|flight)\s*#?\s*\d+\s*$', t, re.I)
                                  for t in r['titles']):
                    g = prev_g      # "Race 1 ... Race 7" of one gender's meet
                elif prev_g:
                    g = 'Boys' if prev_g == 'Girls' else 'Girls'
                elif order:
                    g = order[0]
                else:
                    g = file_g or 'Boys'
            prev_g = g
            rows = [r['rows'][p] for p in sorted(r['rows'])]
            # trailing integers after the time: "...18:02.52   3   1" (class,
            # team place) on most rows -> the last is the team place; a lone
            # number on most rows that runs 1, 2, 3 ... is the team place
            # "7 Serena  Blasios  17:18  Medomak": the team after the time
            # where the other rows of the race put theirs
            from collections import Counter as _C
            rts = [x.get('_rt') for x in rows]
            sc_cnt = _C(x['school'] for x in rows)
            rt_cnt = _C(r for r in rts if r)
            if sum(1 for x in rows if x.get('_rt') and x['school'] == x['_rt']) >= 0.5 * len(rows):
                for x in rows:
                    rt = x.get('_rt')
                    if rt and x['school'] != rt and rt_cnt[rt] >= 2 and sc_cnt[x['school']] <= 1:
                        x['athlete'] = (x['athlete'] + ' ' + x['school']).strip()
                        x['school'] = rt
            for x in rows:
                x.pop('_rt', None)
            tails = [x.pop('_tail', None) for x in rows]
            # (a 0 in the points column: entered, not scoring)
            tails = [None if tl == [0] else tl for tl in tails]
            two = sum(1 for tl in tails if tl and len(tl) == 2)
            one = [tl[0] for tl in tails if tl and len(tl) == 1]
            if two >= 0.4 * len(rows):
                for x, tl in zip(rows, tails):
                    if tl and len(tl) == 2:
                        x['team_place'] = tl[1]
            elif (len(one) >= 0.5 * len(rows) or len(one) >= 10 and one == list(range(1, len(one) + 1))) and \
                    one[:3] == [1, 2, 3][:len(one[:3])] and all(b > a for a, b in zip(one, one[1:])):
                for x, tl in zip(rows, tails):
                    if tl and len(tl) == 1:
                        x['team_place'] = tl[0]
            if len(rows) < 5 and not (len(rows) >= 3 and all(x['school'] for x in rows) and
                                      [x['place'] for x in rows] == list(range(1, len(rows) + 1))):
                continue        # (a whole small race, "only 4 ran", is kept)
            if not any(x.get('result') for x in rows):
                continue        # (no time at all: a team-score table's lines, not a race)
            # "Morgan Deer / Egan CE / Jesseman Scar": surname and school one
            # space apart - the last words repeat as only team codes do
            bare = [x for x in rows if not x['school'] and len(x['athlete'].split()) >= 2]
            lasts = [x['athlete'].split()[-1] for x in bare]
            if len(bare) >= 0.6 * len(rows) and len(set(lasts)) <= 0.4 * len(bare):
                for x in bare:
                    x['athlete'], x['school'] = x['athlete'].rsplit(' ', 1)
            # a name run into a school the race's other rows spell out
            # ("Dunn, Cortlandt Gorham   18:16")
            known = sorted({x['school'] for x in rows if x['school'] and len(x['school']) >= 3},
                           key=len, reverse=True)
            # a surname pushed into the school ("Emma | Larson-Whittaker GSA")
            from collections import Counter
            cnt = Counter(x['school'] for x in rows if x['school'])
            multi = sorted((k for k, n in cnt.items() if n >= 2 and len(k) >= 2), key=len, reverse=True)
            for x in rows:
                sc = x['school']
                if sc and cnt[sc] == 1:
                    for k in multi:
                        if sc.endswith(' ' + k) and len(sc) > len(k) + 1:
                            x['athlete'] = (x['athlete'] + ' ' + sc[:-len(k)].strip()).strip()
                            x['school'] = k
                            break
            for x in rows:
                if x['school']:
                    continue
                for k in known:
                    if x['athlete'].endswith(' ' + k) and len(x['athlete']) > len(k) + 2:
                        x['athlete'], x['school'] = x['athlete'][:-len(k)].strip(), k
                        break
            # a code the other rows use, typed onto the name ("Morrow.N",
            # "HackneyMW", "Kent-MW-MW")
            codes = {x['school'] for x in rows if re.fullmatch(r'[A-Z]{1,4}', x['school'] or '')}
            for x in rows:
                if x['school'] or not codes:
                    continue
                mc = re.fullmatch(r"(.*?[A-Za-z])(?:[.-]|(?<=[a-z]))([A-Z]{1,4})(?:-\2)?", x['athlete'])
                if mc and mc.group(2) in codes and len(mc.group(1)) >= 2:
                    x['athlete'], x['school'] = mc.group(1), mc.group(2)
            dm = None
            # (a distance title may share its line with rows of the column
            # beside it: "2.8 MILES SUNNY, 60 FT FOSTER      42  Dupere ...")
            heads = [l[:m.start()] for l in lines for m in [_START.search(l)] if m and m.start() > 0]
            for t in [t for t in r['titles'] + lines[:12] + heads if not _TIME.search(t)]:
                dm = _DIST.search(t)
                if dm and 0.5 <= float(dm.group(1)) <= 10:
                    break
                dm = None
            if dm:
                unit = dm.group(2).lower()
                event = (f'{dm.group(1)}k Run CC' if unit.startswith('k')
                         else f'{dm.group(1)} Mile Run CC')
            else:
                event = 'Run CC'
            events.append({'event': event, 'gender': g, 'is_relay': False, 'results': rows,
                           '_guess': k in guessed and not order})
        # two unlabelled sheets gendered by the file name and alternation
        # ("gnggirls": the boys' sheet first): the faster race is the boys'
        if len(events) == 2 and all(e['_guess'] for e in events) and \
                {e['gender'] for e in events} == {'Boys', 'Girls'} and events[0]['event'] == events[1]['event']:
            med = []
            for e in events:
                ts = sorted(_secs(x['result']) for x in e['results'] if x['result'])
                med.append(ts[len(ts) // 2] if ts else 0)
            gi = 0 if events[0]['gender'] == 'Girls' else 1
            if med[gi] and med[1 - gi] and med[gi] < med[1 - gi] - 60:
                events[0]['gender'], events[1]['gender'] = events[1]['gender'], events[0]['gender']
        for e in events:
            e.pop('_guess', None)
        # relay meets list each team's combined time ("1. Scarborough
        # 49:47") beside the legs ("1. Jesseman, Scarborough  8:47"): the
        # team lists are not runners, and they name the teams the legs'
        # "Name, Team" cells end in
        if re.search(r'relay|team\s+results', '\n'.join(lines) + ' ' + url_low, re.I):
            teams, keep = set(), []
            for e in events:
                ts = sorted(_secs(x['result']) for x in e['results'] if x['result']) or [0]
                if ts[len(ts) // 2] >= 1800 and \
                        sum(1 for x in e['results'] if not x['school'] or len(x['school']) == 1) > 0.6 * len(ts):
                    teams |= {x['athlete'].lower() for x in e['results']}
                else:
                    keep.append(e)
            events = keep
            for e in events:
                fulls = [(x['athlete'] + ' ' + x['school']).strip() for x in e['results']]
                commas = sum(1 for f in fulls if re.match(r'^[^,]+,\s*\S', f)) \
                    if re.search(r'name,\s*(team|school)', '\n'.join(lines), re.I) else 0
                for x, full in zip(e['results'], fulls):
                    m = re.match(r'^(.*?),\s*(.+)$', full)
                    # "Name, Team" legs: the team list names them, or the
                    # whole list is typed that way
                    if m and (commas >= 0.6 * len(fulls) or
                              any(m.group(2).lower().startswith(t) for t in teams if t)):
                        x['athlete'], x['school'] = m.group(1).strip(), m.group(2).strip()
        # a class-year column before the school ("SO Greely High School"):
        # once most rows carry it, the coded schools do too ("JR NYA")
        flat = [x for e in events for x in e['results']]
        if sum(1 for x in flat if x['grade'] in ('FR', 'SO', 'JR', 'SR')) > 0.5 * len(flat):
            for x in flat:
                mg = re.match(r'^(FR|SO|JR|SR)\s+([A-Z].+)$', x['school'])
                if mg and not x['grade']:
                    x['grade'], x['school'] = mg.group(1), mg.group(2)
        # relay squads ("1. Mt. Ararat A   57:25"): team times, not runners
        squad = sum(1 for x in flat if re.fullmatch(r"[A-Z][A-Za-z.' ]+ [A-F]", x['athlete'])
                    and not x['school'] or re.fullmatch(r'[A-F]', x['school']) and ',' not in x['athlete'])
        if not events or squad > 0.6 * len(flat) and re.search(r'relay', ' '.join(lines[:15]), re.I):
            return empty
        title = next((l.strip() for l in lines if l.strip() and not self._rows(l)), None)
        return {'events': events, 'date': None, 'meet_name': title, 'team_rankings': []}

    # -- columns ---------------------------------------------------------
    @classmethod
    def _unfold_columns(cls, lines):
        """A page set in two columns (pdftotext -layout keeps them side by
        side: "9 Pruett, Hunter Y 19:27      39 Banakos, Nick Y 25:51"): read
        the left column top to bottom, then the right one, so a race title
        printed at the head of the right column ("GIRLS' RESULTS") opens its
        race where it stands. The gutter is where a run of rows starts at one
        x on many lines and no word crosses it."""
        xs = []
        for line in lines:
            for m in _START.finditer(line):
                if m.start() >= 25 and line[max(0, m.start() - 2):m.start()].strip() == '' and \
                        _TIME.search(line[m.start():]):
                    xs.append(m.start())
        if len(xs) < 5:
            return lines
        best = max(set(xs), key=lambda x: sum(1 for y in xs if x <= y <= x + 3))
        if sum(1 for y in xs if best <= y <= best + 3) < 5:
            return lines
        g = best
        # the gutter proper: the nearest blank column left of the rows'
        # places (a right-column title may start left of them)
        for tol in (0, 2):
            c = next((c for c in range(best - 1, max(24, best - 15), -1)
                      if sum(1 for l in lines if len(l) > c and l[c] != ' ') <= tol), None)
            if c is not None:
                g = c + 1
                break
        long_ = [l for l in lines if len(l) > g + 1 and l[:g].strip()]
        crossing = [l for l in long_ if l[g - 1] != ' ' and l[g] != ' ']
        if not long_ or len(crossing) > 0.15 * len(long_):
            return lines
        # a row on the left too: else it is one list (name | time columns)
        if sum(1 for l in lines if cls._rows(l[:g])) < 3:
            return lines
        # only a race title at the head of the right column needs it: the
        # side-by-side reading already joins continuing columns by place
        # (a title over rows of the right column, not a caption below them)
        # (a title over rows of its own column, not a caption below them)
        def titled(part):
            heads = [i for i, l in enumerate(lines)
                     if _GENDER.search(part(l)) and not _TIME.search(part(l))]
            return any(cls._rows(part(l)) for i in heads[:1] for l in lines[i + 1:])
        if not (titled(lambda l: l[g:]) and any(l[:g].strip() for l in lines if len(l) > g)):
            return lines
        left = [l[:g].rstrip() for l in lines]
        right = [l[g:].rstrip() for l in lines]
        return left + cls._unfold_columns(right)

    # -- rows ------------------------------------------------------------
    @classmethod
    def _rows(cls, line):
        """[(column, place, row)] for every timed row on the line."""
        starts = [m for m in _START.finditer(line)]
        # a number inside a row ("1 Sands Jeremiah 12 FAL 16:53": the
        # grade) is no new row when the text before it has no time yet
        kept = []
        for m in starts:
            if kept and not _TIME.search(line[kept[-1].end():m.start()]) and \
                    int(m.group(1)) <= 12 and not re.match(r'\d+[.)]', line[m.start():]):
                continue
            kept.append(m)
        # a team-points cell before a score table printed beside the row
        # ("6 Sean Cook Wtvl 20:23  6     Waterville 56") is no new row:
        # with no time of its own, it stays the row's tail
        starts = []
        for k, m in enumerate(kept):
            nxt = kept[k + 1].start() if k + 1 < len(kept) else len(line)
            sg = line[m.end():nxt]
            if starts and (re.fullmatch(r"\s*[A-Za-z][A-Za-z .'&-]*\s(?:\d{1,3}|NS)\s*", sg) or re.fullmatch(
                    r"\s*[A-Za-z][A-Za-z.'&-]*(?:\s{2,}[A-Za-z][A-Za-z .'&-]*\s(?:\d{1,3}|NS))?\s*", sg)) and \
                    _TIME.search(line[starts[-1].end():m.start()]):
                continue
            starts.append(m)
        out = []
        for k, m in enumerate(starts):
            end = starts[k + 1].start() if k + 1 < len(starts) else len(line)
            seg = line[m.end():end]
            t = _TIME.search(seg)
            if t:
                # "Daniel Ross  SR Houlton/GHCA  5:33.7  17:16.69  1": an
                # average-mile pace before the finish time
                t2 = _TIME.search(seg, t.end())
                if t2 and re.fullmatch(r'\s+', seg[t.end():t2.start()]) and \
                        _secs(t2.group(1)) > 2.5 * _secs(t.group(1)) > 0:
                    seg = seg[:t.start()] + ' ' * (t.end() - t.start()) + seg[t.end():]
                    t = _TIME.search(seg)
            cut = dotted = False
            if not t:
                # a time cut short at the end of the row ("M. Rand - CE:
                # 16:2"): the runner still holds the place, with no time
                t = re.search(r'(?<![\d:.])(\d{1,2}:\d|\d{1,2}:\d{3,4})\s*$', seg) or \
                    re.search(r'(?<=[A-Za-z.]\s)\s*(\d{2,4})(?=\s+\d{1,3}\s*$)', seg)
                # (or a mistyped time cell before the team points: "Andrew
                # Brown  HA  2134  18", "Matt Foster  Ban  23  30")
                cut = True
                dot = None if t else re.search(r'(?<![\d:.])(\d{1,2})\.([0-5]\d)(?:\.(\d{1,2}))?\s*$', seg)
                if dot and 8 <= int(dot.group(1)) and re.search(r'[A-Za-z]', seg[:dot.start()]):
                    # "17.18.6" / "19.18" among "17:18.2" rows: a typed dot for the colon
                    t, cut, dotted = dot, False, True
                bare = None if t else re.search(r'(?<=[A-Za-z]-\s)(\d{1,2})([0-5]\d)\s*$|(?<=[A-Za-z]-)(\d{1,2})([0-5]\d)\s*$'
                                                r'|(?<=[A-Za-z)]\s)\s*(\d{2})([0-5]\d)\s*$', seg)
                if bare and bare.group(5):
                    bare = re.search(r'(?<=[A-Za-z)]\s)\s*()()(\d{2})([0-5]\d)\s*$', seg) \
                        if 8 <= int(bare.group(5)) <= 40 and len(seg.split()) >= 3 else None
                if bare and 8 <= int(bare.group(1) or bare.group(3)) <= 59:
                    # "Clarke-S- 1838" among "Name-S-18:49" rows: the colon left out
                    t, cut, dotted = bare, False, 'bare'
                if not t:
                    continue
            row = cls._row(seg, t)
            if row is None:
                continue
            if cut:
                row['result'] = ''
            elif dotted == 'bare':
                row['result'] = f'{t.group(1) or t.group(3)}:{t.group(2) or t.group(4)}'
            elif dotted:
                row['result'] = f'{t.group(1)}:{t.group(2)}' + (f'.{t.group(3)}' if t.group(3) else '')
            place = int(m.group(1))
            col = 0 if m.start() < 30 else (1 if m.start() < 90 else 2)
            if out and place <= out[-1][1] and col <= out[-1][0]:
                col = out[-1][0] + 1        # (a second list beside the first)
            row['place'] = place
            tail = re.sub(r'\s{3,}[A-Za-z].*$', '', seg[t.end():])   # (a score table beside the row)
            if re.fullmatch(r'(\s+\d{1,3}){1,2}\s*', tail):
                row['_tail'] = [int(x) for x in tail.split()]
            out.append((col, place, row))
        # rows separated only by "; " (a paragraph): one column
        if out and ';' in line:
            out = [(0, p, r) for _c, p, r in out]
        return out

    @staticmethod
    def _row(seg, t):
        left = seg[:t.start()]
        right = seg[t.end():]
        mark = t.group(1).replace(';', ':')
        if mark.count(':') == 2:
            # spreadsheet clock "23:07:00" = 23:07; "17:00:18" = 17:00.18
            mark = mark[:-3] if mark.endswith(':00') or int(mark.split(':')[0]) < 4 else \
                mark[:-3] + '.' + mark[-2:]
        if _NOISE.search(left):
            return None
        school = ''
        left = re.sub(r'[.…]{2,}', ' ', left)          # "(HA) .......16:38"
        left = re.sub(r'\s*[-–:,]+\s*$', '', left.strip())   # "Doughty(BE)-17:41"
        left = re.sub(r'(\))\s*[*#+]+$', r'\1', left)          # "Henry Bauer (HA)**": a footnote mark
        # a relay squad ("Morse 'A'  57:39") is not a runner
        if re.search(r"[‘’'\"][A-D][‘’'\"]\s*$", left):
            return None
        md = re.match(r'^(.*?[A-Za-z])\s*-\s+([A-Z][A-Za-z]{0,3})\s*-?$', left)   # "Morrison- M-"
        m = re.search(r'\(([^()]{1,30})\)\s*$', left)        # agate: "Name (Bel)"
        mh = re.match(r'^(.*?[A-Za-z,.])\s*[-–]\s*([A-Z][A-Za-z.\' -]{1,25})$', left)   # "GRADY,P-GARDINER"
        if m:
            school, name = m.group(1), left[:m.start()]
        elif md and len(md.group(1).split()) <= 3:
            name, school = md.group(1), md.group(2)
        elif re.fullmatch(r"([A-Za-z][A-Za-z'. ]*[A-Za-z.])\s*-\s*([A-Z]{1,4})", left) and len(left.split()) <= 4:
            # "Lepage-M-17:14", "W. Moody-M-19:26": the name, a hyphen, the team code
            name, school = re.fullmatch(r"([A-Za-z][A-Za-z'. ]*[A-Za-z.])\s*-\s*([A-Z]{1,4})", left).groups()
            name = re.sub(r'(\.)\s*\.', r'\1', name)
        elif mh and (',' in mh.group(1) or len(mh.group(1).split()) >= 2) and mh.group(2).isupper() \
                and not re.search(r'\s{2,}', mh.group(1).strip()) \
                and not re.search(r'\s{2,}', mh.group(2)):   # (not "Name     Gray-NG", "Fillmore-P   LR")
            name, school = mh.group(1), mh.group(2)
        else:
            left = left.strip()
            # a trailing team-points / mark cell ("Mess  1", "Cen  !") and
            # a sex cell between name and school ("Doscinski  M  Mt. Blue")
            # are neither name nor school
            for _k in range(2):     # (grade / sex / points cells after the school)
                left = re.sub(r'\s{2,}[\d!*#]{1,3}$', '', left)
                left = re.sub(r'(\S)(\s{2,}(?:\d{1,2}|n/a))\s{2,}[MFBGW]$', r'\1\2', left, flags=re.I)
                left = re.sub(r'\s{2,}n/a$', '', left, flags=re.I)
            left = re.sub(r'(\S)\s{2,}[MFBG]\s{2,}(?=\S{2})', r'\1  ', left)
            # a squad / scorer tag between them ("Eager    V1    PI")
            left = re.sub(r'(\S)\s{2,}(?:J?V\d{0,3}|\d{1,3})(?=\s{2,}\S)', r'\1', left)
            cells = [c for c in re.split(r'\s{2,}|\s[-–]\s', left) if c]
            # (the team after the time, past a points cell: "17:02  1  Water")
            rt = re.match(r'\s*(?:\d{1,3}\s{2,})?([A-Za-z][A-Za-z .\'&/-]{0,30}?)(?=\s{2,}|\s+\d|\s*;|\s*$)', right)
            if len(cells) >= 3:
                # "Mike  Rioux                  Stearns": the school is the
                # last cell, the name cells before it
                gaps = [m for m in re.finditer(r'\s{2,}|\s[-–]\s', left.strip())]
                k = len(gaps) - 1
                name, school = left.strip()[:gaps[k].start()], left.strip()[gaps[k].end():]
                name = re.sub(r'\s+', ' ', name)
                school = re.sub(r'\s{2,}', ' ', school)
            elif len(cells) >= 2:
                # (text after the time on such lines is a team-score table
                # printed alongside: "Butler, Braden  M  17:47  Marshwood 34")
                name, school = cells[0], ' '.join(cells[1:])
                if len(cells) == 2 and re.fullmatch(r'[A-Z][A-Z-]{0,4}', cells[0]) and \
                        re.search(r'[a-z]', cells[1]) and ' ' in cells[1]:
                    name, school = cells[1], cells[0]    # team first: "M-W   J. Pierce"

            elif rt and rt.group(1).strip() and rt.group(1).strip().lower() != 'x' and \
                    not (re.match(r"\s*[A-Za-z][A-Za-z .'&/-]*\s{2,}(?:\d{2,3}|NS)\s*$", right) and
                         re.search(r'\S\s+\S+\s+[A-Z]{2,5}$', left.strip())) and \
                    not re.search(r'record|\bPR\b|\bnew\b|total|\b\d(st|nd|rd|th)\b', rt.group(1), re.I):
                name, school = left, rt.group(1).strip()   # "Swiatek 18:42 Y"
            else:
                w = left.split()
                if len(w) >= 2 and len(w[-1]) <= 5 and w[-1][0].isupper() and (w[-1].isupper() or len(w) >= 3):
                    name, school = ' '.join(w[:-1]), w[-1]
                else:
                    name = left
        name = re.sub(r'\s*-\s*\d{1,2}$', '', name.strip(' ,;:-'))   # "Henri-8": grade tag
        name = re.sub(r'^[)’\']+(?=[A-Za-z])', '', name)                 # (a stray mark before it)
        grade = ''
        mg = re.match(r'^(.*[A-Za-z])\s+(\d{1,2})$', name)      # "Sands Jeremiah 12  FAL"
        if mg and 5 <= int(mg.group(2)) <= 12:
            name, grade = mg.group(1), mg.group(2)
        school = school.strip(' ,;:-')
        mg = re.match(r'^(\d{1,2})\s+([A-Za-z].*)$', school)      # "6 William S Cohen MS"
        if mg and 5 <= int(mg.group(1)) <= 12 and not grade:
            grade, school = mg.group(1), mg.group(2)
        mg = re.match(r'^(FR|SO|JR|SR)\s+([A-Z].*[a-z].*)$', school)   # "SO Greely High School"
        if mg and not grade:
            grade, school = mg.group(1), mg.group(2)
        if not re.search(r'[A-Za-z]{2}', name) or len(name) > 40:
            return None
        if len(re.findall(r'\b\d{1,3}\b', school)) >= 3:
            return None   # a team-score row: "Lewiston  31  2 3 6 9 11 12 14  12:42"
        if re.search(r'\d', name):
            return None
        out = {'athlete': proper_case_name(name) if name.isupper() else name,
               'school': proper_case_team(school), 'result': mark,
               'grade': grade, 'type': 'Finals'}
        mr = re.match(r"\s*([A-Za-z][A-Za-z .'&-]{1,30}?)\s*$", right)
        if mr:
            out['_rt'] = mr.group(1)        # a team cell after the time
        return out
