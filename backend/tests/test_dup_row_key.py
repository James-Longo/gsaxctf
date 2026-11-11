"""Double-ingest check: a track meet printed with initials matches its full-name copy.

Run:  python3 backend/tests/test_dup_row_key.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.scraper_v2 import dup_row_key, initial_only  # noqa: E402


def _p(name, event, mark, season='Indoor', team='Deering'):
    return dict(athlete_name=name, athlete_id=name, event=event, mark=mark, season=season, team=team)


def test_initials_match_full_name():
    """2011 SMAA: sub5 'Allaire, D' 31-04.00 is MileSplit's 'Dan Allaire' 31-4."""
    assert dup_row_key(_p('Allaire, D', 'Boys Shot Put', '31-04.00')) == \
        dup_row_key(_p('Dan Allaire', 'Boys Shot Put', '31-4'))


def test_different_mark_differs():
    assert dup_row_key(_p('R Publicover', 'Boys 55 Meter Dash', '7.01')) != \
        dup_row_key(_p('Ryan Publicover', 'Boys 55 Meter Dash', '7.21'))


def test_xc_keeps_exact_key():
    a, b = _p('Allaire, D', 'Boys 5K', '17:01', 'XC'), _p('Dan Allaire', 'Boys 5K', '17:01', 'XC')
    assert dup_row_key(a) != dup_row_key(b)


def test_initial_only():
    assert initial_only('R Publicover') and initial_only('Allaire, D') and initial_only('D. Allaire')
    assert not initial_only('Dan Allaire') and not initial_only('Allaire, Dan')


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
