"""Entry optimizer: what a team's championship entries should be.

The entry model (track_postseason) predicts what coaches will enter; this
decides what one team (the focal team) should enter - individual events and
relay lineups - under the meet's rules, against the other teams' entries:
known (an entry list, or what they actually entered), or, for a meet not yet
entered, drawn in every simulated meet from the entry model the way the
postseason predictor draws them (`suggest` below). Marks come from the predictor's held-out model with three measured
adjustments (2026-11-12, eve of every championship 2006-2026):

  fatigue  - a race costs ~1.3% per 1000 m the athlete has already run that
             day (1.2-1.6% in every event group) and more right after another
             race: 1.3% for sprints and hurdles, 4.9% for 800-3200;
             the number of events alone costs nothing (field events none).
             Same athlete, event and season, state meet vs conference meet.
             The model's marks carry the average load, so a row moves by
             its load's cost minus the average for that event.
  unusual  - entries the entry model gives a low chance run worse than the
             model's mark (0.3% running, 0.6% field below a 10% chance).
  lineup   - a relay moves by SLOPE x the change in its legs' mean
             leg-event mark against the expected lineup's (see LINEUP_SLOPE).

Live mode backtest (2026-11-13; contenders - each meet's top four - 2006-2026,
relays free, judged against rivals as they entered on fresh simulated meets):
entries chosen against drawn rivals gain +6.7 expected points at conference
meets and +3.5 at states over the coaches' entries (2012+), 95% of what knowing
the rivals' entries gains (+7.0 / +3.6); win chance +4.9 / +4.0 points, close
meets (20-80%) 0.46 -> 0.58. The gain the tool claims matches the one found
(+6.9 claimed / +6.7 found conference, +3.7 / +3.5 state). The entry model's
likeliest entries on their own score 0.8-2.8 points below the coaches'.

Rules: an athlete enters at most MAX_EVENTS events, relay legs included;
per team per event no more entrants than any team had at that meet; only
events the athlete has raced this season; at state meets only events where
their season best clears the meet's line (the 95th percentile of that
year's entrants' season bests).
"""
import collections

import numpy as np

import track_postseason as tp

KM_COST = 0.0133
B2B_COST = 0.013            # sprints and hurdles (1.3 +/- 0.4%)
B2B_DISTANCE = 0.049        # 800 / 1600 / 3200 right after a race (4.9 +/- 1.0%: the 400 into the 800)
DIST = {'4x100 Meter Relay': 100, '4x200 Meter Relay': 200, '4x400 Meter Relay': 400, '4x800 Meter Relay': 800,
        '55 Meter Dash': 55, '100 Meter Dash': 100, '200 Meter Dash': 200, '400 Meter Dash': 400,
        '800 Meter Run': 800, '1 Mile Run': 1609, '1600 Meter Run': 1600, '2 Mile Run': 3219,
        '3200 Meter Run': 3200, '55 Meter Hurdles': 55, '100 Meter Hurdles': 100, '110 Meter Hurdles': 110,
        '300 Meter Hurdles': 300, '1600 Meter Race Walk': 1600}
PENT_EDGES = np.array([0.1, 0.25, 0.5, 0.75, 0.9])
PENT_RUN = np.array([0.0032, 0.0013, 0.0012, 0.0001, -0.0005, -0.0007])
PENT_FIELD = np.array([0.0060, 0.0052, 0.0045, 0.0019, 0.0004, -0.0026])
# Across the lineups coaches chose, a relay's residual moves only 0.03-0.48 x
# its legs' mean gap to the expected lineup (4x400 0.03, 4x100 0.11, 4x800 0.31,
# indoor 4x200 0.29 / 4x800 0.48): coaches swap legs when they know something
# the marks don't. A forced swap costs what the legs' times add up to: slope 1,
# shrunk for noise in the legs' marks.
LINEUP_SLOPE = 0.8
MEASURED_SLOPE = {'4x200 Meter Relay': 0.29, '4x800 Meter Relay': 0.4, '4x100 Meter Relay': 0.11,
                  '4x400 Meter Relay': 0.03}
# a runner with no leg-event mark (relay-only): the likely legs' mean (leg chances
# as weights) plus 1%. Relays run with one or two such legs came in 0.05% / 0.33%
# slower than the model, so they are about average for the relay, not its slowest;
# guessing 'slowest + 3%' made benching them look like 1.35 of the 1.68 points per
# team the optimizer found in leg swaps.
UNKNOWN_LEG = 0.01
REGULAR_LEG = 0.2         # leg chance that makes a runner with no leg-event mark a relay choice


def pent_adj(pent, events):
    b = np.searchsorted(PENT_EDGES, np.nan_to_num(pent, nan=0.0), side='right')
    fld = np.array([tp.is_field(e) for e in events])
    return np.where(fld, PENT_FIELD[b], PENT_RUN[b])


def load_cost(events, order):
    """{event: fatigue cost (log units)} for one athlete's events at a meet."""
    out = {}
    for e in events:
        pos = order.get(e)
        if pos is None or tp.is_field(e):
            out[e] = 0.0
            continue
        before = [x for x in events if x != e and not tp.is_field(x) and order.get(x, 1e9) < pos]
        km = sum(DIST.get(x, 0) for x in before) / 1000
        b2b = any(pos - order[x] == 1 for x in before)
        out[e] = KM_COST * km + (B2B_DISTANCE if tp.FAMILY.get(e) in tp.DISTANCE_FAMILIES else B2B_COST) * b2b
    return out


