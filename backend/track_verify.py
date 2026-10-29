"""
track_verify.py - indoor/outdoor team scores checked against the file's own.

A results file that prints official team scores is re-scored from our parse
and compared. Two ways of scoring, best fit wins:

  printed   the points each row prints (Hy-Tek "Points" column), summed per
            team: no scoring rules involved, so a difference is the parse
            (a missing row, a row filed under the wrong school)
  table     points by printed place (or mark) with a points table fitted
            to the meet (10-8-6-4-2-1, 6-4-3-2-1, 5-3-1, ...), ties shared,
            an optional per-team scoring limit, Finals only, exhibition out

Teams are compared through the school catalog: "BRUN", "Brunswick" and the
official "Brunswick High School" are one school, and a co-op is its members.
A team the catalog can't place falls back to its printed name.

A scores-only file (Hy-Tek "Team Rankings - Through Event 38" posted next to
the results, brunswickscores4_20 beside brunswick4_20) is checked against
the results file of the same meet: same season, same date, the same schools.

    python3 -m backend.track_verify            # every track file -> meet_verification.json
    python3 -m backend.track_verify 2016/Outdoor/BucksportMeet   # one file, verbose
"""

import collections
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, 'backend'))

PARSED = os.path.join(BASE, 'backend', 'data', 'parsed_results')
VERIFICATION = os.path.join(BASE, 'backend', 'data', 'meet_verification.json')

TABLES = [
    ('10-8-6-4-2-1', [10, 8, 6, 4, 2, 1]),
    ('10-8-6-5-4-3-2-1', [10, 8, 6, 5, 4, 3, 2, 1]),
    ('10-8-6-4-3-2-1', [10, 8, 6, 4, 3, 2, 1]),      # SMAA / KVAC: seven places
    ('8-6-4-2-1', [8, 6, 4, 2, 1]),
    ('8-6-4-3-2-1', [8, 6, 4, 3, 2, 1]),
    ('6-4-3-2-1', [6, 4, 3, 2, 1]),
    ('5-3-2-1', [5, 3, 2, 1]),
    ('5-3-1', [5, 3, 1]),
]
RELAY_TABLES = {'5-3-1': [[5], [5, 3, 1]], '5-3-2-1': [[5, 3], [5, 3, 2, 1]]}
BAD = {'DQ', 'DNF', 'DNS', 'NH', 'NM', 'FOUL', 'SCR', 'FS', 'NT', 'ND', 'X'}
TRACK = ('dash', 'run', 'hurdle', 'relay', 'mile', 'walk', 'steeple', 'meter', 'yard', '4x', 'm ')


def _key(name):
    n = re.sub(r'[^a-z0-9 ]', ' ', (name or '').lower())
    n = re.sub(r'\b(high|school|hs|h s|academy|regional|community|area|the|track|team|outdoor|indoor|'
               r'girls|boys|men|women|of)\b', ' ', n)
    return re.sub(r'\s+', '', n)


class Teams:
    """Raw school string -> comparable team id, through the catalog."""

    def __init__(self, year, season, stem):
        from backend import school_catalog as sc
        self.sc, self.year, self.season, self.stem = sc, str(year), season, stem
        self.cache = {}

    def __call__(self, raw, gender=None):
        # Hy-Tek team accounts: "YORK HIGH SCHOOL OUTDOOR 2", "Gorham High
        # School indoor", "Winslow high school track", "Cheverus Stags"
        raw = re.sub(r'(?i)\b(?:outdoor|indoor|itrack|otrack|track(?:\s*(?:&|and)\s*field)?|t\s*&\s*f|'
                     r'xc|girls|boys|men|women)\b', ' ', raw or '').strip(' -')
        k = (raw, gender)
        if k not in self.cache:
            u = None
            # a number can be the name ("Union 122") or an account suffix ("... OUTDOOR 2"):
            # the whole string first, then without the number
            for cand in dict.fromkeys([raw, re.sub(r'\b\d{1,4}\s*$', '', raw).strip(' -')]):
                try:
                    u = self.sc.store_unit(cand, year=self.year, season=self.season, gender=gender,
                                           meet_name=self.stem)
                except Exception:  # noqa: BLE001
                    u = None
                if u:
                    break
            self.cache[k] = u or ('raw:' + _key(re.sub(r'\b\d{1,4}\s*$', '', raw).strip(' -')))
        return self.cache[k]

    def members(self, uid):
        """A co-op and its member schools compare as one team."""
        e = self.sc.info(uid) if not uid.startswith('raw:') else None
        return set((e or {}).get('members') or []) | {uid}


