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


def _row(name, year, meet, mark, sid=None, event='Boys 2 Mile Run CC', unit=UNIT, team='Marshwood Middle School'):
    sid = sid or (name.lower().replace(' ', '-') + '-' + unit)
    return (team.replace(' ', '_'), team, unit, year, 'XC', ac.academic_year(year, 'XC'),
            name, sid, event, mark, None, meet, f'{year}-10-01')


def _runners(rows):
    ents, _ = ac.build_entities(rows)
    groups, _ = ac.cluster(ents, ac.candidate_pairs(ents), {})
    groups, _ = ac.link_across_schools(groups, ents)
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
    rows = [_row('Zuke', 2008, 'TA MS Meet', '11:40', sid='zuke--2008-xc'),
            _row('Joe Zuke', 2008, 'York County MS', '11:30'),
            _row('Zuke', 2011, 'TA MS Meet', '12:10', sid='zuke--2011-xc'),
            _row('Wyatt Zuke', 2012, 'York County MS', '12:00')]
    assert not _together(_runners(rows), 'Joe Zuke', 'Wyatt Zuke')


def test_surname_after_the_runner_graduated_is_not_her():
    # Thornton 2010: 'Lessard' raced the fall after Lauren Lessard (class of 2010) graduated
    hs = dict(unit='me-hs-thornton', team='Thornton Academy', event='Girls 5K Cross Country')
    lauren = [r[:10] + (12,) + r[11:] for r in [_row('Lauren Lessard', 2009, 'SMAA', '21:10', **hs),
                                                _row('Lauren Lessard', 2009, 'Festival', '21:00', **hs)]]
    renee = [r[:10] + (9,) + r[11:] for r in [_row('Renee Lessard', 2010, 'SMAA', '23:10', **hs),
                                               _row('Renee Lessard', 2011, 'SMAA', '22:50', **hs)]]
    # (the store files a short name per season: one id each)
    rows = lauren + renee + [_row('Lessard', 2008, 'Thornton Invite', '21:30', sid='lessard--2008-xc', **hs),
                             _row('Lessard', 2010, 'Thornton Invite', '23:00', sid='lessard--2010-xc', **hs)]
    groups = _runners(rows)
    assert not _together(groups, 'Lauren Lessard', 'Renee Lessard')
    assert not any('Lauren Lessard' in g and len([n for n in g if n == 'Lessard']) > 1 for g in groups)

def test_two_schools_starting_one_year_join_in_either_order():
    # Riggs Peterson: Woodland XC in the fall of 2021, Union 122 from the spring of 2022 on
    w = dict(unit='me-ms-woodland', team='Woodland Elementary School')
    u = dict(unit='me-ms-union-122', team='Union 122 combined middleschool team')
    a = [_row('Riggs Peterson', 2021, 'ALMS 1', '13:10', **w)]
    b = [_row('Riggs Peterson', 2022, 'ALMS 1', '12:40', **u), _row('Riggs Peterson', 2023, 'ALMS 1', '12:20', **u)]
    b[0] = b[0][:4] + ('Outdoor', 2022) + b[0][6:8] + ('Boys 1600 Meter Run', '5:40') + b[0][10:]
    keep, ac.FEEDER_MIN = ac.FEEDER_MIN, 1     # (the real route has a dozen runners)
    try:
        for rows in (a + b, b + a):
            assert len(_runners(rows)) == 1
    finally:
        ac.FEEDER_MIN = keep

def test_typo_inside_a_hyphenated_surname():
    # first and last words agree, the middle word differs by one letter
    rows = [_row('Arianna Stilles-Martin', 2021, 'PVC Meet', '22:15'),
            _row('Arianna Stiles-Martin', 2022, 'Class C North', '22:35')]
    assert _together(_runners(rows), 'Arianna Stilles-Martin', 'Arianna Stiles-Martin')


def test_exhibition_x_is_not_an_initial():
    # MileSplit prints exhibition runners "X McGrath"
    rows = [_row('X McGrath', 2011, 'Kennebunk Meet', '18:40'),
            _row('Sean McGrath', 2011, 'York County MS', '18:20')]
    assert _together(_runners(rows), 'X McGrath', 'Sean McGrath')


