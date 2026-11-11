"""
track_postseason_cv.py - does the track postseason predictor work?

Leave-one-season-out: for every academic year with state meets on file, the
models are fitted on all other years and that year's championships are
predicted from each cutoff (before indoor starts, then through the season to
the day before the meet). Every prediction uses only results dated before its
cutoff.

Measured per championship (one class, one gender), as James judges them:
  * podium teams: how many of the actual top 3 teams were predicted top 3,
    whether the predicted top 3 came in that exact order, and the winner;
  * the probability the model gave the actual winner and the actual top 3;
  * events: predicted event winner right, actual top 3 inside the predicted
    top 3;
  * marks: for each event's actual scorers, predicted vs actual mark.

Baselines on the same meets:
  * last year: the same class meet a year earlier, in its official order;
  * season bests: every candidate's best estimate as it stands (this
    season's best, else the newest earlier mark), entered in the events they
    have run this season (before the season: the events they ran last
    year), scored once with no dice.

    python3 -m backend.track_postseason_cv            # all years, report
    python3 -m backend.track_postseason_cv --years 2024 2025
"""

import argparse
import collections
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import track_postseason as tp  # noqa: E402

OUT = os.environ.get('TRACK_CV_OUT') or os.path.join(tp.CACHE_DIR, 'cv_results.pkl')
LABEL_ORDER = {'Indoor': ['Nov 30', 'Dec 20', 'Jan 10', 'Jan 25', 'Feb 5', 'eve'],
               'Outdoor': ['Nov 30', 'Jan 15', 'Mar 1', 'Apr 25', 'May 10', 'May 24', 'eve']}


def load():
    A0 = pd.read_pickle(os.path.join(tp.CACHE_DIR, 'athletes.pkl'))
    tp.set_lines(A0)
    A = tp.add_columns(A0)
    R = tp.add_columns(pd.read_pickle(os.path.join(tp.CACHE_DIR, 'relays.pkl')))
    with open(os.path.join(tp.CACHE_DIR, 'truths.pkl'), 'rb') as f:
        tr = pickle.load(f)
    return _slim(A), _slim(R), tr


def _slim(df):
    """float32 features: the backtest holds ~1.5M rows in every worker."""
    for col in df.columns:
        if df[col].dtype == np.float64 and col not in ('anchor', 'p_true', 'y'):
            df[col] = df[col].astype(np.float32)
    return df


def actual_order(truth):
    if len(truth['official']) >= 3:
        return [u for _, u in truth['official']]
    return [u for u, _ in sorted(truth['teams'].items(), key=lambda kv: -kv[1])]


def event_truth(truth):
    """{event: [aid as stored in the dataset, in place order]} (top 8)."""
    out = {}
    for ev, rows in truth['events'].items():
        out[ev] = [str(r['aid']) if r['aid'] else None for r in rows[:8]]
    return out


def team_metrics(pred_order, actual, probs=None):
    p3, a3 = pred_order[:3], actual[:3]
    m = dict(incl=len(set(p3) & set(a3)) / 3.0, order=float(p3 == a3), win=float(pred_order[:1] == actual[:1]))
    if probs is not None:
        m['p_winner'] = probs['win'].get(actual[0], 0.0)
        m['p_top3'] = float(np.mean([probs['top3'].get(t, 0.0) for t in a3]))
        teams = set(probs['top3']) | set(a3)
        m['brier3'] = float(np.mean([(probs['top3'].get(t, 0.0) - (t in a3)) ** 2 for t in teams]))
    return m


def event_metrics(rows, stats_win, stats_top3, ev_truth):
    """rows: DataFrame of one championship-day's predictions (index aligned to stats)."""
    wins, incl = [], []
    for ev, idx in rows.groupby('event').indices.items():
        act = ev_truth.get(ev)
        if not act or act[0] is None:
            continue
        aids = rows.aid.values[idx]
        w = aids[np.argmax(stats_win[idx])]
        wins.append(float(w == act[0]))
        top = set(aids[np.argsort(-stats_top3[idx])[:3]])
        incl.append(len(top & set(a for a in act[:3] if a)) / 3.0)
    return dict(ev_win=np.mean(wins) if wins else np.nan, ev_incl=np.mean(incl) if incl else np.nan)