def _gender_of(block):
    g = (block.get('gender') or '').lower()
    return 'Girls' if g in ('girls', 'women', 'female') else 'Boys' if g in ('boys', 'men', 'male') else \
        'Combined' if g == 'combined' else block.get('gender')


def _value(mark, event):
    try:
        from backend.json_store import parse_mark_value
        v, _ = parse_mark_value(mark, event)
        return v
    except Exception:  # noqa: BLE001
        return None


def _races(parsed):
    """(gender, event, is_relay, division#) -> scoring rows (Finals only when
    the event has finals; exhibition and seed rows out)."""
    blocks = collections.OrderedDict()
    for e in parsed.get('events') or []:
        if not isinstance(e, dict) or not e.get('results'):
            continue
        base = (e.get('gender'), e.get('event'), bool(e.get('is_relay')))
        rows = [r for r in e['results'] if r.get('type') != 'Seed' and not r.get('exhibition')]
        if rows:
            blocks.setdefault(base, []).append(rows)
    out = collections.OrderedDict()
    for base, bl in blocks.items():
        # a prelim section is not a race of its own when the event has finals
        fin = [[r for r in b if r.get('type') == 'Finals'] for b in bl]
        fin = [b for b in fin if b]
        use = fin or bl
        seen = []
        for b in use:
            sig = sorted((r.get('athlete') or r.get('school'), r.get('result')) for r in b)
            if sig in seen:
                continue      # the whole report printed twice
            seen.append(sig)
            # a repeated finals block of one event is a division of it
            out[base + (len(seen) - 1,)] = b
    return out


def score_printed(races, teams):
    pts = collections.defaultdict(lambda: collections.defaultdict(float))
    n_with = 0
    for (g, ev, rel, _), rows in races.items():
        got = [r for r in rows if r.get('points') is not None]
        if got:
            n_with += 1
        for r in got:
            pts[g][teams(r.get('school', ''), g)] += r['points']
    return pts if n_with >= max(1, 0.5 * len(races)) else None


def score_table(races, teams, table, relay_table, limit, merge_divisions=False):
    pts = collections.defaultdict(lambda: collections.defaultdict(float))
    for (g, ev, rel, div), rows in races.items():
        tab = relay_table if rel else table
        lim = 1 if rel and limit else limit
        marks = []
        for r in rows:
            m = (r.get('result') or '').strip()
            if not m or m.upper() in BAD or not r.get('school'):
                continue
            pl = r.get('place')
            v = _value(m, ev)
            if v is None and pl is None:
                continue
            marks.append((pl, v, teams(r.get('school', ''), g)))
        if not marks:
            continue
        if all(p is not None for p, _, _ in marks):
            marks.sort(key=lambda x: x[0])
            group = lambda x: x[0]
        else:
            low = any(k in (ev or '').lower() for k in TRACK) and not any(
                k in (ev or '').lower() for k in ('jump', 'vault', 'put', 'throw', 'discus', 'javelin'))
            marks = [x for x in marks if x[1] is not None]
            marks.sort(key=lambda x: x[1], reverse=not low)
            group = lambda x: x[1]
        per = collections.Counter()
        slot, i = 0, 0
        while i < len(marks) and slot < len(tab):
            j = i
            while j < len(marks) and group(marks[j]) == group(marks[i]):
                j += 1
            tied = [x for x in marks[i:j] if not lim or per[x[2]] < lim]
            if tied:
                n = min(len(tied), len(tab) - slot)
                share = sum(tab[slot:slot + n]) / len(tied)
                for x in tied:
                    pts[g][x[2]] += share
                    per[x[2]] += 1
                slot += n
            i = j
    return pts


