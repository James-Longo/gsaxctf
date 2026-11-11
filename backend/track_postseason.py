"""
track_postseason.py - predict the indoor and outdoor track postseasons.

The XC simulator (xc_postseason.py) rates runners from a few races on
different courses. Track has the opposite problem: marks are comparable
across meets, but a championship is decided months after the last thing we
know about most athletes. Before indoor starts, the newest information on a
sprinter is last June; on a freshman it is eighth grade; on a distance
runner it is the fall's cross-country races. This module turns everything
known on a given day into a predicted championship mark and an entry
probability for every athlete and event, then rolls dice.

Data layer
  * Every track row and every XC race, keyed by athlete catalog id
    (backend/athlete_catalog.py) and grouped into blocks: one season of one
    kind (Indoor / Outdoor / XC) in one academic year. Academic years are
    named by their spring: 2027 = XC fall 2026 + Indoor + Outdoor 2027.
  * Marks are on a log scale where lower is better: log(seconds) for races,
    -log(inches) for field events, the course-adjusted log time for XC.
  * Eighth graders: the athlete catalog never joins a middle-school runner
    to their high school (different schools), so a 9th grader's middle
    school marks are joined here by name: one middle-school runner and one
    high-school newcomer of the same gender and name, a year apart, each the
    only one of that name in the state, at a high school the middle school
    is known to feed (learned from the joins themselves). A wrong merge is
    worse than a missed one, so ambiguous names stay apart.

Championships live in backend/data/track_champs.json (built by
`python3 -m backend.track_postseason champs`): the MPA state meets by
class, each with its results file, date and gender.

Model (see build_dataset / fit / simulate below)
  For each championship, cutoff day and candidate athlete-event:
  * features: the best estimate of the target event from each earlier block
    (same event, the indoor/outdoor counterpart, or another event through a
    fitted conversion), this season's marks so far, grade, days left;
  * a gradient-boosted model predicts the championship mark relative to a
    simple anchor (the most informative single estimate) and another its
    spread; a classifier predicts whether the athlete enters the event;
  * relays are team candidates with relay history and the legs' estimates;
  * each simulation draws entries and marks, scores the meet with its
    scoring table, and counts places.

Everything is validated by predicting each past season with models fitted
on the other seasons (track_postseason_cv.py).
"""

import bisect
import collections
import gzip
import json
import math
import os
import pickle
import re
import sys
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import json_store as js  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'backend', 'data')
PARSED = os.path.join(DATA, 'parsed_results')
CHAMPS_PATH = os.path.join(DATA, 'track_champs.json')
CACHE_DIR = os.environ.get('TRACK_CACHE', os.path.join(DATA, 'track_cache'))

TYPES = ('I', 'O', 'X')
SEASON_OF = {'Indoor': 'I', 'Outdoor': 'O', 'XC': 'X'}
SEASON_NAME = {'I': 'Indoor', 'O': 'Outdoor', 'X': 'XC'}

FIELD = ('High Jump', 'Long Jump', 'Triple Jump', 'Pole Vault', 'Shot Put',
         'Discus', 'Javelin', 'Weight Throw', 'Hammer Throw')


def ay_of(year, season):
    """Academic year named by its spring: XC 2026 -> 2027, Indoor 2027 -> 2027."""
    return int(year) + 1 if season in ('XC', 'X') else int(year)


def is_field(event):
    return any(event.startswith(f) for f in FIELD)


def perf(mark, event):
    """Mark -> log scale, lower is better; None when unreadable or absurd."""
    v, is_dist = js.parse_mark_value(mark, event)
    if v is None or v <= 0:
        return None
    if is_field(event):
        if is_dist is False:
            return None
        return -math.log(v)
    if is_dist:
        return None
    return math.log(v)


