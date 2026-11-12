"""Relay legs count toward an athlete's event limit in the simulation."""
import numpy as np
import pandas as pd

from backend import track_postseason as tp


def _pred():
    rows = [dict(aid='star', team='gsa', event=ev, mean=0.0, scale=0.01, pent=0.95, relay=False)
            for ev in ('55 Meter Dash', '200 Meter Dash', '400 Meter Dash')]
    rows.append(dict(aid="('relay', 'gsa')", team='gsa', event='4x200 Meter Relay', mean=0.0, scale=0.01,
                     pent=1.0, relay=True))
    return pd.DataFrame(rows)


def _legs(p_star):
    aids = ['star', 'a', 'b', 'c', 'd']
    return pd.DataFrame(dict(team='gsa', event='4x200 Meter Relay', aid=aids,
                             pleg=[p_star, 0.9, 0.9, 0.9, 0.5]))


def test_legs_count_toward_cap():
    # her leg (relay 1.0 x leg 0.9) ranks below her individual events (0.95): she gives it up
    pred = _pred()
    entered = np.ones((500, len(pred)), bool)
    drawn = tp._cap_entries(pred, entered, 3, _legs(0.9), np.random.default_rng(0))
    aids, sel, _, _ = drawn[3]
    star = list(aids).index('star')
    total = entered[:, :3].sum(1) + sel[:, star]
    assert (total <= 3).all()
    assert (sel.sum(1) == 4).all()                  # the leg she gives up goes to a teammate
    assert sel[:, list(aids).index('d')].all() and not sel[:, star].any()


def test_likelier_leg_beats_an_event():
    pred = _pred()
    entered = np.ones((500, len(pred)), bool)
    drawn = tp._cap_entries(pred, entered, 3, _legs(0.99), np.random.default_rng(0))
    aids, sel, _, _ = drawn[3]
    on = sel[:, list(aids).index('star')]
    assert on.mean() > 0.5 and (entered[on, :3].sum(1) == 2).all()


def test_no_legs_keeps_individual_cap():
    pred = _pred()
    entered = np.ones((50, len(pred)), bool)
    tp._cap_entries(pred, entered, 2, None, np.random.default_rng(0))
    assert (entered[:, :3].sum(1) == 2).all() and entered[:, 3].all()


def test_relay_not_run_draws_no_legs():
    pred = _pred()
    entered = np.ones((50, len(pred)), bool)
    entered[:, 3] = False
    drawn = tp._cap_entries(pred, entered, 3, _legs(0.99), np.random.default_rng(0))
    assert not drawn[3][1].any() and entered[:, :3].all()


if __name__ == '__main__':
    for k, f in list(globals().items()):
        if k.startswith('test_'):
            f()
            print(k, 'ok')
