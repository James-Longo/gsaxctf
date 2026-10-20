"""
xc_postseason_cv.py - leave-one-season-out cross-validation of the XC
postseason predictions (PROTOTYPE).

Each fold holds out one season and predicts every postseason meet the way the
prediction page does: from results before that meet's own day and nothing after
(James 2026-10-18: a race's prediction never sees its own or later results).
Conference meets (by official division) and regionals are scored from the
cascade simulated at each meet's cutoff; state meets from results before state
day with the actual state field (known once regionals are run).

Everything a method learns is refit without the held-out season: course
factors and year-over-year carry-forward (Calibration(exclude_year=)), and
the empirical error distribution the simulator draws from (pseudo-backtest
rows from other seasons only).

Past seasons have no MPA lists on file, so each season's groups are rebuilt
from its own results files: regional fields from who ran each regional,
class from the matching state meet, region from the venue (Belfast = North).

Scores, per podium (one per meet, division and gender):
    inclusion  share of the real top three teams in the predicted top three
    order      share of 1st/2nd/3rd predicted in exactly the right slot
    brier3     Brier score of P(top three) over the meet's teams
    brier1     Brier score of P(win)
Methods are ranked on (inclusion + order) / 2; Brier breaks near-ties.

Individual times (James 2026-10-20: predictions are judged on podium teams, their
order, and individual times): every race of 25+ runners on a 5K course with a
known factor in the held-out season, each runner predicted from results before
that day (season_ratings + the course factor), scored by the median absolute
error and the mean error in seconds (`--time`, `time_summary`).

    python3 -m backend.xc_postseason_cv [--sims N] [--procs N] [--round 1|2]
"""

import os
# One thread per process: the pool already uses every core, and letting each
# worker's gradient boosting start its own thread pool oversubscribed the
# machine 12x (load average 73 on 12 cores).
os.environ.setdefault('OMP_NUM_THREADS', '1')
import json
import math
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import xc_postseason as xp

FOLDS = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
CLASS_RE = re.compile(r'class[-_ ]?([abc])(?![a-z]{2,}ool)', re.I)


# ---------------------------------------------------------------------------
# A past season's postseason, rebuilt from its results files
# ---------------------------------------------------------------------------

