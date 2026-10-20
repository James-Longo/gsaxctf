"""
xc_postseason_publish.py - run the XC postseason predictions and write the
site's data files: one per season, ui/public/data/xc_postseason/<year>.json.gz,
listed in ui/public/data/xc_postseason/index.json.

    python3 -m backend.xc_postseason_publish                     # this season, 5000 sims
    python3 -m backend.xc_postseason_publish --asof 2026-10-15 --sims 5000
    python3 -m backend.xc_postseason_publish --seasons past      # every past season on file

This season: each meet is predicted from results before it only: a meet already
run (date on or before --asof) uses results through the day before it, so a
past prediction stays as it was; meets still ahead use results through --asof.
Each meet records its cutoff.

Past seasons are predicted the way the backtest scores them
(backend/xc_postseason_cv.py): the season's meets are rebuilt from its own
results files, each meet is predicted from results before its own day, and
course factors, carry-forward and the error model are all refit without that
season. Only seasons with their regionals and states on file are published.

A meet that has been run carries its result (`actual`): team places and scores
computed from the finish times (by division where the meet is scored by
division), every runner's place and time beside the prediction, and a summary.
Predicted times are for the meet's own course on a typical day; how much faster
or slower the whole field ran than predicted that day (`day`) moves every runner
together, so time misses are also given with it taken out.

The configuration is the one leave-one-season-out cross-validation chose: the
rating model with FORM_CARRY, and a noise model built from pseudo-backtest
errors on every past season. The CV summary shown on the page is
backend/data/xc_postseason_cv.json.

Run with PYTHONHASHSEED=0 for reproducible predictions.
"""

import argparse
import gzip
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta

from backend import school_catalog as sc
from backend import xc_course_model as cm
from backend import xc_postseason as xp
from backend import xc_postseason_cv as cv

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, 'ui', 'public', 'data', 'xc_postseason')
INDEX = os.path.join(OUT_DIR, 'index.json')
CV_SUMMARY = os.path.join(BASE, 'backend', 'data', 'xc_postseason_cv.json')
BACKTEST_YEARS = [y for y in range(2015, 2026) if y != 2020]
PAST_SIMS = 2000


def _mmss(lt):
    s = int(round(math.exp(lt)))
    return f'{s // 60}:{s % 60:02d}'


def _venue(course):
    """'Cony High School (Augusta)' -> 'Cony', 'Twin Brook Recreation Area' -> 'Twin Brook'."""
    v = re.sub(r'\s*\(.*?\)', '', cm.base_venue(course)).strip()
    return re.sub(r'\s+(High School|HS|Recreation Area|XC course)$', '', v)


def _date(year, day):
    return (date(year, *xp.SEASON_START) + timedelta(days=day)).isoformat()


def _div_label(raw):
    """An official team-score block's heading as a division name."""
    m = re.search(r'\b(large|small)\b', raw or '', re.I)
    if m:
        return m.group(1).title()
    m = re.search(r'class[-_ ]*([abcd])\b', raw or '', re.I)
    if m:
        return f'Class {m.group(1).upper()}'
    return (raw or '').strip() or 'All'


# ---------------------------------------------------------------------------
# One meet: the prediction, then the result beside it
# ---------------------------------------------------------------------------

def race_rows(obs, year, gender, day, members, field):
    """The meet's race that day, restricted to the meet's schools, in
    finishing order: of the races whose runners are mostly this meet's
    schools, the one holding most of the predicted `field` (a JV race the
    same afternoon has the same schools but other runners)."""
    races = defaultdict(list)
    for o in obs:
        if o.year == year and o.gender == gender and o.day == day:
            races[o.race].append(o)
    best = None
    for rows in races.values():
        share = sum(o.team in members for o in rows) / len(rows)
        key = (sum(o.aid in field for o in rows), share)
        if share >= 0.6 and len(rows) >= 20 and (best is None or key > best[0]):
            best = (key, rows)
    if best is None:
        return None
    return sorted((o for o in best[1] if o.team in members), key=lambda o: o.lt)


