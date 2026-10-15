"""
xc_postseason.py - simulate cross-country championship races (PROTOTYPE).

The hard part of XC prediction is not the race, it is the season before it:
hundreds of runners each race a handful of times, on different courses, on
different days, at different points in their fitness curve. This module turns
that into one number per athlete, then rolls dice.

Model, on the log-time scale so effects are multiplicative:

    log T[a, r] = theta[a] + d[r] + e[a, r]
    d[r]        = f[course] + u[r]

  theta[a]  athlete ability for the season, on the Festival-anchored scale
  f         course factor (fitted here across seasons, same idea as
            xc_course_model.py)
  u[r]      race-day effect: mud, heat, a re-routed loop, and the field's
            average fitness on that date. Shrunk toward 0 when few runners
            link the race to the rest of the season.

Within a race every runner shares d[r], so the championship race's own course
and conditions never affect who beats whom. They matter only for reading the
races that came before it.

Races must be anchored -- by a known course or by runners shared with races
already anchored. Islands of races nobody links to the rest of the season
(middle-school circuits, mislabelled distances) are dropped; they were the
single largest source of wrong favourites in the backtest.

Season ratings blend this season's races (recency-weighted, one bad day
down-weighted) with last season's rating carried forward by the typical
year-over-year gain, because in October most runners have 1-3 races on file.

Prediction error is measured, not assumed: every late-season race in 2015-2025
is "predicted" from the races before it, and the simulator draws noise from
those empirical errors. Regional -> state form carry-over (0.65) is measured
on real regional/state pairs.

Validated by cross-validation on real postseasons: settings chosen on 165
championship races (2015-2023), scored on 44 held-out races (2024-2025).
Group membership for a season lives in backend/data/xc_groups.json.
"""

import math
import os
import random
import re
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import school_catalog
from backend import xc_course_model as cm
from backend.json_store import (TEAMS_DIR, _chunk_files, _load_json, enrich_rows,
                                canonical_team_name, parse_mark_value)

SEASON_START = (8, 15)       # day 0 of the season


def season_day(year, iso):
    """Days since Aug 15 of the season year; None for an unknown date."""
    if not iso or not iso[:4].isdigit():
        return None
    try:
        d = date(int(iso[:4]), int(iso[5:7]), int(iso[8:10]))
    except ValueError:
        return None
    return (d - date(int(year), *SEASON_START)).days


def wmedian(pairs):
    """Weighted median of (value, weight) pairs."""
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= total / 2:
            return v
    return pairs[-1][0]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

class Obs:
    __slots__ = ('aid', 'year', 'gender', 'course', 'lt', 'meet', 'day',
                 'team', 'name', 'grade', 'race')

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _name_key(name):
    """Order-free athlete name key: 'Malia, Shamus' == 'Shamus Malia'."""
    return tuple(sorted(re.findall(r'[a-z]+', (name or '').lower())))


def _raw_schools():
    """(year, meet, athlete name key) -> [(school as printed, seconds)].

    A list, because one race can hold two runners with the same name at
    different schools (two Isaac Wrights at the 2026 Festival; 528 such pairs
    in the XC files). The finish time tells them apart.
    """
    out = {}
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'parsed_results')
    for year in os.listdir(base):
        d = os.path.join(base, year, 'XC')
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith('.json'):
                continue
            try:
                j = cm._load_json(os.path.join(d, fn), {})
            except Exception:
                continue
            evs = j.get('events', []) if isinstance(j, dict) else []
            meet = fn[:-5]
            for ev in evs:
                if not isinstance(ev, dict):
                    continue
                # two layouts: events holding a results list, or (PDF list
                # parsers) one flat row per athlete
                rows = ev['results'] if 'results' in ev else [ev]
                for r in rows:
                    name = r.get('athlete') or r.get('athlete_name')
                    if name and r.get('school'):
                        sec, _ = parse_mark_value(r.get('result') or r.get('mark') or '', 'xc')
                        out.setdefault((year, meet, _name_key(name)), []).append((r['school'], sec))
    return out


def xc_unit(store_team, raw_school, year, gender, meet):
    """The team a runner competes for in cross country, as a catalog id.

    School identity comes from backend/school_catalog.py, which resolves the
    school string exactly as printed in the results file (truncations, codes,
    mascots, M/F suffixes) instead of the shared store team, whose clustering
    merges schools (Bangor Christian into Bangor High, middle schools into
    their high schools). team_unit() then turns a school into the co-op it
    ran as that season, by gender. Falls back to the store team's id, then to
    the raw store name, so no runner silently disappears.
    """
    sid = None
    if raw_school:
        # resolve() keys its per-file evidence on the parsed file name
        # ("airline-boys.txt" -> airline-boys.txt.json), so pass that
        sid = school_catalog.resolve(raw_school, year=str(year), season='XC',
                                     gender=gender, meet_name=f'{meet}.json')
    if sid is None:
        sid = school_catalog.id_for_store_name(store_team)
    if sid is None:
        return store_team
    return school_catalog.team_unit(sid, str(year), 'XC', gender) or sid


GENDER_SUFFIX = re.compile(r'\s([MF])$')


def _suffix_gendered(raw):
    """Files that mark gender on the school column instead of the event.

    The 2026 LaLiberte list heads every page "Boys 4k" but writes schools as
    "Morse M" / "Morse F": 106 girls arrive as boys. A file whose school
    strings nearly all carry an M/F suffix, with both present, is read by the
    suffix. Returns {(year, meet)}.
    """
    by_file = defaultdict(list)
    for (year, meet, _), cands in raw.items():
        by_file[(year, meet)] += [school for school, _ in cands]
    out = set()
    for k, schools in by_file.items():
        tags = [m.group(1) for m in (GENDER_SUFFIX.search(s.strip()) for s in schools) if m]
        if len(tags) >= 0.9 * len(schools) and {'M', 'F'} <= set(tags):
            out.add(k)
    return out


def _pick_raw(cands, row):
    """The printed school for this store row: the candidate whose time
    matches, else the only candidate, else None (fall back to the store)."""
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0][0]
    sec, _ = parse_mark_value(row.get('mark', ''), 'xc')
    if sec is not None:
        hits = [s for s, t in cands if t is not None and abs(t - sec) < 0.6]
        if len(set(hits)) == 1:
            return hits[0]
    return None


def _detail_lookup():
    """(athlete_id, year, meet) -> (team, gender, name, grade) from the store.

    xc_course_model's loader keeps only what the course fit needs; the
    simulator also needs to know whose team and which race a row belongs to.
    """
    out = {}
    raw = _raw_schools()
    suffixed = _suffix_gendered(raw)
    for fn in os.listdir(TEAMS_DIR):
        full = os.path.join(TEAMS_DIR, fn)
        if not os.path.isdir(full):
            continue
        team = canonical_team_name(fn)
        for key, chunk in _chunk_files(full):
            if not key.endswith('_XC'):
                continue
            for p in enrich_rows(team, key, _load_json(os.path.join(full, chunk), [])):
                ev = p.get('event', '')
                g = 'Girls' if ev.startswith('Girls') else 'Boys' if ev.startswith('Boys') else None
                if g is None:
                    continue
                gr = str(p.get('grade') or '').strip()
                rs = _pick_raw(raw.get((p['year'], p.get('meet_name'),
                                        _name_key(p.get('athlete_name')))), p)
                if rs and (p['year'], p.get('meet_name')) in suffixed:
                    m = GENDER_SUFFIX.search(rs.strip())
                    if m:
                        g = 'Boys' if m.group(1) == 'M' else 'Girls'
                school = xc_unit(p.get('team') or team, rs, p['year'], g, p.get('meet_name'))

                out[(p['athlete_id'], p['year'], p.get('meet_name'))] = (
                    school, g, p.get('athlete_name', ''),
                    int(gr) if gr.isdigit() and 6 <= int(gr) <= 12 else None)
    return out


