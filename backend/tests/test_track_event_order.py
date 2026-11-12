"""Running order used by the entry model's back-to-back features (adj_fr / adj_gap)."""
from backend import track_postseason as tp


def test_own_file_order():
    # the 2016 Class C boys file prints the schedule: 4x800 first, 200 after the 800
    o = tp.event_order('2016-Outdoor-state-C-Boys')
    assert o['4x800 Meter Relay'] == 0
    assert o['800 Meter Run'] + 1 == o['200 Meter Dash']


def test_future_edition_uses_an_earlier_one():
    # no 2030 file: the latest edition that prints its order, else the Maine order
    o = tp.event_order('2030-Indoor-state-B-Girls')
    assert o['1 Mile Run'] + 1 == o['400 Meter Dash']
    assert o['55 Meter Hurdles'] == 1


def test_hurdles_by_gender():
    assert '110 Meter Hurdles' in tp.event_order('2030-Outdoor-state-A-Boys')
    assert '100 Meter Hurdles' in tp.event_order('2030-Outdoor-state-A-Girls')


if __name__ == '__main__':
    for k, f in list(globals().items()):
        if k.startswith('test_'):
            f()
            print(k, 'ok')
