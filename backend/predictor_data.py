"""Owen's Predictor data: ui/public/data/predictor.json.gz.

Every runner's best mark in each predictor event, over all teams and both
track seasons, with the spellings the athlete catalog merged counted as one
runner and the entries it does not count as runners (field relay team
totals filed under the individual event) left out; plus a least-squares line for every same-gender event pairing, fit
on every runner who has both events. The site only reads this file.

Rebuilt by athlete_catalog.apply (so by every resync) or on its own:
    python3 -m backend.predictor_data
"""
import collections
import os

from backend import json_store as js

DEST = os.path.join(js.DATA_DIR, 'predictor.json.gz')

TRACK = ['55 Meter Dash', '200 Meter Dash', '400 Meter Dash', '800 Meter Run',
         '1 Mile Run', '2 Mile Run', '55 Meter Hurdles']
FIELD = ['Long Jump', 'Triple Jump', 'Shot Put', 'High Jump', 'Pole Vault']
SEASONS = ('Indoor', 'Outdoor')


# What a middle or high school athlete can really do, from a beginner's
# first meet to past the Maine records (seconds; inches for field events).
# Wide on purpose: a 3'10" sixth-grade long jump or a 2:04 400 is a real
# mark and belongs in the fit. Only what no school athlete can do is cut:
# typos, and marks filed under the wrong event, which qaqc check 16 finds at
# their source.
BOUNDS = {
    '55 Meter Dash': (6.0, 15.0),
    '200 Meter Dash': (20.5, 75.0),
    '400 Meter Dash': (46.0, 150.0),
    '800 Meter Run': (110.0, 330.0),
    '1 Mile Run': (240.0, 720.0),
    '2 Mile Run': (520.0, 1500.0),
    '55 Meter Hurdles': (7.0, 20.0),
    'Long Jump': (36.0, 312.0),
    'Triple Jump': (120.0, 600.0),
    'Shot Put': (60.0, 780.0),
    'High Jump': (30.0, 90.0),
    'Pole Vault': (36.0, 204.0),
}


def _valid(event, value):
    lo, hi = BOUNDS[event.split(' ', 1)[1]]
    return lo <= value <= hi


def _runner_of():
    """store athlete id -> (runner id, catalog name)."""
    owner = {}
    for a in js._load_json(js.ATHLETES_PATH, []):
        if a.get('kind') == 'relay':
            continue
        for sid in a.get('members') or [a['id']]:
            owner[sid] = (a['id'], a['name'])
    return owner


def collect_bests():
    """{event: {runner id: best value}} and {runner id: name}."""
    track = {f'{g} {e}' for g in ('Boys', 'Girls') for e in TRACK}
    field = {f'{g} {e}' for g in ('Boys', 'Girls') for e in FIELD}
    owner = _runner_of()
    bests = collections.defaultdict(dict)
    names = {}
    for team in js.list_teams():
        d = js.team_dir(team)
        if not os.path.isdir(d):
            continue
        for key, fn in js._chunk_files(d):
            if not key.endswith(SEASONS):
                continue
            rows = js.enrich_rows(team, key, js._load_json(os.path.join(d, fn), []))
            for p in rows:
                event = p.get('event')
                if event not in track and event not in field:
                    continue
                value, _ = js.parse_mark_value(p.get('mark'), event)
                is_track = event in track
                if value is None or not _valid(event, value):
                    continue
                if p['athlete_id'] not in owner:
                    continue  # a team entry ("Brewer A": a field relay's total), not a runner
                rid, name = owner[p['athlete_id']]
                names.setdefault(rid, name)
                old = bests[event].get(rid)
                if old is None or (value < old if is_track else value > old):
                    bests[event][rid] = value
    return bests, names


def fit(xs, ys):
    """Least-squares y = slope * x + intercept."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0.0
    return slope, my - slope * mx


def build(quiet=False):
    bests, names = collect_bests()
    runners = sorted({r for ev in bests.values() for r in ev})
    index = {r: i for i, r in enumerate(runners)}
    events = {ev: sorted([index[r], round(v, 2)] for r, v in by.items())
              for ev, by in sorted(bests.items())}
    fits = {}
    for g in ('Boys', 'Girls'):
        evs = [f'{g} {e}' for e in TRACK + FIELD if f'{g} {e}' in bests]
        for y_ev in evs:
            for x_ev in evs:
                if x_ev == y_ev:
                    continue
                both = bests[x_ev].keys() & bests[y_ev].keys()
                if len(both) < 2:
                    continue
                slope, intercept = fit([bests[x_ev][r] for r in both], [bests[y_ev][r] for r in both])
                fits[f'{y_ev}|{x_ev}'] = dict(n=len(both), slope=round(slope, 6),
                                              intercept=round(intercept, 4))
    out = dict(order=[f'{g} {e}' for e in TRACK + FIELD for g in ('Boys', 'Girls')],
               track=[f'{g} {e}' for g in ('Boys', 'Girls') for e in TRACK],
               names=[names[r] for r in runners], events=events, fits=fits)
    js._atomic_write(DEST, out)
    if not quiet:
        print(f'{DEST}: {len(runners)} runners, {len(fits)} event pairings')
    return out


if __name__ == '__main__':
    build()