def load(quiet=True):
    """Cleaned XC observations with team, gender and season day attached.

    Reuses the course model's whole cleaning chain (distance-label checks,
    non-HS filter, venue merging, outlier seasons) so the two models agree on
    what counts as a real race.
    """
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf if quiet else sys.stdout):
        raw = cm.clean_observations(team_filter=False)
    detail = _detail_lookup()
    try:
        from backend import athlete_catalog as ac
        runner_of = ac.load_catalog().get('member_of', {})
    except Exception:  # noqa: BLE001 - catalog optional
        runner_of = {}
    seen = set()
    obs = []
    for store_aid, year, course, lt, meet, d in raw:
        det = detail.get((store_aid, year, meet))
        if det is None:
            continue
        day = season_day(year, d)
        team, gender, name, grade = det
        # One runner, one id: the store keys athletes by name + store team, so
        # a school printed two ways ("KENN" and "Kennebunk") or a name typed
        # two ways ("Pellerano" / "Pellarono") gives the same runner two ids,
        # and the duplicate would fill a second of the team's seven spots.
        # The athlete catalog (backend/athlete_catalog.py) joins those; the
        # normalized name is the fallback for ids it doesn't know.
        runner = runner_of.get(store_aid)
        aid = (runner or '-'.join(_name_key(name))) + '--' + team
        # one runner, one race day, one time: the same race posted twice
        # (overall + by-section files, or under two store ids) counts once
        k = (aid, year, course, day if day is not None else meet, round(lt, 5))
        if k in seen:
            continue
        seen.add(k)
        # A race is one results file: one gender, one course, one day. Files
        # from the same afternoon are NOT pooled even though they share the
        # weather: a JV or middle-school 2-miler mislabelled "5K" next to the
        # varsity 5K would otherwise become one bimodal race whose median
        # rates half its field 60% wrong (2016 Greater Houlton girls). The
        # shrinkage toward the course factor recovers what sharing bought.
        race = (int(year), gender, course, day if day is not None else meet, meet)
        obs.append(Obs(aid=aid, year=int(year), gender=gender, course=course,
                       lt=lt, meet=meet, day=day, team=team, name=name,
                       grade=grade, race=race))
    return _drop_gender_conflicts(_drop_off_norm_races(obs))


# A race whose field ran this far from what fields usually run on its course
# is not a fast or slow day: it is a different race -- a junior-high 1.8-miler
# or a mislabelled distance filed under the course's 5K. Junior varsity
# fields run ~10-15% slower than varsity; real conditions move a race ~4%.
OFF_NORM = 0.25


def _drop_off_norm_races(obs):
    """Remove races whose median time is more than OFF_NORM (log) from the
    median race on the same course, measured over all seasons. Catches whole
    circuits of mislabelled races that vouch for each other and so slip past
    the anchoring check (2018 MVC junior-high files labelled 5K)."""
    by_race = defaultdict(list)
    for o in obs:
        by_race[o.race].append(o.lt)
    per_course = defaultdict(list)
    for r, ts in by_race.items():
        if len(ts) >= 10:
            per_course[r[2]].append(cm.median(ts))
    norm = {c: cm.median(v) for c, v in per_course.items() if len(v) >= 3}
    bad = {r for r, ts in by_race.items()
           if r[2] in norm and abs(cm.median(ts) - norm[r[2]]) > OFF_NORM}
    return [o for o in obs if o.race not in bad]


def _drop_gender_conflicts(obs):
    """A runner who appears as both Boys and Girls in one season was put in
    the wrong gender somewhere (a mixed file read as one gender). Keep the
    gender most of their races agree on; drop the others."""
    g = defaultdict(lambda: defaultdict(int))
    for o in obs:
        g[(o.aid, o.year)][o.gender] += 1
    keep = {}
    for k, c in g.items():
        if len(c) > 1:
            top, n = max(c.items(), key=lambda kv: kv[1])
            if n > sum(c.values()) - n:
                keep[k] = top
            else:
                keep[k] = None      # no majority: trust neither
    return [o for o in obs if (o.aid, o.year) not in keep or keep[(o.aid, o.year)] == o.gender]


# ---------------------------------------------------------------------------
# Global calibration: course factors, fitness curve, race-day spread
# ---------------------------------------------------------------------------

def main_component(groups):
    """Races in the largest linked component of each (season, gender).

    Two races are linked when one runner ran both. A cluster of races that no
    runner connects to the rest of the season -- a middle-school circuit, a
    league that never meets anyone else -- has race effects pinned to nothing:
    any constant can be added to all of them and absorbed by their runners'
    abilities. Fitting course factors from such islands produces numbers like
    a 3K course rated as hard as the Festival 5K, so they are left out.
    """
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for rows in groups:
        rs = list({o.race for o in rows})
        for r in rs[1:]:
            parent[find(r)] = find(rs[0])
    size = defaultdict(int)
    for r in list(parent):
        size[find(r)] += 1
    best = {}
    for root, n in size.items():
        k = root[:2]                    # (season, gender)
        if k not in best or n > size[best[k]]:
            best[k] = root
    keep = set(best.values())
    return {r for r in parent if find(r) in keep}


def fit_race_effects(obs, iterations=15):
    """Alternating medians: theta per athlete-season, one effect per race.

    Only athlete-seasons with 2+ races carry information about race effects.
    Race effects are identified within a (season, gender) only up to a
    constant, which decompose() absorbs.
    """
    by_ay = defaultdict(list)
    for o in obs:
        by_ay[(o.aid, o.year)].append(o)
    multi = {k: v for k, v in by_ay.items() if len({o.race for o in v}) >= 2}
    main = main_component(multi.values())
    multi = {k: [o for o in v if o.race in main] for k, v in multi.items()}
    multi = {k: v for k, v in multi.items() if len({o.race for o in v}) >= 2}
    d = defaultdict(float)
    theta = {}
    n_link = {}
    for _ in range(iterations):
        for k, rows in multi.items():
            theta[k] = cm.median([o.lt - d[o.race] for o in rows])
        res = defaultdict(list)
        for k, rows in multi.items():
            for o in rows:
                res[o.race].append(o.lt - theta[k])
        for r, xs in res.items():
            d[r] = cm.median(xs)
        n_link = {r: len(xs) for r, xs in res.items()}
    return dict(d), n_link