def truth_entries(truth):
    """(individual {aid: set(events)}, relays {(unit, event): legs tuple or ()})."""
    ind = collections.defaultdict(set)
    rel = {}
    for ev, rs in truth['events'].items():
        for r in rs:
            if tp.is_relay_event(ev):
                if r['unit'] and (r['unit'], ev) not in rel:
                    rel[(r['unit'], ev)] = tuple(a for a in (r.get('legs') or ()) if a)
            elif r['aid']:
                ind[r['aid']].add(ev)
    return ind, rel


def mean_load(truths, champs_order):
    """Average fatigue cost of entered rows by event (individual entries and
    relay legs): the load the model's marks already carry."""
    tot, n = collections.Counter(), collections.Counter()
    for cid, t in truths.items():
        ind, rel = truth_entries(t)
        if not any(rel.values()):
            continue
        order = champs_order(cid)
        ev_of = collections.defaultdict(set)
        for a, evs in ind.items():
            ev_of[a] |= evs
        for (u, ev), legs in rel.items():
            for a in legs:
                ev_of[a].add(ev)
        for a, evs in ev_of.items():
            for e, c in load_cost(evs, order).items():
                tot[e] += c
                n[e] += 1
    return {e: tot[e] / n[e] for e in n}


class Meet:
    """One championship: every candidate row (all teams), leg candidates,
    the points table, residual draws shared by every entry set tried."""

    def __init__(self, champ_id, rows, legs, truth, z_ath, z_rel, sims=500, seed=0, avg_load=None, slope=None,
                 events=None, table=None, limit=None, line=None):
        """truth: the meet's results (a backtest), or None for a meet not yet
        run - then events and table are given, and limit ({event: entrants
        per team}) and line ({event: state meet line}) from its last edition."""
        self.id = champ_id
        self.seed = seed
        self.slope = slope if slope is not None else LINEUP_SLOPE   # a number, or {relay event: slope}
        self.season = 'Indoor' if '-Indoor-' in champ_id else 'Outdoor'
        self.state = '-state-' in champ_id
        self.cap = tp.MAX_EVENTS[self.season]
        self.order = tp.event_order(champ_id)
        self.table = np.array(truth['table'] if table is None else table, float)
        self.events = sorted(truth['events'] if events is None else events)
        self.sims = sims
        self.avg_load = avg_load or {}
        rows = rows[rows.event.isin(self.events)].reset_index(drop=True)
        rows['aid'] = rows.aid.astype(str)
        self.rows = rows
        self.ix = {(a, e): i for i, (a, e) in enumerate(zip(rows.aid.values, rows.event.values))}
        self.teams = sorted({t for t in rows.team.values if t})
        self.tix = {t: i for i, t in enumerate(self.teams)}
        rng = np.random.default_rng(seed)
        n = len(rows)
        rel = rows.relay.values.astype(bool)
        Z = np.where(rel[None, :], rng.choice(z_rel, size=(sims, n)), rng.choice(z_ath, size=(sims, n)))
        self.base = rows['mean'].values + np.where(rel, 0.0, pent_adj(rows.pent.values, rows.event.values))
        self.noise = rows.scale.values[None, :] * Z
        self.truth = truth
        self.ind_true, self.rel_true = truth_entries(truth) if truth else ({}, {})
        self._drawn = None
        legs = legs.copy()
        legs['aid'] = legs.aid.astype(str)
        self.legs = legs
        # per (team, relay event): leg candidates with their gap to the team's 4th best,
        # and the expected lineup's mean gap (leg chances as weights): the relay's mark is that lineup's
        # leg_pool: runners the optimizer may put on a relay - a leg-event mark, or
        # no mark but likely on it already (a regular); a runner with neither (a
        # thrower, a jumper who never runs relays) is not a choice
        self.leg_gap, self.expected, self.leg_pool = {}, {}, {}
        for (t, e), g in legs.groupby(['team', 'event']):
            gaps = g.leg_gap.values
            w = np.nan_to_num(g.pleg.values.astype(float))
            ok = np.isfinite(gaps)
            likely = float((w[ok] * gaps[ok]).sum() / w[ok].sum()) if ok.any() and w[ok].sum() > 0 else 0.0
            filled = np.where(ok, gaps, likely + UNKNOWN_LEG)
            self.leg_gap[(t, e)] = dict(zip(g.aid.values, filled))
            self.leg_pool[(t, e)] = {a: v for a, v, k, p in zip(g.aid.values, filled, ok, w) if k or p >= REGULAR_LEG}
            self.expected[(t, e)] = float((w * filled).sum() / w.sum()) if w.sum() > 0 else np.nan
        if truth is None:
            self.limit = collections.defaultdict(lambda: 1, limit or {})
            self.line = dict(line or {}) if self.state else {}
            return
        # the meet's limits
        per = collections.Counter()
        for a, evs in self.ind_true.items():
            i0 = next((self.ix[(a, e)] for e in evs if (a, e) in self.ix), None)
            t = rows.team.values[i0] if i0 is not None else None
            for e in evs:
                per[(t, e)] += 1
        self.limit = collections.defaultdict(lambda: 1)
        for (t, e), k in per.items():
            if t:
                self.limit[e] = max(self.limit[e], k)
        self.line = {}
        if self.state:
            for e in self.events:
                sbs = [rows.sb.values[self.ix[(a, e)]] for a, evs in self.ind_true.items()
                       if e in evs and (a, e) in self.ix]
                sbs = [v for v in sbs if v == v]
                if sbs:
                    self.line[e] = float(np.quantile(sbs, 0.95))

    def drawn(self):
        """sims x rows: entered or not in each simulated meet, drawn from the
        entry model with the event limit applied (tp.simulate's draws)."""
        if self._drawn is None:
            r, lg = self.rows, self.legs
            lg = lg if 'pleg' in lg and len(lg) else None
            q, ql = tp._calibrate(r, self.cap, lg, self.seed) if lg is not None else (r.pent.values, None)
            ent = np.random.default_rng(self.seed + 101).random((self.sims, len(r))) < q[None, :]
            tp._cap_entries(r, ent, self.cap, lg, np.random.default_rng(self.seed + 102), ql)
            self._drawn = ent
        return self._drawn

    # -- what an athlete may enter -----------------------------------------
    def eligible(self, aid, ev):
        i = self.ix.get((aid, ev))
        if i is None or tp.is_relay_event(ev):
            return False
        if ev in self.ind_true.get(aid, ()):
            return True
        r = self.rows
        if not (r.cur_same_n.values[i] >= 1):
            return False
        if self.state:
            sb, line = r.sb.values[i], self.line.get(ev)
            return line is not None and sb == sb and sb <= line
        return True

    def relay_shift(self, team, ev, lineup, loads):
        """Relay mark change for a lineup: SLOPE x (legs' mean gap - best four's),
        plus a quarter of each leg's fatigue beyond the average."""
        gaps = self.leg_gap.get((team, ev), {})
        exp = self.expected.get((team, ev), np.nan)
        s = 0.0
        if len(lineup) >= 4 and np.isfinite(exp) and all(a in gaps for a in lineup):
            k = self.slope.get(ev, 0.4) if isinstance(self.slope, dict) else self.slope
            s += k * (np.mean([gaps[a] for a in lineup]) - exp)
        if lineup:
            # a leg 1% slower is a quarter of the relay: the mean over the legs
            s += np.mean([loads.get(a, {}).get(ev, 0.0) for a in lineup]) - self.avg_load.get(ev, 0.0)
        return s


