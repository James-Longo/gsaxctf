"""Summer track: the USATF Maine Youth Developmental Summer Series (14 & under).

Not an MPA school season. Kids compete for summer clubs (GSA's is "Blue Hill
Peninsula", Orono Track Club, Hermon Recreation ...) in two-year age groups,
in Thursday meets from late June, regional Groups A-D, a qualifier, and the
Val Foss Youth State Championships in August. So the summer data stays apart
from the school store: its own files, its own season tab and record board,
results filed by club and age group (docs/agents/summer-track.md).

Sources
  athletic.net (2026 on): read in the browser, one event page at a time
      (athletic.net blocks scripts; no bypass). Each capture is a TSV dump in
      backend/data/summer/raw/an-<meet id>.tsv: a '## <page title>\\t<url>'
      line per event, then one line per result row:
      '<row text, cells joined by " | ">\\t<athletic.net athlete id>\\t<team id>'.
      The meet header goes on a first '#meet\\t<name>\\t<date>\\t<venue>' line.

usage: python3 -m backend.summer_track parse      # raw captures -> backend/data/summer/<year>/
       python3 -m backend.summer_track build      # -> ui/public/data/summer.json.gz
"""
import datetime as dt
import glob
import gzip
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
SUMMER = os.path.join(BASE, 'data', 'summer')
RAW = os.path.join(SUMMER, 'raw')
OUT = os.path.join(ROOT, 'ui', 'public', 'data', 'summer.json.gz')

TITLE = re.compile(r"^(?P<meet>.*?) - (?P<sex>Mens|Womens|Mixed) (?P<age>8 & Under|\d+-\d+|\d+(?: & Over)?|Open) (?P<event>.+?) Results$")
FIELD = ('jump', 'vault', 'put', 'shot', 'discus', 'javelin', 'throw', 'turbo', 'softball', 'hammer')
SEX = {'Mens': 'Boys', 'Womens': 'Girls', 'Mixed': 'Mixed'}


