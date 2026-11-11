"""File-stem level: 'ms' inside a stem means middle school, not the end of 'teams' or 'rams'.

Run:  python3 backend/tests/test_meet_level.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.school_catalog import meet_level  # noqa: E402


def test_teams_is_not_middle_school():
    """2007 Bowdoin College High School Relays (bowdoinboysteams): seniors filed to middle schools."""
    assert meet_level('bowdoinboysteams') is None
    assert meet_level('smaarams') is None


def test_ms_stems_still_middle_school():
    for s in ('conymsboys_oct6', 'bucksportms_may16-1', 'RBMS', 'pcms_may11', 'freeportmsboysteams_sept29',
              'scarboroughmsinvite'):
        assert meet_level(s) == 'ms', s


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