class Plan:
    """A team's entries: individual {aid: set(events)} and relays {event: lineup tuple}."""

    def __init__(self, ind=None, rel=None):
        self.ind = {a: set(e) for a, e in (ind or {}).items() if e}
        self.rel = dict(rel or {})

    def copy(self):
        return Plan(self.ind, self.rel)

    def events_of(self, aid):
        out = set(self.ind.get(aid, ()))
        out |= {e for e, lu in self.rel.items() if aid in lu}
        return out

    def load(self, aid):
        return len(self.events_of(aid))

    def athletes(self):
        return set(self.ind) | {a for lu in self.rel.values() for a in lu}

    def key(self):
        return (tuple(sorted((a, tuple(sorted(e))) for a, e in self.ind.items() if e)),
                tuple(sorted(self.rel.items())))


class Field:
    """Everyone's marks for each event, the focal team's from its plan."""

    def __init__(self, meet, focal, opp_entries=None):
        """opp_entries: (ind, rel) for the other teams (default: what they
        actually entered); a relay's lineup may be () when unknown. 'drawn':
        drawn from the entry model in each simulated meet."""
        self.m = meet
        self.focal = focal
        self.fi = meet.tix[focal]
        self.cache = {}
        if isinstance(opp_entries, str) and opp_entries == 'drawn':
            ent = meet.drawn()
            team = meet.rows.team.values
            self.opp = {}
            for e, idx in meet.rows.groupby('event').indices.items():
                idx = idx[team[idx] != focal]
                marks = np.where(ent[:, idx], meet.base[idx][None, :] + meet.noise[:, idx], np.inf)
                self.opp[e] = (marks, np.array([meet.tix.get(team[i], -1) for i in idx], int))
            for e in meet.events:
                self.opp.setdefault(e, (np.zeros((meet.sims, 0)), np.zeros(0, int)))
            return
        ind, rel = opp_entries or (meet.ind_true, meet.rel_true)
        rows = meet.rows
        team = rows.team.values
        # opponents' entrants and marks, fixed
        loads = {}
        ev_of = collections.defaultdict(set)
        for a, evs in ind.items():
            ev_of[a] |= evs
        for (u, e), lu in rel.items():
            for a in lu:
                ev_of[a].add(e)
        for a, evs in ev_of.items():
            loads[a] = load_cost(evs, meet.order)
        self.opp = {}
        for e in meet.events:
            idx, shift = [], []
            if tp.is_relay_event(e):
                for (u, ev), lu in rel.items():
                    i = meet.ix.get((str(('relay', u)), ev))
                    if ev == e and i is not None and u != focal:
                        idx.append(i)
                        shift.append(meet.relay_shift(u, e, lu, loads))
            else:
                for a, evs in ind.items():
                    i = meet.ix.get((a, e))
                    if e in evs and i is not None and team[i] != focal:
                        idx.append(i)
                        shift.append(loads.get(a, {}).get(e, 0.0) - meet.avg_load.get(e, 0.0))
            idx = np.array(idx, int)
            marks = meet.base[idx][None, :] + np.array(shift)[None, :] + meet.noise[:, idx] if len(idx) \
                else np.zeros((meet.sims, 0))
            self.opp[e] = (marks, np.array([meet.tix.get(team[i], -1) for i in idx], int))

    def focal_marks(self, plan, e):
        m = self.m
        if tp.is_relay_event(e):
            lu = plan.rel.get(e)
            i = m.ix.get((str(('relay', self.focal)), e))
            if not lu or i is None:
                return np.zeros((m.sims, 0))
            loads = {a: load_cost(plan.events_of(a), m.order) for a in lu}
            return (m.base[i] + m.relay_shift(self.focal, e, lu, loads) + m.noise[:, i])[:, None]
        cols = []
        for a, evs in plan.ind.items():
            if e in evs:
                i = m.ix[(a, e)]
                c = load_cost(plan.events_of(a), m.order)[e] - m.avg_load.get(e, 0.0)
                cols.append(m.base[i] + c + m.noise[:, i])
        return np.stack(cols, 1) if cols else np.zeros((m.sims, 0))

    def event_points(self, plan, e, sig):
        """sims x teams points in event e; cached by the focal entrants' signature."""
        k = (e, sig)
        if k in self.cache:
            return self.cache[k]
        om, ot = self.opp[e]
        fm = self.focal_marks(plan, e)
        marks = np.concatenate([om, fm], 1)
        tid = np.concatenate([ot, np.full(fm.shape[1], self.fi)])
        sims, n = marks.shape
        pts = np.zeros((sims, len(self.m.teams) + 1))
        L = min(len(self.m.table), n)
        if L:
            order = np.argsort(marks, axis=1)[:, :L]
            ar = np.arange(sims)
            for p in range(L):
                col = order[:, p]
                ok = np.isfinite(marks[ar, col])                      # inf: not entered in that sim
                np.add.at(pts, (ar[ok], tid[col[ok]]), self.m.table[p])     # -1 (no team) lands in the last column
        pts = pts[:, :-1]
        if len(self.cache) > 20000:
            self.cache.clear()
        self.cache[k] = pts
        return pts

    def sig(self, plan, e):
        """What the focal team's points in e depend on: its entrants there and their loads."""
        if tp.is_relay_event(e):
            lu = plan.rel.get(e)
            return ('R', tuple(sorted((a, tuple(sorted(plan.events_of(a)))) for a in lu)) if lu else ())
        return tuple(sorted((a, tuple(sorted(plan.events_of(a)))) for a, evs in plan.ind.items() if e in evs))

    def total(self, plan):
        return sum(self.event_points(plan, e, self.sig(plan, e)) for e in self.m.events)


