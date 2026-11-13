import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import track_entries as te  # noqa: E402

OUT = {'4x800 Meter Relay': 0, '110 Meter Hurdles': 1, '100 Meter Dash': 2, '1600 Meter Run': 3,
       '4x100 Meter Relay': 4, '400 Meter Dash': 5, '300 Meter Hurdles': 6, '800 Meter Run': 7,
       '200 Meter Dash': 8, '3200 Meter Run': 9, '4x400 Meter Relay': 10}
IND = {'1 Mile Run': 0, '400 Meter Dash': 1, '800 Meter Run': 2}


def test_distance_already_run_costs():
    c = te.load_cost({'1600 Meter Run', '3200 Meter Run'}, OUT)
    assert c['1600 Meter Run'] == 0
    assert c['3200 Meter Run'] == pytest.approx(1.6 * te.KM_COST)


def test_back_to_back_into_the_800_costs_more_than_sprints():
    c = te.load_cost({'400 Meter Dash', '800 Meter Run'}, IND)
    assert c['800 Meter Run'] == pytest.approx(0.4 * te.KM_COST + te.B2B_DISTANCE)
    c = te.load_cost({'400 Meter Dash', '300 Meter Hurdles'}, OUT)
    assert c['300 Meter Hurdles'] == pytest.approx(0.4 * te.KM_COST + te.B2B_COST)


def test_field_events_carry_no_load():
    c = te.load_cost({'Long Jump', '100 Meter Dash', '200 Meter Dash'}, OUT)
    assert c['Long Jump'] == 0
    assert c['200 Meter Dash'] == pytest.approx(0.1 * te.KM_COST)


def test_plan_counts_relay_legs_toward_the_cap():
    p = te.Plan({'a': {'400 Meter Dash', '200 Meter Dash'}}, {'4x400 Meter Relay': ('a', 'b', 'c', 'd')})
    assert p.load('a') == 3 and p.load('b') == 1
    q = p.copy()
    q.ind['a'].discard('200 Meter Dash')
    assert p.load('a') == 3 and q.load('a') == 2


def test_short_event_names():
    al = te.event_aliases(['55 Meter Dash', '55 Meter Hurdles', '1 Mile Run', '2 Mile Run', '4x800 Meter Relay',
                           'High Jump', 'Shot Put'])
    assert te.parse_event('55', al) == '55 Meter Dash'
    assert te.parse_event('55H', al) == '55 Meter Hurdles'
    assert te.parse_event('mile', al) == '1 Mile Run'
    assert te.parse_event('2 mile', al) == '2 Mile Run'
    assert te.parse_event('4x8', al) == '4x800 Meter Relay'
    assert te.parse_event('HJ', al) == 'High Jump'
    assert te.parse_event('shot', al) == 'Shot Put'
    with pytest.raises(SystemExit):
        te.parse_event('pole vault', al)


def test_plan_file(tmp_path):
    r = te.Roster(['a1', 'a2', 'a3', 'a4', 'a5'], {'a1': 'Jane Doe', 'a2': 'Amy Smith', 'a3': 'Kay Lee',
                                                   'a4': 'Bo Diaz', 'a5': 'Jane Roe'})
    al = te.event_aliases(['200 Meter Dash', 'Long Jump', '4x400 Meter Relay'])
    p = tmp_path / 'plan.txt'
    p.write_text('# GSA\nJane Doe: 200, LJ\nSmith: 200\n4x400: Jane Roe, Amy Smith, Lee, Diaz\n')
    plan = te.read_plan(str(p), r, al)
    assert plan.ind == {'a1': {'200 Meter Dash', 'Long Jump'}, 'a2': {'200 Meter Dash'}}
    assert plan.rel == {'4x400 Meter Relay': ('a5', 'a2', 'a3', 'a4')}
    with pytest.raises(SystemExit):
        r.find('Jane')            # two Janes


def test_drawn_rivals_score_only_when_entered():
    import numpy as np
    import pandas as pd
    rows = pd.DataFrame(dict(aid=['f1', 'r1', 'r2'], team=['F', 'R', 'R'], event=['200 Meter Dash'] * 3,
                             mean=[3.30, 3.20, 3.10], scale=[0.001] * 3, pent=[1.0, 0.0, 1.0],
                             relay=[False] * 3, cur_same_n=[2, 2, 2], sb=[3.3] * 3, field_rank=[3, 2, 1]))
    legs = pd.DataFrame(columns=['team', 'event', 'aid', 'pleg', 'leg_gap'])
    m = te.Meet('2027-Outdoor-state-C-Girls', rows, legs, None, np.zeros(10), np.zeros(10), sims=50,
                events=['200 Meter Dash'], table=[10, 8, 6], limit={}, line={})
    f = te.Field(m, 'F', 'drawn')
    pts = f.total(te.Plan({'f1': {'200 Meter Dash'}}))
    # r1 never enters: F is second behind r2, every simulated meet
    assert pts[:, m.tix['F']].mean() == pytest.approx(8)
    assert pts[:, m.tix['R']].mean() == pytest.approx(10)
