"""XC postseason simulator checks (no store, no results files).

Run:  python3 backend/tests/test_xc_postseason.py      (or pytest, if installed)

The season is synthetic: one class C South regional run on day 50, its
state meet on day 57, predicted with results through day 56. Each test
names the failure it pins down.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from backend import xc_postseason as xp  # noqa: E402

SCHOOLS = 'ABCDE'
STATE_DAY = 57


class NoNoise:
    """Every runner runs exactly their rating."""
    def draw(self, n, prior, rng, sd=None):
        return 0.0

    def draw_pooled(self, rng):
        return 0.0


def _season():
    """Five teams of five ran the regional (A fastest, E slowest).
    A also has A6, its fastest, who missed the regional but raced on day 45;
    A7, fast but last raced on day 20 (done for the season); A8, who ran the
    regional as A's slowest. B has only its five regional runners active, and
    B6, fast, last raced on day 20. E, which misses qualifying, has E6, who
    missed the regional."""
    ratings, obs = {}, []

    def runner(aid, team, theta, last, raced=False):
        ratings[aid] = dict(theta=theta, sd=0.03, n=3, team=team, name=aid,
                            last=last, prior=False, grade=11)
        if raced:
            obs.append(xp.Obs(aid=aid, year=2026, gender='Girls', course=('X', 5000),
                              lt=theta, meet='regional-c-south', day=50, team=team,
                              name=aid, grade=11, race='r1'))

    for i, t in enumerate(SCHOOLS):
        for k in range(1, 6):
            runner(f'{t}{k}', t, 7.0 + 0.01 * i + 0.001 * k, 50, raced=True)
    runner('A6', 'A', 6.90, 45)
    runner('A7', 'A', 6.95, 20)
    runner('A8', 'A', 7.20, 50, raced=True)
    runner('B6', 'B', 6.95, 20)
    runner('E6', 'E', 6.95, 45)
    groups = {'schools': {t: {'name': t, 'class': 'C', 'region': 'South'} for t in SCHOOLS},
              'meets': [{'id': 'reg_C_S', 'name': 'C South', 'day': 50, 'class': 'C', 'region': 'South'},
                        {'id': 'state_C', 'name': 'C state', 'day': STATE_DAY, 'class': 'C',
                         'from': ['reg_C_S']}]}
    return ratings, obs, groups


def _state_field():
    ratings, obs, groups = _season()
    _, _, _, res = xp.simulate_postseason(obs, 2026, 'Girls', STATE_DAY, groups, None, NoNoise(),
                                          sims=5, params={'dnf': False, 'program_icc': 0.0},
                                          ratings=ratings)
    return set(res['state_C']['athletes'])


def test_state_team_comes_from_the_season_roster():
    """A qualifying team's state seven come from its whole roster, active
    runners first: A6 goes though she missed the regional (one meet does not
    decide), A7 does not though she is fast (no race in the last two weeks)."""
    team_a = {a for a in _state_field() if a.startswith('A')}
    assert team_a == {'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A8'}, team_a


def test_short_active_roster_fills_from_the_rest():
    """A team with fewer than seven active runners fills from the rest of its
    roster: B6 has not raced lately but B has only five active runners."""
    assert {a for a in _state_field() if a.startswith('B')} == {'B1', 'B2', 'B3', 'B4', 'B5', 'B6'}


def test_non_qualifying_team_sends_only_its_individuals():
    """A team that missed qualifying sends only its runners who placed in the
    top INDIVIDUAL_QUALIFIERS at the regional: E6 did not race it, so stays home."""
    state = _state_field()
    assert 'E6' not in state
    assert {'E1', 'E2', 'E3', 'E4', 'E5'} <= state


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