def compare(blocks, computed, teams):
    """Total absolute difference and per-team rows for one scoring."""
    total, rows = 0.0, []
    for b in blocks:
        g = _gender_of(b)
        if g == 'Combined':
            ours = collections.defaultdict(float)
            for gg in computed:
                for t, v in computed[gg].items():
                    ours[t] += v
        else:
            ours = computed.get(g, {})
        used = set()
        got_by = []
        for t in b['teams']:
            uid = teams(t['team'], g if g != 'Combined' else None)
            fam = teams.members(uid)
            hit = {k for k in ours if k in fam or teams.members(k) & {uid}}
            used |= hit
            got_by.append([t, sum(ours[k] for k in hit), bool(hit)])
        # An official name the catalog can't place ("LINCLOLN ACADEMY") is
        # the team of ours nobody claimed with the same points, or failing
        # that one sharing a word of the name.
        spare = {k: v for k, v in ours.items() if k not in used and v}
        for row in got_by:
            t, got, hit = row
            if hit or not spare:
                continue
            same = [k for k, v in spare.items() if abs(v - t['score']) <= 0.5]
            words = set(re.findall(r'[a-z]{4,}', t['team'].lower())) - {'high', 'school', 'academy', 'track'}
            named = [k for k in spare if words & set(re.findall(r'[a-z]{4,}', k.replace('-', ' ')))]
            pick = same[0] if len(same) == 1 else named[0] if len(named) == 1 else None
            if pick:
                row[1] = spare.pop(pick)
        # A team split in two -- relays under the full name, individuals
        # under a code or nickname ("Lawrence" / "Bulldogs", "Mta Road
        # Runners" / "Mta") -- is short by exactly one unclaimed group's points.
        for _ in range(3):
            for row in got_by:
                t, got, _h = row
                short = t['score'] - got
                if short <= 0.5 or not spare:
                    continue
                fit = [k for k, v in spare.items() if abs(v - short) <= 0.5]
                if len(fit) == 1:
                    row[1] = got + spare.pop(fit[0])
        for t, got, _ in got_by:
            d = got - t['score']
            total += abs(d)
            rows.append(dict(gender=g, team=t['team'], official=t['score'], computed=round(got, 2),
                             delta=round(d, 2)))
    return total, rows


def _merge_divisions(blocks, teams):
    """Several scores blocks for one sex (Junior / Senior / Open divisions,
    each scored on its own): every printed point is in exactly one of them,
    so their sum per team is what the printed points add up to."""
    by_g = collections.OrderedDict()
    for b in blocks:
        by_g.setdefault(_gender_of(b), []).append(b)
    out = []
    for g, bl in by_g.items():
        if len(bl) == 1:
            out.append(bl[0])
            continue
        tot, names = collections.OrderedDict(), {}
        for b in bl:
            for t in b['teams']:
                k = teams(t['team'], g)
                tot[k] = tot.get(k, 0.0) + t['score']
                names.setdefault(k, t['team'])
        out.append({'gender': g, 'divisions': len(bl),
                    'teams': [{'rank': i + 1, 'team': names[k], 'score': v}
                              for i, (k, v) in enumerate(tot.items())]})
    return out