def objective(pts, fi, kind='points'):
    if kind == 'points':
        return float(pts[:, fi].mean())
    noise = np.random.default_rng(3).random(pts.shape) * 1e-6
    rank = (-(pts + noise)).argsort(1).argsort(1)[:, fi]
    if kind == 'win':
        return float((rank == 0).mean()) + 1e-4 * float(pts[:, fi].mean())
    if kind == 'top3':
        return float((rank < 3).mean()) + 1e-4 * float(pts[:, fi].mean())
    raise ValueError(kind)


class Optimizer:
    """Best-improvement local search over a team's entries."""

    def __init__(self, field, kind='points', eps=0.02, available=None, fix_relays=False, force=(), forbid=()):
        """available: athletes who may be entered (default: anyone with a row);
        fix_relays: keep the starting plan's relays and lineups as they are;
        force / forbid: (athlete, event) pairs that must / must not be in the
        plan (a relay event: on its lineup)."""
        self.force, self.forbid = set(force), set(forbid)
        self.f = field
        self.m = field.m
        self.kind = kind
        self.eps = eps if kind == 'points' else 0.002
        m = self.m
        team = m.rows.team.values
        ok = (lambda a: True) if available is None else (lambda a: a in available)
        self.ath = sorted({a for a, t, r in zip(m.rows.aid.values, team, m.rows.relay.values)
                           if t == field.focal and not r and ok(a)})
        self.elig = {a: [e for e in m.events if m.eligible(a, e)] for a in self.ath}
        self.relays = [] if fix_relays else \
            [e for e in m.events if tp.is_relay_event(e) and (str(('relay', field.focal)), e) in m.ix]
        self.pool = {e: {a: g for a, g in m.leg_pool.get((field.focal, e), {}).items() if ok(a)} for e in self.relays}
        self.n_eval = 0

    def score(self, plan):
        self.n_eval += 1
        return objective(self.f.total(plan), self.f.fi, self.kind)

    def feasible(self, plan):
        m = self.m
        cnt = collections.Counter(e for evs in plan.ind.values() for e in evs)
        if any(k > m.limit[e] for e, k in cnt.items()):
            return False
        if any(e in plan.events_of(a) for a, e in self.forbid) or \
                any(e not in plan.events_of(a) for a, e in self.force):
            return False
        return all(plan.load(a) <= m.cap for a in plan.athletes())

    def best_lineup(self, plan, e, exclude=()):
        """Fastest four by leg gap among runners with room."""
        cands = sorted((g, a) for a, g in self.pool[e].items()
                       if a not in exclude and (a, e) not in self.forbid and plan.load(a) < self.m.cap)
        return tuple(a for _, a in cands[:4]) if len(cands) >= 4 else None

    def moves(self, plan):
        m = self.m
        cnt = collections.Counter(e for evs in plan.ind.values() for e in evs)
        for a in self.ath:
            mine = plan.ind.get(a, set())
            room = plan.load(a) < m.cap
            for e in self.elig[a]:
                if e in mine:
                    p = plan.copy(); p.ind[a].discard(e); yield ('drop', a, e), p
                    for e2 in self.elig[a]:
                        if e2 not in mine and cnt[e2] < m.limit[e2]:
                            p = plan.copy(); p.ind[a].discard(e); p.ind[a].add(e2); yield ('swap', a, e, e2), p
                elif room and cnt[e] < m.limit[e]:
                    p = plan.copy(); p.ind.setdefault(a, set()).add(e); yield ('add', a, e), p
        for e in self.relays:
            lu = plan.rel.get(e)
            if lu:
                p = plan.copy(); p.rel.pop(e); yield ('drop relay', e), p
                for k, out in enumerate(lu):
                    for a in self.pool[e]:
                        if a in lu:
                            continue
                        if plan.load(a) < m.cap:
                            p = plan.copy(); p.rel[e] = lu[:k] + (a,) + lu[k + 1:]; yield ('leg', e, out, a), p
                        # a runner at the cap gives up one individual event for the leg
                        elif plan.load(a) == m.cap:
                            for e2 in plan.ind.get(a, ()):
                                p = plan.copy(); p.ind[a].discard(e2); p.rel[e] = lu[:k] + (a,) + lu[k + 1:]
                                yield ('event->leg', e, out, a, e2), p
                    # the runner leaving takes an individual event instead
                    for e2 in self.elig.get(out, ()):
                        if e2 in plan.ind.get(out, ()) or cnt[e2] >= m.limit[e2]:
                            continue
                        sub = [a for a in sorted(self.pool[e], key=self.pool[e].get)
                               if a not in lu and plan.load(a) < m.cap]
                        if sub:
                            p = plan.copy(); p.rel[e] = lu[:k] + (sub[0],) + lu[k + 1:]
                            p.ind.setdefault(out, set()).add(e2)
                            yield ('leg->event', e, out, sub[0], e2), p
            else:
                lu = self.best_lineup(plan, e)
                if lu:
                    p = plan.copy(); p.rel[e] = lu; yield ('add relay', e), p

    def run(self, start, max_steps=200):
        cur = start.copy()
        cur_s = self.score(cur)
        hist = []
        for _ in range(max_steps):
            best = None
            for mv, p in self.moves(cur):
                if not self.feasible(p):
                    continue
                s = self.score(p)
                if best is None or s > best[0]:
                    best = (s, mv, p)
            if best is None or best[0] <= cur_s + self.eps:
                break
            cur_s, mv, cur = best
            hist.append((mv, cur_s))
        return cur, cur_s, hist