def history(obs, year):
    """Groups (same shape as load_groups) plus the actual results to score.

    Returns dict(groups, cutoff, state_day, actual) where actual maps
    (meet id, division or '') -> list of team units in finishing order, and
    races maps meet id -> {gender: rows}.
    """
    races = {k: v for k, v in xp.championship_races(obs).items() if k[0] == year}
    by_kind = defaultdict(list)
    for (y, g, meet), rows in races.items():
        by_kind[xp.kind_of(meet)].append((g, meet, rows))
    days = sorted({rows[0].day for _, _, rows in by_kind['Regional']}
                  | {rows[0].day for _, _, rows in by_kind['State']}
                  | {rows[0].day for _, _, rows in by_kind['Class']})
    if not days:
        return None
    reg_day = min(rows[0].day for _, _, rows in by_kind['Regional']) if by_kind['Regional'] else None
    state_day = max(days)
    if reg_day is None:
        cand = [d for d in days if d < state_day]
        reg_day = max(cand) if cand else None

    states, regionals = [], []
    for kind in ('Regional', 'State', 'Class'):
        for g, meet, rows in by_kind[kind]:
            d = rows[0].day
            if d == state_day:
                states.append((g, meet, rows))
            elif d == reg_day:
                regionals.append((g, meet, rows))

    # class of each state race from its file name; class of a regional by
    # the state race (same gender) its teams overlap most
    state_class = {}
    for g, meet, rows in states:
        m = CLASS_RE.search(meet)
        if m:
            state_class[(g, meet)] = m.group(1).upper()
    schools = {}
    meets = []
    actual = {}
    for g, meet, rows in regionals:
        teams = {o.team for o in rows}
        best, cls = 0, None
        for (sg, smeet), c in state_class.items():
            if sg != g:
                continue
            st_teams = {o.team for o in races[(year, sg, smeet)]}
            ov = len(teams & st_teams)
            if ov > best:
                best, cls = ov, c
        if cls is None:
            m = CLASS_RE.search(meet) or re.search(r'(?:^|[-_ ])([abc])[-_ ]?(?:boys|girls)', meet, re.I)
            cls = m.group(1).upper() if m else None
        if cls is None:
            continue
        region = 'North' if rows[0].course[0] == 'Belfast' else 'South'
        mid = f'reg_{cls}_{region}_{g}'
        for t in teams:
            schools.setdefault(t, {'class': cls, 'region': region, 'name': t})
        meets.append({'id': mid, 'gender': g, 'class': cls, 'region': region,
                      'schools': sorted(teams), 'day': rows[0].day, 'file': meet})
        actual[(mid, '')] = _order(rows)
    for (g, smeet), cls in state_class.items():
        rows = races[(year, g, smeet)]
        mid = f'state_{cls}_{g}'
        froms = [m['id'] for m in meets if m.get('class') == cls and m['gender'] == g
                 and m['id'].startswith('reg_')]
        if not froms:
            continue
        meets.append({'id': mid, 'gender': g, 'class': cls, 'from': froms,
                      'day': rows[0].day, 'file': smeet})
        actual[(mid, '')] = _order(rows)

    conf_days = []
    for kind in ('PVC', 'KVAC'):
        for i_file, (g, meet, rows) in enumerate(sorted(by_kind[kind], key=lambda x: x[1])):
            groups_ = xp.scoring_groups(year, g, meet) or [('', {o.team for o in rows})]
            # a season can post one file per division (2017 PVC class B and
            # class C files): one meet id per file
            mid = f'{kind.lower()}_{g}_{i_file}'
            divs = {}
            for i, (label, members) in enumerate(groups_):
                key = label or f'all'
                if key in divs:
                    key = f'{key} {i}'
                members = {t for t in members if t in {o.team for o in rows}}
                if len(members) < 3:
                    continue
                divs[key] = sorted(members)
                for t in members:
                    schools.setdefault(t, {'class': None, 'region': None, 'name': t})
                div_rows = [o for o in rows if o.team in members]
                actual[(mid, key if len(groups_) > 1 else '')] = _order(div_rows)
            if not divs:
                continue
            m = {'id': mid, 'gender': g, 'schools': sorted({t for v in divs.values() for t in v}),
                 'day': rows[0].day, 'file': meet}
            if len(divs) > 1:
                m['divisions'] = divs
            meets.append(m)
            conf_days.append(rows[0].day)

    oct15 = xp.season_day(year, f'{year}-10-15')
    cutoff = min([oct15] + conf_days + ([reg_day] if reg_day else []))
    return dict(groups={'schools': schools, 'meets': meets}, cutoff=cutoff,
                state_day=state_day, actual=actual, races=races)


def _order(rows):
    ranked, _ = xp.score_race([o.aid for o in sorted(rows, key=lambda o: o.lt)],
                              {o.aid: o.team for o in rows})
    return [t for t, _, _ in ranked]


# ---------------------------------------------------------------------------
# Scoring a predicted meet against what happened
# ---------------------------------------------------------------------------

def score_podium(pred_teams, actual_order):
    """pred_teams: team -> dict(exp_place_all, place_dist). None if the
    meet had fewer than three scoring teams."""
    if len(actual_order) < 3 or len(pred_teams) < 3:
        return None
    ranked = sorted(pred_teams, key=lambda t: pred_teams[t]['exp_place_all'])
    p3, a3 = ranked[:3], actual_order[:3]
    teams = set(pred_teams) | set(actual_order)
    b3 = b1 = 0.0
    for t in teams:
        d = pred_teams.get(t, {}).get('place_dist', {})
        pt3 = sum(v for k, v in d.items() if k <= 3)
        pt1 = d.get(1, 0.0)
        b3 += (pt3 - (t in a3)) ** 2
        b1 += (pt1 - (t == a3[0])) ** 2
    return dict(inclusion=len(set(p3) & set(a3)) / 3,
                order=sum(1 for i in range(3) if p3[i] == a3[i]) / 3,
                brier3=b3 / len(teams), brier1=b1 / len(teams),
                pt3=[(sum(v for k, v in pred_teams.get(t, {}).get('place_dist', {}).items() if k <= 3),
                      t in a3) for t in teams],
                pt1=[(pred_teams.get(t, {}).get('place_dist', {}).get(1, 0.0), t == a3[0])
                     for t in teams])


