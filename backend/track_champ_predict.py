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
  {year, season, asof, champs: [{id, kind, division, gender, date, table, cutoff, basis,
   teams: [{team, pts, p: [1st, 2nd, 3rd]}], events: {event: [{n, t, m, p, x, w, pl}]},
   entries: {event: [{n, t, p, e}]}, legs: {relay event: [{n, t, p, e}]}}]}
entries / legs: each athlete's (relays: each team's) chance of entering the
event, and each runner's chance of running a leg, from the meet simulated
with entries predicted (event limit applied, legs included); e: they did
(meets already run). teams / events: the outcome, from the actual entries
for a meet already run (basis 'entered'), else from the predicted ones
(basis 'predicted'); per event row: athlete name (relays: none), team,
predicted mark, entry chance, expected points, chance of winning, place
taken. Teams are named as the store files them (school_catalog.store_name),
like track_champ_results.
"""

import argparse
import collections
import gzip
import json
import multiprocessing as mp
import os
import pickle
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


ENTRY_MIN = 0.02   # entry and leg chances below this are left out (unless they entered)


def _event_rows(pred, st, names, ev_truth=None):
    """Per event: predicted mark, entry chance, expected points, win chance, place."""
    pred = pred.assign(**{k: v for k, v in st.items() if k != 'legs'})
    events = {}
    for ev, rows in pred.groupby('event'):
        rows = rows[(rows.entered >= MIN_ROW) | (rows.exp_pts >= MIN_ROW)].sort_values('exp_pts', ascending=False)
        out = []
        for r in rows.itertuples():
            row = dict(n='' if r.relay else names.get(r.aid, ''), t=sc.store_name(r.team) or r.team,
                       m=tp.mark_str(r.mean, ev), p=round(float(r.entered), 3),
                       x=round(float(r.exp_pts), 2), w=round(float(r.win), 3))
            pl = (ev_truth or {}).get((r.aid, ev))
            if pl:
                row['pl'] = pl
            out.append(row)
        events[ev] = out
    return events


def _teams(pts, teams):
    return [dict(team=sc.store_name(t['team']) or t['team'], pts=round(t['mean'], 2),
                 p=[round(x, 4) for x in t['places']]) for t in tp.team_summary(pts, teams)]


def _truth_sets(truth):
    """From a meet already run: {(aid, event): place} for athletes and relays,
    {(aid, relay event)} for relay legs, and every entrant's (aid, event, name, unit)."""
    place, legs, rows = {}, set(), []
    for ev, rs in truth['events'].items():
        for i, r in enumerate(rs):
            k = (str(r['aid']), ev) if r['aid'] else None
            if k and k not in place:
                place[k] = i + 1
            rows.append((k, ev, r))
            for a in (r.get('legs') or ()) if tp.is_relay_event(ev) else ():
                if not a.startswith('?'):
                    legs.add((a, ev))
    return place, legs, rows


