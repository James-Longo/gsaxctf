"""
track_champ_predict.py - the postseason predictor's championship predictions,
for the site's postseason simulator.

    python3 -m backend.track_champ_predict --past            # every season in the backtest dataset
    python3 -m backend.track_champ_predict --year 2027       # this season's meets as of today

--past: each season's championships predicted the day before the meet by
models fitted on the other seasons (the backtest's leave-one-season-out), so
predicted vs result on the site is honest. --year: the live prediction from
results before today, models fitted on earlier seasons (what the routine runs).

Writes ui/public/data/track_preds/<year>_<season>.json.gz:
  {year, season, asof, champs: [{id, kind, division, gender, date, table, cutoff,
   teams: [{team, pts, p: [1st, 2nd, 3rd]}], events: {event: [{n, t, m, p, x, w, pl}]}}]}
per event row: athlete name (relays: none), team, predicted mark, entry
chance, expected points, chance of winning, and for a meet already run the
place they took (absent: did not compete in it). Teams are named as the store files
them (school_catalog.store_name), like track_champ_results.
"""

import argparse
import collections
import gzip
import json
import multiprocessing as mp
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import school_catalog as sc  # noqa: E402
from backend import track_postseason as tp  # noqa: E402

OUT_DIR = os.path.join(tp.BASE, 'ui', 'public', 'data', 'track_preds')
SIMS = 4000
MIN_ROW = 0.05     # rows below this entry chance and expected points are left out


def champ_out(champ, pred, model, table, names, cutoff):
    pts, teams, st = tp.simulate(pred, table, *model.z_for(champ['id']), sims=SIMS, seed=1,
                                 max_events=tp.max_events_for(champ['id']))
    summ = tp.team_summary(pts, teams)
    pred = pred.assign(**st)
    events = {}
    for ev, rows in pred.groupby('event'):
        rows = rows[(rows.pent >= MIN_ROW) | (rows.exp_pts >= MIN_ROW)].sort_values('exp_pts', ascending=False)
        out = []
        for r in rows.itertuples():
            unit = r.team
            row = dict(n='' if r.relay else names.get(r.aid, ''), t=sc.store_name(unit) or unit,
                       m=tp.mark_str(r.mean, ev), p=round(float(r.pent), 3),
                       x=round(float(r.exp_pts), 2), w=round(float(r.win), 3))
            if 'place' in rows and np.isfinite(r.place):
                row['pl'] = int(r.place)
            out.append(row)
        events[ev] = out
    keep = ('id', 'kind', 'conference', 'division', 'gender', 'date')
    return dict({k: champ[k] for k in keep if k in champ}, table=table, cutoff=cutoff,
                teams=[dict(team=sc.store_name(t['team']) or t['team'], pts=round(t['mean'], 2),
                            p=[round(x, 4) for x in t['places']]) for t in summ],
                events=events)


def write(year, season, champs, asof):
    os.makedirs(OUT_DIR, exist_ok=True)
    raw = json.dumps(dict(year=year, season=season, asof=asof, champs=champs), separators=(',', ':'),
                     default=lambda o: o.item())   # numpy scalars
    with gzip.open(os.path.join(OUT_DIR, f'{year}_{season}.json.gz'), 'wb', compresslevel=9) as f:
        f.write(raw.encode('utf-8'))
    index = sorted(f[:-len('.json.gz')] for f in os.listdir(OUT_DIR) if f.endswith('.json.gz'))
    with open(os.path.join(OUT_DIR, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=1)


_SHARED = {}


def _past_year(year):
    A, R, tr, champs, names = (_SHARED[k] for k in ('A', 'R', 'tr', 'champs', 'names'))
    model = tp.Model().fit(A[A.year != year], R[R.year != year])
    At = A[(A.year == year) & (A.label == 'eve') & A.in_top.astype(bool)]
    Rt = R[(R.year == year) & (R.label == 'eve')]
    pred = model.predict(At, Rt)
    pred = pred.merge(pd.concat([At[['champ', 'aid', 'event', 'place']], Rt[['champ', 'aid', 'event', 'place']]]),
                      on=['champ', 'aid', 'event'], how='left')
    out = collections.defaultdict(list)
    for c in champs:
        if c['year'] != year:
            continue
        rows = pred[pred.champ == c['id']].reset_index(drop=True)
        if not len(rows):
            continue
        out[c['season']].append(champ_out(c, rows, model, tr[c['id']]['table'], names, rows.cutoff.iloc[0]))
    for season, cs in out.items():
        write(year, season, cs, None)
    return year, {k: len(v) for k, v in out.items()}


def past(years=None, procs=4):
    from backend import track_postseason_cv as cv
    A, R, tr = cv.load()
    store = tp.load_store(quiet=True)
    _SHARED.update(A=A, R=R, tr=tr, champs=tp.load_champs(), names={str(k): v for k, v in store.name.items()})
    years = years or sorted(A.year.unique())
    os.environ['OMP_NUM_THREADS'] = '2'
    with mp.get_context('fork').Pool(procs) as pool:
        for year, by in pool.imap_unordered(_past_year, years):
            print(f'{year}: {by} championships', file=sys.stderr, flush=True)


DATASET_DAYS = 28   # the training dataset (past seasons) is rebuilt when older than this


def _dataset_ok():
    """The dataset is recent and built from the current store (a new athlete
    catalog or relay-leg resolution rebuilds the store, then this)."""
    path = os.path.join(tp.CACHE_DIR, 'athletes.pkl')
    tp.load_store(quiet=True)            # rebuilds store.pkl when the data or catalog changed
    return (os.path.exists(path) and (date.today() - date.fromtimestamp(os.path.getmtime(path))).days <= DATASET_DAYS
            and os.path.getmtime(path) > os.path.getmtime(os.path.join(tp.CACHE_DIR, 'store.pkl')))


def live(year, asof):
    if not _dataset_ok():
        tp.build_dataset(procs=4, quiet=True)
    out, model = tp.predict_season(year, asof, sims=1, quiet=True)
    names = {str(k): v for k, v in tp._G['fz'].s.name.items()}
    by = collections.defaultdict(list)
    for o in out:
        c = o['champ']
        pred = o['pred'].drop(columns=['win', 'top3', 'exp_pts'], errors='ignore')
        by[c['season']].append(champ_out(c, pred, model, o['table'], names, o['cutoff']))
    for season, champs in by.items():
        write(year, season, champs, asof)
        print(f'{year} {season}: {len(champs)} championships as of {asof}', file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--past', action='store_true')
    ap.add_argument('--years', type=int, nargs='*')
    ap.add_argument('--year', type=int)
    ap.add_argument('--asof', default=date.today().isoformat())
    a = ap.parse_args(argv)
    if a.past:
        past(a.years)
    elif a.year:
        live(a.year, a.asof)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