def decompose(d, n_link, min_link=8, iterations=12):
    """Split race effects into level[season, gender] + course + u[race].

    There is deliberately no global fitness-curve term. Everyone in a race
    shares its date, so the field's average fitness on that day is already
    inside d[race]; an athlete's race reads as "relative to the field that
    day", and season-long improvement common to everyone cancels. (Measured
    directly from runners who raced one course twice in a season, the field
    gains ~3% from early September to the championships, but a curve fitted
    jointly with course factors is not identified: each course is raced at
    roughly the same point every year.)

    Weighted medians throughout, weight = linked runners capped at 60, so the
    Festival does not outvote every other race but a 6-runner dual meet does
    not move a course either.
    """
    races = [r for r in d if n_link.get(r, 0) >= min_link]
    w = {r: min(n_link[r], 60) for r in races}
    level = defaultdict(float)
    course = defaultdict(float)
    for _ in range(iterations):
        grp = defaultdict(list)
        for r in races:
            grp[(r[0], r[1])].append((d[r] - course[r[2]], w[r]))
        level = defaultdict(float, {k: wmedian(v) for k, v in grp.items()})
        grp = defaultdict(list)
        for r in races:
            grp[r[2]].append((d[r] - level[(r[0], r[1])], w[r]))
        course = defaultdict(float, {k: wmedian(v) for k, v in grp.items()})
    # anchor: Festival course at 0 so factors read like the course table
    ref_c = course.get(cm.REFERENCE_COURSE, 0.0)
    for c in course:
        course[c] -= ref_c
    for k in level:
        level[k] += ref_c
    u = {r: d[r] - level[(r[0], r[1])] - course[r[2]] for r in races}
    # Same check the course table applies: once length is divided out, no real
    # course is 25% harder or 20% easier than the Festival. A "3K" that comes
    # out as hard as a 5K is a middle-school course hanging off the state by a
    # single crossover runner; leave it unrated rather than trust it.
    course = {c: f for c, f in course.items()
              if cm.DIFF_RANGE[0] <= cm.difficulty_of(f, c[1]) <= cm.DIFF_RANGE[1]}
    return dict(level), course, u


class Calibration:
    """Everything learned from seasons other than the one being predicted:
    course factors, each athlete-season's full-season ability, and the
    typical year-over-year change used to carry last season forward."""

    def __init__(self, obs, exclude_year=None):
        train = [o for o in obs if o.year != exclude_year]
        d, n = fit_race_effects(train)
        self.level, self.course, self.u = decompose(d, n)
        # x - d is ability on the season's own gauge (fit_race_effects only
        # identifies race effects up to a per-season constant); adding the
        # season level back puts every season on the one Festival scale
        by_ay = defaultdict(list)
        for o in train:
            if o.race in d:
                by_ay[(o.aid, o.year)].append(
                    o.lt - d[o.race] + self.level.get((o.year, o.gender), 0.0))
        self.ability = {k: cm.median(v) for k, v in by_ay.items()}
        # what a typical field runs on each course, for sanity-checking races
        # that nothing else in their season can vouch for
        race_t = defaultdict(list)
        for o in train:
            race_t[o.race].append(o.lt)
        per_course = defaultdict(list)
        for r, ts in race_t.items():
            if len(ts) >= 10:
                per_course[r[2]].append(cm.median(ts))
        self.course_median = {c: cm.median(v) for c, v in per_course.items()
                              if len(v) >= 3}
        self.grade = {}
        self.meta = {}
        for o in sorted(train, key=lambda o: o.day if o.day is not None else -1):
            if o.grade:
                self.grade[(o.aid, o.year)] = o.grade
            self.meta[(o.aid, o.year)] = (o.gender, o.team, o.name)
        self._yoy(train)

    def _yoy(self, train):
        """Median change in ability from one season to the next, by gender and
        the grade the athlete was in the earlier season. Negative = faster."""
        gender = {o.aid: o.gender for o in train}
        diffs = defaultdict(list)
        for (aid, y), a in self.ability.items():
            b = self.ability.get((aid, y + 1))
            if b is None:
                continue
            g = self.grade.get((aid, y))
            diffs[(gender[aid], g)].append(b - a)
            if g is not None:
                diffs[(gender[aid], None)].append(b - a)
        self.yoy = {}
        self.yoy_sd = {}
        for k, v in diffs.items():
            if len(v) < 30:
                continue
            m = cm.median(v)
            self.yoy[k] = m
            self.yoy_sd[k] = 1.4826 * cm.median([abs(x - m) for x in v])

    def prior(self, aid, year, gender):
        """(mean, sd) for this season from last season, or None."""
        a = self.ability.get((aid, year - 1))
        if a is None:
            return None
        g = self.grade.get((aid, year - 1))
        key = (gender, g) if (gender, g) in self.yoy else (gender, None)
        if key not in self.yoy:
            return None
        return a + self.yoy[key], self.yoy_sd[key]


DEFAULTS = dict(
    tau=30.0,          # days; a race this old counts 1/e as much as today's
    race_sd=0.035,     # spread of one race around an athlete's level (log)
    shrink_k=6.0,      # linked runners at which a race effect is half-trusted
    slow_clip=2.5,     # races this many race_sd slower than the estimate
                       # (a fall, a sick day) are down-weighted
    use_prior=True,
    fill_returning=False,  # fill empty championship spots with last season's
                           # non-seniors who have no race on file yet
    method='model',    # 'model' | 'raw_best' | 'raw_last' | 'course_best' |
                       # 'course_mean' -- simpler systems kept for comparison
)


def season_ratings(obs, year, gender, cutoff, calib, params=None, iterations=10):
    """Ability of every athlete with data in `year` before season day `cutoff`.

    Returns aid -> dict(theta, sd, n, team, name, last). theta is a log time
    on the Festival-anchored scale; only differences between athletes in one
    race matter to the simulator.
    """
    P = dict(DEFAULTS, **(params or {}))
    rows = [o for o in obs if o.year == year and o.gender == gender
            and o.day is not None and o.day < cutoff]
    if P['method'] == 'ensemble':
        # average the ratings of several methods; a runner missing from a
        # component (no 5K for raw_last, say) averages the rest
        parts = [season_ratings(obs, year, gender, cutoff, calib,
                                dict(P, method=m))[0] for m in P.get('components', ('model', 'course_mean'))]
        out = {}
        for a, r in parts[0].items():
            ths = [p_[a]['theta'] for p_ in parts if a in p_]
            out[a] = dict(r, theta=sum(ths) / len(ths))
        return out, {}
    if P['method'] != 'model':
        return _simple_ratings(rows, calib, P), {}
    rows = _drop_unanchored(rows, calib, P, year, gender)
    by_a = defaultdict(list)
    for o in rows:
        by_a[o.aid].append(o)
    races = {o.race for o in rows}
    prior_r = {r: calib.course.get(r[2]) for r in races}
    u = {r: 0.0 for r in races}
    pri = {}
    if P['use_prior']:
        for a in by_a:
            p = calib.prior(a, year, gender)
            if p:
                pri[a] = p
    theta = {}

    def d_of(r):
        return (prior_r[r] or 0.0) + u[r]

    for _ in range(iterations):
        for a, rs in by_a.items():
            theta[a] = _combine(a, rs, d_of, cutoff, pri.get(a), P)[0]
        res = defaultdict(list)
        for a, rs in by_a.items():
            if len(rs) < 2 and a not in pri:
                continue            # a lone race says nothing about the race
            for o in rs:
                res[o.race].append(o.lt - theta[a] - (prior_r[o.race] or 0.0))
        for r in races:
            xs = res.get(r, [])
            if not xs:
                continue
            m = cm.median(xs)
            if prior_r[r] is None:
                u[r] = m                # unknown course: the data is all we have
            else:
                u[r] = m * len(xs) / (len(xs) + P['shrink_k'])
        # gauge: unknown courses float freely, so keep known-course races
        # centred on their historical factors
        known = [(u[r], len(res.get(r, []))) for r in races
                 if prior_r[r] is not None and res.get(r)]
        if known:
            shift = wmedian(known)
            for r in races:
                u[r] -= shift

    out = {}
    for a, rs in by_a.items():
        th, sd, n = _combine(a, rs, d_of, cutoff, pri.get(a), P)
        last = max(rs, key=lambda o: o.day)
        out[a] = dict(theta=th, sd=sd, n=n, team=last.team, name=last.name,
                      last=last.day, prior=a in pri, grade=last.grade)
    if P['fill_returning']:
        _add_returning(out, calib, year, gender)
    return out, {r: d_of(r) for r in races}