def test_middle_school_to_its_high_school():
    # Bay School (Blue Hill) runners go on to George Stevens Academy (Blue Hill)
    g = 'Girls 5K Run CC'
    rows = [_row('Bella Cimeno', 2011, 'Coastal MS', '13:10', event=g, unit='me-ms-bay-school', team='Bay School'),
            _row('Bella Cimeno', 2012, 'Coastal MS', '12:55', event=g, unit='me-ms-bay-school', team='Bay School'),
            _row('Bella Cimeno', 2013, 'PVC Champs', '21:40', event=g, unit='me-hs-gsa', team='George Stevens Academy'),
            _row('Bella Cimeno', 2014, 'PVC Champs', '21:02', event=g, unit='me-hs-gsa', team='George Stevens Academy')]
    assert _together(_runners(rows), 'Bella Cimeno', 'Bella Cimeno') and len(_runners(rows)) == 1


def test_one_name_at_two_schools_at_once_is_two_runners():
    g = 'Girls 5K Run CC'
    rows = [_row('Emma Smith', 2012, 'Coastal MS', '13:10', event=g, unit='me-ms-bay-school', team='Bay School'),
            _row('Emma Smith', 2012, 'PVC Meet', '21:40', event=g, unit='me-hs-gsa', team='George Stevens Academy')]
    assert len(_runners(rows)) == 2


def test_three_schools_two_spellings_one_runner():
    # Arianna Stiles-Martin: Bay School XC (fall 2018), Blue Hill track the same school year and
    # XC after it as 'Ariana', then George Stevens Academy
    g, t = 'Girls 5K Run CC', 'Girls 800 Meter Run'
    rows = [_row('Arianna Stiles-Martin', 2018, 'Coastal MS', '13:40', event=g, unit='me-ms-bay-school', team='Bay School'),
            _row('Ariana Stiles-Martin', 2019, 'Blue Hill Meet', '2:40', event=t, unit='me-ms-blue-hill',
                 team='Blue Hill Consolidated School'),
            _row('Arianna Stiles-Martin', 2019, 'Coastal MS', '13:05', event=g, unit='me-ms-blue-hill',
                 team='Blue Hill Consolidated School'),
            _row('Arianna Stiles-Martin', 2021, 'PVC Champs', '22:15', event=g, unit='me-hs-gsa', team='George Stevens Academy')]
    assert len(_runners(rows)) == 1


def test_unsupported_move_cuts_the_chain_not_the_town_link():
    # an Owen Bean at a South Portland middle school (2014 track) does not stop the Hall-Dale MS
    # Owen Bean (2015 XC) from joining the Hall-Dale HS Owen Bean (2017-19): same town
    g = 'Boys 5K Run CC'
    rows = [_row('Owen Bean', 2014, 'SMAA MS', '2:40', event='Boys 800 Meter Run', unit='me-ms-memorial-sp',
                 team='Memorial Middle School'),
            _row('Owen Bean', 2015, 'CAL MS', '10:51', event='Boys 3K Run CC', unit='me-ms-hall-dale', team='HallDale Middle School'),
            _row('Owen Bean', 2017, 'MVC', '20:17', event=g, unit='me-hs-hall-dale', team='HallDale High School'),
            _row('Owen Bean', 2018, 'MVC', '19:50', event=g, unit='me-hs-hall-dale', team='HallDale High School')]
    assert len(_runners(rows)) == 2


def test_surname_twice_in_one_race_joins_no_runner():
    # cape10_5 2007: 'Swiatek' 19:27 (Michaela) and 'Swiatek' 23:25 (another York girl) in one race;
    # the surname entry is two girls, so it joins neither Swiatek
    g = 'Girls 3.0 Mile Run CC'
    rows = [_row('Swiatek', 2007, 'Cape Meet', '19:27', sid='swiatek', event=g, unit='me-hs-york', team='York High School'),
            _row('Swiatek', 2007, 'Cape Meet', '23:25', sid='swiatek', event=g, unit='me-hs-york', team='York High School'),
            _row('Michaela Swiatek', 2007, 'WMC Meet', '19:40', event=g, unit='me-hs-york', team='York High School'),
            _row('Michaela Swiatek', 2008, 'WMC Meet', '19:10', event=g, unit='me-hs-york', team='York High School')]
    assert not _together(_runners(rows), 'Swiatek', 'Michaela Swiatek')


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