class ScaledNoise:
    """A NoiseModel whose draws are stretched or shrunk around their median:
    scale > 1 makes the prediction less sure of itself."""

    def __init__(self, base, scale):
        self.base, self.scale = base, scale

    def draw(self, n, prior, rng, sd=None):
        e = self.base.draw(n, prior, rng, sd)
        if self.scale == 1.0:
            return e
        m = self.base.shift(n, prior)
        return m + (e - m) * self.scale

    def shift(self, n, prior):
        return self.base.shift(n, prior)

    def draw_pooled(self, rng):
        e = self.base.draw_pooled(rng)
        return e if self.scale == 1.0 else e * self.scale


# ---------------------------------------------------------------------------
# Methods and folds
# ---------------------------------------------------------------------------

def method(name, params=None, diet='all', form_carry=xp.FORM_CARRY, noise_scale=1.0,
           learned=False):
    return dict(name=name, params=params or {}, diet=diet,
                form_carry=form_carry, noise_scale=noise_scale, learned=learned)


ROUND1 = [
    method('model (current)'),
    method('recency 15 days', {'tau': 15.0}),
    method('recency 60 days', {'tau': 60.0}),
    method('no recency', {'tau': 1e6}),
    method('no 2025-style prior', {'use_prior': False}),
    method('course-adjusted average', {'method': 'course_mean'}),
    method('raw season-best 5K', {'method': 'raw_best'}),
    method('raw last 5K', {'method': 'raw_last'}),
    method('Festival race only', diet='festival'),
    method('form carry 0.40', form_carry=0.40),
    method('form carry 0.85', form_carry=0.85),
    method('spread x0.80', noise_scale=0.80),
    method('spread x1.25', noise_scale=1.25),
]

ROUND1_PLUS = ROUND1 + [
    method('ensemble: model + course-adjusted', {'method': 'ensemble', 'components': ['model', 'course_mean']}),
    method('ensemble: model + course + last 5K', {'method': 'ensemble', 'components': ['model', 'course_mean', 'raw_last']}),
    method('boosted correction (learned)', learned=True),
]

ROUND2 = [method('model (current)')]
for _fc in (0.85, 0.95):
    for _sp in (1.0, 1.1, 1.25):
        ROUND2.append(method(f'model, carry {_fc}, spread x{_sp}', form_carry=_fc, noise_scale=_sp))
        ROUND2.append(method(f'boosted, carry {_fc}, spread x{_sp}', form_carry=_fc,
                             noise_scale=_sp, learned=True))

FINAL = [
    method('model (current)'),
    method('model, carry 0.85', form_carry=0.85),
    method('model, carry 0.95', form_carry=0.95),
    method('model, carry 0.95, spread x1.25', form_carry=0.95, noise_scale=1.25),
    method('boosted, carry 0.95', form_carry=0.95, learned=True),
    method('boosted, carry 0.95, spread x1.25', form_carry=0.95, noise_scale=1.25, learned=True),
]

_G = {}


SIM_ONLY = ('program_icc',)   # simulation settings: do not change ratings or error models


def _pkey(params):
    return json.dumps({k: v for k, v in params.items() if k not in SIM_ONLY}, sort_keys=True)


def _pseudo_task(args):
    pkey, year = args
    params = json.loads(pkey)
    return pkey, year, xp.pseudo_backtest(_G['obs'], years=[year], params=params,
                                          calibs=_G['calibs'])