def _add_returning(out, calib, year, gender):
    """Last season's non-seniors with no race on file this season, rated from
    their carried-forward prior. n=0 marks them: they only fill a school's
    seven when it has fewer runners with races (see seven_for), and the
    simulator widens their noise to the year-over-year spread."""
    for (aid, y), (g, team, name) in calib.meta.items():
        if y != year - 1 or g != gender or aid in out:
            continue
        gr = calib.grade.get((aid, y))
        if gr is not None and gr >= 12:
            continue
        p = calib.prior(aid, year, gender)
        if not p:
            continue
        out[aid] = dict(theta=p[0], sd=p[1], n=0, team=team, name=name,
                        last=None, prior=True, grade=(gr + 1) if gr else None)


def seven_for(rated):
    """A school's championship entries from its (theta, aid, n) list: runners
    with races this season first, fastest first; returning runners with no
    race yet only fill what is left."""
    return [a for _, _, a in sorted((n == 0, th, a) for th, a, n in rated)[:MAX_ENTRY]]


def _simple_ratings(rows, calib, P):
    """Baselines a coach could compute by hand, for the comparison.

    raw_best / raw_last: season-best or most recent 5K time, courses ignored.
    course_best / course_mean: every race converted with the published-style
    course factor, then best or average -- course table, no race effects.
    """
    by_a = defaultdict(list)
    for o in rows:
        if P['method'].startswith('raw'):
            if o.course[1] == 5000:
                by_a[o.aid].append((o.day, o.lt, o))
        elif o.course in calib.course:
            by_a[o.aid].append((o.day, o.lt - calib.course[o.course], o))
    out = {}
    for a, rs in by_a.items():
        vals = [v for _, v, _ in rs]
        if P['method'] in ('raw_best', 'course_best'):
            th = min(vals)
        elif P['method'] == 'raw_last':
            th = max(rs, key=lambda t: t[0])[1]
        else:
            th = sum(vals) / len(vals)
        last = max(rs, key=lambda t: t[0])[2]
        out[a] = dict(theta=th, sd=P['race_sd'], n=len(rs), team=last.team,
                      name=last.name, last=last.day, prior=False,
                      grade=last.grade)
    return out


def _drop_unanchored(rows, calib, P, year, gender):
    """Keep only races that can be placed on the season's scale.

    A race is placed either by its course factor or by runners it shares with
    races already placed. Anchoring is transitive but must reach solid ground:
    a middle-school circuit whose runners only race each other is linked
    internally yet tied to nothing, and every rating inside it would float.

      - known course: admitted. If fewer than MIN_ANCHOR of its runners raced
        anywhere else (or carry last season's rating) it leans on the course
        factor alone, so its field must also run near that course's norm --
        the check that catches a junior-high 2-miler filed as a 5K.
      - unknown course: admitted once MIN_ANCHOR of its runners also ran an
        admitted race or carry last season's rating; repeated until stable.
    """
    races = defaultdict(list)
    per_a = defaultdict(set)
    for o in rows:
        races[o.race].append(o)
        per_a[o.aid].add(o.race)
    has_prior = {a for a in per_a
                 if P['use_prior'] and calib.prior(a, year, gender)}
    ok = set()
    for r, rs in races.items():
        if r[2] not in calib.course:
            continue
        anchors = sum(1 for o in rs if len(per_a[o.aid]) > 1 or o.aid in has_prior)
        norm = calib.course_median.get(r[2])
        if anchors >= MIN_ANCHOR or (
                norm is not None
                and abs(cm.median([o.lt for o in rs]) - norm) <= MAX_OFF_NORM):
            ok.add(r)
    grew = True
    while grew:
        grew = False
        for r, rs in races.items():
            if r in ok:
                continue
            anchors = sum(1 for o in rs if o.aid in has_prior
                          or any(q in ok for q in per_a[o.aid] if q != r))
            if anchors >= MIN_ANCHOR:
                ok.add(r)
                grew = True
    return [o for o in rows if o.race in ok]


MIN_ANCHOR = 3
MAX_OFF_NORM = 0.15


def _combine(aid, rs, d_of, cutoff, prior, P):
    """Precision-weighted blend of this season's races and last season's
    carried-forward rating, with recency weighting and slow-race clipping."""
    ests = [(o.lt - d_of(o.race), math.exp(-(cutoff - o.day) / P['tau'])) for o in rs]
    s2 = P['race_sd'] ** 2
    terms = [(e, w / s2) for e, w in ests]
    if prior:
        terms.append((prior[0], 1.0 / prior[1] ** 2))
    th = sum(e * w for e, w in terms) / sum(w for _, w in terms)
    # one bad day should not define a season: re-weight races that ran far
    # slower than everything else says this athlete is
    if P['slow_clip'] and len(terms) > 1:
        lim = P['slow_clip'] * P['race_sd']
        terms2 = [(e, w * (lim / (e - th) if e - th > lim else 1.0)) for e, w in terms]
        th = sum(e * w for e, w in terms2) / sum(w for _, w in terms2)
        terms = terms2
    prec = sum(w for _, w in terms)
    return th, math.sqrt(1.0 / prec), len(rs)


# ---------------------------------------------------------------------------
# Pseudo-championship backtest: predict every big late-season race
# ---------------------------------------------------------------------------

LATE_DAY = 40         # ~Sep 24 onward: the part of the season that looks
                      # like championship racing
MIN_FIELD = 25