def verify(parsed, year, season, stem, results=None):
    blocks = [b for b in parsed.get('team_rankings') or [] if b.get('teams')]
    if not blocks:
        return None
    src = results or parsed
    teams = Teams(year, season, stem)
    races = _races(src)
    if not races:
        return dict(status='scores_only')
    # a girls' file that also prints the boys' standings: nothing to check them against
    sexes = {k[0] for k in races}
    blocks = [b for b in blocks if _gender_of(b) in sexes or _gender_of(b) == 'Combined']
    if not blocks:
        return dict(status='rankings_other_gender')
    blocks = _merge_divisions(blocks, teams)
    candidates = []
    pp = score_printed(races, teams)
    if pp is not None:
        candidates.append(('printed', pp))
    for name, tab in TABLES:
        for lim in (None, 3):
            rel_tabs = RELAY_TABLES.get(name, [tab])
            for rt in rel_tabs:
                label = f'{name}{"/3" if lim else ""}{"/relay " + "-".join(map(str, rt)) if rt != tab else ""}'
                candidates.append((label, score_table(races, teams, tab, rt, lim)))
    best = None
    for label, comp in candidates:
        total, rows = compare(blocks, comp, teams)
        if best is None or total < best[0] - 1e-9:
            best = (total, label, rows)
    total, label, rows = best
    off = [r for r in rows if abs(r['delta']) > 0.5]
    official = sum(r['official'] for r in rows)
    status = 'verified' if not off else \
        'verified_close' if total <= max(2.0, 0.02 * official) else 'mismatch'
    return dict(status=status, scoring_system=label, teams_off=len(off),
                max_delta=max((abs(r['delta']) for r in rows), default=0.0),
                total_delta=round(total, 2), teams=len(rows),
                worst=sorted(off, key=lambda r: -abs(r['delta']))[:5])


def _load(path):
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {'events': d}
    except (OSError, ValueError):
        return None


def _partner(year, season, stem, parsed, index):
    """The results file a scores-only file belongs to: same season, same
    date, and the most official schools among its rows."""
    date = (parsed.get('date') or '')[:10]
    if not date:
        return None       # undated: any meet of the season with these schools would do
    teams = Teams(year, season, stem)
    names = {teams(t['team']) for b in parsed.get('team_rankings') or [] for t in b.get('teams', [])}
    best, best_n = None, 0
    for st, d in index.get((year, season), {}).items():
        if st == stem or not d.get('events') or (d.get('date') or '')[:10] != date:
            continue
        other = Teams(year, season, st)
        schools = {other(r.get('school')) for e in d['events'] if isinstance(e, dict)
                   for r in (e.get('results') or [])[:40]}
        n = len(names & schools)
        if n > best_n:
            best, best_n = st, n
    return best if best_n >= 2 else None


def check_all(quiet=False):
    say = (lambda *a: None) if quiet else print
    out = {}
    index = collections.defaultdict(dict)
    files = []
    for year in sorted(os.listdir(PARSED)):
        for season in ('Indoor', 'Outdoor'):
            d = os.path.join(PARSED, year, season)
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if fn.endswith('.json'):
                    p = _load(os.path.join(d, fn))
                    if p is not None:
                        index[(year, season)][fn[:-5]] = p
                        files.append((year, season, fn[:-5]))
    for year, season, stem in files:
        parsed = index[(year, season)][stem]
        key = f'{year}_{season}_{stem}'
        try:
            v = verify(parsed, year, season, stem)
            if v and v['status'] == 'scores_only':
                partner = _partner(year, season, stem, parsed, index)
                if partner:
                    v = verify(parsed, year, season, stem, results=index[(year, season)][partner])
                    v['results_file'] = partner
            out[key] = v or {'status': 'no_rankings'}
        except Exception as e:  # noqa: BLE001
            out[key] = {'status': 'error', 'error': str(e)[:200]}
    c = collections.Counter(v['status'] for v in out.values())
    say('track team-score verification:', dict(c))
    return out


def save(results):
    try:
        with open(VERIFICATION, encoding='utf-8') as f:
            ver = json.load(f)
    except (OSError, ValueError):
        ver = {}
    for k in [k for k in ver if re.match(r'\d{4}_(Indoor|Outdoor)_', k)]:
        del ver[k]
    ver.update(results)
    with open(VERIFICATION, 'w', encoding='utf-8') as f:
        json.dump(ver, f, indent=1, sort_keys=True)


def main():
    if len(sys.argv) > 1:
        year, season, stem = sys.argv[1].split('/', 2)
        parsed = _load(os.path.join(PARSED, year, season, stem + '.json'))
        print(json.dumps(verify(parsed, year, season, stem), indent=1))
        return
    save(check_all())


if __name__ == '__main__':
    main()
