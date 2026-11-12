"""Entry optimizer: what a team's championship entries should be.

The entry model (track_postseason) predicts what coaches will enter; this
decides what one team (the focal team) should enter - individual events and
relay lineups - under the meet's rules, against the other teams' entries
as known (an entry list, or what they actually entered; drawing them from
the entry model for a live meet is not built yet). Marks come from the predictor's held-out model with three measured
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
MISSING_LEG_GAP = 0.03      # a runner with no leg-event mark: this much slower than the team's slowest


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

    def __init__(self, champ_id, rows, legs, truth, z_ath, z_rel, sims=500, seed=0, avg_load=None, slope=None):
        self.id = champ_id
        self.slope = slope if slope is not None else LINEUP_SLOPE   # a number, or {relay event: slope}
        self.season = 'Indoor' if '-Indoor-' in champ_id else 'Outdoor'
        self.state = '-state-' in champ_id
        self.cap = tp.MAX_EVENTS[self.season]
        self.order = tp.event_order(champ_id)
        self.table = np.array(truth['table'], float)
        self.events = sorted(truth['events'])
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
        self.ind_true, self.rel_true = truth_entries(truth)
        legs = legs.copy()
        legs['aid'] = legs.aid.astype(str)
        self.legs = legs
        # per (team, relay event): leg candidates with their gap to the team's 4th best,
        # and the expected lineup's mean gap (leg chances as weights): the relay's mark is that lineup's
        self.leg_gap, self.expected = {}, {}
        for (t, e), g in legs.groupby(['team', 'event']):
            gaps = g.leg_gap.values
            known = np.sort(gaps[np.isfinite(gaps)])
            worst = known.max() if len(known) else 0.0
            filled = np.where(np.isfinite(gaps), gaps, max(worst, 0) + MISSING_LEG_GAP)
            self.leg_gap[(t, e)] = dict(zip(g.aid.values, filled))
            w = np.nan_to_num(g.pleg.values.astype(float))
            self.expected[(t, e)] = float((w * filled).sum() / w.sum()) if w.sum() > 0 else np.nan
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
        actually entered); a relay's lineup may be () when unknown."""
        self.m = meet
        self.focal = focal
        self.fi = meet.tix[focal]
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
        self.cache = {}

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
                np.add.at(pts, (ar, tid[col]), self.m.table[p])     # -1 (no team) lands in the last column
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

    def __init__(self, field, kind='points', eps=0.02, available=None, fix_relays=False):
        """available: athletes who may be entered (default: anyone with a row);
        fix_relays: keep the starting plan's relays and lineups as they are."""
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
        self.pool = {e: {a: g for a, g in m.leg_gap.get((field.focal, e), {}).items() if ok(a)} for e in self.relays}
        self.n_eval = 0

    def score(self, plan):
        self.n_eval += 1
        return objective(self.f.total(plan), self.f.fi, self.kind)

    def feasible(self, plan):
        m = self.m
        cnt = collections.Counter(e for evs in plan.ind.values() for e in evs)
        if any(k > m.limit[e] for e, k in cnt.items()):
            return False
        return all(plan.load(a) <= m.cap for a in plan.athletes())

    def best_lineup(self, plan, e, exclude=()):
        """Fastest four by leg gap among runners with room."""
        cands = sorted((g, a) for a, g in self.pool[e].items()
                       if a not in exclude and plan.load(a) < self.m.cap)
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


def actual_plan(meet, focal):
    team = meet.rows.team.values
    ind = {}
    for a, evs in meet.ind_true.items():
        mine = {e for e in evs if (a, e) in meet.ix and team[meet.ix[(a, e)]] == focal}
        if mine:
            ind[a] = mine
    rel = {e: lu for (u, e), lu in meet.rel_true.items() if u == focal and lu}
    return Plan(ind, rel)