def pseudo_backtest(obs, years=None, params=None, calibs=None, min_day=LATE_DAY):
    """For every large late-season race, rate its runners from the races
    before it and record how wrong the rating was.

    Errors are taken relative to the race's own median miss, so race-day
    conditions (and the course) drop out -- exactly as they do in a
    championship, where only the order matters.

    Returns a list of dicts: err, n (prior races this season), prior (had
    last season), sd (model's own uncertainty), plus race/athlete keys.
    """
    races = defaultdict(list)
    for o in obs:
        if o.day is not None and o.day >= min_day:
            races[o.race].append(o)
    years = sorted({r[0] for r in races} if years is None else years)
    calibs = calibs if calibs is not None else {}
    out = []
    for y in years:
        if y not in calibs:
            calibs[y] = Calibration(obs, exclude_year=y)
        cal = calibs[y]
        cache = {}
        for r, rows in sorted(races.items(), key=lambda kv: str(kv[0])):
            if r[0] != y or len(rows) < MIN_FIELD:
                continue
            key = (r[1], r[3])
            if key not in cache:
                cache[key] = season_ratings(obs, y, r[1], r[3], cal, params)[0]
            rat = cache[key]
            pred = [(o, rat[o.aid]) for o in rows if o.aid in rat]
            if len(pred) < 10:
                continue
            miss = cm.median([o.lt - p['theta'] for o, p in pred])
            for o, p in pred:
                out.append(dict(err=o.lt - p['theta'] - miss, n=p['n'],
                                prior=p['prior'], sd=p['sd'], race=r,
                                aid=o.aid, theta=p['theta'], lt=o.lt,
                                gap=None if p['last'] is None else r[3] - p['last']))
    return out


def robust_sd(xs):
    m = cm.median(xs)
    return 1.4826 * cm.median([abs(x - m) for x in xs])


def spearman_by_race(rows):
    """Mean within-race rank correlation of predicted vs actual order."""
    by = defaultdict(list)
    for r in rows:
        by[r['race']].append((r['theta'], r['lt']))
    vals = []
    for prs in by.values():
        n = len(prs)
        if n < 10:
            continue
        rp = {i: k for k, i in enumerate(sorted(range(n), key=lambda i: prs[i][0]))}
        ra = {i: k for k, i in enumerate(sorted(range(n), key=lambda i: prs[i][1]))}
        dsq = sum((rp[i] - ra[i]) ** 2 for i in range(n))
        vals.append(1 - 6 * dsq / (n * (n * n - 1)))
    return sum(vals) / len(vals), len(vals)


# ---------------------------------------------------------------------------
# Scoring and simulation
# ---------------------------------------------------------------------------

TEAM_MIN = 5          # finishers needed for a team score
SCORERS = 5
DISPLACERS = 2        # 6th and 7th runners push other teams back
MAX_ENTRY = 7


def score_race(order, team_of):
    """Standard XC scoring. `order` is athlete ids in finishing order.

    Runners from teams with fewer than five finishers run as individuals and
    are removed before places are counted; each team's first seven take
    places, the first five score, and ties go to the better sixth runner.
    Returns (ranked list of (team, score, places), {aid: team place or None}).
    """
    counts = defaultdict(int)
    for a in order:
        counts[team_of[a]] += 1
    scoring = {t for t, n in counts.items() if n >= TEAM_MIN}
    places = defaultdict(list)
    tplace = {}
    p = 0
    for a in order:
        t = team_of[a]
        if t in scoring and len(places[t]) < SCORERS + DISPLACERS:
            p += 1
            places[t].append(p)
            tplace[a] = p
        else:
            tplace[a] = None
    ranked = []
    for t, ps in places.items():
        sixth = ps[SCORERS] if len(ps) > SCORERS else 10 ** 6
        ranked.append((sum(ps[:SCORERS]), sixth, t, ps))
    ranked.sort()
    return [(t, s, ps) for s, _, t, ps in ranked], tplace


# Physically plausible range of a miss, in log time. Beating your rating by
# more than ~15% does not happen; a "miss" that large is a data error (wrong
# distance label, two races in one file, a mis-joined name), and drawing one
# in simulation lets a 34-minute runner win a state meet. The slow side is
# real -- falls, illness, a jog-in -- so it is allowed to run much further.
NOISE_RANGE = (math.log(0.85), math.log(1.5))


class NoiseModel:
    """Empirical prediction errors, bucketed by how much the rating knew.

    Drawn from directly rather than fitted to a normal curve: XC misses are
    heavy-tailed on the slow side (falls, illness, a bad day), and those
    tails are what turn a favourite into a third-place team. Misses outside
    NOISE_RANGE are data errors and are dropped.
    """

    def __init__(self, rows):
        rows = [r for r in rows if NOISE_RANGE[0] <= r['err'] <= NOISE_RANGE[1]]
        self.buckets = defaultdict(list)
        for r in rows:
            self.buckets[self.key(r['n'], r['prior'])].append(r['err'])
        self.pooled = [r['err'] for r in rows]
        self.sd = robust_sd(self.pooled)
        # bucket medians, computed once: shift() is called per simulated draw
        self._shift = {k: cm.median(v) for k, v in self.buckets.items() if len(v) >= 50}

    @staticmethod
    def key(n, prior):
        return (min(n, 3), bool(prior))

    def shift(self, n, prior):
        """Median miss for runners with this history: how far their typical
        race lands from their rating. Newcomers run a little faster than
        their few races say (they are still improving); returners rated
        partly from last season run a little slower. The simulator applies
        this through draw(); add it to a rating to get an expected time."""
        if not n:
            return 0.0
        return self._shift.get(self.key(n, prior), 0.0)

    def draw(self, n, prior, rng, sd=None):
        if n == 0:
            # no race this season: use the measured misses of runners rated
            # from last season alone when the backtest produced enough of
            # them; otherwise stretch the pooled shape to the year-over-year
            # spread
            b = self.buckets.get(self.key(0, True))
            if b and len(b) >= 50:
                return b[rng.randrange(len(b))]
            return self.pooled[rng.randrange(len(self.pooled))] * (sd or 2 * self.sd) / self.sd
        b = self.buckets.get(self.key(n, prior))
        if not b or len(b) < 50:
            b = self.pooled
        return b[rng.randrange(len(b))]


def pick_entries(ratings, teams, max_entry=MAX_ENTRY):
    """Each team's championship seven: its fastest rated runners.

    `teams` maps team -> set of store team names (a school can appear under
    several spellings). Returns aid -> team label.
    """
    by_team = defaultdict(list)
    for aid, r in ratings.items():
        for label, names in teams.items():
            if r['team'] in names:
                by_team[label].append((r['theta'], aid, r['n']))
                break
    out = {}
    for label, rs in by_team.items():
        for aid in seven_for(rs)[:max_entry]:
            out[aid] = label
    return out