def _division_members(meet, members, schools):
    """[(division label or None, set of team units)]."""
    divs = meet.get('divisions')
    if not divs:
        return [(None, set(members))]
    out = []
    for label, spec in divs.items():
        if isinstance(spec, (list, set, tuple)):
            out.append((label, set(spec)))
        else:
            out.append((label, {s for s in members if schools.get(s, {}).get('class') == spec}))
    return out


def meet_members(meet, schools):
    if 'schools' in meet:
        return set(meet['schools'])
    if 'region' in meet:
        return {s for s, i in schools.items() if i['class'] == meet['class'] and i['region'] == meet['region']}
    return {s for s, i in schools.items() if i['class'] == meet['class']}


def prediction_out(res, rat, school_of, races, noise, name, course_f):
    """The page's teams and athletes lists for one simulated meet. Athletes
    keep `_aid` and `_e` (log predicted time on the meet's course) for the
    comparison; publish() drops them."""
    teams = []
    for t, v in res['teams'].items():
        div, team = t if isinstance(t, tuple) else (None, t)
        pd = v['place_dist']
        teams.append(dict(
            team=name(team), store=sc.store_name(team), div=div, win=round(v['win'], 3),
            top3=round(sum(p for k, p in pd.items() if k <= 3), 3),
            exp=round(v['exp_place_all'], 2), appear=round(v['appear'], 3),
            score=round(v['med_score']),
            qual=None if v['qualify'] is None else round(v['qualify'], 3),
            # 1st, 2nd, 3rd, 4th or lower; sums to `appear` (share of
            # simulations in which the team scored)
            odds=[round(pd.get(k, 0), 4) for k in (1, 2, 3)]
                 + [round(sum(p for k, p in pd.items() if k >= 4), 4)],
            _id=team, _pd=pd))
    teams.sort(key=lambda t: (t['div'] or '', t['exp']))
    aths = []
    for a, v in res['athletes'].items():
        rr = rat[a]
        e = rr['theta'] + noise.shift(rr['n'], rr['prior']) + (course_f or 0.0)
        aths.append(dict(
            name=rr['name'], school=name(school_of[a]), div=v.get('div'), grade=rr.get('grade'),
            t=_mmss(e), _e=e, _aid=a, n=rr['n'], start=round(v['start'], 3),
            med=v['med'], p10=v['p10'], p90=v['p90'], top10=round(v['top10'], 3),
            qual=None if v['qualify'] is None else round(v['qualify'], 3),
            races=[[cm.base_venue(o.course[0]), _mmss(o.lt)]
                   for o in sorted(races.get(a, []), key=lambda o: o.day or 0)]))
    return teams, aths