def likely_plan(meet, focal, available=None):
    """The entry model's likeliest entries for a team: each relay it more
    likely runs than not, on it the four likeliest legs; then each athlete's
    likelier-than-not events, likeliest first, while under the cap and the
    event limit."""
    r = meet.rows
    ok = (lambda a: True) if available is None else (lambda a: a in available)
    plan = Plan()
    for i in np.flatnonzero((r.team.values == focal) & r.relay.values.astype(bool) & (r.pent.values >= 0.5)):
        e = r.event.values[i]
        lg = meet.legs[(meet.legs.team == focal) & (meet.legs.event == e)].sort_values('pleg', ascending=False)
        lu = tuple(a for a in lg.aid.values if ok(a) and not a.startswith('?')
                   and plan.load(a) < meet.cap)[:4]
        if len(lu) == 4:
            plan.rel[e] = lu
    cnt = collections.Counter()
    ind = r[(r.team.values == focal) & ~r.relay.values.astype(bool) & (r.pent.values >= 0.5)]
    for a, e in zip(*[ind.sort_values('pent', ascending=False)[c].values for c in ('aid', 'event')]):
        if ok(a) and plan.load(a) < meet.cap and cnt[e] < meet.limit[e]:
            plan.ind.setdefault(a, set()).add(e)
            cnt[e] += 1
    return plan


def limits_of(truth):
    """{event: the most entrants any one team had} at a meet."""
    per = collections.Counter()
    for ev, rs in truth['events'].items():
        if not tp.is_relay_event(ev):
            for r in rs:
                if r['unit'] and r['aid']:
                    per[(r['unit'], ev)] += 1
    out = collections.defaultdict(lambda: 1)
    for (u, e), k in per.items():
        out[e] = max(out[e], k)
    return dict(out)


def actual_plan(meet, focal):
    team = meet.rows.team.values
    ind = {}
    for a, evs in meet.ind_true.items():
        mine = {e for e in evs if (a, e) in meet.ix and team[meet.ix[(a, e)]] == focal}
        if mine:
            ind[a] = mine
    rel = {e: lu for (u, e), lu in meet.rel_true.items() if u == focal and lu}
    return Plan(ind, rel)


# ---------------------------------------------------------------------------
# Live: suggested entries for a coming meet
# ---------------------------------------------------------------------------
#
#   python3 backend/track_entries.py meets --year 2027
#   python3 backend/track_entries.py suggest --meet 2027-Indoor-state-B-Girls [--plan entries.txt]
#        [--scratch NAME ...] [--force NAME=EVENT ...] [--forbid NAME=EVENT ...] [--relays-fixed]
#
# A plan file is one line per athlete or relay, '#' starts a comment:
#   Jane Doe: 55, 200, LJ
#   4x200: Jane Doe, Amy Smith, Kay Lee, Bo Diaz
# Events can be short (55, 55H, mile, 2 mile, 4x8, HJ, shot); names are
# matched to the team's athletes (full name, else a unique last or first name).

import os
import pickle
import re
import sys

TEAM = 'me-hs-gsa'
LIVE_DIR = os.path.join(tp.CACHE_DIR, 'entries')
LIVE_SIMS, CHECK_SIMS = 1500, 4000


def _stamp():
    p = os.path.join(tp.CACHE_DIR, 'athletes.pkl')
    return f'{int(os.path.getmtime(p))}' if os.path.exists(p) else '0'