def simulate(ratings, entries, noise, sims=2000, seed=0):
    """Monte Carlo one race. Returns per-team and per-athlete summaries."""
    rng = random.Random(seed)
    aids = list(entries)
    team_place = defaultdict(lambda: defaultdict(int))
    team_score = defaultdict(list)
    ind_place = defaultdict(list)
    for _ in range(sims):
        perf = [(ratings[a]['theta'] + noise.draw(ratings[a]['n'], ratings[a]['prior'], rng,
                                                   ratings[a]['sd']), a)
                for a in aids]
        perf.sort()
        order = [a for _, a in perf]
        ranked, _ = score_race(order, entries)
        for i, (t, s, _) in enumerate(ranked):
            team_place[t][i + 1] += 1
            team_score[t].append(s)
        for i, a in enumerate(order):
            ind_place[a].append(i + 1)
    teams = {}
    for t in set(entries.values()):
        dist = team_place.get(t, {})
        k = sum(dist.values())
        teams[t] = dict(
            win=dist.get(1, 0) / sims,
            exp_place=(sum(p * c for p, c in dist.items()) / k) if k else None,
            place_dist={p: c / sims for p, c in sorted(dist.items())},
            scored=k / sims,
            med_score=cm.median(team_score[t]) if team_score.get(t) else None)
    inds = {}
    for a, ps in ind_place.items():
        ps.sort()
        inds[a] = dict(med=ps[len(ps) // 2], p10=ps[len(ps) // 10],
                       p90=ps[(9 * len(ps)) // 10],
                       top=lambda k, ps=ps: sum(1 for p in ps if p <= k) / len(ps))
    return teams, inds


# ---------------------------------------------------------------------------
# Championship backtest: real regionals, states and conference meets
# ---------------------------------------------------------------------------

CHAMP_FILE = re.compile(
    r'class|north|south|state|pvc|kvac', re.I)
NOT_CHAMP = re.compile(r'jv|middle|[-_ ]ms[-_ .]|junior|college|2nd|second|'
                       r'jh|combined|\bne|^ne|york-county', re.I)


def championship_races(obs, min_day=50, min_rows=40):
    """(year, gender, meet) -> rows for every championship results file."""
    out = defaultdict(list)
    for o in obs:
        m = o.meet or ''
        if o.day is None or o.day < min_day:
            continue
        if CHAMP_FILE.search(m) and not NOT_CHAMP.search(m):
            out[(o.year, o.gender, m)].append(o)
    return {k: v for k, v in out.items() if len(v) >= min_rows}


PARSED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'parsed_results')


def scoring_groups(year, gender, meet):
    """Teams scored together in this results file, one set per official
    Team Scores block. A conference meet scored by division (PVC Large and
    Small, KVAC A and B) prints one block per division, and a podium only
    means something inside its division. Returns [] when the file has fewer
    than two blocks for this gender (score the race as one group)."""
    import json
    path = os.path.join(PARSED_DIR, str(year), 'XC', f'{meet}.json')
    try:
        with open(path, encoding='utf-8') as f:
            j = json.load(f)
    except (OSError, ValueError):
        return []
    blocks = [b for b in (j.get('team_rankings') or []) if isinstance(j, dict)
              and (b.get('gender') in (None, '', gender))]
    if len(blocks) < 2:
        return []
    groups = []
    for b in blocks:
        units = set()
        for t in b.get('teams', []):
            sid = school_catalog.resolve(t.get('team', ''), year=str(year), season='XC',
                                         gender=gender, meet_name=f'{meet}.json')
            if sid:
                units.add(school_catalog.team_unit(sid, str(year), 'XC', gender) or sid)
        if units:
            groups.append((b.get('division') or b.get('event_header') or '', units))
    return groups


def kind_of(meet):
    m = meet.lower()
    if 'pvc' in m:
        return 'PVC'
    if 'kvac' in m:
        return 'KVAC'
    if re.search(r'north|south|^nm|^sm', m):
        return 'Regional'
    if 'state' in m:
        return 'State'
    return 'Class'        # bare class-x files: regional or state by date


def champ_backtest(obs, noise, calibs, years=None, sims=1000, params=None,
                   as_of=None, rate_obs=None):
    """`as_of` maps season -> season day: rate everyone from data before that
    day instead of the race day, to test how much a thin season costs.
    `rate_obs` replaces the observations ratings are built from (results are
    always read from `obs`), to test a restricted data diet. `noise` may be a
    callable year -> NoiseModel so each season's noise excludes itself."""
    races = championship_races(obs)
    results = []
    for (y, g, meet), rows in sorted(races.items()):
        if years and y not in years:
            continue
        if y not in calibs:
            calibs[y] = Calibration(obs, exclude_year=y)
        day = rows[0].day
        cut = min(day, as_of[y]) if as_of and y in as_of else day
        ratings, _ = season_ratings(rate_obs if rate_obs is not None else obs,
                                    y, g, cut, calibs[y], params)
        teams_actual = {o.team for o in rows}
        groups = scoring_groups(y, g, meet) or [('', teams_actual)]
        for div, members in groups:
            div_rows = [o for o in rows if o.team in members] if div else rows
            res = _backtest_group(y, g, meet, day, div, div_rows, ratings, noise, sims)
            if res:
                results.append(res)
    return results


def _backtest_group(y, g, meet, day, div, rows, ratings, noise, sims):
    """Simulate one scoring group of a championship and compare to what
    happened. Runners' order is independent of who else is scored, so a
    division is simulated on its own entries."""
    teams_actual = {o.team for o in rows}
    entries = pick_entries(ratings, {t: {t} for t in teams_actual})
    if len(entries) < 20:
        return None
    nz = noise(y) if callable(noise) else noise
    sim_t, sim_i = simulate(ratings, entries, nz, sims=sims, seed=y)
    actual_order = [o.aid for o in sorted(rows, key=lambda o: o.lt)]
    ranked, _ = score_race(actual_order, {o.aid: o.team for o in rows})
    actual_place = {t: i + 1 for i, (t, _, _) in enumerate(ranked)}
    ran = {o.aid for o in rows}
    both = [o for o in rows if o.aid in ratings]
    ind_sp = None
    if len(both) >= 10:
        n = len(both)
        rp = {o.aid: i for i, o in enumerate(sorted(both, key=lambda o: ratings[o.aid]['theta']))}
        ra = {o.aid: i for i, o in enumerate(sorted(both, key=lambda o: o.lt))}
        ind_sp = 1 - 6 * sum((rp[a] - ra[a]) ** 2 for a in rp) / (n * (n * n - 1))
    # individual podium: our projected top three entrants (by median
    # simulated place) against the race's real top three. A real medallist
    # we failed to enter counts as a miss.
    ind_pod = None
    if len(sim_i) >= 10:
        pred3 = {a for a in sorted(sim_i, key=lambda a: (sim_i[a]['med'], ratings[a]['theta']))[:3]}
        ind_pod = len(pred3 & {o.aid for o in sorted(rows, key=lambda o: o.lt)[:3]})
    return dict(ind_spearman=ind_sp, ind_podium=ind_pod, division=div,
        year=y, gender=g, meet=meet, kind=kind_of(meet), day=day,
        n_runners=len(rows), n_teams=len(ranked),
        entry_hit=len(ran & set(entries)) / len(ran),
        rated=len([a for a in ran if a in ratings]) / len(ran),
        teams=[dict(team=t, actual=actual_place[t],
                    pred_place=sim_t.get(t, {}).get('exp_place'),
                    win=sim_t.get(t, {}).get('win', 0.0),
                    place_dist=sim_t.get(t, {}).get('place_dist', {}))
               for t in actual_place])


# ---------------------------------------------------------------------------
# A postseason: conference meet, regionals, states, in one simulated world
# ---------------------------------------------------------------------------

# How much of a runner's race-day result is "form" that carries from one
# postseason meet to the next, rather than fresh luck. Measured directly on
# 3,124 regional -> state pairs (2015-2025) rated from the same cutoff:
# Pearson 0.69. Chosen by leave-one-season-out cross-validation of the whole
# forecast (10 folds, 283 podiums, scored on top-3 inclusion and order):
# 0.95 beat 0.65 by +0.004 +/- 0.002 (better in 4 seasons, worse in 1) with
# unchanged calibration. A higher value also keeps each meet's draw closer to
# the empirical error shape instead of blending two draws.
FORM_CARRY = 0.95

GROUPS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'xc_groups.json')