def _festival_obs(obs, year):
    """The held-out season reduced to its Festival of Champions race."""
    days = defaultdict(int)
    for o in obs:
        if o.year == year and o.course == ('Belfast', 5000) and o.day is not None:
            days[o.day] += 1
    if not days:
        return None
    fday = max(days, key=days.get)
    return [o for o in obs if o.year != year or (o.course == ('Belfast', 5000) and o.day == fday)]


def _feature_task(year):
    return year, xp.feature_backtest(_G['obs'], [year], _G['calibs'])


def _learned(year):
    """Boosted correction for a held-out season, plus its honest error rows:
    out-of-fold residuals over the training seasons, so the simulator's
    spread reflects what the corrected ratings really miss by."""
    feat = _G['features']
    train = [y for y in feat if y != year]
    model = xp.LearnedCorrection([r for y in train for r in feat[y]])
    resid = []
    for t in train:
        inner = xp.LearnedCorrection([r for y in train if y != t for r in feat[y]])
        rows = feat[t]
        import numpy as np
        X = np.array([[r['f'][k] for k in xp.FEATURES] for r in rows], dtype=float)
        pred = inner.m.predict(X)
        for r, dp in zip(rows, pred):
            resid.append(dict(r, err=r['err'] - float(dp)))
    return model, resid


def _rate(m, obs, year, g, cutoff, calib, rate_obs=None, learned=None):
    base, d = xp.season_ratings(rate_obs if rate_obs is not None else obs,
                                year, g, cutoff, calib, m['params'])
    if learned is None:
        return base
    feats = xp.athlete_features(rate_obs if rate_obs is not None else obs,
                                year, g, cutoff, calib, (base, d))
    return learned.correct(base, feats)


def _learned_task(year):
    return year, _learned(year)


def _fold_task(args):
    mi, year, sims = args
    m = _G['methods'][mi]
    obs, calibs, hist = _G['obs'], _G['calibs'], _G['hist'][year]
    learned = None
    if m.get('learned'):
        # trained once per held-out season and shared by every configuration
        # that uses it (carry-over and spread don't change the learned model)
        learned, rows = _G['learned'][year]
    else:
        rows = [r for y, rs in _G['pseudo'][_pkey(m['params'])].items() if y != year for r in rs]
    noise = ScaledNoise(xp.NoiseModel(rows), m['noise_scale'])
    rate_obs = _festival_obs(obs, year) if m['diet'] == 'festival' else None
    if m['diet'] == 'festival' and rate_obs is None:
        return mi, year, []
    out = []
    # checkpoint A: every conference and regional meet predicted the day before it,
    # from results before that day only (the live prediction's rule); the cascade is
    # simulated from that cutoff and only the meets run that day are scored
    for g in ('Boys', 'Girls'):
        gm = [x for x in hist['groups']['meets'] if x['gender'] == g]
        if not gm:
            continue
        groups = {'schools': hist['groups']['schools'], 'meets': gm}
        for day in sorted({x['day'] for x in gm if not x['id'].startswith('state')}):
            ratings = _rate(m, obs, year, g, day, calibs[year], rate_obs, learned)
            _, _, _, res = xp.simulate_postseason(
                obs, year, g, day, groups, calibs[year], noise, sims=sims,
                seed=year, params=m['params'], form_carry=m['form_carry'], ratings=ratings)
            todays = {x['id'] for x in gm if x['day'] == day and not x['id'].startswith('state')}
            for (mid, div), actual in hist['actual'].items():
                if mid not in todays:
                    continue
                teams = res.get(mid, {}).get('teams', {})
                pred = {(t[1] if isinstance(t, tuple) else t): v for t, v in teams.items()
                        if (div and isinstance(t, tuple) and t[0] == div) or (not div and not isinstance(t, tuple))}
                sc = score_podium(pred, actual)
                if sc:
                    stage = 'conference' if mid.startswith(('pvc', 'kvac')) else mid.split('_')[0]
                    out.append(dict(checkpoint='day before', stage=stage, meet=mid, div=div,
                                    gender=g, **sc))
    # (state meets: checkpoint B, from results before state day and the real state field)
    # checkpoint B: state meets predicted from results before state day
    for x in hist['groups']['meets']:
        if not x['id'].startswith('state'):
            continue
        g = x['gender']
        rows_ = hist['races'][(year, g, x['file'])]
        ratings = _rate(m, obs, year, g, x['day'], calibs[year], rate_obs, learned)
        entries = xp.pick_entries(ratings, {t: {t} for t in {o.team for o in rows_}})
        if len(entries) < 20:
            continue
        teams, _ = xp.simulate(ratings, entries, noise, sims=sims, seed=year,
                               icc=m['params'].get('program_icc', xp.DEFAULTS['program_icc']))
        n = len([t for t in teams if teams[t]['scored'] > 0])
        pred = {t: dict(place_dist=v['place_dist'],
                        exp_place_all=sum(p * c for p, c in v['place_dist'].items())
                        + (1 - sum(v['place_dist'].values())) * (n + 1))
                for t, v in teams.items()}
        sc = score_podium(pred, hist['actual'][(x['id'], '')])
        if sc:
            out.append(dict(checkpoint='day before', stage='state', meet=x['id'],
                            div='', gender=g, **sc))
    return mi, year, out