# One name per summer club. Results print the club many ways (town, code, truncation:
# 'Blue Hill', 'Blue Hill Penins', 'Blue Hill Peninsula TC' are GSA's club). Codes
# that could be two clubs (LRD, WR, WREC, Wja) stay as printed.
CLUBS = [
    (r'^(blue|bue) hill', 'Blue Hill Peninsula'),
    (r'^(orono|red riots?|rrtc)\b', 'Orono Red Riots'),
    (r'^(old town|ottc)\b', 'Old Town Track Club'),
    (r'^(bangor|ban)\b|^angor', 'Bangor'),
    (r'^(brewer|rewer)\b', 'Brewer'),
    (r'^(hampden|ham)\b', 'Hampden'),
    (r'^hermon', 'Hermon Recreation'),
    (r'^(lincoln|linc)\b', 'Lincoln'),
    (r'^central\b', 'Central Track Club'),
    (r'^pittsfield', 'Pittsfield'),
    (r'^(explosion)', 'Explosion Track Club (Lee)'),
    (r'^sebasticook', 'Sebasticook Valley Track Club'),
    (r'^(skow|kowhegan)', 'Skowhegan Rec'),
    (r'^(waterville|wtvl)\b', 'Waterville'),
    (r'^(winslow|wins)\b', 'Winslow Rec'),
    (r'^winthrop', 'Winthrop Rec'),
    (r'^(augusta|aug)\b', 'Augusta Rec'),
    (r'^gardiner|^boys & girls club of gardiner', 'Gardiner'),
    (r'^(sandy river|srtc)\b', 'Sandy River Track Club'),
    (r'^(auburn rec|aub$|auburn$)', 'Auburn Rec'),
    (r'^(auburn running|a running pa)', 'Auburn Running Club'),
    (r'^(lewiston)\b', 'Lewiston Rec'),
    (r'^(lisbon|lis)\b', 'Lisbon Striders'),
    (r'^(brunswick|brd)\b', 'Brunswick Rec'),
    (r'^(topsham|tobe|tobt|tolgo|tota)\b', 'Topsham Rec'),
    (r'^(woolwich|wool)\b', 'Woolwich Junior Athletics'),
    (r'^wiscasset', 'Wiscasset Parks & Rec'),
    (r'^(scar|scarboro)', 'Scarborough Rec'),
    (r'^(cnyt|c/ny|cumb|cumberland)', 'Cumberland/North Yarmouth'),
    (r'^(falmouth)', 'Falmouth Flyers'),
    (r'^(freeport fam)', 'Freeport Family Track & Field'),
    (r'^(port rec|portland)', 'Portland Rec'),
    (r'^(westbrook|west)\b', 'Westbrook'),
    (r'^(windham|wind)\b', 'Windham'),
    (r'^(gorham)\b', 'Gorham Rec'),
    (r'^(york)\b', 'York Parks & Rec'),
    (r'^(kennebunk)', 'Kennebunk Rec'),
    (r'^(wells)\b', 'Wells Rec'),
    (r'^(panthers?|panther track)', 'Panther Track Club'),
    (r'^(lakers)', 'Lakers Track Club'),
    (r'^(hornets|healthy horn)', 'Healthy Hornets Track Club'),
    (r'^(trail|trailblazers|mustang trail)', 'Trailblazers'),
    (r'^(falcon fusio)', 'Falcon Fusion'),
    (r'^(clc elite)', 'CLC Elite Track Club'),
    (r'^(saco bay)', 'Saco Bay Striders'),
    (r'^(gttc|granite town)', 'Granite Town Track Club'),
    (r'^(oxfo|oxford)', 'Oxford Hills'),
    (r'^(waldo)', 'Waldo County Track Club'),
    (r'^(01-)?(un-|una|unat|unnat|unatt)', 'Unattached'),
    (r'^ed riot', 'Orono Red Riots'),
    (r'^bruns', 'Brunswick Rec'),
    (r'^wiscasett?', 'Wiscasset Parks & Rec'),
    (r'^poland', 'Poland Track Club'),
    (r'^freeport (hs|high school)', 'Freeport High School'),
    (r'^patriot (pole|pv|vault)', 'Patriot Pole Vault Club'),
    (r'^maine (rw|race ?w)', 'Maine Racewalkers'),
    (r'^sugarloaf', 'Sugarloaf Mountain'),
    (r'^v-tesse', 'V-Tesse Track Club'),
    (r'^camb\.? jets|^cambridge jets', 'Cambridge Jets'),
    (r'^jeri(cho)? ?jets', 'Jericho Jets'),
    (r'^inf(ant)? ?jesus', 'Infant Jesus TC'),
    (r'^cool running', 'Cool Runnings'),
]


def canon_club(raw):
    c = re.sub(r'\s+', ' ', raw or '').strip()
    c = re.sub(r',\s*\S.*$', '', c) if not re.match(r'^[A-Z][a-z]+, [A-Z]', c) else c   # 'Dirigo R.C.,Bar Har': drop the town
    c = re.sub(r"(\s+(?:[+-]?[jJxX]?\d[\d.:\-]*[mqQ]?|NWI|NT|ND|DQ|DNS|FOUL))+$", '', c).strip()     # seed / mark / wind columns run in
    for rx, name in CLUBS:
        if re.search(rx, c, re.I):
            return name
    return c