def compare(meet, rows, members, schools, teams, aths, name, course_known):
    """The result beside the prediction: per division, actual team places and
    scores (scored from the finish times, as the simulator scores), every
    runner's place and time with their prediction, and summary measures."""
    fc_ath = {a['_aid']: a for a in aths}
    fc_team = {(t['div'], t['_id']): t for t in teams}
    rank = {}
    for t in teams:                     # predicted order within each division
        rank[(t['div'], t['_id'])] = sum(1 for u in teams if u['div'] == t['div'] and u['exp'] < t['exp']) + 1
    ran = {o.aid for o in rows}
    # the day: how far the field as a whole ran from its predicted times
    day = None
    if course_known:
        both = [o.lt - fc_ath[o.aid]['_e'] for o in rows if o.aid in fc_ath]
        if len(both) >= 10:
            day = cm.median(both)
    out_t, out_a, summary = [], [], {}
    for div, mem in _division_members(meet, members, schools):
        sub = [o for o in rows if o.team in mem]
        if not sub:
            continue
        ranked, _ = xp.score_race([o.aid for o in sub], {o.aid: o.team for o in sub})
        for i, (t, score, _) in enumerate(ranked):
            f = fc_team.get((div, t))
            out_t.append(dict(div=div, team=name(t), store=sc.store_name(t), place=i + 1, score=score,
                              pred=rank.get((div, t)), pscore=f and f['score'],
                              p=f and round(f['_pd'].get(i + 1, 0.0), 3)))
        scored = {t for t, _, _ in ranked}
        for t in teams:                 # predicted to score, but fewer than five finished
            if t['div'] == div and t['_id'] not in scored and t['appear'] >= 0.5:
                out_t.append(dict(div=div, team=t['team'], store=t['store'], place=None, score=None,
                                  pred=rank.get((div, t['_id'])), pscore=t['score'], p=None))
        hits, place_err, t_err = [], [], []
        for i, o in enumerate(sub):
            f = fc_ath.get(o.aid)
            row = dict(div=div, name=o.name, school=name(o.team), grade=o.grade,
                       place=i + 1, t=_mmss(o.lt))
            if f:
                row.update(pt=f['t'] if course_known else None, p10=f['p10'], p90=f['p90'], med=f['med'])
                hits.append(f['p10'] <= i + 1 <= f['p90'])
                place_err.append(abs(i + 1 - f['med']))
                if day is not None:
                    t_err.append(abs(math.exp(o.lt) - math.exp(f['_e'] + day)))
            out_a.append(row)
        div_teams = [t for t in teams if t['div'] == div]
        pred3 = [t['_id'] for t in sorted(div_teams, key=lambda t: t['exp'])[:3]]
        act3 = [t for t, _, _ in ranked[:3]]
        summary[div or ''] = dict(
            teams=len(ranked),
            winner=bool(pred3 and act3 and pred3[0] == act3[0]),
            podium=len(set(pred3) & set(act3)) if len(act3) == 3 else None,
            order=sum(1 for i in range(min(3, len(pred3), len(act3))) if pred3[i] == act3[i]),
            runners=len(hits), in_range=round(sum(hits) / len(hits), 3) if hits else None,
            place_err=cm.median(place_err) if place_err else None,
            time_err=round(cm.median(t_err)) if t_err else None)
    dns = [dict(div=a['div'], name=a['name'], school=a['school'])
           for a in aths if a['_aid'] not in ran and a['start'] >= 0.5]
    return dict(day=None if day is None else round(math.exp(day) - 1, 4),
                summary=summary, teams=out_t, athletes=out_a, dns=dns)


def _clean(gm):
    for r in gm.values():
        for t in r['teams']:
            t.pop('_id', None)
            t.pop('_pd', None)
        for a in r['athletes']:
            a.pop('_e', None)
            a.pop('_aid', None)


def _sort_aths(mid, aths):
    if mid.startswith('state'):
        # the state field changes every simulation: list who usually gets
        # there, most likely first, and drop 1-in-100 flukes
        aths = [x for x in aths if x['start'] >= 0.01]
        aths.sort(key=lambda x: (x['start'] < 0.5, x['med'] if x['start'] >= 0.5 else -x['start'], x['_e']))
    else:
        aths.sort(key=lambda x: (x['div'] or '', x['med'], x['_e']))
    return aths


# ---------------------------------------------------------------------------
# This season
# ---------------------------------------------------------------------------

def predict_season(year, asof, sims, obs, noise, cal, seed=0, say=lambda *a: None):
    groups = xp.load_groups(year)
    gname = lambda sid: groups['schools'].get(sid, {}).get('name') or xp.school_name(sid)
    # Every race is predicted from results before it, never after: a meet already
    # run keeps the prediction it had the day before (its results feed only the meets
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
            for m in groups['meets']:
                mid = m['id']
                if mid not in mids or mid not in res:
                    continue
                members = meet_members(m, groups['schools'])
                rows = None
                if m.get('date') and m['date'] <= asof:
                    rows = race_rows(obs, year, g, xp.season_day(year, m['date']), members, res[mid]['athletes'])
                course = rows[0].course if rows else tuple(m['course']) if m.get('course') else None
                course_f = cal.course.get(course) if course else None
                teams, aths = prediction_out(res[mid], rat, school_of, races, noise, gname, course_f)
                aths = _sort_aths(mid, aths)
                out = dict(teams=teams, athletes=aths, asof=cut_date, course_known=course_f is not None)
                if rows:
                    out['actual'] = compare(m, rows, members, groups['schools'], teams, aths, gname,
                                            course_f is not None)
                data[g][mid] = out
    for g in data:
        _clean(data[g])
    meets = [{k: m[k] for k in ('id', 'name', 'date', 'venue') if k in m}
             | ({'divisions': list(m['divisions'])} if 'divisions' in m else {})
             | {'asof': cut_of[m['id']]}
             for m in groups['meets']]
    out = dict(year=year, asof=asof, sims=sims, kind='prediction', meets=meets, data=data, races=len(race_ids))
    try:
        with open(CV_SUMMARY, encoding='utf-8') as f:
            cvs = json.load(f)
        chosen = next(r for r in cvs['rows'] if r.get('chosen'))
        out['backtest'] = dict(seasons=cvs['folds'], podiums=cvs['n_podiums'],
                               inclusion=round(chosen['inc'], 3), order=round(chosen['order'], 3))
    except (OSError, ValueError, StopIteration):
        pass
    return out


