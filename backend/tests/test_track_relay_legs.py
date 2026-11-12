"""Relay legs resolve to the team's runners, whatever the spelling."""
from backend import track_postseason as tp
from backend.athlete_catalog import clean_name, leg_near, match_leg, relay_leg_names


def near(a, b):
    return leg_near(clean_name(a), clean_name(b))


def test_near_spellings():
    assert near('Ripley King-Ofsiani', 'Ripley King-Ofsiany')
    assert near('Ripley Kingofsiany', 'Ripley King-Ofsiany')
    assert near('R King-Ofsiany', 'Ripley King-Ofsiany')
    assert near('King-Ofsiany', 'Ripley King-Ofsiany')
    assert near('Zac Greaton', 'Zach Greaton')


def test_near_keeps_siblings_apart():
    assert not near('Sumner King-Ofsiany', 'Ripley King-Ofsiany')
    assert not near('Sam Bonsey', 'Kourtney Bonsey')
    assert not near('Joe Zuke', 'Wyatt Zuke')
    assert not near('Lee', 'Anna Lee')          # too short to stand alone


def _store():
    s = tp.Store()
    s.roster = {('gsa', 'Girls', 2025): {'ripley', 'lola', 'adams-l', 'adams-k'}}
    s.spell = {'ripley': {'ripley king ofsiany'}, 'lola': {'lola stratton'},
               'adams-l': {'lucy adams'}, 'adams-k': {'kate adams'}}
    return s


def test_leg_id():
    s = _store()
    assert s.leg_id('Ripley King-Ofsiani', 'gsa', 'Girls', 2025) == 'ripley'
    assert s.leg_id('Lola Stratton', 'gsa', 'Girls', 2026) == 'lola'      # the season after
    assert s.leg_id('Adams', 'gsa', 'Girls', 2025) is None                # two runners fit
    assert s.leg_id('Ripley King-Ofsiany', 'gsa', 'Boys', 2025) is None   # other gender


def test_leg_id_last_name_first():
    assert _store().leg_id('King-Ofsiany, Ripley', 'gsa', 'Girls', 2025) == 'ripley'


def test_leg_exact_a_season_away_beats_near():
    s = tp.Store()
    s.roster = {('be', 'Girls', 2003): {'kristen'}, ('be', 'Girls', 2004): {'jenn', 'kristen'}}
    s.spell = {'kristen': {'kristen adams', 'adams'}, 'jenn': {'jenn adams'}}
    assert s.leg_id('Jenn Adams', 'be', 'Girls', 2003) == 'jenn'
    assert s.leg_id('Adams', 'be', 'Girls', 2003) == 'kristen'      # surname alone, one runner that season


def test_relay_leg_names_last_first():
    assert relay_leg_names('Saucier, Taylor, Stivers, Harrison, McGhie, Ian, Merrill, Zach') == \
        ['Taylor Saucier', 'Harrison Stivers', 'Ian McGhie', 'Zach Merrill']
    assert relay_leg_names('A Bee, C Dee, E Eff, G Gee') == ['A Bee', 'C Dee', 'E Eff', 'G Gee']
