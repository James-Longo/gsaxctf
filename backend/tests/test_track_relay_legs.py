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


def test_catalog_relays_link_runners():
    from collections import Counter
    from backend.athlete_catalog import resolve_relays
    ents = {'r': dict(members=Counter({'ripley-gsa': 9}), toks=['ripley', 'king', 'ofsiany'], ays=[2025], unit='gsa', g='Girls'),
            'c': dict(members=Counter({'cadence-gsa': 9}), toks=['cadence', 'pert'], ays=[2025], unit='gsa', g='Girls')}
    groups = [['r'], ['c']]
    athletes = [dict(id='ripley-gsa', name='Ripley King-Ofsiany', rows=9), dict(id='cadence-gsa', name='Cadence Pert', rows=9)]
    def relay(sid, names):
        return dict(unit='gsa', gender='Girls', events=Counter({'Girls 4x400 Meter Relay': 1}), members=Counter({sid: 1}),
                    names=Counter({names: 1}), teams=Counter({'GSA': 1}), seasons={'Outdoor'}, ays={2025})
    relays = {'a': relay('rel-a', 'Ripley King-Ofsiani, Cadence Pert, Ava Vardaros, Lu Mo'),
              'b': relay('rel-b', 'Ripley King-Ofsiany, Cadence Pert, Ava Vardaros, Lu Mo')}
    member_of = {}
    out, n, placed = resolve_relays(relays, groups, ents, athletes, member_of)
    assert len(out) == 1                                  # one team: the spellings are one runner
    assert sorted(out[0]['members']) == ['rel-a', 'rel-b']
    ava = next(a for a in athletes if a['name'] == 'Ava Vardaros')
    assert ava['relay_only'] and ava['relays'] == [out[0]['id']]
    assert athletes[0]['relays'] == [out[0]['id']]
    assert placed == n == 8
