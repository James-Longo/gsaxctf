"""Athlete catalog: how a surname-only or initial name joins a runner.

Run:  python3 backend/tests/test_athlete_catalog.py      (or pytest, if installed)

Rows are synthetic store rows (no store needed). Each test names the
failure it pins down.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from backend import athlete_catalog as ac  # noqa: E402

UNIT = 'me-ms-marshwood'


def _row(name, year, meet, mark, sid=None, event='Boys 2 Mile Run CC'):
    sid = sid or name.lower().replace(' ', '-')
    return ('Marshwood_MS', 'Marshwood Middle School', UNIT, year, 'XC', ac.academic_year(year, 'XC'),
            name, sid, event, mark, None, meet, f'{year}-10-01')


def _runners(rows):
    ents, _ = ac.build_entities(rows)
    groups, _ = ac.cluster(ents, ac.candidate_pairs(ents), {})
    return [sorted(ents[k]['name'] for k in g) for g in groups]


def _together(groups, a, b):
    return any(a in g and b in g for g in groups)


def test_surname_joins_the_runner_named_a_season_away():
    # Saco MS meet 2009 prints surnames only; Jack Letellier's full name is
    # printed only in 2010 (and 2008 by another runner of another name)
    rows = [_row('Letellier', 2009, 'Saco MS Meet', '8:18'),
            _row('Jack Letellier', 2010, 'York County MS', '8:30'),
            _row('Jack Letellier', 2010, 'Wells MS Meet', '8:25')]
    assert _together(_runners(rows), 'Letellier', 'Jack Letellier')


def test_surname_twice_in_one_race_is_two_runners():
    # two Gibsons at 9:51 and 10:55 in one race: neither is Curtis alone
    rows = [_row('Gibson', 2009, 'Saco MS Meet', '9:51', sid='gibson'),
            _row('Gibson', 2009, 'Saco MS Meet', '10:55', sid='gibson'),
            _row('Curtis Gibson', 2009, 'York County MS', '9:58')]
    assert not _together(_runners(rows), 'Gibson', 'Curtis Gibson')


def test_surname_never_bridges_two_brothers():
    # "Zuke" in 2008 is Joe's season; a "Zuke" a season from Wyatt's must not
    # make Joe and Wyatt one runner
    rows = [_row('Zuke', 2008, 'TA MS Meet', '11:40'),
            _row('Joe Zuke', 2008, 'York County MS', '11:30'),
            _row('Zuke', 2011, 'TA MS Meet', '12:10'),
            _row('Wyatt Zuke', 2012, 'York County MS', '12:00')]
    assert not _together(_runners(rows), 'Joe Zuke', 'Wyatt Zuke')


def test_exhibition_x_is_not_an_initial():
    # MileSplit prints exhibition runners "X McGrath"
    rows = [_row('X McGrath', 2011, 'Kennebunk Meet', '18:40'),
            _row('Sean McGrath', 2011, 'York County MS', '18:20')]
    assert _together(_runners(rows), 'X McGrath', 'Sean McGrath')


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