def live_inputs(meet_id, asof, quiet=False):
    """The predictor's rows for one coming meet (results before asof), cached
    by meet, day and dataset: {pred, legs, table, events, lines, limits, z,
    names, cutoff, avg_load}."""
    os.makedirs(LIVE_DIR, exist_ok=True)
    path = os.path.join(LIVE_DIR, f'{meet_id}_{asof}_{_stamp()}.pkl')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return pickle.load(f)
    year = int(meet_id[:4])
    if not quiet:
        print(f'predicting {meet_id} from results before {asof} (a few minutes; cached after)', file=sys.stderr)
    out, model = tp.predict_season(year, asof, sims=1, quiet=True, only={meet_id})
    if not out:
        raise SystemExit(f'no prediction for {meet_id} as of {asof}: not a coming championship, '
                         f'or no meet of the season yet among its teams')
    o = out[0]
    fz, tr = tp._G['fz'], tp._G['tr']
    nm = {str(k): v for k, v in fz.s.name.items()}
    pred = o['pred'].drop(columns=['win', 'top3', 'exp_pts', 'entered'], errors='ignore')
    pred['aid'] = pred.aid.astype(str)
    legs = o['legs'].copy() if o['legs'] is not None else None
    if legs is not None:
        legs['aid'] = legs.aid.astype(str)
    limits = limits_of(o['last_truth'])
    if o['held']:
        for e, k in limits_of(tr[meet_id]).items():
            limits[e] = max(limits.get(e, 1), k)
    d = dict(pred=pred, legs=legs, table=o['table'], events=sorted(set(pred.event)), lines=o['lines'],
             limits=limits, z=model.z_for(meet_id), cutoff=o['cutoff'],
             names={a: nm.get(a, a) for a in set(pred.aid) | (set(legs.aid) if legs is not None else set())},
             avg_load=mean_load(tr, tp.event_order))
    with open(path, 'wb') as f:
        pickle.dump(d, f, protocol=pickle.HIGHEST_PROTOCOL)
    return d


def live_meet(meet_id, d, sims, seed):
    return Meet(meet_id, d['pred'], d['legs'] if d['legs'] is not None else d['pred'].iloc[:0][['team', 'event', 'aid']],
                None, *d['z'], sims=sims, seed=seed, avg_load=d['avg_load'],
                events=d['events'], table=d['table'], limit=d['limits'], line=d['lines'])


# -- reading what a coach types ---------------------------------------------

def _squash(t):
    return re.sub(r'[^a-z0-9]', '', t.lower())


def event_aliases(events):
    al = {}
    hurdles = [e for e in events if 'Hurdles' in e]
    for e in events:
        el = e.lower()
        al[_squash(e)] = e
        m = re.match(r'4x(\d+)', el)
        if m:
            for k in (f'4x{m.group(1)}', f'4x{m.group(1)[0]}', f'{m.group(1)}relay'):
                al[k] = e
            continue
        m = re.match(r'(\d+) meter (dash|run|race walk)', el)
        if m:
            al[m.group(1) + ('walk' if 'walk' in el else '')] = e
        m = re.match(r'(\d+) meter hurdles', el)
        if m:
            for k in (f'{m.group(1)}h', f'{m.group(1)}mh', f'{m.group(1)}hurdles'):
                al[k] = e
            if len(hurdles) == 1:
                al['hurdles'] = al['h'] = e
        if el == '1 mile run':
            for k in ('mile', '1mile', 'onemile', '1600'):
                al.setdefault(k, e)
        if el == '2 mile run':
            for k in ('2mile', 'twomile', '3200'):
                al.setdefault(k, e)
        if tp.is_field(e):
            w = el.split()
            al[w[0][0] + w[1][0]] = e          # hj, lj, tj, pv, sp, dt, jt
            al[w[0]] = e                        # high, long, triple, pole, shot, discus, javelin
    return al


def parse_event(text, aliases):
    e = aliases.get(_squash(text))
    if e is None:
        raise SystemExit(f"event '{text}' is not one of this meet's (try 55, 55H, mile, 4x8, HJ, shot)")
    return e


class Roster:
    """The focal team's athletes, matched by name."""

    def __init__(self, aids, names):
        self.names = {a: names.get(a, a) for a in aids}
        self.by_key = collections.defaultdict(list)
        for a, n in self.names.items():
            w = re.findall(r'[a-z]+', (n or '').lower())
            self.by_key[('full', tp.name_key(n))].append(a)
            if w:
                self.by_key[('last', w[-1])].append(a)
                self.by_key[('first', w[0])].append(a)

    def find(self, text):
        w = re.findall(r'[a-z]+', text.lower())
        for k in (('full', tp.name_key(text)), ('last', w[-1] if w else ''), ('first', w[0] if w else '')):
            hit = self.by_key.get(k, [])
            if len(hit) == 1:
                return hit[0]
            if len(hit) > 1 and k[0] == 'full':
                break
        raise SystemExit(f"no single athlete on the team matches '{text}'")

    def name(self, a):
        return self.names.get(a, a)


def read_plan(path, roster, aliases):
    plan = Plan()
    for raw in open(path, encoding='utf-8'):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if ':' not in line:
            raise SystemExit(f"plan line without 'name: events': {line}")
        head, rest = (x.strip() for x in line.split(':', 1))
        items = [x.strip() for x in re.split(r'[,;]', rest) if x.strip()]
        ev = aliases.get(_squash(head))
        if ev and tp.is_relay_event(ev):
            plan.rel[ev] = tuple(roster.find(x) for x in items)
        else:
            plan.ind.setdefault(roster.find(head), set()).update(parse_event(x, aliases) for x in items)
    return plan


def pairs(specs, roster, aliases):
    out = []
    for s in specs or ():
        if '=' not in s:
            raise SystemExit(f"'{s}': write NAME=EVENT")
        n, e = s.split('=', 1)
        out.append((roster.find(n), parse_event(e, aliases)))
    return out


# -- the advice ------------------------------------------------------------