def canon_event(event):
    """One name per event across sources, in athletic.net's spelling ('100 Meters', '80m Hurdles',
    '800m Racewalk', '4x100 Relay', 'Javelin'); None for exhibition races."""
    e = re.sub(r'\s+', ' ', event).strip()
    if re.search(r'(?i)exhibition', e):
        return None
    e = re.sub(r'(?i)(?<!\d)(\d+)\s*(?:m|meters?)\b', r'\1 Meters', e)
    e = re.sub(r'(?i)^(\d+) Meters (?:Dash|Run)$', r'\1 Meters', e)
    e = re.sub(r'(?i)^(\d+) Meters (?:Race ?Walk)$', r'\1m Racewalk', e)
    e = re.sub(r'(?i)^(\d+) Meters Hurdles$', r'\1m Hurdles', e)
    e = re.sub(r'(?i)^(\d+)mh$', r'\1m Hurdles', e)
    e = re.sub(r'(?i)^4x(\d+) Meters? Relay$|^4x(\d+) Relay$', lambda m: f'4x{m.group(1) or m.group(2)} Relay', e)
    e = re.sub(r'(?i)^(Discus|Javelin)(?: Throw)?$', lambda m: m.group(1).title(), e)
    e = re.sub(r'(?i)^shot(?: put)?$', 'Shot Put', e)
    return e


def is_field(event):
    return any(k in event.lower() for k in FIELD)


def mark_value(mark, field):
    """Seconds for a time, metres for a distance; None if not a mark."""
    m = mark.strip().rstrip('ah').strip()
    if field:
        x = re.fullmatch(r'(\d+(?:\.\d+)?)m', m)
        if x:
            return float(x.group(1))
        x = re.fullmatch(r"(\d+)-(\d+(?:\.\d+)?)", m)   # feet-inches
        return round((int(x.group(1)) * 12 + float(x.group(2))) * 0.0254, 3) if x else None
    x = re.fullmatch(r'(?:(\d+):)?(\d+(?:\.\d+)?)', m)
    return (int(x.group(1) or 0) * 60 + float(x.group(2))) if x else None


def parse_row(text, aid, tid, field, relay):
    cells = [c.strip() for c in text.split(' | ')]
    place = int(cells[0]) if cells and cells[0].isdigit() else None
    if place is not None:
        cells = cells[1:]
    if not relay and cells and re.fullmatch(r"[A-Z][A-Z'.]{0,3}", cells[0]):
        cells = cells[1:]                      # the avatar's initials
    tail = cells[-1] if cells else ''
    age = re.search(r'Yr:\s*(\d+)', tail)
    if relay:
        # '<club> - A | 56.47a | PB<leg>, <leg>, ...'
        team = re.sub(r'\s+-\s+[A-Z]$', '', cells[0]) if cells else ''
        mark = cells[1] if len(cells) > 1 else ''
        legs = re.sub(r'^(?:PB|SB)', '', cells[2]).split(', ') if len(cells) > 2 else []
        return dict(place=place, name=None, club=team, mark=mark, legs=[l for l in legs if l], aid=None, club_id=tid or None)
    name, club = (cells + ['', ''])[:2]
    mark = cells[2] if len(cells) > 2 else ''
    return dict(place=place, name=name, club=club, mark=mark, age=int(age.group(1)) if age else None,
                pb='PB' in tail.split('•')[0] if '•' in tail or tail.startswith('PB') else False,
                aid=aid or None, club_id=tid or None, field=field)