def run(methods, sims=600, procs=12, log=print):
    import pickle
    from multiprocessing import Pool
    obs = _G.get('obs') or xp.load()
    calibs = _G.get('calibs') or {y: xp.Calibration(obs, exclude_year=y) for y in FOLDS}
    _G.update(obs=obs, calibs=calibs, methods=methods,
              hist={y: history(obs, y) for y in FOLDS})
    log(f'{len(obs):,} observations; folds {FOLDS}')
    pkeys = sorted({_pkey(m['params']) for m in methods})
    with Pool(procs) as pool:
        pseudo = defaultdict(dict)
        for pk, y, rows in pool.imap_unordered(_pseudo_task, [(pk, y) for pk in pkeys for y in FOLDS]):
            pseudo[pk][y] = rows
        _G['pseudo'] = pseudo
        log(f'error models built for {len(pkeys)} rating variants')
    if any(m.get('learned') for m in methods):
        cache = os.environ.get('XC_FEATURE_CACHE')
        if cache and os.path.exists(cache):
            with open(cache, 'rb') as f:
                _G['features'] = pickle.load(f)
        else:
            with Pool(procs) as pool:
                _G['features'] = dict(pool.imap_unordered(_feature_task, FOLDS))
            if cache:
                with open(cache, 'wb') as f:
                    pickle.dump(_G['features'], f)
        log(f"feature rows: {sum(len(v) for v in _G['features'].values()):,}")
        with Pool(procs) as pool:
            _G['learned'] = dict(pool.imap_unordered(_learned_task, FOLDS))
        log('learned corrections trained, one per held-out season')
    with Pool(procs) as pool:
        tasks = [(mi, y, sims) for mi in range(len(methods)) for y in FOLDS]
        res = defaultdict(list)
        for mi, y, out in pool.imap_unordered(_fold_task, tasks):
            for r in out:
                r['fold'] = y
            res[mi].extend(out)
    return {methods[mi]['name']: dict(method=methods[mi], podiums=res[mi]) for mi in res}


# ---------------------------------------------------------------------------
# Individual times: every race of the held-out season
# ---------------------------------------------------------------------------

TIME_MIN_FIELD = 25


def _time_task(args):
    mi, year = args
    m = _G['methods'][mi]
    obs, cal = _G['obs'], _G['calibs'][year]
    races = defaultdict(list)
    for o in obs:
        if o.year == year and o.day is not None and o.day >= 7 and o.course[1] == 5000:
            races[o.race].append(o)
    cache, out = {}, []
    for r, rows in sorted(races.items(), key=lambda kv: str(kv[0])):
        f = cal.course.get(r[2])
        if len(rows) < TIME_MIN_FIELD or f is None:
            continue
        k = (r[1], r[3])
        if k not in cache:
            cache[k] = _rate(m, obs, year, r[1], r[3], cal)
        rat = cache[k]
        champ = bool(xp.CHAMP_FILE.search(r[4]) and not xp.NOT_CHAMP.search(r[4]) and r[3] >= 50)
        for o in rows:
            a = rat.get(o.aid)
            if a and a['n'] > 0:
                out.append((r[1], o.grade, champ, r[3], o.aid, o.lt, a['theta'] + f))
    return mi, year, out


