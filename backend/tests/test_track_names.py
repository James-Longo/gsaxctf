"""Track postseason name joins (no store).

Run:  python3 backend/tests/test_track_names.py      (or pytest, if installed)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend import track_postseason as tp  # noqa: E402


def test_initial_key_joins_state_sheet_to_initial_store_name():
    # 2005 Class B state sheet prints 'Needleman, Grace'; the store kept the WMC sheets' 'G Needleman'
    assert tp.initial_key('Needleman, Grace') == tp.initial_key('G Needleman') == 'g needleman'
    assert tp.initial_key('Kyle Toot') == tp.initial_key('K Toot')


def test_initial_key_drops_suffix_and_needs_two_names():
    assert tp.initial_key('Smith Jr, John') == tp.initial_key('John Smith Jr') == 'j smith'
    assert tp.initial_key('Giffard') is None
    assert tp.initial_key('') is None


if __name__ == '__main__':
    for k, f in list(globals().items()):
        if k.startswith('test_'):
            f()
    print('ok')