def champ_out(champ, pred, z, table, names, cutoff, legs=None, truth=None):
    """One championship for the site.

    entries: per event, each athlete's (relays: each team's) chance of
    entering it, from the meet simulated with entries predicted (event limit
    applied, relay legs included); legs: per relay event, each runner's
    chance of running a leg. Where the meet has been run, `e` marks who did.
    teams / events: the outcome. A meet already run is simulated from its
    actual entries (basis 'entered'), a coming one from the predicted entries
    (basis 'predicted').
    z: the (athlete, relay) residual pools for this kind of meet."""
    cap = tp.max_events_for(champ['id'])
    top = pred[pred.in_top.astype(bool)].reset_index(drop=True) if 'in_top' in pred else pred
    pts, teams, st = tp.simulate(top, table, *z, sims=SIMS, seed=1, max_events=cap, legs=legs)
    place, leg_truth, truth_rows = _truth_sets(truth) if truth else ({}, set(), [])
    team = lambda u: sc.store_name(u) or u  # noqa: E731
    entries = collections.defaultdict(list)
    seen = set()
    for i, r in enumerate(top.itertuples()):
        p = float(st['entered'][i])
        k = (r.aid, r.event)
        if p < ENTRY_MIN and k not in place:
            continue
        row = dict(n='' if r.relay else names.get(r.aid, ''), t=team(r.team), p=round(p, 3))
        if truth:
            row['e'] = int(k in place)
        entries[r.event].append(row)
        seen.add(k)
    for k, ev, r in truth_rows:          # entrants the prediction gave no chance
        if r['unit'] and k not in seen and (k or not tp.is_relay_event(ev)):
            entries[ev].append(dict(n='' if tp.is_relay_event(ev) else r.get('name', ''), t=team(r['unit']), p=0.0, e=1))
            if k:
                seen.add(k)
    for rows in entries.values():
        rows.sort(key=lambda x: -x['p'])
    leg_out = collections.defaultdict(list)
    seen_legs = set()
    for i, a, p in st['legs']:
        ev = top.event.values[i]
        if a.startswith('?') or (p < ENTRY_MIN and (a, ev) not in leg_truth):
            continue
        row = dict(n=names.get(a, ''), t=team(top.team.values[i]), p=round(p, 3))
        if truth:
            row['e'] = int((a, ev) in leg_truth)
        leg_out[ev].append(row)
        seen_legs.add((a, ev))
    if truth:                            # legs the prediction gave no chance
        for ev, rs in truth['events'].items():
            for r in rs:
                for a in (r.get('legs') or ()) if tp.is_relay_event(ev) else ():
                    if not a.startswith('?') and (a, ev) not in seen_legs and r['unit']:
                        leg_out[ev].append(dict(n=names.get(a, ''), t=team(r['unit']), p=0.0, e=1))
                        seen_legs.add((a, ev))
    for rows in leg_out.values():
        rows.sort(key=lambda x: -x['p'])
    basis = 'predicted'
    out_pts, out_teams, out_st, out_pred = pts, teams, st, top
    if truth:
        kr, _ = tp.apply_entries(pred.reset_index(drop=True), tp.entries_from_truth(truth))
        kr = kr[kr.pent > 0].reset_index(drop=True)
        out_pts, out_teams, out_st = tp.simulate(kr, table, *z, sims=SIMS, seed=1, max_events=None)
        out_pred, basis = kr, 'entered'
    keep = ('id', 'kind', 'conference', 'division', 'gender', 'date')
    return dict({k: champ[k] for k in keep if k in champ}, table=table, cutoff=cutoff, basis=basis,
                teams=_teams(out_pts, out_teams), events=_event_rows(out_pred, out_st, names, place),
                entries=dict(entries), legs=dict(leg_out))


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
    """One season from the backtest's saved fit (models fitted without it)."""
    from backend import track_postseason_cv as cv
    tr, champs, names = (_SHARED[k] for k in ('tr', 'champs', 'names'))
    fit = cv.load_fit(year)
    pred = fit['pred']
    pred = pred[pred.label == 'eve']      # top 50 per event, plus entrants outside them (known entries)
    lp = fit['lp']
    lp = lp[lp.label == 'eve'] if lp is not None else None
    out = collections.defaultdict(list)
    for c in champs:
        if c['year'] != year:
            continue
        rows = pred[pred.champ == c['id']].reset_index(drop=True)
        if not len(rows):
            continue
        lg = lp[lp.champ == c['id']] if lp is not None else None
        z = fit['z']['state' if '-state-' in c['id'] else 'conf']
        out[c['season']].append(champ_out(c, rows, z, tr[c['id']]['table'], names, rows.cutoff.iloc[0], lg,
                                          truth=tr[c['id']]))
    for season, cs in out.items():
        write(year, season, cs, None)
    return year, {k: len(v) for k, v in out.items()}


def past(years=None, procs=4):
    """Every season from the backtest's saved fits (fitted first where
    missing, 2 workers), then simulated (light)."""
    from backend import track_postseason_cv as cv
    with open(os.path.join(tp.CACHE_DIR, 'truths.pkl'), 'rb') as f:
        tr = pickle.load(f)
    champs = tp.load_champs()
    years = years or sorted({c['year'] for c in champs if c['year'] >= 2006})
    cv.ensure_fits(years)
    store = tp.load_store(quiet=True)
    _SHARED.update(tr=tr, champs=champs, names={str(k): v for k, v in store.name.items()})
    os.environ['OMP_NUM_THREADS'] = '2'
    with mp.get_context('fork').Pool(procs) as pool:
        for year, by in pool.imap_unordered(_past_year, years):
            print(f'{year}: {by} championships', file=sys.stderr, flush=True)


DATASET_DAYS = 28   # the training dataset (past seasons) is rebuilt when older than this


def _dataset_ok():
    """The dataset is recent and built from the current store (a new athlete
    catalog or relay-leg resolution rebuilds the store, then this)."""
    path = os.path.join(tp.CACHE_DIR, 'athletes.pkl')
    tp.load_store(quiet=True)
    if not os.path.exists(os.path.join(tp.CACHE_DIR, 'legs.pkl')):
        return False            # rebuilds store.pkl when the data or catalog changed
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
        pred = o['pred'].drop(columns=['win', 'top3', 'exp_pts', 'entered'], errors='ignore')
        by[c['season']].append(champ_out(c, pred, model.z_for(c['id']), o['table'], names, o['cutoff'], o.get('legs')))
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