def school_name(sid):
    e = school_catalog.info(sid) or {}
    return e.get('mpa') or e.get('name') or sid


def load_groups(year):
    """The season's meets (xc_groups.json) plus every team's class and region
    from the catalog's MPA classification. Teams are catalog unit ids: a
    school, or the co-op it races as. Conference members listed by name in
    xc_groups.json are resolved through the catalog too."""
    import json
    with open(GROUPS_PATH, encoding='utf-8') as f:
        g = json.load(f)[str(year)]
    key = f'xc_{year}'
    schools = {}
    cat = school_catalog._load()[0]
    entries = cat['schools']          # co-ops have entries here too
    for sid, e in entries.items():
        for c in (e.get('mpa_class') or {}).get(key, []):
            cls, region = c['class'].split()
            schools[sid] = dict(name=e.get('mpa') or e.get('name') or sid,
                                class_=cls, region=region)
    for sid in schools:
        schools[sid]['class'] = schools[sid].pop('class_')
    # A co-op the MPA list does not class (formed after the bulletin, or known
    # to the catalog from another sport but printed in XC results) races in
    # its members' class when they all share one. Lisbon/Oak Hill ran the 2026
    # Festival as one team though the 2026-27 bulletin lists both schools.
    for c in cat.get('coops', []):
        cid = c['id']
        if cid in schools:
            continue
        mem = [schools[m] for m in c.get('members', []) if m in schools]
        if mem and len({(m['class'], m['region']) for m in mem}) == 1:
            schools[cid] = {'name': c.get('label') or cid, 'class': mem[0]['class'],
                            'region': mem[0]['region'], 'inherited': True}
    for m in g['meets']:
        if 'schools' in m:
            ids = []
            for name in m['schools']:
                sid = school_catalog.resolve(name, year=str(year), season='XC')
                if sid is None:
                    raise ValueError(f'{m["id"]}: catalog cannot resolve {name!r}')
                # the school and whatever co-op it races as, for each gender
                ids += [sid] + [school_catalog.team_unit(sid, str(year), 'XC', gen) or sid
                                for gen in ('Boys', 'Girls')]
            m['schools'] = sorted(set(ids))
    g['schools'] = schools
    return g


def team_qualifiers(n_scoring):
    """MPA: half the region's teams go to states, rounded up, minimum four."""
    return min(n_scoring, max(4, math.ceil(n_scoring / 2)))


INDIVIDUAL_QUALIFIERS = 30