def mark_errors(rows, col, truth, champ):
    """[(event, place, err, grade)] for the actual top 8 with a prediction."""
    out = []
    key = {(a, e): i for i, (a, e) in enumerate(zip(rows.aid.values, rows.event.values))}
    for ev, rs in truth['events'].items():
        if tp.is_relay_event(ev):
            continue
        for place, r in enumerate(rs[:8]):
            i = key.get((str(r['aid']), ev)) if r['aid'] else None
            err = rows[col].values[i] - r['p'] if i is not None else np.nan
            out.append((ev, place + 1, err, r.get('grade')))
    return out


def entry_metrics(rows, truth, champ, label, year, method):
    """How well one championship-day's entry probabilities (`pent`) match who
    competed, for individual events and relays separately:
      recall      - mean probability given to the actual entrants (an entrant
                    with no candidate row counts 0);
      scorers     - the same over each event's actual top 8;
      precision   - share of the expected entries that were real;
      ratio       - expected entries / actual entries;
      brier       - over the candidate rows."""
    out = []
    p = dict(zip(zip(rows.aid.astype(str).values, rows.event.values), rows.pent.values))
    for relay in (False, True):
        act, top = set(), set()
        for ev, rs in truth['events'].items():
            if tp.is_relay_event(ev) != relay:
                continue
            for i, r in enumerate(rs):
                k = tp.relay_key(r['unit']) if relay else (str(r['aid']) if r['aid'] else None)
                if not k or (relay and not r['unit']):
                    continue
                act.add((k, ev))
                if i < 8:
                    top.add((k, ev))
        sel = rows.relay.values == relay
        keys = list(zip(rows.aid.astype(str).values[sel], rows.event.values[sel]))
        pe = rows.pent.values[sel].astype(float)
        y = np.array([k in act for k in keys], float)
        if not len(act):
            continue
        out.append(dict(champ=champ, label=label, year=year, season=champ.split('-')[1], method=method,
                        relay=relay, n_act=len(act),
                        recall=sum(p.get(k, 0.0) for k in act) / len(act),
                        scorers=sum(p.get(k, 0.0) for k in top) / max(1, len(top)),
                        precision=float((pe * y).sum() / pe.sum()) if pe.sum() else np.nan,
                        ratio=float(pe.sum() / len(act)),
                        brier=float(np.mean((pe - y) ** 2)) if len(pe) else np.nan))
    return out


def baseline_rows(df):
    """Season-bests baseline: mark = anchor, entered if run this season (or,
    with nothing this season yet, run in the same kind of season last year)."""
    d = df.copy()
    has_cur = d['cur_all'].fillna(0) > 0 if 'cur_all' in d else pd.Series(False, index=d.index)
    cur_same = (d['cur_d'].notna() & (d['cur_sig'] == 0))
    prev_same = (d['p1_sig'] == 0) | (d['p2_sig'] == 0)
    d['pent'] = np.where(has_cur, cur_same, prev_same).astype(float)
    d['mean'] = d['anchor']
    d['scale'] = 1e-9
    return d


def baseline_relays(df):
    d = df.copy()
    cur = d['cur_d'].notna()
    prev = d['p1_d'].notna() | d['p2_d'].notna()
    d['pent'] = np.where(d['days_left'] < 40, cur | prev, prev | cur).astype(float)
    d['mean'] = d['anchor']
    d['scale'] = 1e-9
    return d


METHODS = ('model', 'season bests', 'model, known entries', 'season bests, known entries', 'last year')
_SHARED = {}   # set before the workers fork, so they share it instead of each getting a copy


def _score(rows, method, champ, label, year, truth, actual, z, sims, max_events, results, team_rows):
    """Simulate one championship-day's rows and record the team and event metrics."""
    pts, teams, st = tp.simulate(rows, truth['table'], *z, sims=sims, seed=hash(champ) % 1000,
                                 max_events=max_events)
    summ = tp.team_summary(pts, teams)
    m = dict(champ=champ, label=label, year=year, season=champ.split('-')[1], method=method)
    if sims > 1:
        probs = dict(win={s['team']: s['win'] for s in summ}, top3={s['team']: s['top3'] for s in summ})
        m.update(team_metrics([s['team'] for s in summ], actual, probs))
    else:
        m.update(team_metrics([teams[j] for j in np.argsort(-pts[0])], actual))
    m.update(event_metrics(rows, st['win'], st['top3'], event_truth(truth)))
    results.append(m)
    if team_rows is not None:
        act_pts = dict(truth['teams'])
        for sc_, u in truth['official']:
            act_pts[u] = sc_
        act_rank = {u: i + 1 for i, u in enumerate(actual)}
        for s in summ:
            team_rows.append(dict(champ=champ, label=label, year=year, method=method, team=s['team'],
                                  pred=s['mean'], win=s['win'], top3=s['top3'],
                                  actual=act_pts.get(s['team'], 0.0), rank=act_rank.get(s['team'], 99)))