def time_errors(methods, procs=12):
    """name -> fold -> [(gender, grade, champ, day, aid, actual log, predicted log)]."""
    from multiprocessing import Pool
    _G['methods'] = methods
    res = defaultdict(dict)
    with Pool(procs) as pool:
        for mi, y, rows in pool.imap_unordered(_time_task, [(mi, y) for mi in range(len(methods)) for y in FOLDS]):
            res[methods[mi]['name']][y] = rows
    return res


def grade_shift_tables(rows_by_fold, min_rows=200):
    """For each held-out season, the median log miss of each gender and grade
    over the other seasons: the `grade_shift` that season is rated with."""
    out = {}
    for y in rows_by_fold:
        by = defaultdict(list)
        for f, rows in rows_by_fold.items():
            if f == y:
                continue
            for g, gr, _, _, _, a, p in rows:
                if gr is not None:
                    by[f'{g}|{gr}'].append(a - p)
        out[str(y)] = {k: cm_median(v) for k, v in by.items() if len(v) >= min_rows}
    return out


def cm_median(v):
    v = sorted(v)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def time_summary(rows_by_fold, keep=None):
    """Median absolute error and mean error, seconds. `keep` (a set of
    (fold, aid, day)) restricts every method to the same runners."""
    def stats(rs):
        d = [math.exp(a) - math.exp(p) for *_, a, p in rs]
        if not d:
            return None
        ad = sorted(abs(x) for x in d)
        return dict(n=len(d), medae=cm_median(ad), bias=sum(d) / len(d),
                    mae=sum(x for x in ad if x <= 300) / sum(1 for x in ad if x <= 300))
    rows = {y: [r for r in v if keep is None or (y, r[4], r[3]) in keep] for y, v in rows_by_fold.items()}
    allr = [r for v in rows.values() for r in v]
    return dict(all=stats(allr), champ=stats([r for r in allr if r[2]]),
                fold=dict((y, stats(v)['medae']) for y, v in rows.items() if v))


def summarize(results):
    """One row per method: CV means and fold-level spread of the objective."""
    rows = []
    for name, r in results.items():
        P = r['podiums']
        if not P:
            continue
        def mean(k, sub=P):
            v = [p[k] for p in sub]
            return sum(v) / len(v) if v else float('nan')
        per_fold = defaultdict(list)
        for p in P:
            per_fold[p['fold']].append((p['inclusion'] + p['order']) / 2)
        fold_means = [sum(v) / len(v) for v in per_fold.values()]
        fm = sum(fold_means) / len(fold_means)
        fse = math.sqrt(sum((x - fm) ** 2 for x in fold_means) / (len(fold_means) - 1) / len(fold_means))
        stages = {}
        for st in ('conference', 'reg', 'state'):
            for cp in ('mid-October', 'after regionals'):
                sub = [p for p in P if p['stage'] == st and p['checkpoint'] == cp]
                if sub:
                    stages[f'{cp}:{st}'] = dict(n=len(sub), objective=mean('inclusion', sub) / 2 + mean('order', sub) / 2,
                                                inclusion=mean('inclusion', sub), order=mean('order', sub))
        rows.append(dict(name=name, n=len(P), objective=(mean('inclusion') + mean('order')) / 2,
                         objective_se=fse, inclusion=mean('inclusion'), order=mean('order'),
                         brier3=mean('brier3'), brier1=mean('brier1'), stages=stages))
    rows.sort(key=lambda r: (-round(r['objective'], 3), r['brier3']))
    return rows