def parse_capture(path):
    meet = dict(name=None, date=None, venue=None)
    events = []
    ev = None
    mid = re.search(r'an-(\d+)', path).group(1)
    for line in open(path, encoding='utf-8').read().splitlines():
        if not line.strip():
            continue
        if line.startswith('#meet\t'):
            _, meet['name'], meet['date'], meet['venue'] = (line.split('\t') + ['', '', ''])[:4]
            try:
                meet['date'] = dt.datetime.strptime(meet['date'], '%b %d, %Y').date().isoformat()
            except ValueError:
                pass
            meet['venue'] = re.sub(r',?\s*ME US$', '', meet['venue']).strip()
            continue
        if line == '#skipped':
            return None
        if line.startswith('## '):
            title, url = (line[3:].split('\t') + [''])[:2]
            m = TITLE.match(title)
            if not m:
                ev = None
                print('  title?', title, file=sys.stderr)
                continue
            meet['name'] = meet['name'] or m.group('meet')
            event = m.group('event').strip()
            ev = dict(gender=SEX[m.group('sex')], age_group=m.group('age'), event=event,
                      relay=bool(re.search(r'relay|4x', event, re.I)), url=url, results=[])
            events.append(ev)
            continue
        if ev is None:
            continue
        text, aid, tid = (line.split('\t') + ['', ''])[:3]
        r = parse_row(text, aid, tid, is_field(ev['event']), ev['relay'])
        if r['mark']:
            r['value'] = mark_value(r['mark'], is_field(ev['event']))
        r.pop('field', None)
        ev['results'].append(r)
    grp = re.search(r'Group ([A-D])', meet['name'] or '')
    return dict(meet_name=meet['name'], date=meet['date'], venue=meet['venue'],
                series_group=grp.group(1) if grp else None,
                source=dict(site='athletic.net', url=f'https://www.athletic.net/TrackAndField/meet/{mid}/results', meet_id=mid),
                events=events)


# ---------------------------------------------------------------------------
# MileSplit raw text (Hy-Tek results), backend/summer_milesplit.py
# ---------------------------------------------------------------------------
# Division names in older series results; the age range each covers is checked
# against the ages the rows print (python3 -m backend.summer_track divisions).
DIVISION = {'mite': '8 & Under', 'mt': '8 & Under', 'sub-bantam': '8 & Under', 'subbantam': '8 & Under',
            'bantam': '9-10', 'bn': '9-10', 'midget': '11-12', 'mid': '11-12', 'md': '11-12', 'mi': 'MI?',
            'youth': '13-14', 'yh': '13-14', 'int': '15-16', 'intermediate': '15-16', 'young': '17-18'}
AGE_RX = re.compile(r"(?i)\b(\d{1,2}\s*(?:&|and)\s*(?:under|un|u)\b|\d{1,2}u\b|under\s*\d{1,2}|\d{1,2}\s*-\s*\d{1,2}\b|"
                    r"\d{1,2}-(?!\d)|sub-?bantam|bantam|midget|youth|intermediate|int|mite|young|bn|mid|md|mi|yh|mt|"
                    r"\d{1,2}(?=\s+(?:years?\s+old\b|girls\b|boys\b|division\b)|\s*$))(?!\s*(?:x|m\b|meter|yard))")
GENDER_RX = re.compile(r"(?i)\b(girls|boys|women|men|mixed|female|male)\b")
EVENT_WORD = re.compile(r"(?i)meter|dash|run|mile|hurdle|relay|jump|vault|put|throw|walk|discus|javelin|shot|turbo|softball|pentathlon")


def age_group(tok):
    t = re.sub(r'\s+', ' ', tok.strip().lower())
    m = re.fullmatch(r'(\d{1,2}) ?(?:&|and) ?(?:under|un|u)|(\d{1,2})u|under ?(\d{1,2})', t)
    if m:
        return f'{next(g for g in m.groups() if g)} & Under'
    m = re.fullmatch(r'(\d{1,2}) ?- ?(\d{1,2})', t)
    if m:
        return f'{m.group(1)}-{m.group(2)}'
    m = re.fullmatch(r'(\d{1,2})-?', t)
    if m:
        n = int(m.group(1))
        if not t.isdigit():
            return f'{n} & Over'
        # a single age goes into its USATF two-year group
        return '8 & Under' if n <= 8 else f'{n - (n + 1) % 2}-{n - (n + 1) % 2 + 1}' if n <= 14 else str(n)
    return DIVISION.get(t.replace(' ', ''), tok.strip())