def mark_str(p, event):
    """Log-scale value back to a printed mark."""
    if p is None or not math.isfinite(p):
        return ''
    if is_field(event):
        inches = math.exp(-p)
        ft = int(inches // 12)
        return f"{ft}-{inches - 12 * ft:05.2f}"
    s = math.exp(p)
    if s >= 60:
        m = int(s // 60)
        return f"{m}:{s - 60 * m:05.2f}"
    return f"{s:.2f}"


def name_key(name):
    return ' '.join(sorted(re.findall(r'[a-z]+', (name or '').lower())))


def initial_key(name):
    """First initial + last name ('Needleman, Grace' and 'G Needleman' -> 'g needleman')."""
    name = name or ''
    if ',' in name:
        last, first = name.split(',', 1)
        first, last = re.findall(r'[a-z]+', first.lower()), re.findall(r'[a-z]+', last.lower())
    else:
        toks = re.findall(r'[a-z]+', name.lower())
        first, last = toks[:1], toks[1:]
    last = [t for t in last if t not in ('jr', 'sr', 'ii', 'iii', 'iv')]
    if not first or not last:
        return None
    return f'{first[0][0]} {last[-1]}'


def full_key(name):
    """First + last name tokens, order-free, for joining middle school to high school."""
    toks = [t for t in re.findall(r'[a-z]+', (name or '').lower())
            if t not in ('jr', 'sr', 'ii', 'iii', 'iv', 'fr', 'so', 'ms')]
    if len(toks) < 2:
        return None
    return ' '.join(sorted(toks))


# ---------------------------------------------------------------------------
# Event families: an indoor event and its outdoor counterpart
# ---------------------------------------------------------------------------

FAMILY = {
    '55 Meter Dash': 'short', '100 Meter Dash': 'short', '60 Meter Dash': 'short',
    '55 Meter Hurdles': 'hurdles', '100 Meter Hurdles': 'hurdles', '110 Meter Hurdles': 'hurdles',
    '60 Meter Hurdles': 'hurdles', '300 Meter Hurdles': 'long hurdles', '400 Meter Hurdles': 'long hurdles',
    '200 Meter Dash': '200', '300 Meter Dash': '400', '400 Meter Dash': '400', '500 Meter Run': '400',
    '600 Meter Run': '800', '800 Meter Run': '800', '1000 Meter Run': '1600',
    '1500 Meter Run': '1600', '1600 Meter Run': '1600', '1 Mile Run': '1600',
    '3000 Meter Run': '3200', '3200 Meter Run': '3200', '2 Mile Run': '3200',
    '1600 Meter Race Walk': 'walk', '1 Mile Race Walk': 'walk',
    'High Jump': 'HJ', 'Long Jump': 'LJ', 'Triple Jump': 'TJ', 'Pole Vault': 'PV',
    'Shot Put': 'SP', 'Discus': 'DT', 'Javelin': 'JT',
    '4x100 Meter Relay': 'R4x100', '4x200 Meter Relay': 'R4x200',
    '4x400 Meter Relay': 'R4x400', '4x800 Meter Relay': 'R4x800',
}
DISTANCE_FAMILIES = {'800', '1600', '3200'}
RELAY_LEGS = {'4x100 Meter Relay': ('100 Meter Dash', '55 Meter Dash', '200 Meter Dash'),
              '4x200 Meter Relay': ('200 Meter Dash', '55 Meter Dash', '100 Meter Dash'),
              '4x400 Meter Relay': ('400 Meter Dash', '200 Meter Dash', '800 Meter Run'),
              '4x800 Meter Relay': ('800 Meter Run', '1 Mile Run', '1600 Meter Run', '400 Meter Dash')}


def is_relay_event(event):
    return 'Relay' in event


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class Store:
    """Every mark, by athlete and block.

    marks[aid][(ay, typ)][event] = (dates, prefix_best, values) with dates
    sorted ('YYYY-MM-DD'; unknown dates are filed at the block's end so they
    only count once the block is over).
    relays[(unit, gender)][(ay, typ)][event] = same, plus legs per mark.
    """

    def __init__(self):
        self.marks = {}
        self.relays = {}
        self.gender = {}
        self.name = {}
        self.class_of = {}
        self.where = {}          # aid -> sorted [(date, unit, level)]
        self.ms_link = {}        # middle-school aid -> high-school aid
        self.feeder = {}         # middle-school unit -> {hs unit: share}
        self.champ_dates = {}
        # events outside FAMILY (yard races, medleys, ...): dates only, for
        # the qualifier check (backend/track_qualifiers.py)
        self.alt = {}            # aid -> {(ay, typ): {event: [dates]}}
        self.alt_relays = {}     # (unit, gender) -> same

    # -- queries -----------------------------------------------------------
    def best(self, aid, block, event, cutoff):
        """(best value, count) in one block and event from marks before cutoff."""
        b = self.marks.get(aid, {}).get(block)
        if not b or event not in b:
            return None, 0
        dates, pref, _ = b[event]
        i = bisect.bisect_left(dates, cutoff)
        if i == 0:
            return None, 0
        return pref[i - 1], i

    def series(self, aid, block, event, cutoff):
        b = self.marks.get(aid, {}).get(block)
        if not b or event not in b:
            return [], []
        dates, _, vals = b[event]
        i = bisect.bisect_left(dates, cutoff)
        return dates[:i], vals[:i]

    def relay_best(self, unit, gender, block, event, cutoff):
        b = self.relays.get((unit, gender), {}).get(block)
        if not b or event not in b:
            return None, 0, None
        dates, pref, vals, legs = b[event]
        i = bisect.bisect_left(dates, cutoff)
        if i == 0:
            return None, 0, None
        j = min(range(i), key=lambda k: vals[k])
        return pref[i - 1], i, legs[j]

    def unit_at(self, aid, cutoff):
        """(unit, level, date) of the athlete's last result before cutoff."""
        w = self.where.get(aid)
        if not w:
            return None, None, None
        i = bisect.bisect_left(w, (cutoff,))
        if i == 0:
            return None, None, None
        return w[i - 1][1], w[i - 1][2], w[i - 1][0]

    def grade_in(self, aid, ay):
        c = self.class_of.get(aid)
        if c is None:
            return None
        return 12 - (c - ay)


BLOCK_END = {'I': (3, 15), 'O': (6, 30), 'X': (11, 30)}


def block_end(ay, typ):
    m, d = BLOCK_END[typ]
    y = ay - 1 if typ == 'X' else ay
    return f'{y:04d}-{m:02d}-{d:02d}'


def _row_level(unit, meet, grade, folder_level, cache={}):
    if folder_level == 'ms' or (unit or '').startswith('me-ms'):
        return 'ms'
    if grade is not None and grade <= 8:
        return 'ms'
    if meet not in cache:
        from backend import school_catalog as sc
        cache[meet] = sc.meet_level(meet)
    lv = cache[meet]
    if lv == 'college':
        return 'college'
    return 'ms' if lv == 'ms' else 'hs'


def _xc_ratings():
    """[(store aid, ay, date, course-adjusted log time)] from the course model."""
    from backend import xc_course_model as cm
    import contextlib
    import io
    try:
        f = json.load(gzip.open(os.path.join(js.DATA_DIR, 'xc_courses.json.gz')))
    except Exception:  # noqa: BLE001
        return []
    fac = {c['course']: math.log(c['factor']) for c in f['courses'] if c.get('factor')}
    with contextlib.redirect_stdout(io.StringIO()):
        obs = cm.clean_observations(team_filter=False)
    out = []
    for store_aid, year, course, lt, meet, d in obs:
        if course not in fac:
            continue
        out.append((store_aid, ay_of(year, 'XC'), (d or '')[:10], lt - fac[course]))
    return out


def load_store(use_cache=True, quiet=False):
    """Build (or read the cached) Store from the team store."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, 'store.pkl')
    stamp = os.path.getmtime(os.path.join(js.DATA_DIR, 'manifest.json'))
    if use_cache and os.path.exists(path):
        try:
            with open(path, 'rb') as f:
                s = pickle.load(f)
            if getattr(s, 'stamp', None) == stamp and hasattr(s, 'alt'):
                return s
        except Exception:  # noqa: BLE001 - rebuild
            pass
    from backend import athlete_catalog as ac
    res = ac.resolver()
    man = json.load(open(os.path.join(js.DATA_DIR, 'manifest.json')))
    folder_level = {t['slug']: t.get('level') for t in man['teams']}
    s = Store()
    s.stamp = stamp
    raw = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(list)))
    rraw = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(list)))
    grades = collections.defaultdict(list)
    where = collections.defaultdict(list)
    names = collections.defaultdict(collections.Counter)
    n = 0
    for (folder, team, unit, year, season, _ay, nm, store_aid, event, mark, grade, meet, d) in ac.load_rows():
        if season == 'XC':
            continue
        g = 'Boys' if event.startswith('Boys') else 'Girls' if event.startswith('Girls') else None
        if g is None:
            continue
        ev = event[len(g) + 1:]
        if ev not in FAMILY:
            if season != 'XC' and perf(mark, ev) is not None:
                dd = d if re.match(r'^\d{4}-\d\d-\d\d$', d or '') else block_end(ay_of(year, season), SEASON_OF[season])
                blk = (ay_of(year, season), SEASON_OF[season])
                if is_relay_event(ev):
                    s.alt_relays.setdefault((unit, g), {}).setdefault(blk, {}).setdefault(ev, []).append(dd)
                else:
                    s.alt.setdefault(res(store_aid), {}).setdefault(blk, {}).setdefault(ev, []).append(dd)
            continue
        p = perf(mark, ev)
        if p is None:
            continue
        typ = SEASON_OF[season]
        ay = ay_of(year, season)
        dd = d if re.match(r'^\d{4}-\d\d-\d\d$', d or '') else block_end(ay, typ)
        lv = _row_level(unit, meet, grade, folder_level.get(folder))
        if lv == 'college':
            continue
        if is_relay_event(ev):
            # legs when the file prints them, else only the team ("Orono Relay")
            legs = tuple(sorted(name_key(x) for x in nm.split(',') if name_key(x))) if ',' in nm else ()
            rraw[(unit, g)][(ay, typ)][ev].append((dd, p, legs))
            continue
        aid = res(store_aid)
        raw[aid][(ay, typ)][ev].append((dd, p))
        s.gender.setdefault(aid, g)
        names[aid][nm] += 1
        where[aid].append((dd, unit, lv))
        if grade is not None and 6 <= grade <= 12:
            grades[aid].append(ay + 12 - grade)
        n += 1
    # cross country: course-adjusted ratings, one 'XC' event per fall
    for store_aid, ay, d, x in _xc_ratings():
        aid = res(store_aid)
        if aid not in raw and aid not in s.gender:
            continue          # XC-only runners never show up on a track
        dd = d if re.match(r'^\d{4}-\d\d-\d\d$', d or '') else block_end(ay, 'X')
        raw[aid][(ay, 'X')]['XC'].append((dd, x))
    for aid, blocks in raw.items():
        out = {}
        for blk, evs in blocks.items():
            out[blk] = {}
            for ev, lst in evs.items():
                lst.sort()
                dates = [a for a, _ in lst]
                vals = [b for _, b in lst]
                pref = list(np.minimum.accumulate(vals))
                out[blk][ev] = (dates, pref, vals)
        s.marks[aid] = out
    for key, blocks in rraw.items():
        out = {}
        for blk, evs in blocks.items():
            out[blk] = {}
            for ev, lst in evs.items():
                lst.sort()
                out[blk][ev] = ([a for a, _, _ in lst], list(np.minimum.accumulate([b for _, b, _ in lst])),
                                [b for _, b, _ in lst], [c for _, _, c in lst])
        s.relays[key] = out
    for aid, cs in grades.items():
        s.class_of[aid] = int(round(float(np.median(cs))))
    for aid, w in where.items():
        w.sort()
        s.where[aid] = w
    s.name = {aid: c.most_common(1)[0][0] for aid, c in names.items()}
    _link_middle_school(s, quiet=quiet)
    if not quiet:
        print(f'store: {n} marks, {len(s.marks)} athletes, {len(s.relays)} relay teams, '
              f'{len(s.ms_link)} middle-school joins')
    with open(path, 'wb') as f:
        pickle.dump(s, f, protocol=pickle.HIGHEST_PROTOCOL)
    return s


def _link_middle_school(s, quiet=False):
    """Join each 9th grader to their own middle-school marks (see module doc).

    Two passes: the first joins only names unique on both sides and learns
    which high schools each middle school feeds; the second keeps the joins
    whose high school is one the middle school sends at least 10% of its
    runners to (or whose middle school has too few joins to say).
    """
    ms_by = collections.defaultdict(list)   # (ay, gender, key) -> [(aid, unit)]
    hs_new = collections.defaultdict(list)  # (ay, gender, key) -> [(aid, unit)]
    for aid, w in s.where.items():
        g = s.gender.get(aid)
        k = full_key(s.name.get(aid))
        if not g or not k:
            continue
        ms_ays = collections.defaultdict(collections.Counter)
        hs_ays = collections.defaultdict(collections.Counter)
        for d, u, lv in w:
            ay = int(d[:4]) + (1 if int(d[5:7]) >= 8 else 0)
            (ms_ays if lv == 'ms' else hs_ays)[ay][u] += 1
        if ms_ays and not hs_ays:
            last = max(ms_ays)
            ms_by[(last, g, k)].append((aid, ms_ays[last].most_common(1)[0][0]))
        if hs_ays and not ms_ays:
            first = min(hs_ays)
            gr = s.grade_in(aid, first)
            if gr is None or gr == 9:
                hs_new[(first, g, k)].append((aid, hs_ays[first].most_common(1)[0][0]))
    cands = []
    for (ay, g, k), hs in hs_new.items():
        if len(hs) != 1:
            continue
        ms = ms_by.get((ay - 1, g, k), [])
        if len(ms) != 1:
            continue
        cands.append((ms[0][0], ms[0][1], hs[0][0], hs[0][1]))
    flow = collections.defaultdict(collections.Counter)
    for _, mu, _, hu in cands:
        flow[mu][hu] += 1
    s.feeder = {}
    for mu, c in flow.items():
        tot = sum(c.values())
        s.feeder[mu] = {hu: n / tot for hu, n in c.items()}
    kept = 0
    for ma, mu, ha, hu in cands:
        f = s.feeder.get(mu, {})
        if sum(flow[mu].values()) >= 5 and f.get(hu, 0) < 0.10:
            continue
        s.ms_link[ma] = ha
        kept += 1
    # merge: the middle-school marks become the high-school athlete's
    for ma, ha in s.ms_link.items():
        for blk, evs in s.marks.pop(ma, {}).items():
            tgt = s.marks.setdefault(ha, {}).setdefault(blk, {})
            for ev, (dates, pref, vals) in evs.items():
                if ev in tgt:
                    lst = sorted(list(zip(tgt[ev][0], tgt[ev][2])) + list(zip(dates, vals)))
                    dd = [a for a, _ in lst]
                    vv = [b for _, b in lst]
                    tgt[ev] = (dd, list(np.minimum.accumulate(vv)), vv)
                else:
                    tgt[ev] = (dates, pref, vals)
        s.where[ha] = sorted(s.where.get(ha, []) + s.where.pop(ma, []))
        if s.class_of.get(ha) is None and s.class_of.get(ma) is not None:
            s.class_of[ha] = s.class_of[ma]
        s.class_of.pop(ma, None)
    # a joined 9th grader with no grade on file was in 8th grade the year before
    for ma, ha in s.ms_link.items():
        if s.class_of.get(ha) is None:
            first = min(int(d[:4]) + (1 if int(d[5:7]) >= 8 else 0) for d, _, lv in s.where[ha] if lv == 'hs')
            s.class_of[ha] = first + 3
    s.feeder_best = {mu: max(f.items(), key=lambda kv: kv[1]) for mu, f in s.feeder.items()}
    if not quiet:
        print(f'middle school joins: {len(cands)} unique-name pairs, {kept} kept; '
              f'{len(s.feeder)} middle schools with a known high school')


# ---------------------------------------------------------------------------
# Championship catalog
# ---------------------------------------------------------------------------

STATE_EXCLUDE = re.compile(
    r'kvac|smaa|wmc|college|womens|mens|woman|usatf|new.?england|^ne|newengland|middle|jv|frosh|fresh|'
    r'record|scores?$|team-scores|thomas|umaine|busline|aroostook|alms|pvc|emitl|seed|twilight|'
    r'high-point', re.I)
LETTER_RX = [re.compile(r'class[\s_%20-]*([abc])(?![a-z])', re.I),
             re.compile(r'class([abc])(?:boys|girls|results|indoor|state|\d)', re.I),
             re.compile(r'class([abc])$', re.I),
             re.compile(r'state[\s_-]*([abc])(?:boys|girls|[\s_-]|$)', re.I),
             re.compile(r'class[\s_-]*([abc])', re.I)]


def _letter(text):
    text = text.replace('%20', ' ')
    for rx in LETTER_RX:
        m = rx.search(text)
        if m:
            return m.group(1).upper()
    return None


def _read_parsed(year, season, stem):
    p = os.path.join(PARSED, str(year), season, stem + '.json')
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:  # noqa: BLE001
        return None


def build_champs(first=2003, last=2026):
    """Find the state class meets in the parsed results; returns the catalog."""
    out = []
    for y in range(first, last + 1):
        for season in ('Indoor', 'Outdoor'):
            d = os.path.join(PARSED, str(y), season)
            if not os.path.isdir(d):
                continue
            cands = []
            for fn in sorted(os.listdir(d)):
                if not fn.endswith('.json'):
                    continue
                stem = fn[:-5]
                stem_plain = re.sub(r'^ms-', '', stem)
                if STATE_EXCLUDE.search(stem_plain):
                    continue
                j = _read_parsed(y, season, stem)
                if not isinstance(j, dict):
                    continue
                dt = str(j.get('date') or '')
                if not re.match(r'^\d{4}-\d\d-\d\d$', dt) or int(dt[:4]) != y:
                    continue
                if not (dt[5:7] == '02' or dt[5:7] == '06' or (season == 'Outdoor' and dt[5:7] == '05')):
                    continue
                mn = j.get('meet_name') or ''
                if STATE_EXCLUDE.search(mn) and 'Principals' not in mn:
                    continue
                by_g = collections.Counter()
                schools = collections.defaultdict(set)
                for ev in j.get('events', []):
                    for r in ev.get('results', []):
                        by_g[ev.get('gender')] += 1
                        schools[ev.get('gender')].add(r.get('school'))
                letter = _letter(stem) or _letter(mn)
                state_like = bool(letter) or 'Principals' in mn or re.search(r'state', stem + mn, re.I)
                if not state_like:
                    continue
                for g in ('Boys', 'Girls'):
                    if by_g[g] >= 150 and len(schools[g]) >= 25:
                        named = re.search(r'boy|girl', stem, re.I)
                        mismatch = named and not re.search(g[:-1], stem, re.I)
                        cands.append(dict(year=y, season=season, gender=g, file=stem, date=dt,
                                          letter=letter, rows=by_g[g], schools=sorted(s for s in schools[g] if s),
                                          meet_name=mn, mismatch=bool(mismatch)))
            out.extend(cands)
    # the state meet of a class is the latest such meet of that class in the season
    known = [c for c in out if c['letter']]
    for c in out:
        if c['letter']:
            continue
        best, score = None, 0
        sc = set(c['schools'])
        for k in known:
            if k['season'] != c['season'] or k['gender'] != c['gender'] or abs(k['year'] - c['year']) > 2:
                continue
            j = len(sc & set(k['schools'])) / max(1, len(sc | set(k['schools'])))
            if j > score:
                best, score = k['letter'], j
        if score >= 0.3:
            c['letter'] = best
            c['letter_from'] = f'school overlap {score:.2f}'
    final = {}
    for c in out:
        if not c['letter']:
            continue
        k = (c['year'], c['season'], c['letter'], c['gender'])
        cur = final.get(k)
        rank = (c['date'], not c['mismatch'], c['rows'])
        if cur is None or rank > (cur['date'], not cur['mismatch'], cur['rows']):
            final[k] = c
    champs = []
    for (y, season, letter, g), c in sorted(final.items()):
        champs.append(dict(id=f'{y}-{season}-state-{letter}-{g}', year=y, season=season,
                           kind='state', division=letter, gender=g, date=c['date'],
                           file=c['file'], letter_from=c.get('letter_from', 'name')))
    return champs


CONF_FILE = [
    # (season, kind, regex on the file name, division from the name)
    ('Outdoor', 'PVC', re.compile(r'small.?sch|pvc.?sm|pvcsmall', re.I), 'Small'),
    ('Outdoor', 'PVC', re.compile(r'pvc.?l(?:arge|s|g|b)|large.?sch|pvclarge', re.I), 'Large'),
    ('Indoor', 'EMITL', re.compile(r'emitl.*small|small.*emitl', re.I), 'Small'),
    ('Indoor', 'EMITL', re.compile(r'emitl.*large|large.*emitl', re.I), 'Large'),
    ('Indoor', 'EMITL', re.compile(r'em(?:itl|til).*champ|^emitlresults\d{4}$', re.I), None),
]
CONF_SKIP = re.compile(r'frosh|fresh|jv|middle|^ms-pvc|records|high-point|week', re.I)
NUMBERED = re.compile(r'meet[\s_-]*\d', re.I)   # a numbered regular-season meet


def build_conf_champs(first=2008, last=2026):
    """Conference championships GSA's league runs: PVC Large/Small outdoor and
    EMITL indoor (one meet until 2018, Large/Small since). A file holding
    both divisions is split by the teams of each division's score block."""
    out = []
    for y in range(first, last + 1):
        for season in ('Indoor', 'Outdoor'):
            d = os.path.join(PARSED, str(y), season)
            if not os.path.isdir(d):
                continue
            picks = {}
            for fn in sorted(os.listdir(d)):
                stem = fn[:-5]
                if not fn.endswith('.json') or CONF_SKIP.search(stem):
                    continue
                if NUMBERED.search(stem) and not re.search(r'champ', stem, re.I):
                    continue
                for s_, kind, rx, div in CONF_FILE:
                    if s_ != season or not rx.search(stem):
                        continue
                    if kind == 'PVC' and not re.search(r'pvc|small|large', stem, re.I):
                        continue
                    j = _read_parsed(y, season, stem)
                    if not isinstance(j, dict):
                        break
                    dt = str(j.get('date') or '')
                    if not re.match(r'^\d{4}-\d\d-\d\d$', dt) or int(dt[:4]) != y:
                        break
                    if kind == 'PVC' and dt[5:7] not in ('05', '06'):
                        break
                    if kind == 'EMITL' and dt[5:7] != '02':
                        break
                    by_g = collections.Counter(ev.get('gender') for ev in j.get('events', [])
                                               for _ in ev.get('results', []))
                    blocks = [b for b in (j.get('team_rankings') or []) if b.get('division')]
                    for g in ('Boys', 'Girls'):
                        if by_g[g] < 80:
                            continue
                        named = re.search(r'boy|girl', stem, re.I)
                        if named and not re.search(g[:-1], stem, re.I):
                            continue
                        divs = [div] if div else []
                        teams = {}
                        if not div:
                            for b in blocks:
                                if b.get('gender') != g:
                                    continue
                                dv = 'Small' if re.search(r'small', b['division'], re.I) else \
                                    'Large' if re.search(r'large', b['division'], re.I) else None
                                if dv:
                                    divs.append(dv)
                                    teams[dv] = [t['team'] for t in b.get('teams', [])]
                            if not divs:
                                divs = ['All']
                        for dv in divs:
                            k = (kind, dv, g)
                            cand = dict(id=f'{y}-{season}-{kind.lower()}-{dv}-{g}', year=y, season=season,
                                        kind='conf', conference=kind, division=dv, gender=g, date=dt,
                                        file=stem, rows=by_g[g])
                            if dv in teams:
                                cand['teams'] = teams[dv]
                            if k not in picks or cand['rows'] > picks[k]['rows']:
                                picks[k] = cand
                    break
            for c in picks.values():
                c.pop('rows', None)
                out.append(c)
    return sorted(out, key=lambda c: c['id'])


def load_champs():
    with open(CHAMPS_PATH, encoding='utf-8') as f:
        return json.load(f)['champs']


# ---------------------------------------------------------------------------
# Championship results (truth)
# ---------------------------------------------------------------------------

def _unit_of(raw_school, year, season, gender, file):
    from backend import school_catalog as sc
    sid = sc.resolve(raw_school, year=str(year), season=season, gender=gender, meet_name=file + '.json')
    if sid is None:
        return None
    return sc.team_unit(sid, str(year), season, gender) or sid


def _misspelled(store, cands, name, unit, d):
    """The one athlete of this school with the row's mark that day whose surname is
    spelled nearly the same ('Carngie' for Carnegie, 2006 Class A), or None."""
    import difflib
    last = (name.split(',')[0] if ',' in (name or '') else (name or ' ').split()[-1]).lower()
    hits = {a for a in cands if store.unit_at(a, d + '~')[0] == unit and
            difflib.SequenceMatcher(None, last, (store.name.get(a) or ' ').split()[-1].lower()).ratio() >= 0.75}
    return hits.pop() if len(hits) == 1 else None


def champ_results(champ, store):
    """What happened: per event the scored order, plus team totals.

    Returns {'events': {event: [(place, unit, aid or relay key, p, mark)]},
             'teams': {unit: points}, 'official': [(rank, unit, score)] }.
    Places come from the finals (prelims for those who missed them); the
    mark is the athlete's best of the meet in that event.
    """
    y, season, g, file = champ['year'], champ['season'], champ['gender'], champ['file']
    j = _read_parsed(y, season, file) or {}
    only = None
    if champ.get('teams'):
        only = {_unit_of(t, y, season, g, file) for t in champ['teams']} - {None}
    # athlete names -> catalog ids, through the store rows of this meet
    ids = _meet_ids(store, champ)
    grouped = collections.defaultdict(list)
    for ev in j.get('events', []):
        if ev.get('gender') != g:
            continue
        name = ev.get('event', '')
        canon = canonical(name, g)
        if canon is None:
            continue
        grouped[canon].extend(ev.get('results', []))
    events = {}
    for ev, rs in grouped.items():
        rs = [r for r in rs if r.get('type') != 'Seed' and not r.get('exhibition')]
        finals = [r for r in rs if r.get('type') == 'Finals']
        fin_keys = {(name_key(r.get('athlete') or ''), r.get('school')) for r in finals}
        rows = []
        for r in rs:
            p = perf(r.get('result') or '', ev)
            if p is None:
                continue
            key = (name_key(r.get('athlete') or ''), r.get('school'))
            in_final = r.get('type') == 'Finals'
            if finals and not in_final and key in fin_keys:
                continue          # their final counts, not the prelim
            unit = _unit_of(r.get('school') or '', y, season, g, file)
            if only is not None and unit not in only:
                continue          # the other division of a two-division file
            if is_relay_event(ev):
                who = ('relay', unit)
            else:
                who = ids.get((name_key(r.get('athlete') or ''), ev)) or ids.get(name_key(r.get('athlete') or '')) \
                    or ids.get(('mark', ev, round(p, 5))) or ids.get(('init', initial_key(r.get('athlete')))) \
                    or _misspelled(store, ids.get(('marks', ev, round(p, 5)), ()), r.get('athlete'), unit, champ['date'])
            rows.append(dict(unit=unit, aid=who, p=p, mark=r.get('result'), final=in_final or not finals,
                             name=r.get('athlete') or '', grade=r.get('grade')))
        # finalists ahead of everyone else, each group by mark
        rows.sort(key=lambda r: (not r['final'], r['p']))
        events[ev] = rows
    official = []
    for blk in j.get('team_rankings', []) or []:
        if blk.get('gender') not in (g, None) or blk.get('kind') == 'xc':
            continue
        if champ.get('teams') and blk.get('division') and \
                not re.search(champ['division'], blk['division'], re.I):
            continue          # the other division's score block
        for t in blk.get('teams', []):
            u = _unit_of(t.get('team') or '', y, season, g, file)
            if u:
                official.append((t.get('score') or 0.0, u))
        if official:
            break
    official.sort(key=lambda x: -x[0])
    # the scoring table: the one that reproduces the official totals
    # (state meets scored six places before 2022, eight since)
    best = None
    for table in TABLES:
        teams = score_places(events, table)
        err = sum(abs(teams.get(u, 0) - sc_) for sc_, u in official) if official else 0
        if best is None or err < best[0] - 1e-9:
            best = (err, table, teams)
    return dict(events=events, teams=best[2], table=best[1], official=official)


TABLES = ([10, 8, 6, 5, 4, 3, 2, 1], [10, 8, 6, 4, 2, 1], [8, 6, 4, 2, 1], [6, 4, 3, 2, 1])


def score_places(events, table):
    teams = collections.defaultdict(float)
    for ev, rows in events.items():
        for i, r in enumerate(rows[:len(table)]):
            if r['unit']:
                teams[r['unit']] += table[i]
    return dict(teams)


_IDS_CACHE = {}


def _meet_ids(store, champ):
    """(name key, event) -> catalog id for the athletes in this meet's store rows."""
    k = champ['id']
    if k in _IDS_CACHE:
        return _IDS_CACHE[k]
    out = {}
    ay = ay_of(champ['year'], champ['season'])
    typ = SEASON_OF[champ['season']]
    d = champ['date']
    for aid, blocks in store.marks.items():
        if store.gender.get(aid) != champ['gender']:
            continue
        b = blocks.get((ay, typ))
        if not b:
            continue
        for ev, (dates, _, vals) in b.items():
            if d in dates:
                nk = name_key(store.name.get(aid))
                out[(nk, ev)] = aid
                out.setdefault(nk, aid)
                # a store name kept as an initial ('G Needleman' for 'Needleman, Grace')
                ik = ('init', initial_key(store.name.get(aid)))
                if ik[1]:
                    out[ik] = aid if out.get(ik, aid) == aid else None
                # a name printed differently in the store ('King-Ofsiany')
                # still has the same mark on the same day
                for dd, v in zip(dates, vals):
                    if dd == d:
                        mk = ('mark', ev, round(v, 5))
                        out[mk] = aid if mk not in out else None
                        out.setdefault(('marks', ev, round(v, 5)), []).append(aid)
    _IDS_CACHE[k] = out
    return out


def canonical(raw_event, gender):
    from backend.event_canon import canonical_event
    r = canonical_event(raw_event, gender)
    if not r:
        return None
    ev = r[1]
    return ev if ev in FAMILY else None


# ---------------------------------------------------------------------------
# Conversions between events
# ---------------------------------------------------------------------------

def season_bests(store):
    """{(gender, (typ, event)): {(aid, ay): best}} over whole blocks."""
    out = collections.defaultdict(dict)
    for aid, blocks in store.marks.items():
        g = store.gender.get(aid)
        if not g:
            continue
        for (ay, typ), evs in blocks.items():
            for ev, (_, pref, _) in evs.items():
                out[(g, (typ, ev))][(aid, ay)] = pref[-1]
    return out


def relay_bests(store):
    out = collections.defaultdict(dict)
    for (unit, g), blocks in store.relays.items():
        for (ay, typ), evs in blocks.items():
            for ev, (_, pref, _, _) in evs.items():
                out[(g, (typ, ev))][(unit, ay)] = pref[-1]
    return out


def fit_conversions(bests, min_n=80):
    """{(gender, target key, source key): (a, b, sigma, n)}: target ~ a + b * source,
    fitted on athletes (or relay teams) with both in one academic year,
    trimmed once at 3 robust SDs."""
    by_g = collections.defaultdict(list)
    for (g, key), d in bests.items():
        if len(d) >= min_n:
            by_g[g].append(key)
    conv = {}
    for g, keys in by_g.items():
        for tk in keys:
            if tk[0] == 'X':
                continue
            td = bests[(g, tk)]
            for sk in keys:
                if sk == tk:
                    continue
                sd = bests[(g, sk)]
                common = td.keys() & sd.keys() if len(td) < len(sd) else sd.keys() & td.keys()
                if len(common) < min_n:
                    continue
                x = np.array([sd[k] for k in common])
                y = np.array([td[k] for k in common])
                keep = np.ones(len(x), bool)
                for _ in range(2):
                    b, a = np.polyfit(x[keep], y[keep], 1)
                    r = y - (a + b * x)
                    mad = np.median(np.abs(r[keep])) * 1.4826
                    keep = np.abs(r) < 3 * mad
                if keep.sum() < min_n or not (0.2 < b < 3):
                    continue
                sig = float(np.std(r[keep]))
                conv[(g, tk, sk)] = (float(a), float(b), sig, int(keep.sum()))
    return conv


def conversion_table(conv):
    """{(gender, target key): [(source key, a, b, sigma)] sorted by sigma}."""
    out = collections.defaultdict(list)
    for (g, tk, sk), (a, b, sig, n) in conv.items():
        out[(g, tk)].append((sk, a, b, sig))
    for k in out:
        out[k].sort(key=lambda x: x[3])
    return dict(out)


# ---------------------------------------------------------------------------
# Candidates and features
# ---------------------------------------------------------------------------

DRIFT = 0.03          # anchor choice: one year of age costs like a 3% conversion error
MAX_CANDIDATES = 50   # per event and championship, by anchor
CLOSE_SIGMA = 0.05    # a conversion this good makes another event evidence (100 -> 200)
STALE_DAYS = 450      # no result in this long: not on a team any more


def slots_for(ay, typ):
    """Earlier blocks a championship in (ay, typ) can learn from, newest first."""
    if typ == 'I':
        track = [(ay - 1, 'O'), (ay - 1, 'I'), (ay - 2, 'O'), (ay - 2, 'I')]
    else:
        track = [(ay, 'I'), (ay - 1, 'O'), (ay - 1, 'I'), (ay - 2, 'O')]
    return [(ay, typ)] + track + [(ay, 'X'), (ay - 1, 'X')]


SLOT_NAMES = ['cur', 'p1', 'p2', 'p3', 'p4', 'x0', 'x1']


def _days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _block_mid(blk):
    ay, typ = blk
    return {'I': f'{ay:04d}-01-15', 'O': f'{ay:04d}-05-10', 'X': f'{ay - 1:04d}-10-10'}[typ]


class Featurizer:
    """Builds candidate rows for a championship at a cutoff."""

    def __init__(self, store, conv_table, rconv_table, champ_entries, norms):
        self.s = store
        self.conv = conv_table
        self.rconv = rconv_table
        self.entries = champ_entries     # aid -> {(ay, typ): set(families)}
        self.relay_entries = None
        self.norms = norms               # (gender, key) -> (mu, sd)
        self.by_unit = collections.defaultdict(set)
        for aid, w in store.where.items():
            for _, u, _ in w:
                self.by_unit[u].add(aid)
        self._tu = {}

    def team(self, unit, year, season, gender):
        k = (unit, year, season, gender)
        if k not in self._tu:
            from backend import school_catalog as sc
            self._tu[k] = sc.team_unit(unit, str(year), season, gender) or unit
        return self._tu[k]

    # -- athlete side --------------------------------------------------------
    def sources(self, aid, blk, cutoff):
        """[(source key, best, n)] in one block before cutoff."""
        b = self.s.marks.get(aid, {}).get(blk)
        if not b:
            return []
        out = []
        for ev, (dates, pref, _) in b.items():
            i = bisect.bisect_left(dates, cutoff)
            if i:
                out.append(((blk[1], ev), pref[i - 1], i))
        return out

    def estimate(self, g, tkey, srcs, table=None):
        """Best single estimate of the target from one block's sources:
        (value, sigma, n, family evidence)."""
        if not srcs:
            return None
        table = self.conv if table is None else table
        fam = FAMILY.get(tkey[1])
        best = None
        famok = False
        for sk, v, n in srcs:
            if sk == tkey:
                return (v, 0.0, n, True)
            sfam = 'XC' if sk[1] == 'XC' else FAMILY.get(sk[1])
            if sfam == fam or (sfam == 'XC' and fam in DISTANCE_FAMILIES):
                famok = True
        lookup = {sk: (v, n) for sk, v, n in srcs}
        for sk, a, b, sig in table.get((g, tkey), ()):
            if sk in lookup:
                v, n = lookup[sk]
                best = (a + b * v, sig, n, famok)
                break
        return best

    def candidates(self, champ, units, cutoff):
        """{aid: team unit} for athletes who may compete for these teams."""
        s = self.s
        y, season, g = champ['year'], champ['season'], champ['gender']
        lo = (date.fromisoformat(cutoff) - timedelta(days=STALE_DAYS)).isoformat()
        out = {}
        for u, aids in self.by_unit.items():
            hs = u
            if u in s.feeder_best and not u.startswith('me-hs'):
                hu, share = s.feeder_best[u]     # a middle school: the high school it feeds
                hs = hu if share >= 0.5 else None
            if hs is None:
                continue
            tu = self.team(hs, y, season, g)
            if tu not in units:
                continue
            for aid in aids:
                if s.gender.get(aid) != g:
                    continue
                cu, lv, last = s.unit_at(aid, cutoff)
                if cu != u or last is None or last < lo:
                    continue
                gr = s.grade_in(aid, y)
                if gr is not None and gr > 12:
                    continue
                if lv == 'ms' and u in s.feeder_best:
                    hu, share = s.feeder_best[u]
                    if share < 0.5:
                        continue
                out[aid] = tu
        return out

    def athlete_rows(self, champ, units, cutoff, events):
        s = self.s
        y, season, g = champ['year'], champ['season'], champ['gender']
        typ = SEASON_OF[season]
        slots = slots_for(y, typ)
        cands = self.candidates(champ, units, cutoff)
        rows = []
        for aid, tu in cands.items():
            srcs = [self.sources(aid, blk, cutoff) for blk in slots]
            fams = set()
            for ss in srcs:
                for sk, _, _ in ss:
                    fams.add('XC' if sk[1] == 'XC' else FAMILY.get(sk[1]))
            gr = s.grade_in(aid, y)
            cur_all = sum(n for _, _, n in srcs[0])
            cur_events = len(srcs[0])
            _, lv, last = s.unit_at(aid, cutoff)
            prev = self.entries.get(aid, {})
            for ev in events:
                if is_relay_event(ev):
                    continue
                fam = FAMILY[ev]
                if fam not in fams and not (fam in DISTANCE_FAMILIES and 'XC' in fams):
                    continue
                tkey = (typ, ev)
                ests = [self.estimate(g, tkey, ss) for ss in srcs]
                if not any(e is not None and (e[3] or e[1] <= CLOSE_SIGMA) for e in ests):
                    continue
                best = None
                for k, (blk, e) in enumerate(zip(slots, ests)):
                    if e is None:
                        continue
                    age = max(0, _days(min(_block_mid(blk), cutoff), champ['date'])) / 365.0
                    cost = e[1] ** 2 + (DRIFT * age) ** 2
                    if best is None or cost < best[0]:
                        best = (cost, e[0], k)
                anchor = best[1]
                f = dict(aid=aid, team=tu, event=ev, anchor=anchor, anchor_slot=best[2],
                         grade=gr if gr is not None else np.nan,
                         ms_last=1.0 if lv == 'ms' else 0.0,
                         days_left=_days(cutoff, champ['date']),
                         cur_all=cur_all, cur_events=cur_events,
                         days_since_last=_days(last, cutoff) if last else np.nan)
                for name, e in zip(SLOT_NAMES, ests):
                    f[f'{name}_d'] = e[0] - anchor if e else np.nan
                    f[f'{name}_sig'] = e[1] if e else np.nan
                    f[f'{name}_n'] = e[2] if e else 0
                _, vals = s.series(aid, slots[0], ev, cutoff)
                f['cur_same_n'] = len(vals)
                f['cur_last_d'] = vals[-1] - anchor if vals else np.nan
                f['cur_med_d'] = float(np.median(vals)) - anchor if vals else np.nan
                f['cur_share'] = len(vals) / cur_all if cur_all else np.nan
                mu, sd = self.norms.get((g, tkey), (anchor, 0.05))
                f['anchor_z'] = (anchor - mu) / sd
                # last championships: same kind of season a year ago, and the
                # other season most recently
                same_prev = prev.get((y - 1, typ), set())
                other_prev = prev.get((y, 'I') if typ == 'O' else (y - 1, 'O'), set())
                f['prev_same_fam'] = 1.0 if fam in same_prev else (0.0 if same_prev else np.nan)
                f['prev_other_fam'] = 1.0 if fam in other_prev else (0.0 if other_prev else np.nan)
                f['prev_n_events'] = len(same_prev | other_prev)
                rows.append(f)
        _ranks(rows)
        return rows

    # -- relay side ----------------------------------------------------------
    def relay_rows(self, champ, units, cutoff, events, athlete_rows):
        s = self.s
        y, season, g = champ['year'], champ['season'], champ['gender']
        typ = SEASON_OF[season]
        slots = slots_for(y, typ)[:5]
        team_keys = collections.defaultdict(list)
        for (u, gg) in s.relays:
            if gg != g:
                continue
            tu = self.team(u, y, season, g)
            if tu in units:
                team_keys[tu].append(u)
        # individual estimates for leg events, per team
        legs_by = collections.defaultdict(lambda: collections.defaultdict(list))
        for r in athlete_rows:
            legs_by[r['team']][r['event']].append(r['anchor'])
        rows = []
        for ev in events:
            if not is_relay_event(ev):
                continue
            tkey = (typ, ev)
            for tu in units:
                srcs = []
                for blk in slots:
                    best = {}
                    for u in team_keys.get(tu, ()):
                        b = s.relays.get((u, g), {}).get(blk)
                        if not b:
                            continue
                        for rev, (dates, pref, _, _) in b.items():
                            i = bisect.bisect_left(dates, cutoff)
                            if i:
                                k = (blk[1], rev)
                                if k not in best or pref[i - 1] < best[k][0]:
                                    best[k] = (pref[i - 1], i)
                    srcs.append([(k, v, n) for k, (v, n) in best.items()])
                ests = [self.estimate(g, tkey, ss, self.rconv) for ss in srcs]
                leg_ev = next((le for le in RELAY_LEGS[ev] if len(legs_by[tu].get(le, [])) >= 1), None)
                legs = sorted(legs_by[tu].get(leg_ev, [])) if leg_ev else []
                legs_mean = float(np.mean(legs[:4])) if len(legs) >= 4 else np.nan
                if not any(e is not None for e in ests) and not np.isfinite(legs_mean):
                    continue
                best = None
                for k, (blk, e) in enumerate(zip(slots, ests)):
                    if e is None:
                        continue
                    age = max(0, _days(min(_block_mid(blk), cutoff), champ['date'])) / 365.0
                    cost = e[1] ** 2 + (DRIFT * age) ** 2
                    if best is None or cost < best[0]:
                        best = (cost, e[0], k)
                legs_est = math.log(4) + legs_mean if np.isfinite(legs_mean) else np.nan
                if best is None:
                    anchor, slot = legs_est, -1
                else:
                    anchor, slot = best[1], best[2]
                f = dict(aid=('relay', tu), team=tu, event=ev, anchor=anchor, anchor_slot=slot,
                         days_left=_days(cutoff, champ['date']),
                         legs_d=legs_est - anchor if np.isfinite(legs_est) else np.nan,
                         legs_n=len(legs), legs_ev=RELAY_LEGS[ev].index(leg_ev) if leg_ev else -1)
                for name, e in zip(SLOT_NAMES[:5], ests):
                    f[f'{name}_d'] = e[0] - anchor if e else np.nan
                    f[f'{name}_sig'] = e[1] if e else np.nan
                    f[f'{name}_n'] = e[2] if e else 0
                mu, sd = self.norms.get((g, tkey), (anchor, 0.05))
                f['anchor_z'] = (anchor - mu) / sd
                prev = self.relay_entries.get(tu, {}) if self.relay_entries else {}
                f['prev_same_fam'] = 1.0 if ev in prev.get((y - 1, typ), set()) else 0.0
                rows.append(f)
        _ranks(rows)
        return rows


def _ranks(rows):
    """Rank of each row's anchor within its team and the whole field, per event."""
    by_ev = collections.defaultdict(list)
    for r in rows:
        by_ev[r['event']].append(r)
    for ev, rs in by_ev.items():
        rs.sort(key=lambda r: r['anchor'])
        team_n = collections.Counter()
        for i, r in enumerate(rs):
            team_n[r['team']] += 1
            r['field_rank'] = i + 1
            r['team_rank'] = team_n[r['team']]
            r['field_gap'] = r['anchor'] - rs[min(7, len(rs) - 1)]['anchor']


def cutoffs_for(champ):
    """Prediction days for a championship: before indoor starts, then through
    the season(s) to the day before. (label, date)."""
    y = champ['year']
    eve = (date.fromisoformat(champ['date']) - timedelta(days=1)).isoformat()
    if champ['season'] == 'Indoor':
        days = [('Nov 30', f'{y - 1}-11-30'), ('Dec 20', f'{y - 1}-12-20'), ('Jan 10', f'{y}-01-10'),
                ('Jan 25', f'{y}-01-25'), ('Feb 5', f'{y}-02-05')]
    else:
        days = [('Nov 30', f'{y - 1}-11-30'), ('Jan 15', f'{y}-01-15'), ('Mar 1', f'{y}-03-01'),
                ('Apr 25', f'{y}-04-25'), ('May 10', f'{y}-05-10'), ('May 24', f'{y}-05-24')]
    return [(lab, d) for lab, d in days if d < eve] + [('eve', eve)]


# ---------------------------------------------------------------------------
# Dataset: every championship x cutoff x candidate, with what happened
# ---------------------------------------------------------------------------

_G = {}


def truths(store, champs):
    path = os.path.join(CACHE_DIR, 'truths.pkl')
    if os.path.exists(path) and os.path.getmtime(path) > os.path.getmtime(os.path.join(CACHE_DIR, 'store.pkl')) \
            and os.path.getmtime(path) > os.path.getmtime(CHAMPS_PATH):
        with open(path, 'rb') as f:
            return pickle.load(f)
    out = {c['id']: champ_results(c, store) for c in champs}
    with open(path, 'wb') as f:
        pickle.dump(out, f)
    return out


def setup(store=None, champs=None):
    """Everything the featurizer needs, fitted on all seasons (conversions and
    norms are about events, not about who wins)."""
    store = store or load_store()
    champs = champs or load_champs()
    tr = truths(store, champs)
    conv = conversion_table(fit_conversions(season_bests(store)))
    rconv = conversion_table(fit_conversions(relay_bests(store), min_n=40))
    entries = collections.defaultdict(lambda: collections.defaultdict(set))
    rentries = collections.defaultdict(lambda: collections.defaultdict(set))
    vals = collections.defaultdict(list)
    for c in champs:
        t = tr[c['id']]
        typ = SEASON_OF[c['season']]
        for ev, rows in t['events'].items():
            for i, r in enumerate(rows):
                if is_relay_event(ev):
                    if r['unit']:
                        rentries[r['unit']][(c['year'], typ)].add(ev)
                elif r['aid']:
                    entries[r['aid']][(c['year'], typ)].add(FAMILY[ev])
                if i < 8:
                    vals[(c['gender'], (typ, ev))].append(r['p'])
    norms = {k: (float(np.mean(v)), float(np.std(v)) or 0.05) for k, v in vals.items() if len(v) >= 20}
    fz = Featurizer(store, conv, rconv, {k: dict(v) for k, v in entries.items()}, norms)
    fz.relay_entries = {k: dict(v) for k, v in rentries.items()}
    return fz, champs, tr


def champ_units(truth):
    return {r['unit'] for rows in truth['events'].values() for r in rows if r['unit']}


def rows_for(champ, cutoff, label, truth, units=None, events=None, keep=()):
    """Candidate rows (athletes, relays) for one championship at one cutoff,
    labelled with what happened when the truth is known. `keep`: (aid, event)
    pairs kept however far down the field they rank (an entry list's)."""
    fz = _G['fz']
    units = units if units is not None else champ_units(truth)
    events = events if events is not None else sorted(truth['events'])
    ath = fz.athlete_rows(champ, units, cutoff, events)
    rel = fz.relay_rows(champ, units, cutoff, events, ath)
    got = {}
    if truth:
        for ev, rows in truth['events'].items():
            for place, r in enumerate(rows):
                k = (r['aid'], ev)
                if r['aid'] and k not in got:
                    got[k] = (r['p'], place + 1)
    keep_a = []
    by_ev = collections.defaultdict(list)
    for r in ath:
        by_ev[r['event']].append(r)
    for ev, rs in by_ev.items():
        for r in rs:
            hit = got.get((r['aid'], ev))
            r['in_top'] = r['field_rank'] <= MAX_CANDIDATES
            if not r['in_top'] and not hit and (str(r['aid']), ev) not in keep:
                continue
            keep_a.append(r)
    for r in keep_a + rel:
        hit = got.get((r['aid'], r['event']))
        r['entered'] = 1 if hit else 0
        r['p_true'] = hit[0] if hit else np.nan
        r['place'] = hit[1] if hit else np.nan
        r['champ'] = champ['id']
        r['cutoff'] = cutoff
        r['label'] = label
        r.setdefault('in_top', True)
    return keep_a, rel


def _job(args):
    champ, label, cutoff = args
    truth = _G['tr'][champ['id']]
    return rows_for(champ, cutoff, label, truth)


def build_dataset(first=2006, procs=10, quiet=False):
    """All championships from `first` on, every cutoff: two DataFrames."""
    import multiprocessing as mp
    import pandas as pd
    fz, champs, tr = setup()
    _G.update(fz=fz, tr=tr)
    jobs = [(c, lab, d) for c in champs if c['year'] >= first for lab, d in cutoffs_for(c)]
    ath, rel = [], []
    with mp.get_context('fork').Pool(procs) as pool:
        for i, (a, r) in enumerate(pool.imap_unordered(_job, jobs, chunksize=4)):
            ath.extend(a)
            rel.extend(r)
            if not quiet and i % 100 == 0:
                print(f'  {i}/{len(jobs)} championship-days', flush=True)
    A = pd.DataFrame(ath)
    R = pd.DataFrame(rel)
    A['aid'] = A['aid'].astype(str)
    R['aid'] = R['aid'].astype(str)
    A.to_pickle(os.path.join(CACHE_DIR, 'athletes.pkl'))
    R.to_pickle(os.path.join(CACHE_DIR, 'relays.pkl'))
    if not quiet:
        print(f'{len(A)} athlete rows ({int(A.entered.sum())} entered), {len(R)} relay rows')
    return A, R


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

SLOT_FEATS = [f'{n}_{k}' for n in SLOT_NAMES for k in ('d', 'sig', 'n')]
ATH_FEATS = ['anchor_z', 'anchor_slot', 'grade', 'ms_last', 'days_left', 'cur_all', 'cur_events',
             'days_since_last', 'cur_same_n', 'cur_last_d', 'cur_med_d', 'cur_share',
             'prev_same_fam', 'prev_other_fam', 'prev_n_events', 'field_rank', 'team_rank',
             'field_gap', 'ev_code', 'typ', 'boys', 'is_state', 'std_gap', 'std_gap_any'] + SLOT_FEATS
REL_FEATS = ['anchor_z', 'anchor_slot', 'days_left', 'legs_d', 'legs_n', 'legs_ev', 'prev_same_fam',
             'field_rank', 'field_gap', 'ev_code', 'typ', 'boys', 'is_state'] + SLOT_FEATS[:15]
# std_gap / std_gap_any: the qualifying line, how this season's mark stands
# against the marks that got athletes into the same meet the two seasons
# before (state meets enter by qualifying standard)
EVENT_CODES = {ev: i for i, ev in enumerate(sorted(FAMILY))}
Y_CLIP = 0.25
_LINES = {}


def _meet_key(champ_ids):
    """'2024-Indoor-state-A-Boys' -> 'Indoor-state-A-Boys'."""
    return champ_ids.str[5:]


def qual_lines(df, q=0.9):
    """{(meet key, event, year): the q-quantile of entrants' season bests on
    the eve of that year's meet} from a dataset of candidate rows."""
    d = df[(df.label == 'eve') & (df.entered == 1) & (df.cur_sig == 0)]
    best = d['anchor'] + d['cur_d']
    g = best.groupby([_meet_key(d.champ), d.event, d.champ.str[:4].astype(int)]).quantile(q)
    return {k: float(v) for k, v in g.items()}


def set_lines(df):
    _LINES.clear()
    _LINES.update(qual_lines(df))


def _std_cols(df):
    key = _meet_key(df['champ']).values
    yr = df['champ'].str[:4].astype(int).values
    ev = df['event'].values
    line = np.full(len(df), np.nan)
    for i, (k, e, y) in enumerate(zip(key, ev, yr)):
        v = [_LINES[(k, e, y - j)] for j in (1, 2) if (k, e, y - j) in _LINES]
        if v:
            line[i] = np.mean(v)
    cur = np.where(df['cur_sig'].values == 0, df['anchor'].values + df['cur_d'].values, np.nan)
    df['std_gap'] = cur - line
    df['std_gap_any'] = df['anchor'].values - line
    return df


def add_columns(df):
    """Columns the models need that the featurizer leaves implicit."""
    df = df.copy()
    df['ev_code'] = df['event'].map(EVENT_CODES).astype(float)
    df['typ'] = df['champ'].str.contains('-Outdoor-').astype(float)
    df['boys'] = df['champ'].str.endswith('-Boys').astype(float)
    df['is_state'] = df['champ'].str.contains('-state-').astype(float)   # entries work differently
    df['year'] = df['champ'].str[:4].astype(int)
    df['y'] = (df['p_true'] - df['anchor']).clip(-Y_CLIP, Y_CLIP)
    if len(df) and 'cur_sig' in df:
        df = _std_cols(df)
    for c in ATH_FEATS + REL_FEATS:
        if c not in df.columns:
            df[c] = np.nan
    return df


def _hgb(kind, **kw):
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    base = dict(max_iter=300, learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=80,
                l2_regularization=1.0, random_state=0)
    base.update(kw)
    if kind == 'clf':
        return HistGradientBoostingClassifier(**base)
    return HistGradientBoostingRegressor(**base)


class Part:
    """Mark, spread and entry models for athletes or for relays."""

    def __init__(self, feats):
        self.feats = feats

    def fit(self, df, folds=3):
        f = self.feats
        ent = df[df.entered == 1]
        ent = ent[np.isfinite(ent.y)]
        cat = [f.index('ev_code')]
        self.mark = _hgb('reg', loss='absolute_error', categorical_features=cat).fit(ent[f], ent.y)
        # spread: out-of-fold absolute residuals, by groups of seasons
        years = np.array(sorted(ent.year.unique()))
        oof = np.full(len(ent), np.nan)
        for k in range(folds):
            hold = np.isin(ent.year.values, years[k::folds])
            m = _hgb('reg', loss='absolute_error', categorical_features=cat).fit(ent[f][~hold], ent.y[~hold])
            oof[hold] = ent.y.values[hold] - m.predict(ent[f][hold])
        self.spread = _hgb('reg', categorical_features=cat, max_iter=200).fit(ent[f], np.abs(oof))
        sc = np.maximum(self.spread.predict(ent[f]), 0.004)
        z = oof / sc
        self.z = np.clip(z[np.isfinite(z)], -8, 8)
        top = df[df.in_top]
        self.entry = _hgb('clf', categorical_features=cat).fit(top[f], top.entered)
        return self

    def predict(self, df):
        f = self.feats
        X = df[f]
        mean = df['anchor'].values + self.mark.predict(X)
        scale = np.maximum(self.spread.predict(X), 0.004)
        pent = self.entry.predict_proba(X)[:, 1]
        return mean, scale, pent


class Model:
    """State meets are predicted by models fitted on state meets only: adding
    the conference meets to their training made state podiums worse (-0.7 to
    -1.1 pts, 2026-10-23). Conference meets use models fitted on both."""

    def fit(self, A, R):
        sa, sr = A[A.is_state == 1], R[R.is_state == 1]
        self.ath = Part(ATH_FEATS).fit(sa)
        self.rel = Part(REL_FEATS).fit(sr)
        self.conf = (Part(ATH_FEATS).fit(A), Part(REL_FEATS).fit(R)) if (A.is_state == 0).any() else None
        return self

    def predict(self, A, R):
        import pandas as pd
        out = []
        for kind in (1, 0):
            ath, rel = (self.ath, self.rel) if kind or self.conf is None else self.conf
            for part, df, is_rel in ((ath, A, False), (rel, R, True)):
                df = df[df.is_state == kind]
                if len(df):
                    m, s, p = part.predict(df)
                    d = df[['champ', 'cutoff', 'label', 'aid', 'team', 'event', 'anchor']].copy()
                    d['mean'], d['scale'], d['pent'] = m, s, p
                    d['relay'] = is_rel
                    out.append(d)
        return pd.concat(out, ignore_index=True) if out else None

    def z_for(self, champ_id):
        """Standardized residual pools (athletes, relays) for this kind of meet."""
        if '-state-' in champ_id or self.conf is None:
            return self.ath.z, self.rel.z
        return self.conf[0].z, self.conf[1].z


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

# Teammates' standardized misses correlate ~0.065 (backtest residuals), but a
# shared team-day draw made state podiums no better and Brier slightly worse
# (2026-10-23), so it is off.
PROGRAM_ICC = 0.0

# individual events an athlete may enter: no state meet on file has an indoor
# athlete in more than 3, outdoor athletes run up to 4 (423 cases)
MAX_EVENTS = {'Indoor': 3, 'Outdoor': 4}


def max_events_for(champ_id):
    return MAX_EVENTS['Indoor' if '-Indoor-' in champ_id else 'Outdoor']


def simulate(pred, table, z_ath, z_rel, sims=2000, seed=0, max_events=4, icc=PROGRAM_ICC):
    """Monte Carlo meets from one championship-day's predictions.

    pred: DataFrame rows (aid, team, event, mean, scale, pent, relay).
    Returns (team_points [sims x teams], teams, per-row stats dict).
    """
    rng = np.random.default_rng(seed)
    teams = sorted(set(pred.team))
    tix = {t: i for i, t in enumerate(teams)}
    pts = np.zeros((sims, len(teams)))
    n = len(pred)
    entered = rng.random((sims, n)) < pred.pent.values[None, :]
    # an athlete enters at most `max_events` individual events: keep the most
    # likely ones when a draw gives more
    ath = ~pred.relay.values
    if max_events:
        by_aid = collections.defaultdict(list)
        for i, (a, r) in enumerate(zip(pred.aid.values, pred.relay.values)):
            if not r:
                by_aid[a].append(i)
        for a, idx in by_aid.items():
            if len(idx) <= max_events:
                continue
            idx = sorted(idx, key=lambda i: -pred.pent.values[i])
            cnt = np.cumsum(entered[:, idx], axis=1)
            entered[:, idx] &= cnt <= max_events
    za = rng.choice(z_ath, size=(sims, n))
    zr = rng.choice(z_rel, size=(sims, n)) if len(z_rel) else za
    z = np.where(ath[None, :], za, zr)
    team_idx = np.array([tix[t] for t in pred.team.values])
    if icc:
        # a program's good or bad day moves all its athletes together
        day = rng.standard_normal((sims, len(teams)))
        z = math.sqrt(1 - icc) * z + math.sqrt(icc) * day[:, team_idx]
    marks = pred['mean'].values[None, :] + pred.scale.values[None, :] * z
    marks = np.where(entered, marks, np.inf)
    win = np.zeros(n)
    top3 = np.zeros(n)
    exp_pts = np.zeros(n)
    place_sum = np.zeros(n)
    tbl = np.array(table, float)
    for ev, idx in pred.groupby('event').indices.items():
        m = marks[:, idx]
        order = np.argsort(m, axis=1)
        k = min(len(tbl), len(idx))
        for place in range(k):
            col = order[:, place]
            ok = np.isfinite(m[np.arange(sims), col])
            rows = idx[col]
            np.add.at(exp_pts, rows[ok], tbl[place])
            np.add.at(pts, (np.arange(sims)[ok], team_idx[rows[ok]]), tbl[place])
            if place == 0:
                np.add.at(win, rows[ok], 1)
            if place < 3:
                np.add.at(top3, rows[ok], 1)
    stats = dict(win=win / sims, top3=top3 / sims, exp_pts=exp_pts / sims)
    return pts, teams, stats


def team_summary(pts, teams):
    """Per team: mean points, P(win), P(top 3), place distribution."""
    sims = pts.shape[0]
    # ranks with random tie-breaking
    noise = np.random.default_rng(1).random(pts.shape) * 1e-6
    rank = (-(pts + noise)).argsort(axis=1).argsort(axis=1)
    out = []
    for j, t in enumerate(teams):
        out.append(dict(team=t, mean=float(pts[:, j].mean()), p10=float(np.percentile(pts[:, j], 10)),
                        p90=float(np.percentile(pts[:, j], 90)),
                        win=float((rank[:, j] == 0).mean()), top3=float((rank[:, j] < 3).mean()),
                        exp_place=float(rank[:, j].mean() + 1)))
    out.sort(key=lambda r: -r['mean'])
    return out


# ---------------------------------------------------------------------------
# Entries: unknown (the entry model guesses) or known (an entry list)
# ---------------------------------------------------------------------------
#
# Two ways to simulate a championship:
#   unknown entries - before the entry lists are out, every candidate enters
#                     each event with the entry model's probability;
#   known entries   - once the meet's entries (or seed list) are published,
#                     exactly the listed athletes and relays run, each event
#                     they are entered in. Marks are still the model's.
# An entrant the model has no row for (no results before the cutoff) runs
# from their seed mark when the list gives one, else is left out and counted.

def relay_key(unit):
    return str(('relay', unit))


class Entries:
    """items: {(key, event): seed value on the log scale, or None}, where
    key is the athlete catalog id or relay_key(team unit); teams: key -> unit."""

    def __init__(self, items, teams, source='', unmatched=0):
        self.items = items
        self.teams = teams
        self.source = source
        self.unmatched = unmatched     # list rows that could not be tied to an athlete

    def keys(self):
        return set(self.items)

    def __len__(self):
        return len(self.items)


def entries_from_truth(truth):
    """Who actually competed: the backtest's stand-in for an entry list
    (scratches are missed, so it is slightly better than a real list)."""
    items, teams, unmatched = {}, {}, 0
    for ev, rows in truth['events'].items():
        for r in rows:
            if not r['aid'] or not r['unit']:
                unmatched += 1
                continue
            k = str(r['aid'])
            items[(k, ev)] = None
            teams[k] = r['unit']
    return Entries(items, teams, source='who competed', unmatched=unmatched)


def entries_from_list(rows, champ, store, cutoff):
    """An entry or seed list: rows of {event, team, name or isRelay, mark}
    (the ui/public/data/seeds/*.json layout). Names are matched to athletes
    of that team (by the team the athlete last competed for before the
    cutoff), then to a statewide unique name of that gender."""
    g = champ['gender']
    y, season = champ['year'], champ['season']
    by_name = collections.defaultdict(list)
    for aid, nm in store.name.items():
        if store.gender.get(aid) == g:
            by_name[name_key(nm)].append(aid)
    tu_cache = {}

    def team_of(aid):
        if aid not in tu_cache:
            u, lv, _ = store.unit_at(aid, cutoff)
            if u and lv == 'ms' and u in store.feeder_best:
                u = store.feeder_best[u][0]
            tu_cache[aid] = _G['fz'].team(u, y, season, g) if u else None
        return tu_cache[aid]

    items, teams, unmatched = {}, {}, 0
    for e in rows:
        ev_raw = e.get('event', '')
        if e.get('gender') and e['gender'] != g:
            continue
        if ev_raw.startswith(('Boys ', 'Girls ')):
            if not ev_raw.startswith(g):
                continue
            ev_raw = ev_raw.split(' ', 1)[1]
        ev = canonical(ev_raw, g) or (ev_raw if ev_raw in FAMILY else None)
        unit = _unit_of(e.get('team') or '', y, season, g, champ.get('file') or 'entries')
        if ev is None or unit is None:
            unmatched += 1
            continue
        seed = perf(e.get('mark') or '', ev)
        if e.get('isRelay') or is_relay_event(ev):
            items[(relay_key(unit), ev)] = seed
            teams[relay_key(unit)] = unit
            continue
        cands = by_name.get(name_key(e.get('name') or ''), [])
        hit = [a for a in cands if team_of(a) == unit]
        aid = hit[0] if len(hit) == 1 else (cands[0] if len(cands) == 1 and not hit else None)
        if aid is None:
            # an athlete with no results on file: runs from the seed mark
            aid = f"entry:{unit}:{name_key(e.get('name') or '')}"
        items[(str(aid), ev)] = seed
        teams[str(aid)] = unit
    return Entries(items, teams, source='entry list', unmatched=unmatched)


def load_entry_file(path):
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    return d['entries'] if isinstance(d, dict) else d


SEED_SCALE = 0.03     # spread for an entrant known only by a seed mark (~3%)


def apply_entries(pred, entries):
    """Fix who runs what: listed (athlete, event) pairs enter for sure,
    everything else is out. Listed entrants the model has no row for run
    from their seed mark. Returns (pred, entrants left out for lack of a mark)."""
    import pandas as pd
    pred = pred.copy()
    keys = entries.keys()
    have = set(zip(pred.aid.values, pred.event.values))
    pred['pent'] = [1.0 if k in keys else 0.0 for k in zip(pred.aid.values, pred.event.values)]
    extra, dropped = [], 0
    for (k, ev), seed in entries.items.items():
        if (k, ev) in have:
            continue
        if seed is None:
            dropped += 1
            continue
        extra.append(dict(champ=pred.champ.iloc[0] if len(pred) else '', cutoff=pred.cutoff.iloc[0] if len(pred) else '',
                          label=pred.label.iloc[0] if len(pred) else '', aid=k, team=entries.teams[k], event=ev,
                          anchor=seed, mean=seed, scale=SEED_SCALE, pent=1.0, relay=k.startswith("('relay'")))
    if extra:
        pred = pd.concat([pred, pd.DataFrame(extra)], ignore_index=True)
    return pred, dropped


# ---------------------------------------------------------------------------
# Live predictions
# ---------------------------------------------------------------------------

def next_edition(champ, year):
    """The coming edition of a championship, from its last one: same class,
    teams, events and scoring; the same weekday a year (or more) on."""
    last = date.fromisoformat(champ['date'])
    d = last + timedelta(days=364 * (year - champ['year']))
    while (d - last).days % 7:
        d += timedelta(days=1)
    c = dict(champ)
    c.update(id=champ['id'].replace(str(champ['year']), str(year), 1), year=year,
             date=d.isoformat(), estimated_date=True, based_on=champ['id'])
    return c


def predict_season(year, asof, sims=5000, quiet=False, entries=None):
    """Predict every championship of academic year `year` (named by its
    spring) from results before `asof`. Championships already on file use
    their real teams and date; the rest are copied from their last edition.

    entries: {championship id: entry-list path or list of rows}. Those meets
    are simulated with known entries (see apply_entries), the rest with
    unknown entries."""
    import pandas as pd
    fz, champs, tr = setup()
    _G.update(fz=fz, tr=tr)
    latest = {}
    for c in champs:
        k = (c['season'], c['kind'], c.get('conference'), c['division'], c['gender'])
        if c['year'] < year and (k not in latest or c['year'] > latest[k]['year']):
            latest[k] = c
    targets = []
    for k, c in sorted(latest.items(), key=lambda kv: kv[1]['id']):
        if c['year'] < year - 2:
            continue          # a meet not held lately
        have = next((x for x in champs if x['year'] == year and
                     (x['season'], x['kind'], x.get('conference'), x['division'], x['gender']) == k), None)
        targets.append((have or next_edition(c, year), tr[c['id']], have is not None))
    A0 = pd.read_pickle(os.path.join(CACHE_DIR, 'athletes.pkl'))
    set_lines(A0)
    A = add_columns(A0)
    R = add_columns(pd.read_pickle(os.path.join(CACHE_DIR, 'relays.pkl')))
    model = Model().fit(A[A.year < year], R[R.year < year])
    out = []
    for champ, last_truth, held in targets:
        cutoff = min(asof, (date.fromisoformat(champ['date']) - timedelta(days=1)).isoformat())
        units = champ_units(tr[champ['id']]) if held else champ_units(last_truth)
        events = sorted(tr[champ['id']]['events']) if held else sorted(last_truth['events'])
        ent = None
        src_ = (entries or {}).get(champ['id'])
        if src_ is not None:
            rows_ = load_entry_file(src_) if isinstance(src_, str) else src_
            ent = entries_from_list(rows_, champ, fz.s, cutoff)
            units = units | set(ent.teams.values())
            events = sorted(set(events) | {ev for _, ev in ent.items})
        a, r = rows_for(champ, cutoff, 'live', None, units=units, events=events,
                        keep=ent.keys() if ent else ())
        if ent is None:
            a = [x for x in a if x['in_top']]
        if not a:
            continue
        Adf = add_columns(pd.DataFrame(a).assign(aid=lambda d: d.aid.astype(str)))
        Rdf = add_columns(pd.DataFrame(r).assign(aid=lambda d: d.aid.astype(str))) if r else Adf.iloc[:0]
        pred = model.predict(Adf, Rdf)
        dropped = 0
        if ent is not None:
            pred, dropped = apply_entries(pred, ent)
        table = (tr[champ['id']] if held else last_truth)['table']
        pts, teams, st = simulate(pred, table, *model.z_for(champ['id']), sims=sims, seed=1,
                                  max_events=None if ent else max_events_for(champ['id']))
        out.append(dict(champ=champ, cutoff=cutoff, held=held, pred=pred.assign(**{k: v for k, v in st.items()}),
                        teams=team_summary(pts, teams), table=table,
                        entries='known' if ent else 'unknown',
                        entry_stats=dict(listed=len(ent), unmatched=ent.unmatched,
                                         no_results=sum(k.startswith('entry:') for k, _ in ent.items),
                                         no_mark=dropped) if ent else None))
        if not quiet:
            top = ', '.join(f"{t['team'].replace('me-hs-', '')} {t['mean']:.0f} ({100 * t['win']:.0f}%)"
                            for t in out[-1]['teams'][:4])
            print(f"{champ['id']:34} as of {cutoff} ({out[-1]['entries']} entries): {top}")
    return out, model


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    sub = ap.add_subparsers(dest='cmd')
    sub.add_parser('champs', help='rebuild backend/data/track_champs.json')
    sub.add_parser('store', help='rebuild the cached store')
    sub.add_parser('dataset', help='rebuild the backtest dataset (all championships x cutoffs)')
    pp = sub.add_parser('predict', help='predict a season\'s championships')
    pp.add_argument('--year', type=int, required=True, help='academic year, named by its spring (2027)')
    pp.add_argument('--asof', default=date.today().isoformat(), help='use results before this day')
    pp.add_argument('--entries', nargs='*', default=[], metavar='CHAMP=PATH',
                    help='known entries for a meet: championship id = entry-list JSON')
    pp.add_argument('--sims', type=int, default=4000)
    pp.add_argument('--out', help='pickle the predictions here')
    a = ap.parse_args(argv)
    if a.cmd == 'champs':
        champs = build_champs() + build_conf_champs()
        # the store files a meet under its sub5 index date where that and the
        # sheet's title disagree (2006 Class A: index 6/3, title 6/10); the
        # champ takes the store's date so its athletes join and the eve
        # cutoff falls before the meet's own marks
        synced = json.load(open(os.path.join(DATA, 'scrape_state.json'))).get('synced_meets', {})
        for c in champs:
            k = f"{c['year']}_{c['season']}_{c['file']}"
            d = synced.get(k)
            if d and re.match(r'^\d{4}-\d\d-\d\d$', d) and d != c['date']:
                c['sheet_date'], c['date'] = c['date'], d
        with open(CHAMPS_PATH, 'w', encoding='utf-8') as f:
            json.dump({'_doc': 'MPA state track meets by class and gender, found by '
                               'backend/track_postseason.py build_champs; edit by hand only to fix a pick.',
                       'champs': champs}, f, indent=1)
        print(f'{len(champs)} championships')
        for c in champs:
            print(c['id'], c['date'], c['file'], c.get('letter_from', ''), len(c.get('teams', [])))
    elif a.cmd == 'store':
        load_store(use_cache=False)
    elif a.cmd == 'dataset':
        build_dataset()
    elif a.cmd == 'predict':
        ent = dict(x.split('=', 1) for x in a.entries)
        out, _ = predict_season(a.year, a.asof, sims=a.sims, entries=ent)
        for o in out:
            if o['entry_stats']:
                print(f"  {o['champ']['id']}: {o['entry_stats']}")
        if a.out:
            with open(a.out, 'wb') as f:
                pickle.dump(out, f)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