def calibration_table(podiums, key='pt3', bins=10):
    """Reliability: predicted probability bin -> (count, observed rate)."""
    acc = defaultdict(lambda: [0, 0])
    for p in podiums:
        for prob, hit in p[key]:
            b = min(int(prob * bins), bins - 1)
            acc[b][0] += 1
            acc[b][1] += hit
    return {f'{b / bins:.1f}-{(b + 1) / bins:.1f}': (n, h / n) for b, (n, h) in sorted(acc.items())}


TIMES = [
    method('model (current)'),
    method('in-season trend by grade', {'trend': True}),
    method('trend, rated at last race', {'trend': True, 'trend_eval': 'last'}),
    method('trend, half the pooling', {'trend': True, 'trend_scale': 2.0}),
    method('recency 15 days', {'tau': 15.0}),
    method('recency 60 days', {'tau': 60.0}),
    method('no grade prior for newcomers', {'pool_level': False}),
    method('grade shift', {'grade_shift': 'auto'}),
]


def experiment(methods, sims, procs, log=print):
    """Times for every method (a 'grade shift' method is fitted from the first
    method's misses on the other seasons), then the podium cross-validation."""
    obs = xp.load()
    _G.update(obs=obs, calibs={y: xp.Calibration(obs, exclude_year=y) for y in FOLDS})
    log('calibrated')
    plain = [m for m in methods if m['params'].get('grade_shift') != 'auto']
    times = time_errors(plain, procs)
    log('times done for', len(plain), 'methods')
    tables = grade_shift_tables(times[plain[0]['name']])
    for m in methods:
        if m['params'].get('grade_shift') == 'auto':
            m['params'] = dict(m['params'], grade_shift=tables)
    shifted = [m for m in methods if isinstance(m['params'].get('grade_shift'), dict)]
    if shifted:
        times.update(time_errors(shifted, procs))
    pods = run(methods, sims=sims, procs=procs, log=log)
    return times, pods, tables


if __name__ == '__main__':
    import argparse
    import pickle
    ap = argparse.ArgumentParser()
    ap.add_argument('--sims', type=int, default=600)
    ap.add_argument('--procs', type=int, default=12)
    ap.add_argument('--out', required=True)
    ap.add_argument('--methods', default='ROUND1')
    ap.add_argument('--time', action='store_true', help='also score individual times (experiment())')
    a = ap.parse_args()
    methods = globals()[a.methods] if a.methods in globals() else json.load(open(a.methods))
    if a.time:
        times, pods, tables = experiment(methods, a.sims, a.procs)
        pickle.dump(dict(times=times, pods=pods, tables=tables), open(a.out, 'wb'))
        keep = None
        for name, rows in times.items():   # the runners every method rated
            k = {(y, r[4], r[3]) for y, v in rows.items() for r in v}
            keep = k if keep is None else keep & k
        pod = {r['name']: r for r in summarize(pods)}
        for m in methods:
            t = time_summary(times[m['name']], keep)
            p = pod.get(m['name'], {})
            print(f"{m['name']:30s} podium inclusion {p.get('inclusion', float('nan')):.3f} order {p.get('order', float('nan')):.3f} "
                  f"objective {p.get('objective', float('nan')):.3f}±{p.get('objective_se', float('nan')):.3f} | "
                  f"time median |err| {t['all']['medae']:.1f}s mean {t['all']['bias']:+.1f}s "
                  f"(championships {t['champ']['medae']:.1f}s, {t['champ']['bias']:+.1f}s)", flush=True)
        raise SystemExit
    res = run(methods, sims=a.sims, procs=a.procs)
    pickle.dump(res, open(a.out, 'wb'))
    for r in summarize(res):
        print(f"{r['name']:26s} objective {r['objective']:.3f}±{r['objective_se']:.3f}  "
              f"inclusion {r['inclusion']:.3f}  order {r['order']:.3f}  "
              f"brier3 {r['brier3']:.4f}  brier1 {r['brier1']:.4f}  ({r['n']} podiums)", flush=True)
