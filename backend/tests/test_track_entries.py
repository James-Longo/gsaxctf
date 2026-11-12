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