def ms_header(line):
    """(gender, age group, event) for an event header line, else None."""
    s = re.sub(r'^\s*(?:#\d+\s+|Event\s+\d+\s+)?', '', line).strip()
    if not EVENT_WORD.search(s) or re.match(r'^\d', s) and not re.match(r'^\d+\s*(m|meter|x)', s, re.I):
        return None
    g = GENDER_RX.search(s)
    a = AGE_RX.search(s)
    if not g or not a:
        return None
    gender = {'girls': 'Girls', 'women': 'Girls', 'female': 'Girls', 'boys': 'Boys', 'men': 'Boys', 'male': 'Boys'}.get(g.group(1).lower(), 'Mixed')
    ev = s
    for m in sorted([g, a], key=lambda m: -m.start()):
        ev = ev[:m.start()] + ev[m.end():]
    ev = re.sub(r'\s+', ' ', ev).strip(' -,')
    ev = re.sub(r'(?i)\b(finals?|prelims?|timed finals|results|division|years old|age)\b', '', ev)
    ev = re.sub(r'\s+', ' ', ev).strip(' -,')
    ev = re.sub(r'(?i)\b(\d+)\s*(?:m|meters?)\b', r'\1 Meters', ev)
    return gender, age_group(a.group(1)), ev.title().replace('X', 'x') if ev.isupper() or ev.islower() else ev


COLS = ('name', 'age', 'year', 'yr', 'team', 'school', 'affiliation', 'relay', 'seed', 'finals', 'final', 'mark',
        'time', 'prelims', 'h#', 'wind', 'points', 'pts', 'place', 'heat')


def ms_columns(line):
    """{label: start} from a results column header, e.g. 'Name  Age Team  Seed  Finals H#'."""
    out = {}
    for m in re.finditer(r'\S+', line):
        w = m.group(0).lower()
        if w in COLS and w not in out:
            out[w] = m.start()
    return out if 'finals' in out or 'mark' in out or 'time' in out or 'final' in out else None


MARK_TOK = re.compile(r"^[xXjJ]?(?:\d+:)?\d+(?:\.\d+)?[mhaq]?$|^[xXjJ]?\d+-\d+(?:\.\d+)?$|^(?:DQ|DNF|DNS|NH|FOUL|FAIL|SCR|NM|FS|ND)$")


def ms_row(line, cols, field):
    """One result row, read by column: each value sits under its heading (numbers right-aligned)."""
    m = re.match(r'\s*(\d+|--)\s', line)
    if not m:
        return None
    labels = sorted(cols.items(), key=lambda kv: kv[1])
    toks = [(t.start(), t.end(), t.group(0)) for t in re.finditer(r'\S+', line)]
    mark_col = next(k for k in ('finals', 'final', 'mark', 'time') if k in cols)
    ms_, me_ = cols[mark_col], cols[mark_col] + len(mark_col)
    cand = [t for t in toks if MARK_TOK.match(t[2]) and t[0] <= me_ + 2 and t[1] >= ms_ - 2]
    mark = cand[-1][2] if cand else ''
    mark = re.sub(r'^[xXjJ]', '', mark)         # exhibition / jump-off flags
    mark = re.sub(r'(?<=\d)[q]$', '', mark)
    # text columns end where the first numeric column (seed / mark) begins
    num_start = min([cols[k] for k in ('seed', 'finals', 'final', 'mark', 'time', 'prelims') if k in cols] + [len(line)])
    def text(label, nxt):
        a = cols[label]
        b = nxt
        return line[a:b]
    order = [k for k, _ in labels]
    def span(label):
        i = order.index(label)
        a = cols[label] - (3 if label in ('age', 'year', 'yr') else 0)
        nxt = [cols[k] - (3 if k in ('age', 'year', 'yr') else 0) for k in order[i + 1:]]
        b = min(nxt) if nxt else len(line)
        return line[max(a, 0):min(b, num_start - 1) if label in ('team', 'school', 'affiliation', 'name') else b]
    name = span('name').strip() if 'name' in cols else ''
    name = re.sub(r'^\d+\s+', '', name)                # bib number printed before the name
    team = next((span(k) for k in ('team', 'school', 'affiliation') if k in cols), '')
    team = re.sub(r"(\s+'?[A-F]'?)?(\s+[xXjJ]?[\d:.\-]+|\s+[xXjJ])*\s*$", '', team).strip()
    agec = span('age').strip() if 'age' in cols else ''   # 'Year'/'YR' columns print grade or season count, not age
    age = int(agec) if agec.isdigit() and 4 <= int(agec) <= 19 else None
    if re.match(r'^[^,]+,\s*\S', name):                 # 'Saraceno, Emma' -> 'Emma Saraceno'
        last, first = name.split(',', 1)
        name = f'{first.strip()} {last.strip()}'
    place = int(m.group(1)) if m.group(1).isdigit() else None
    return dict(place=place, name=name, club=team, mark=mark, age=age, aid=None, club_id=None)