def evaluate_year(args):
    """One held-out season, both ways: entries unknown (the entry model
    guesses who runs what) and entries known (exactly who competed runs,
    see tp.apply_entries); each against the season-bests baseline."""
    year, sims, modes = args
    A, R, tr, last_year = (_SHARED[k] for k in ('A', 'R', 'tr', 'last_year'))
    model = tp.Model().fit(A[A.year != year], R[R.year != year])
    # entrants outside the top 50 are only needed when the entries are known
    At = A[(A.year == year) & (A.in_top | (A.entered == 1))]
    Rt = R[R.year == year]
    pred = model.predict(At, Rt)
    pred = pred.merge(pd.concat([At[['champ', 'cutoff', 'aid', 'event', 'grade', 'in_top']],
                                 Rt[['champ', 'cutoff', 'aid', 'event', 'in_top']]]),
                      on=['champ', 'cutoff', 'aid', 'event'], how='left')
    base = pd.concat([baseline_rows(At), baseline_relays(Rt)], ignore_index=True)
    base['relay'] = base['aid'].str.startswith("('relay'")
    results, marks, team_rows, ents = [], [], [], []
    for (champ, label), rows in pred.groupby(['champ', 'label']):
        truth = tr[champ]
        actual = actual_order(truth)
        rows = rows.reset_index(drop=True)
        z = model.z_for(champ)
        b = base[(base.champ == champ) & (base.label == label)].reset_index(drop=True)
        if 'unknown' in modes:
            top = rows[rows.in_top.astype(bool)].reset_index(drop=True)
            ents.extend(entry_metrics(top, truth, champ, label, year, 'model'))
            _score(top, 'model', champ, label, year, truth, actual, z, sims, tp.max_events_for(champ), results, team_rows)
            bt = b[b.in_top.astype(bool)].reset_index(drop=True)
            if len(bt):
                ents.extend(entry_metrics(bt, truth, champ, label, year, 'season bests'))
                _score(bt, 'season bests', champ, label, year, truth, actual, (np.zeros(1), np.zeros(1)),
                       1, tp.max_events_for(champ), results, None)
        if 'known' in modes:
            ent = tp.entries_from_truth(truth)
            kr, _ = tp.apply_entries(rows, ent)
            _score(kr, 'model, known entries', champ, label, year, truth, actual, z, sims, None,
                   results, team_rows)
            if len(b):
                kb, _ = tp.apply_entries(b, ent)
                kb['scale'] = kb['scale'].fillna(1e-9)
                _score(kb, 'season bests, known entries', champ, label, year, truth, actual,
                       (np.zeros(1), np.zeros(1)), 1, None, results, None)
        for ev, place, err, gr in mark_errors(rows, 'mean', truth, champ):
            marks.append(dict(champ=champ, label=label, year=year, method='model', event=ev,
                              place=place, err=err, grade=gr))
        for ev, place, err, gr in mark_errors(rows, 'anchor', truth, champ):
            marks.append(dict(champ=champ, label=label, year=year, method='season bests', event=ev,
                              place=place, err=err, grade=gr))
        prev = last_year.get(champ)
        if prev:
            ml = dict(champ=champ, label=label, year=year, season=champ.split('-')[1], method='last year')
            ml.update(team_metrics(prev, actual))
            results.append(ml)
    return results, marks, team_rows, ents


def last_year_orders(tr, champs):
    by = {(c['year'], c['season'], c['division'], c['gender']): c['id'] for c in champs}
    out = {}
    for c in champs:
        p = by.get((c['year'] - 1, c['season'], c['division'], c['gender']))
        if p:
            out[c['id']] = actual_order(tr[p])
    return out