def entrant_points(field, plan, e):
    """[(focal entrant: athlete id or 'relay', expected points)] in event e."""
    m = field.m
    om, ot = field.opp[e]
    fm = field.focal_marks(plan, e)
    who = ['relay'] if tp.is_relay_event(e) else [a for a, evs in plan.ind.items() if e in evs]
    if not fm.shape[1]:
        return []
    marks = np.concatenate([om, fm], 1)
    sims = marks.shape[0]
    pts = np.zeros((sims, fm.shape[1]))
    order = np.argsort(marks, axis=1)[:, :min(len(m.table), marks.shape[1])]
    ar = np.arange(sims)
    for p in range(order.shape[1]):
        col = order[:, p]
        ok = np.isfinite(marks[ar, col]) & (col >= om.shape[1])
        np.add.at(pts, (ar[ok], col[ok] - om.shape[1]), m.table[p])
    return list(zip(who, pts.mean(0)))


def fit_constraints(plan, meet, force, forbid):
    """The plan with forbidden entries out and forced ones in (an athlete
    over the cap gives up their likeliest-to-be-dropped other event)."""
    p = plan.copy()
    for a, e in forbid:
        if tp.is_relay_event(e) and a in p.rel.get(e, ()):
            p.rel.pop(e)
        p.ind.get(a, set()).discard(e)
    for a, e in force:
        if tp.is_relay_event(e):
            if a not in p.rel.get(e, ()):
                lu = list(p.rel.get(e, ()))
                p.rel[e] = tuple(lu[:3] + [a]) if len(lu) >= 4 else tuple(lu + [a])
        else:
            p.ind.setdefault(a, set()).add(e)
        while p.load(a) > meet.cap:
            other = [x for x in p.ind.get(a, ()) if (a, x) not in force]
            if not other:
                break
            p.ind[a].discard(min(other, key=lambda x: meet.rows.pent.values[meet.ix[(a, x)]]))
    return p


def describe_move(mv, name):
    k = mv[0]
    if k == 'add':
        return f'add {name(mv[1])} to the {mv[2]}'
    if k == 'drop':
        return f'take {name(mv[1])} out of the {mv[2]}'
    if k == 'swap':
        return f'{name(mv[1])}: {mv[2]} -> {mv[3]}'
    if k == 'leg':
        return f'{mv[1]}: {name(mv[3])} runs for {name(mv[2])}'
    if k == 'event->leg':
        return f'{mv[1]}: {name(mv[3])} runs for {name(mv[2])} (gives up the {mv[4]})'
    if k == 'leg->event':
        return f'{mv[1]}: {name(mv[3])} runs for {name(mv[2])}, who enters the {mv[4]}'
    if k == 'add relay':
        return f'enter the {mv[1]}'
    if k == 'drop relay':
        return f'scratch the {mv[1]}'
    return str(mv)


def summary(field, plan):
    p = field.total(plan)
    fi = field.fi
    noise = np.random.default_rng(1).random(p.shape) * 1e-6
    rank = (-(p + noise)).argsort(1).argsort(1)[:, fi]
    return dict(pts=p[:, fi].mean(), p10=np.percentile(p[:, fi], 10), p90=np.percentile(p[:, fi], 90),
                win=(rank == 0).mean(), top3=(rank < 3).mean(), all=p.mean(0))


