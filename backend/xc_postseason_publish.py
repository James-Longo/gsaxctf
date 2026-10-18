"""
xc_postseason_publish.py - run the XC postseason forecast and write the
site's data file, ui/public/data/xc_postseason.json.gz.

    python3 -m backend.xc_postseason_publish            # today's season, 5000 sims
    python3 -m backend.xc_postseason_publish --asof 2026-10-15 --sims 5000

Each meet is forecast from results before it only: a meet already run (date on or
before --asof) uses results through the day before it, so a past forecast stays as
it was; meets still ahead use results through --asof. Each meet records its cutoff.

The configuration is the one leave-one-season-out cross-validation chose
(backend/xc_postseason_cv.py): the rating model with FORM_CARRY, and a noise
model built from pseudo-backtest errors on every past season. The CV summary
shown on the page is backend/data/xc_postseason_cv.json.

Run with PYTHONHASHSEED=0 for a reproducible forecast.
"""

import argparse
import gzip
import json
import math
import os
import sys
from collections import defaultdict
from datetime import date, timedelta

from backend import school_catalog as sc
from backend import xc_course_model as cm
from backend import xc_postseason as xp

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, 'ui', 'public', 'data', 'xc_postseason.json.gz')
CV_SUMMARY = os.path.join(BASE, 'backend', 'data', 'xc_postseason_cv.json')
BACKTEST_YEARS = [y for y in range(2015, 2026) if y != 2020]


def _mmss(lt):
    s = int(round(math.exp(lt)))
    return f'{s // 60}:{s % 60:02d}'


def forecast(year, asof, sims, seed=0, quiet=False):
    say = (lambda *a: None) if quiet else (lambda *a: print(*a, file=sys.stderr))
    obs = xp.load()
    say(f'{len(obs):,} observations')
    groups = xp.load_groups(year)
    # error model from every past season, each predicted without itself
    calibs = {y: xp.Calibration(obs, exclude_year=y) for y in BACKTEST_YEARS}
    noise = xp.NoiseModel(xp.pseudo_backtest(obs, years=BACKTEST_YEARS, calibs=calibs))
    cal = xp.Calibration(obs)
    say('calibrated')
    name = lambda sid: groups['schools'].get(sid, {}).get('name') or xp.school_name(sid)
    # Every race is predicted from results before it, never after: a meet already
    # run keeps the forecast it had the day before (its results feed only the meets
    # after it); a meet still ahead uses everything through `asof`.
    def meet_cut(m):
        if not m.get('date'):
            return asof
        return min(asof, (date.fromisoformat(m['date']) - timedelta(days=1)).isoformat())
    cut_of = {m['id']: meet_cut(m) for m in groups['meets']}

    data = {'Boys': {}, 'Girls': {}}
    race_ids = set()
    for cut_date in sorted(set(cut_of.values())):
      # ratings use results strictly before `cutoff`: through cut_date, the day before the race
      cutoff = xp.season_day(year, cut_date) + 1
      mids = {mid for mid, c in cut_of.items() if c == cut_date}
      say(f'data through {cut_date}: {sorted(mids)}')
      races = defaultdict(list)
      for o in obs:
          if o.year == year and (o.day is None or o.day < cutoff):
              races[o.aid].append(o)
      race_ids |= {o.race for v in races.values() for o in v}
      for g in ('Boys', 'Girls'):
        ratings, _ = xp.season_ratings(obs, year, g, cutoff, cal, {})
        rat, school_of, _, res = xp.simulate_postseason(
            obs, year, g, cutoff, groups, cal, noise, sims=sims, seed=seed,
            form_carry=xp.FORM_CARRY, ratings=ratings)
        say(g, len(rat), 'rated')
        gm = data[g]
        for mid, r in res.items():
            if mid not in mids:
                continue
            teams = []
            for t, v in r['teams'].items():
                div, team = t if isinstance(t, tuple) else (None, t)
                pd = v['place_dist']
                teams.append(dict(
                    team=name(team), store=sc.store_name(team), div=div, win=round(v['win'], 3),
                    top3=round(sum(p for k, p in pd.items() if k <= 3), 3),
                    exp=round(v['exp_place_all'], 2), appear=round(v['appear'], 3),
                    score=round(v['med_score']),
                    qual=None if v['qualify'] is None else round(v['qualify'], 3),
                    # 1st, 2nd, 3rd, 4th or lower; sums to `appear` (share
                    # of simulations in which the team scored)
                    odds=[round(pd.get(k, 0), 4) for k in (1, 2, 3)]
                         + [round(sum(p for k, p in pd.items() if k >= 4), 4)]))
            teams.sort(key=lambda t: (t['div'] or '', t['exp']))
            aths = []
            for a, v in r['athletes'].items():
                rr = rat[a]
                e = rr['theta'] + noise.shift(rr['n'], rr['prior'])
                aths.append(dict(
                    name=rr['name'], school=name(school_of[a]), div=v.get('div'), grade=rr.get('grade'),
                    t=_mmss(e), _e=e, n=rr['n'], start=round(v['start'], 3),
                    med=v['med'], p10=v['p10'], p90=v['p90'], top10=round(v['top10'], 3),
                    qual=None if v['qualify'] is None else round(v['qualify'], 3),
                    races=[[cm.base_venue(o.course[0]), _mmss(o.lt)]
                           for o in sorted(races.get(a, []), key=lambda o: o.day or 0)]))
            if mid.startswith('state'):
                # the state field changes every simulation: list who usually
                # gets there, most likely first, and drop 1-in-100 flukes
                aths = [x for x in aths if x['start'] >= 0.01]
                aths.sort(key=lambda x: (x['start'] < 0.5, x['med'] if x['start'] >= 0.5 else -x['start'], x['_e']))
            else:
                aths.sort(key=lambda x: (x['div'] or '', x['med'], x['_e']))
            for x in aths:
                x.pop('_e')
            gm[mid] = dict(teams=teams, athletes=aths, asof=cut_date)

    meets = [{k: m[k] for k in ('id', 'name', 'date', 'venue') if k in m}
             | ({'divisions': list(m['divisions'])} if 'divisions' in m else {})
             | {'asof': cut_of[m['id']]}
             for m in groups['meets']]
    out = dict(year=year, asof=asof, sims=sims, meets=meets, data=data, races=len(race_ids))
    try:
        with open(CV_SUMMARY, encoding='utf-8') as f:
            cv = json.load(f)
        chosen = next(r for r in cv['rows'] if r.get('chosen'))
        out['backtest'] = dict(seasons=cv['folds'], podiums=cv['n_podiums'],
                               inclusion=round(chosen['inc'], 3), order=round(chosen['order'], 3))
    except (OSError, ValueError, StopIteration):
        pass
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--asof', default=date.today().isoformat(), help='use results through this date (YYYY-MM-DD)')
    ap.add_argument('--sims', type=int, default=5000)
    ap.add_argument('--out', default=OUT)
    a = ap.parse_args()
    year = int(a.asof[:4])
    out = forecast(year, a.asof, a.sims)
    raw = json.dumps(out, separators=(',', ':')).encode('utf-8')
    with gzip.open(a.out, 'wb', compresslevel=9) as f:
        f.write(raw)
    print(f'{a.out}: {len(raw) // 1024} KB raw, {os.path.getsize(a.out) // 1024} KB gz', file=sys.stderr)


if __name__ == '__main__':
    main()