def run(years=None, sims=1000, procs=4, modes=('unknown', 'known')):
    import multiprocessing as mp
    A, R, tr = load()
    champs = tp.load_champs()
    years = years or sorted(y for y in A.year.unique() if y >= 2008)
    ly = last_year_orders(tr, champs)
    _SHARED.update(A=A, R=R, tr=tr, last_year=ly)
    jobs = [(y, sims, modes) for y in years]
    res, marks, teams, ents = [], [], [], []
    os.environ['OMP_NUM_THREADS'] = '2'
    with mp.get_context('fork').Pool(procs) as pool:
        for r, m, t, e in pool.imap_unordered(evaluate_year, jobs):
            ents.extend(e)
            res.extend(r)
            marks.extend(m)
            teams.extend(t)
            print(f'  year {r[0]["year"] if r else "?"} done', flush=True)
    out = dict(results=pd.DataFrame(res), marks=pd.DataFrame(marks), teams=pd.DataFrame(teams),
               entries=pd.DataFrame(ents))
    with open(OUT, 'wb') as f:
        pickle.dump(out, f)
    return out


def _se_by_year(df, col):
    by = df.groupby('year')[col].mean()
    return by.mean(), by.std(ddof=1) / np.sqrt(max(1, len(by) - 1)) if len(by) > 1 else np.nan


def report(out=None):
    if out is None:
        with open(OUT, 'rb') as f:
            out = pickle.load(f)
    res, marks = out['results'], out['marks']
    lines = []
    res = res.assign(kind=np.where(res.champ.str.contains('-state-'), 'state', 'conference'))
    for season, kind in (('Indoor', 'state'), ('Outdoor', 'state'), ('Indoor', 'conference'),
                         ('Outdoor', 'conference')):
        r = res[(res.season == season) & (res.kind == kind)]
        if not len(r):
            continue
        n_meets = r[r.method == 'model'].champ.nunique()
        lines.append(f'\n{season} {kind}: {n_meets} meets (division x gender), '
                     f'{r.year.nunique()} seasons')
        lines.append(f'{"cutoff":8} {"method":27} {"podium":>7} {"order":>6} {"winner":>7} '
                     f'{"P(win)":>7} {"P(top3)":>8} {"ev win":>7} {"ev top3":>8}')
        for lab in LABEL_ORDER[season]:
            for meth in METHODS:
                x = r[(r.label == lab) & (r.method == meth)]
                if not len(x):
                    continue
                def f(c, pct=True):
                    if c not in x or x[c].isna().all():
                        return '      -'
                    v = x[c].mean()
                    return f'{100 * v:6.1f}%' if pct else f'{v:7.3f}'
                lines.append(f'{lab:8} {meth:27} {f("incl")} {f("order")} {f("win")} '
                             f'{f("p_winner")} {f("p_top3")} {f("ev_win")} {f("ev_incl")}')
        # paired differences in podium inclusion, SE over seasons
        for ma, mb in (('model', 'season bests'), ('model, known entries', 'season bests, known entries'),
                       ('model, known entries', 'model')):
            if not ((r.method == ma).any() and (r.method == mb).any()):
                continue
            lines.append(f'  {ma} - {mb}, podium teams (paired, SE over seasons):')
            for lab in LABEL_ORDER[season]:
                a = r[(r.label == lab) & (r.method == ma)].set_index('champ')
                b = r[(r.label == lab) & (r.method == mb)].set_index('champ')
                j = a[['incl', 'year']].join(b[['incl']], rsuffix='_b', how='inner')
                if not len(j):
                    continue
                j['d'] = j['incl'] - j['incl_b']
                mu, se = _se_by_year(j, 'd')
                better = (j.groupby('year')['d'].mean() > 0).sum()
                worse = (j.groupby('year')['d'].mean() < 0).sum()
                lines.append(f'    {lab:8} {100 * mu:+5.1f} +/- {100 * se:4.1f} pts  '
                             f'(seasons better {better}, worse {worse})')
    m = marks.copy()
    m['abserr'] = np.abs(m['err'])
    lines.append('\nMarks of the actual top 8 (median |error|, % of the mark; coverage = share predicted):')
    for season in ('Indoor', 'Outdoor'):
        mm = m[m.champ.str.contains(f'-{season}-')]
        for lab in LABEL_ORDER[season]:
            parts = []
            for meth in ('model', 'season bests'):
                x = mm[(mm.label == lab) & (mm.method == meth)]
                if not len(x):
                    continue
                cov = x.err.notna().mean()
                parts.append(f'{meth}: {100 * x.abserr.median():4.2f}% (bias {100 * x.err.median():+.2f}%, '
                             f'coverage {100 * cov:.0f}%)')
            lines.append(f'  {season:7} {lab:7} ' + ' | '.join(parts))
    e = out.get('entries')
    if e is not None and len(e):
        e = e[e.champ.str.contains('-state-')]
        lines.append('\nState meet entries (recall = mean P(enter) of actual entrants; scorers = of the top 8;'
                     ' ratio = expected / actual entries):')
        for season in ('Indoor', 'Outdoor'):
            for relay in (False, True):
                lines.append(f'  {season} {"relays" if relay else "individuals"}')
                for lab in LABEL_ORDER[season]:
                    parts = []
                    for meth in ('model', 'season bests'):
                        x = e[(e.season == season) & (e.relay == relay) & (e.label == lab) & (e.method == meth)]
                        if len(x):
                            parts.append(f'{meth}: recall {100 * x.recall.mean():4.1f}% scorers '
                                         f'{100 * x.scorers.mean():4.1f}% precision {100 * x.precision.mean():4.1f}% '
                                         f'ratio {x.ratio.mean():4.2f} brier {x.brier.mean():.4f}')
                    lines.append(f'    {lab:7} ' + ' | '.join(parts))
    text = '\n'.join(lines)
    print(text)
    return text