def suggest(meet_id, team=TEAM, asof=None, plan_path=None, scratch=(), force=(), forbid=(), fix_relays=False,
            kind='points', out=sys.stdout):
    from datetime import date
    asof = asof or date.today().isoformat()
    d = live_inputs(meet_id, asof)
    m = live_meet(meet_id, d, LIVE_SIMS, seed=5)
    if team not in m.tix:
        raise SystemExit(f'{team} has no athletes in the prediction for {meet_id}')
    rows = m.rows
    mine = rows[(rows.team == team) & ~rows.relay.astype(bool)]
    legs_mine = m.legs[m.legs.team == team] if len(m.legs) else m.legs
    roster = Roster(set(mine.aid) | set(legs_mine.aid), d['names'])
    al = event_aliases(m.events)
    out_ = {roster.find(n) for n in scratch or ()}
    force, forbid = pairs(force, roster, al), pairs(forbid, roster, al)
    avail = set(roster.names) - out_
    f = Field(m, team, 'drawn')
    starts = {'likely': likely_plan(m, team, available=avail)}
    if plan_path:
        starts['yours'] = read_plan(plan_path, roster, al)
        bad = [(a, e) for a, evs in starts['yours'].ind.items() for e in evs if (a, e) not in m.ix]
        for a, e in bad:
            print(f'note: {roster.name(a)} has no {e} mark to go on; left out of your plan', file=out)
            starts['yours'].ind[a].discard(e)
    best = None
    for nm, st in starts.items():
        st = fit_constraints(st, m, force, forbid)
        starts[nm] = st
        opt = Optimizer(f, kind=kind, available=avail, fix_relays=fix_relays, force=force, forbid=forbid)
        plan, s, hist = opt.run(st)
        if best is None or s > best[1] + 1e-9:
            best = (plan, s, hist, nm)
    plan, _, hist, start_name = best
    base_name = 'yours' if plan_path else 'likely'
    if start_name != base_name:
        # the moves from the coach's plan: run again from it, then list what differs
        opt = Optimizer(f, kind=kind, available=avail, fix_relays=fix_relays, force=force, forbid=forbid)
        _, _, hist = opt.run(starts[base_name])
    # judged on fresh simulated meets (rivals and marks drawn anew)
    chk = live_meet(meet_id, d, CHECK_SIMS, seed=77)
    fc = Field(chk, team, 'drawn')
    s_base, s_best = summary(fc, starts[base_name]), summary(fc, plan)
    name = roster.name
    w = lambda *a: print(*a, file=out)  # noqa: E731
    w(f"{meet_id}  {team}  results before {d['cutoff']}  (rivals' entries drawn from the entry model)")
    lbl = 'your plan' if plan_path else 'likely entries'
    w(f"  {lbl:16} {s_base['pts']:5.1f} pts (80%: {s_base['p10']:.0f}-{s_base['p90']:.0f})  "
      f"win {100 * s_base['win']:3.0f}%  top 3 {100 * s_base['top3']:3.0f}%")
    w(f"  {'suggested':16} {s_best['pts']:5.1f} pts (80%: {s_best['p10']:.0f}-{s_best['p90']:.0f})  "
      f"win {100 * s_best['win']:3.0f}%  top 3 {100 * s_best['top3']:3.0f}%")
    riv = sorted(((v, t) for t, v in zip(chk.teams, s_best['all']) if t != team), reverse=True)[:4]
    w('  rivals: ' + ', '.join(f"{t.replace('me-hs-', '')} {v:.0f}" for v, t in riv))
    if hist:
        w(f'\nchanges from {lbl}, expected points each (on the optimizer\'s own simulated meets):')
        prev = Optimizer(f, kind=kind).score(starts[base_name])
        for mv, s in hist:
            w(f'  {s - prev:+5.2f}  {describe_move(mv, name)}')
            prev = s
    else:
        w(f'\nno change to {lbl} gains {Optimizer(f).eps:.2f}+ points')
    w('\nsuggested entries (predicted mark, expected points):')
    base = starts[base_name]
    for e in sorted(m.events, key=lambda x: m.order.get(x, 99)):
        ep = dict(entrant_points(fc, plan, e))
        if tp.is_relay_event(e):
            lu = plan.rel.get(e)
            was = base.rel.get(e)
            if not lu and not was:
                continue
            i = m.ix.get((str(('relay', team)), e))
            mk = tp.mark_str(m.base[i] + m.relay_shift(team, e, lu, {a: load_cost(plan.events_of(a), m.order) for a in lu}), e) \
                if lu and i is not None else ''
            txt = ', '.join(name(a) for a in lu) if lu else '(not entered)'
            chg = '' if tuple(lu or ()) == tuple(was or ()) else '   was: ' + (', '.join(name(a) for a in was) if was else 'not entered')
            w(f"  {e:20} {txt}  {mk}  {ep.get('relay', 0):.1f}{chg}")
            continue
        now = sorted(a for a, evs in plan.ind.items() if e in evs)
        was = sorted(a for a, evs in base.ind.items() if e in evs)
        if not now and not was:
            continue
        parts = []
        for a in now:
            i = m.ix[(a, e)]
            c = load_cost(plan.events_of(a), m.order)[e] - m.avg_load.get(e, 0.0)
            parts.append(f"{'+' if a not in was else ''}{name(a)} {tp.mark_str(m.base[i] + c, e)} ({ep.get(a, 0):.1f})")
        parts += [f'-{name(a)}' for a in was if a not in now]
        w(f"  {e:20} " + '; '.join(parts))
    w('\nper athlete: ' + '; '.join(f"{name(a)} {len(plan.events_of(a))}" for a in sorted(plan.athletes(), key=name)))
    return plan, s_base, s_best


def coming_meets(year, team=TEAM):
    """The championships the team went to at their last edition, named for `year`."""
    with open(os.path.join(tp.CACHE_DIR, 'truths.pkl'), 'rb') as f:
        tr = pickle.load(f)
    latest = {}
    for c in tp.load_champs():
        k = (c['season'], c['kind'], c.get('conference'), c['division'], c['gender'])
        if c['year'] < year and (k not in latest or c['year'] > latest[k]['year']):
            latest[k] = c
    out = []
    for c in latest.values():
        if c['year'] >= year - 2 and team in tp.champ_units(tr[c['id']]):
            out.append(tp.next_edition(c, year))
    return sorted(out, key=lambda c: c['date'])


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='Suggested championship entries for a team.')
    sub = ap.add_subparsers(dest='cmd')
    mp_ = sub.add_parser('meets', help="the team's coming championships")
    mp_.add_argument('--year', type=int, required=True, help='academic year, named by its spring (2027)')
    mp_.add_argument('--team', default=TEAM)
    sp = sub.add_parser('suggest', help='suggested entries for one meet')
    sp.add_argument('--meet', required=True, help='championship id, e.g. 2027-Indoor-state-B-Girls')
    sp.add_argument('--team', default=TEAM)
    sp.add_argument('--asof', help='use results before this day (default today)')
    sp.add_argument('--plan', help='your entries, to check and improve (see the file header)')
    sp.add_argument('--scratch', nargs='*', default=[], metavar='NAME', help='not available')
    sp.add_argument('--force', nargs='*', default=[], metavar='NAME=EVENT', help='must be entered')
    sp.add_argument('--forbid', nargs='*', default=[], metavar='NAME=EVENT', help='must not be entered')
    sp.add_argument('--relays-fixed', action='store_true', help='keep relays and lineups as in the plan')
    sp.add_argument('--goal', default='points', choices=['points', 'win', 'top3'])
    a = ap.parse_args(argv)
    if a.cmd == 'meets':
        for c in coming_meets(a.year, a.team):
            print(f"{c['id']:34} {c['date']}{' (date estimated)' if c.get('estimated_date') else ''}")
    elif a.cmd == 'suggest':
        suggest(a.meet, a.team, a.asof, a.plan, a.scratch, a.force, a.forbid, a.relays_fixed, a.goal)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