# ---------------------------------------------------------------------------
# Past seasons, rebuilt from their results files
# ---------------------------------------------------------------------------

def _past_ids(hist):
    """history() ids are per gender (reg_C_North_Boys); the page's are shared
    by both genders (reg_C_N), with a display name, date and venue."""
    ids, info = {}, {}
    nth = defaultdict(int)
    for m in sorted(hist['groups']['meets'], key=lambda m: m['id']):
        hid, g = m['id'], m['gender']
        if hid.startswith('reg_'):
            _, cls, region, _ = hid.split('_')
            pid, name = f'reg_{cls}_{region[0]}', f'Class {cls} {region} Regional'
        elif hid.startswith('state_'):
            cls = hid.split('_')[1]
            pid, name = f'state_{cls}', f'Class {cls} State'
        else:
            kind = hid.split('_')[0]
            nth[(kind, g)] += 1
            k = nth[(kind, g)]
            pid = kind if k == 1 else f'{kind}{k}'
            f = m.get('file', '')
            cm_ = re.search(r'class[-_ ]?([abc])(?![a-z])', f, re.I)
            sub = f' Class {cm_.group(1).upper()}' if cm_ and not m.get('divisions') else \
                f' {re.search(r"large|small", f, re.I).group(0).title()}' if re.search(r'large|small', f, re.I) else ''
            name = f'{kind.upper()} Championship{sub}'
        ids[hid] = pid
        info.setdefault(pid, dict(id=pid, name=name, day=m['day']))
    return ids, info


def past_season(year, sims, obs, cal, noise, say=lambda *a: None):
    hist = cv.history(obs, year)
    if not hist:
        return None
    meets = hist['groups']['meets']
    # a state meet whose regionals are not all on file has an incomplete field
    regs = {m['id'] for m in meets if m['id'].startswith('reg_')}
    meets = [m for m in meets if not m['id'].startswith('state_')
             or (len(m['from']) >= 2 and all(f in regs for f in m['from']))]
    if sum(m['id'].startswith('reg_') for m in meets) < 6 or sum(m['id'].startswith('state_') for m in meets) < 3:
        return None
    schools = hist['groups']['schools']
    for m in meets:
        if m.get('divisions'):
            labels = {k: _div_label(k) for k in m['divisions']}
            for k, v in m['divisions'].items():
                # a block printed without its class ('Results - Men'): the class
                # most of its teams ran their regional in
                if not re.match(r'(Large|Small|Class [A-D])$', labels[k]):
                    cls = [schools.get(t, {}).get('class') for t in v]
                    top = max(set(cls), key=cls.count) if cls else None
                    if top and cls.count(top) >= 0.6 * len(cls):
                        labels[k] = f'Class {top}'
            if len(set(labels.values())) == len(labels):
                m['divisions'] = {labels[k]: v for k, v in m['divisions'].items()}
    ids, info = _past_ids(dict(groups=dict(meets=meets)))
    name = lambda sid: xp.school_name(sid)
    data = {'Boys': {}, 'Girls': {}}
    venue = {}
    for g in ('Boys', 'Girls'):
        gm = [m for m in meets if m['gender'] == g]
        groups = {'schools': schools, 'meets': gm}
        for day in sorted({m['day'] for m in gm}):
            ratings, _ = xp.season_ratings(obs, year, g, day, cal, {})
            races = defaultdict(list)
            for o in obs:
                if o.year == year and o.gender == g and o.day is not None and o.day < day:
                    races[o.aid].append(o)
            rat, school_of, _, res = xp.simulate_postseason(
                obs, year, g, day, groups, cal, noise, sims=sims, seed=year,
                form_carry=xp.FORM_CARRY, ratings=ratings)
            for m in gm:
                if m['day'] != day or m['id'] not in res:
                    continue
                members = meet_members(m, schools)
                rows = race_rows(obs, year, g, day, members, res[m['id']]['athletes'])
                course_f = cal.course.get(rows[0].course) if rows else None
                teams, aths = prediction_out(res[m['id']], rat, school_of, races, noise, name, course_f)
                aths = _sort_aths(m['id'], aths)
                pid = ids[m['id']]
                out = dict(teams=teams, athletes=aths, asof=_date(year, day - 1),
                           course_known=course_f is not None)
                if rows:
                    venue.setdefault(pid, _venue(rows[0].course[0]))
                    out['actual'] = compare(m, rows, members, schools, teams, aths, name, course_f is not None)
                data[g][pid] = out
        say(year, g, 'done')
    for g in data:
        _clean(data[g])
    out_meets = []
    for pid, i in sorted(info.items(), key=lambda kv: (kv[1]['day'], kv[0])):
        m = dict(id=pid, name=i['name'], date=_date(year, i['day']), venue=venue.get(pid, ''),
                 asof=_date(year, i['day'] - 1))
        divs = sorted({d for g in data for t in data[g].get(pid, {}).get('teams', []) for d in [t['div']] if d})
        if divs:
            m['divisions'] = divs
        out_meets.append(m)
    return dict(year=year, asof=_date(year, max(i['day'] for i in info.values())), sims=sims,
                kind='backtest', meets=out_meets, data=data)