def compare(path_a, path_b, method='model', kind='state'):
    """Paired differences (a - b) by cutoff, SE over seasons: podium teams,
    order, winner, P(top 3), and the entry metrics when both runs have them."""
    outs = []
    for p in (path_a, path_b):
        with open(p, 'rb') as f:
            outs.append(pickle.load(f))
    lines = [f'{path_a} - {path_b}, method {method!r}, {kind} meets']
    for season in ('Indoor', 'Outdoor'):
        lines.append(f'{season}:')
        for lab in LABEL_ORDER[season]:
            ra, rb = [o['results'] for o in outs]
            sel = lambda r: r[(r.method == method) & (r.label == lab) & (r.season == season) &
                              (r.champ.str.contains('-state-') == (kind == 'state'))].set_index('champ')
            j = sel(ra).join(sel(rb), rsuffix='_b', how='inner')
            if not len(j):
                continue
            parts = []
            for c in ('incl', 'order', 'win', 'p_top3'):
                if c not in j or j[c].isna().all():
                    continue
                j['d'] = j[c] - j[c + '_b']
                mu, se = _se_by_year(j, 'd')
                parts.append(f'{c} {100 * mu:+5.1f}+/-{100 * se:3.1f}')
            ea, eb = outs[0].get('entries'), outs[1].get('entries')
            if ea is not None and eb is not None and len(ea) and len(eb):
                for relay in (False, True):
                    sel2 = lambda e: e[(e.method == method) & (e.label == lab) & (e.season == season) &
                                       (e.relay == relay) & e.champ.str.contains('-state-')].set_index('champ')
                    k = sel2(ea).join(sel2(eb), rsuffix='_b', how='inner')
                    for c in ('scorers', 'precision'):
                        if len(k):
                            k['d'] = k[c] - k[c + '_b']
                            mu, se = _se_by_year(k, 'd')
                            parts.append(f'{"rel" if relay else "ind"} {c} {100 * mu:+4.1f}+/-{100 * se:3.1f}')
            lines.append(f'  {lab:7} n={len(j):3} ' + '  '.join(parts))
    text = '\n'.join(lines)
    print(text)
    return text


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--years', type=int, nargs='*')
    ap.add_argument('--sims', type=int, default=1000)
    ap.add_argument('--procs', type=int, default=4)
    ap.add_argument('--report', action='store_true', help='only print the last results')
    ap.add_argument('--entries', choices=('unknown', 'known', 'both'), default='both',
                    help='simulate with entries unknown (predicted), known (who competed), or both')
    ap.add_argument('--compare', nargs=2, metavar=('A', 'B'), help='paired differences of two result files')
    ap.add_argument('--method', default='model')
    a = ap.parse_args(argv)
    if a.compare:
        compare(*a.compare, method=a.method)
        return
    if a.report:
        report()
        return
    modes = ('unknown', 'known') if a.entries == 'both' else (a.entries,)
    out = run(a.years, a.sims, a.procs, modes)
    report(out)


if __name__ == '__main__':
    main()
