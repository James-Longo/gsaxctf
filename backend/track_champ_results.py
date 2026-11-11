"""
track_champ_results.py - what happened at each track championship, for the
site's postseason simulator (predicted vs result).

    python3 -m backend.track_champ_results                 # every season on file
    python3 -m backend.track_champ_results --year 2026 --season Indoor

Reads the championships in backend/data/track_champs.json (MPA state meets by
class, EMITL / PVC conference meets by division) through
track_postseason.champ_results: places from the finals, the other division of
a two-division sheet left out, team totals scored with the table that
reproduces the official scores. Writes one file per season,
ui/public/data/track_champs/<year>_<season>.json.gz, listed in index.json.

Teams are named as the store files them (school_catalog.store_name), the names
the simulator reads its results under.
"""

import argparse
import collections
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import school_catalog as sc  # noqa: E402
from backend import track_postseason as tp  # noqa: E402

OUT_DIR = os.path.join(tp.BASE, 'ui', 'public', 'data', 'track_champs')


class _NoStore:
    """champ_results only uses the store to join athletes to catalog ids,
    which the site does not need."""
    marks, gender, name = {}, {}, {}


def champ_out(champ):
    r = tp.champ_results(champ, _NoStore())
    table = r['table']
    name = lambda u, raw='': sc.store_name(u) if u else raw  # noqa: E731
    events = {}
    for ev, rows in r['events'].items():
        out = []
        for i, x in enumerate(rows):
            row = dict(pl=i + 1, n=x['name'], t=name(x['unit'], x.get('school', '')), m=x['mark'])
            if x.get('grade'):
                row['g'] = x['grade']
            if i < len(table) and x['unit']:
                row['pts'] = table[i]
            out.append(row)
        events[ev] = out
    official = {name(u): s for s, u in r['official']}
    teams = [dict(team=name(u), score=s, official=official.get(name(u)))
             for u, s in sorted(r['teams'].items(), key=lambda kv: -kv[1])]
    keep = ('id', 'year', 'season', 'kind', 'conference', 'division', 'gender', 'date', 'file')
    return dict({k: champ[k] for k in keep if k in champ}, table=table, teams=teams, events=events)


def write(year, season, champs):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f'{year}_{season}.json.gz')
    out = [champ_out(c) for c in champs]
    out = [c for c in out if c['events']]
    raw = json.dumps(dict(year=year, season=season, champs=out), separators=(',', ':')).encode('utf-8')
    with gzip.open(path, 'wb', compresslevel=9) as f:
        f.write(raw)
    return len(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int)
    ap.add_argument('--season', choices=('Indoor', 'Outdoor'))
    a = ap.parse_args(argv)
    by = collections.defaultdict(list)
    for c in tp.load_champs():
        if (a.year is None or c['year'] == a.year) and (a.season is None or c['season'] == a.season):
            by[(c['year'], c['season'])].append(c)
    for (y, s), cs in sorted(by.items()):
        n = write(y, s, cs)
        print(f'{y} {s}: {n} of {len(cs)} championships with results', file=sys.stderr)
    index = sorted(f[:-len('.json.gz')] for f in os.listdir(OUT_DIR) if f.endswith('.json.gz'))
    with open(os.path.join(OUT_DIR, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=1)


if __name__ == '__main__':
    main()