def simulate_postseason(obs, year, gender, cutoff, groups, calib, noise,
                        sims=2000, seed=0, params=None, form_carry=FORM_CARRY,
                        rate_obs=None, ratings=None):
    """Simulate every meet in `groups['meets']`, regionals feeding states.

    Returns (ratings, entries_by_meet, results_by_meet). Results hold, per
    team: place distribution and win probability (per division for meets
    scored by division), and for regionals the chance of reaching states;
    per athlete: place quantiles (within the division, for meets scored by
    division) and qualifying chance.
    """
    if ratings is None:
        ratings, _ = season_ratings(rate_obs if rate_obs is not None else obs,
                                    year, gender, cutoff, calib, params)
    by_school = defaultdict(list)
    for aid, r in ratings.items():
        if r['team'] in groups['schools']:
            by_school[r['team']].append((r['theta'], aid, r['n']))
    seven = {s: seven_for(v) for s, v in by_school.items()}
    school_of = {a: s for s, aids in seven.items() for a in aids}

    meets = {m['id']: m for m in groups['meets']}
    fields = {}
    for mid, m in meets.items():
        if 'from' in m:
            continue
        if 'schools' in m:
            members = [s for s in m['schools'] if s in groups['schools']]
        else:
            members = [s for s, i in groups['schools'].items()
                       if i['class'] == m['class'] and i['region'] == m['region']]
        fields[mid] = [a for s in members for a in seven.get(s, [])]

    rng = random.Random(seed)
    acc = defaultdict(lambda: dict(team_place=defaultdict(lambda: defaultdict(int)),
                                   team_scores=defaultdict(list),
                                   team_q=defaultdict(int), ind_place=defaultdict(list),
                                   ind_q=defaultdict(int), started=defaultdict(int),
                                   ind_div={}))
    a_carry = math.sqrt(form_carry)
    a_race = math.sqrt(1 - form_carry)

    def run(mid, aids, form):
        perf = sorted((ratings[a]['theta'] + a_carry * form[a] + a_race *
                       noise.draw(ratings[a]['n'], ratings[a]['prior'], rng,
                                  ratings[a]['sd']), a)
                      for a in aids)
        order = [a for _, a in perf]
        st = acc[mid]
        divs = meets[mid].get('divisions')
        # a meet scored by division places its runners within the division
        div_place = {}
        if divs:
            for dname, cls in divs.items():
                # a division is a class letter (PVC Large = MPA class B) or,
                # for past seasons, the explicit teams of an official block
                if isinstance(cls, (list, set, tuple)):
                    members = set(cls)
                    sub = [a for a in order if school_of[a] in members]
                else:
                    sub = [a for a in order
                           if groups['schools'].get(school_of[a], {}).get('class') == cls]
                for i, a in enumerate(sub):
                    div_place[a] = i + 1
                    st['ind_div'][a] = dname
                ranked, _ = score_race(sub, school_of)
                for i, (t, sc, _) in enumerate(ranked):
                    st['team_place'][(dname, t)][i + 1] += 1
                    st['team_scores'][(dname, t)].append(sc)
        for i, a in enumerate(order):
            st['ind_place'][a].append(div_place.get(a, i + 1))
            st['started'][a] += 1
        if divs:
            return order, None
        ranked, _ = score_race(order, school_of)
        for i, (t, sc, _) in enumerate(ranked):
            st['team_place'][t][i + 1] += 1
            st['team_scores'][t].append(sc)
        return order, ranked

    for _ in range(sims):
        form = {a: noise.draw(ratings[a]['n'], ratings[a]['prior'], rng, ratings[a]['sd'])
                for a in school_of}
        qual = defaultdict(set)
        for mid, aids in fields.items():
            order, ranked = run(mid, aids, form)
            m = meets[mid]
            if 'region' not in m or ranked is None:
                continue
            q_teams = {t for t, _, _ in ranked[:team_qualifiers(len(ranked))]}
            q = {a for a in order if school_of[a] in q_teams}
            q |= set(order[:INDIVIDUAL_QUALIFIERS])
            for t in q_teams:
                acc[mid]['team_q'][t] += 1
            for a in q:
                acc[mid]['ind_q'][a] += 1
            qual[m['class']] |= q
        for mid, m in meets.items():
            if 'from' in m:
                run(mid, sorted(qual[m['class']]), form)

    results = {}
    for mid, st in acc.items():
        teams = {}
        # how many teams a division (or meet) ever scores, for the
        # unconditional expected place below
        n_scored = defaultdict(int)
        for t in st['team_place']:
            n_scored[t[0] if isinstance(t, tuple) else None] += 1
        for t, dist in st['team_place'].items():
            k = sum(dist.values())
            scores = st['team_scores'][t]
            last = n_scored[t[0] if isinstance(t, tuple) else None] + 1
            teams[t] = dict(win=dist.get(1, 0) / sims, appear=k / sims,
                            exp_place=sum(p * c for p, c in dist.items()) / k,
                            # a state team that rarely qualifies is not a
                            # contender: count missing the meet as last place
                            exp_place_all=(sum(p * c for p, c in dist.items())
                                           + (sims - k) * last) / sims,
                            place_dist={p: c / sims for p, c in sorted(dist.items())},
                            med_score=cm.median(scores),
                            qualify=st['team_q'].get(t, 0) / sims if 'region' in meets[mid] else None)
        inds = {}
        for a, ps in st['ind_place'].items():
            ps.sort()
            k = len(ps)
            inds[a] = dict(div=st['ind_div'].get(a), start=k / sims, med=ps[k // 2], p10=ps[k // 10], p90=ps[(9 * k) // 10],
                           top10=sum(p <= 10 for p in ps) / sims,
                           top25=sum(p <= 25 for p in ps) / sims,
                           qualify=st['ind_q'].get(a, 0) / sims if 'region' in meets[mid] else None)
        results[mid] = dict(teams=teams, athletes=inds)
    entries = {mid: aids for mid, aids in fields.items()}
    return ratings, school_of, entries, results


# ---------------------------------------------------------------------------
# Learned correction (gradient boosting) and rating ensembles
# ---------------------------------------------------------------------------

FEATURES = ['th_model', 'th_course', 'th_last', 'th_best', 'n', 'has_prior',
            'prior_gap', 'grade', 'girls', 'days_since', 'trend', 'spread',
            'big_field_gap', 'team_rank']


def athlete_features(obs, year, gender, cutoff, calib, rated=None):
    """aid -> feature dict, from races before `cutoff` only.

    Every rating is relative to the current model (th_model), so a learned
    model predicts a correction to it rather than a time from scratch.
    """
    base, d = rated if rated else season_ratings(obs, year, gender, cutoff, calib)
    course, _ = season_ratings(obs, year, gender, cutoff, calib, {'method': 'course_mean'})
    last, _ = season_ratings(obs, year, gender, cutoff, calib, {'method': 'raw_last'})
    best, _ = season_ratings(obs, year, gender, cutoff, calib, {'method': 'course_best'})
    rows = defaultdict(list)
    size = defaultdict(int)
    for o in obs:
        if o.year == year and o.gender == gender and o.day is not None and o.day < cutoff:
            rows[o.aid].append(o)
            size[o.race] += 1
    team_th = defaultdict(list)
    for a, r in base.items():
        team_th[r['team']].append((r['theta'], a))
    team_rank = {a: i for v in team_th.values() for i, (_, a) in enumerate(sorted(v))}
    out = {}
    for a, r in base.items():
        th = r['theta']
        rs = [o for o in rows.get(a, []) if o.race in d]
        est = [(o.day, o.lt - d[o.race], size[o.race]) for o in rs]
        if len(est) >= 2:
            md = sum(x for x, _, _ in est) / len(est)
            me = sum(e for _, e, _ in est) / len(est)
            var = sum((x - md) ** 2 for x, _, _ in est)
            trend = sum((x - md) * (e - me) for x, e, _ in est) / var if var else 0.0
            spread = (sum((e - me) ** 2 for _, e, _ in est) / (len(est) - 1)) ** 0.5
        else:
            trend, spread = 0.0, 0.0
        big = [e for _, e, s in est if s >= 300]
        small = [e for _, e, s in est if s < 300]
        p = calib.prior(a, year, gender)
        out[a] = dict(
            th_model=0.0,
            th_course=(course[a]['theta'] - th) if a in course else 0.0,
            th_last=(last[a]['theta'] - th) if a in last else 0.0,
            th_best=(best[a]['theta'] - th) if a in best else 0.0,
            n=r['n'], has_prior=1.0 if p else 0.0,
            prior_gap=(p[0] - th) if p else 0.0,
            grade=r.get('grade') or 0, girls=1.0 if gender == 'Girls' else 0.0,
            days_since=(cutoff - r['last']) if r.get('last') is not None else 99,
            trend=trend, spread=spread,
            big_field_gap=(sum(big) / len(big) - sum(small) / len(small)) if big and small else 0.0,
            team_rank=team_rank.get(a, 9))
    return out


class LearnedCorrection:
    """Gradient-boosted correction to the model's rating.

    Trained on (features at a cutoff -> how far the runner's next late-season
    race landed from their rating, relative to that race's median miss).
    Absolute-error loss so a fall or a jog-in does not drag the fit.
    """

    def __init__(self, rows, seed=0):
        from sklearn.ensemble import HistGradientBoostingRegressor
        import numpy as np
        X = np.array([[r['f'][k] for k in FEATURES] for r in rows], dtype=float)
        y = np.array([r['err'] for r in rows], dtype=float)
        self.m = HistGradientBoostingRegressor(
            loss='absolute_error', max_depth=3, learning_rate=0.05,
            max_iter=300, l2_regularization=1.0, min_samples_leaf=200,
            random_state=seed)
        self.m.fit(X, y)

    def correct(self, ratings, feats):
        import numpy as np
        aids = [a for a in ratings if a in feats]
        if not aids:
            return ratings
        X = np.array([[feats[a][k] for k in FEATURES] for a in aids], dtype=float)
        pred = self.m.predict(X)
        out = dict(ratings)
        for a, dp in zip(aids, pred):
            out[a] = dict(ratings[a], theta=ratings[a]['theta'] + float(dp))
        return out


def feature_backtest(obs, years, calibs, min_day=LATE_DAY):
    """Like pseudo_backtest, but each prediction carries its feature row:
    the training set for LearnedCorrection."""
    races = defaultdict(list)
    for o in obs:
        if o.day is not None and o.day >= min_day:
            races[o.race].append(o)
    out = []
    for y in years:
        cal = calibs[y]
        cache = {}
        for r, rows in sorted(races.items(), key=lambda kv: str(kv[0])):
            if r[0] != y or len(rows) < MIN_FIELD:
                continue
            key = (r[1], r[3])
            if key not in cache:
                rated = season_ratings(obs, y, r[1], r[3], cal)
                cache[key] = (rated[0], athlete_features(obs, y, r[1], r[3], cal, rated))
            rat, feats = cache[key]
            pred = [(o, rat[o.aid]) for o in rows if o.aid in rat and o.aid in feats]
            if len(pred) < 10:
                continue
            miss = cm.median([o.lt - p['theta'] for o, p in pred])
            for o, p in pred:
                out.append(dict(err=o.lt - p['theta'] - miss, n=p['n'], prior=p['prior'],
                                sd=p['sd'], race=r, aid=o.aid, f=feats[o.aid]))
    return out