_G = {}


def _past_task(year):
    rows = [r for r in _G['rows'] if r['race'][0] != year]
    return year, past_season(year, _G['sims'], _G['obs'], _G['calibs'][year], xp.NoiseModel(rows))


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def write(out):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f'{out["year"]}.json.gz')
    raw = json.dumps(out, separators=(',', ':')).encode('utf-8')
    with gzip.open(path, 'wb', compresslevel=9) as f:
        f.write(raw)
    print(f'{path}: {len(raw) // 1024} KB raw, {os.path.getsize(path) // 1024} KB gz', file=sys.stderr)
    try:
        with open(INDEX, encoding='utf-8') as f:
            index = json.load(f)
    except (OSError, ValueError):
        index = {'seasons': []}
    seasons = {s['year']: s for s in index['seasons']}
    seasons[out['year']] = dict(year=out['year'], kind=out['kind'], asof=out['asof'],
                                built=date.today().isoformat())
    index['seasons'] = sorted(seasons.values(), key=lambda s: -s['year'])
    with open(INDEX, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--asof', default=date.today().isoformat(), help='use results through this date (YYYY-MM-DD)')
    ap.add_argument('--sims', type=int, default=5000)
    ap.add_argument('--past-sims', type=int, default=PAST_SIMS)
    ap.add_argument('--seasons', choices=['current', 'past', 'all'], default='current')
    ap.add_argument('--procs', type=int, default=min(10, os.cpu_count() or 1))
    a = ap.parse_args()
    say = lambda *x: print(*x, file=sys.stderr, flush=True)
    obs = xp.load()
    say(f'{len(obs):,} observations')
    # error model from every past season, each predicted without itself
    calibs = {y: xp.Calibration(obs, exclude_year=y) for y in BACKTEST_YEARS}
    rows = xp.pseudo_backtest(obs, years=BACKTEST_YEARS, calibs=calibs)
    say('calibrated')
    if a.seasons in ('past', 'all'):
        from multiprocessing import get_context
        _G.update(obs=obs, calibs=calibs, rows=rows, sims=a.past_sims)
        with get_context('fork').Pool(a.procs) as pool:
            for y, out in pool.imap_unordered(_past_task, BACKTEST_YEARS):
                if out is None:
                    say(y, 'skipped: regionals or states not on file')
                    continue
                write(out)
    if a.seasons in ('current', 'all'):
        year = int(a.asof[:4])
        write(predict_season(year, a.asof, a.sims, obs, xp.NoiseModel(rows), xp.Calibration(obs), say=say))


if __name__ == '__main__':
    main()