def parse_ms_text(path):
    lines = open(path, encoding='utf-8').read().splitlines()
    head = lines[0].split('\t') + [''] * 5
    meet = dict(name=head[1], date=head[2] or None, venue=head[3], url=head[4])
    events, ev, cols = [], None, None
    for i, line in enumerate(lines[1:], 1):
        if line.startswith('#file'):
            ev, cols = None, None
            continue
        h = ms_header(line) if not re.search(r'\d[:.]\d|\d-\d\d\.\d', line) else None
        if h and not ms_columns(line):
            gender, age, event = h
            ev = dict(gender=gender, age_group=age, event=event, relay=bool(re.search(r'(?i)relay|4x', event)), url=meet['url'], results=[])
            events.append(ev)
            cols = None
            continue
        if ev is None:
            continue
        c = ms_columns(line)
        if c:
            cols = c
            continue
        if cols is None:
            continue
        if ev['relay']:
            r = ms_row(line, cols, False)
            if r:
                r['legs'] = []
                r['club'] = r['club'] or re.sub(r"\s+'?[A-F]'?$", '', r['name'] or '').strip()
                r['name'] = None
                ev['results'].append(r)
            elif ev['results'] and re.search(r'\d\)\s*\S', line):
                legs = re.findall(r'\d\)\s*([^\d)]+?)(?:\s+\d{1,2})?\s*(?=\d\)|$)', line)
                for leg in legs:
                    leg = leg.strip()
                    if re.match(r'^[^,]+,\s*\S', leg):
                        last, first = leg.split(',', 1)
                        leg = f'{first.strip()} {last.strip()}'
                    if leg:
                        ev['results'][-1]['legs'].append(leg)
            continue
        r = ms_row(line, cols, is_field(ev['event']))
        if r and r['name']:
            ev['results'].append(r)
    for e in events:
        for r in e['results']:
            r['value'] = mark_value(r['mark'], is_field(e['event'])) if r['mark'] else None
        if e['age_group'] == 'MI?':
            # 'MI' stands for MITE in some files and Midget in others (even within one):
            # the ages the event prints decide; unaged events default to MITE
            ages = sorted(r['age'] for r in e['results'] if r.get('age'))
            e['age_group'] = '11-12' if ages and ages[len(ages) // 2] >= 11 else '8 & Under'
    grp = re.search(r'(?i)group\s*([A-D])\b', meet['name'] or '')
    return dict(meet_name=meet['name'], date=meet['date'], venue=meet['venue'], series_group=grp.group(1).upper() if grp else None,
                season='Outdoor', source=dict(site='milesplit', url=meet['url'], meet_id=re.search(r'ms-(\d+)', path).group(1)),
                events=[e for e in events if e['results']])


def parse():
    n = 0
    for path in sorted(glob.glob(os.path.join(RAW, 'an-*.tsv')) + glob.glob(os.path.join(RAW, 'ms-*.txt'))):
        doc = parse_capture(path) if path.endswith('.tsv') else parse_ms_text(path)
        if doc is None:
            continue           # not a series meet
        year = (doc['date'] or '')[:4] or 'unknown'
        dest = os.path.join(SUMMER, year, os.path.basename(path)[:-4] + '.json')
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        json.dump(doc, open(dest, 'w'), indent=1)
        rows = sum(len(e['results']) for e in doc['events'])
        print(f"{doc['date']} {doc['meet_name']}: {len(doc['events'])} events, {rows} rows")
        n += 1
    print(n, 'meets parsed')


def build():
    """One file for the site: meets, and every scored row (place or mark) flattened."""
    meets, rows = [], []
    dropped = 0
    for path in sorted(glob.glob(os.path.join(SUMMER, '[0-9]' * 4, '*.json'))):
        d = json.load(open(path))
        mi = len(meets)
        meets.append(dict(name=d['meet_name'], date=d['date'], venue=d['venue'], group=d.get('series_group'),
                          url=d['source'].get('url'), season=d.get('season', 'Outdoor')))
        for e in d['events']:
            ev = canon_event(e['event'])
            if ev is None:
                continue
            for r in e['results']:
                if r.get('value') is None:
                    continue           # DNS / DQ / NM
                if re.match(r'^\d', r['club'] or ''):
                    continue           # a team-score line read as a row
                if re.match(r"^'[A-Z]'", r['club'] or ''):
                    dropped += 1
                    continue           # a relay row filed under another event, club lost (sub5 parse)
                rows.append([mi, e['gender'], e['age_group'], ev, r['place'], r['name'] or '',
                             canon_club(r['club']), r['mark'].rstrip('a'), r['value'], r.get('age'), r.get('aid') or '',
                             ', '.join(r.get('legs') or [])])
    # truncated spellings ('Providence Co', 'Amherst Track Cl') join the one longer
    # name they begin; ambiguous prefixes stay as printed
    n = {}
    for r in rows:
        n[r[6]] = n.get(r[6], 0) + 1
    def key(c):
        k = re.sub(r'[^a-z0-9]', '', c.lower().replace('&', 'and'))
        return re.sub(r'(?:trackclub|trackcl|trackc|track|trac|tra|tr|tc)$', 'tc', k)
    keys = {c: key(c) for c in n}
    merge = {}
    by_key = {}
    for c, k in keys.items():
        by_key.setdefault(k, []).append(c)
    for k, cs in by_key.items():          # same name once spelled out: keep the commonest spelling
        best = max(cs, key=lambda c: n[c])
        for c in cs:
            if c != best:
                merge[c] = best
    for c, k in keys.items():
        if len(k) < 6 or c in merge:
            continue
        longer = sorted({key(o) for o, ko in keys.items() if o != c and ko.startswith(k) and len(ko) > len(k)}, key=len)
        # one longer name, or a chain of cuts of one name ('Providence Co' < 'Providence Cobras')
        if longer and all(longer[-1].startswith(x) for x in longer):
            longer = {longer[-1]}
        if len(longer) == 1:
            target = max((o for o, ko in keys.items() if ko in longer), key=lambda o: n[o])
            merge[c] = merge.get(target, target)
    for r in rows:
        r[6] = merge.get(r[6], r[6])
    # clubs that race the Maine series (MileSplit / athletic.net meets) list first on the site
    series = sorted({r[6] for r in rows if r[6] and meets[r[0]]['url'] and 'sub5' not in meets[r[0]]['url']
                     and 'sub5.com' not in (meets[r[0]]['url'] or '')}, key=str.lower)
    out = dict(built=dt.date.today().isoformat(), series_clubs=series,
               cols=['meet', 'gender', 'age_group', 'event', 'place', 'name', 'club', 'mark', 'value', 'age', 'aid', 'legs'],
               meets=meets, rows=rows)
    with gzip.open(OUT, 'wt', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))
    print(f'{len(meets)} meets, {len(rows)} rows -> {os.path.relpath(OUT, ROOT)}; '
          f'{len(merge)} truncated club names merged; {dropped} misfiled relay rows dropped')


if __name__ == '__main__':
    {'parse': parse, 'build': build}[sys.argv[1]]()
