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


def test_mixed_relay_legs_are_the_teams_boys_and_girls():
    from collections import Counter
    from backend.athlete_catalog import resolve_relays
    ents = {'c': dict(members=Counter({'caleb-gsa': 9}), toks=['caleb', 'hale'], ays=[2006], unit='gsa', g='Boys'),
            'm': dict(members=Counter({'molly-gsa': 9}), toks=['molly', 'doherty'], ays=[2006], unit='gsa', g='Girls')}
    athletes = [dict(id='caleb-gsa', name='Caleb Hale', rows=9), dict(id='molly-gsa', name='Molly Doherty', rows=9)]
    relays = {'x': dict(unit='gsa', gender='Mixed', events=Counter({'Mixed 1320 Yard Sprint Medley Relay': 1}),
                        members=Counter({'rel-x': 1}), names=Counter({'Molly Doherty, Caleb Hale': 1}),
                        teams=Counter({'GSA': 1}), seasons={'Indoor'}, ays={2006})}
    out, n, placed = resolve_relays(relays, [['c'], ['m']], ents, athletes, {})
    assert placed == n == 2
    assert len(athletes) == 2                             # no relay-only copies of either runner


def test_coed_relay_under_a_boys_event_finds_its_girls():
    from collections import Counter
    from backend.athlete_catalog import resolve_relays
    ents = {'c': dict(members=Counter({'cam-gsa': 9}), toks=['cameron', 'gordon'], ays=[2017], unit='gsa', g='Boys'),
            'h': dict(members=Counter({'hanna-gsa': 9}), toks=['hanna', 'jordan'], ays=[2017], unit='gsa', g='Girls')}
    athletes = [dict(id='cam-gsa', name='Cameron Gordon', rows=9), dict(id='hanna-gsa', name='Hanna Jordan', rows=9)]
    relays = {'x': dict(unit='gsa', gender='Girls', events=Counter({'Girls 1600 Meter Sprint Medley Relay': 1}),
                        members=Counter({'rel-x': 1}), names=Counter({'Cameron Gordon, Hanna Jordan': 1}),
                        teams=Counter({'GSA': 1}), seasons={'Indoor'}, ays={2017})}
    out, n, placed = resolve_relays(relays, [['c'], ['h']], ents, athletes, {})
    assert placed == n == 2 and len(athletes) == 2


def test_relay_only_runner_on_boys_and_coed_relays_is_one_runner():
    from collections import Counter
    from backend.athlete_catalog import resolve_relays
    athletes = []
    def relay(sid, gender, names):
        return dict(unit='gsa', gender=gender, events=Counter({f'{gender} 1200 Meter Sprint Medley Relay': 1}),
                    members=Counter({sid: 1}), names=Counter({names: 1}), teams=Counter({'GSA': 1}),
                    seasons={'Indoor'}, ays={2017})
    relays = {'a': relay('rel-a', 'Boys', 'Brendan Penfold, Trevor Cochrane'),
              'b': relay('rel-b', 'Mixed', 'Brendan Penfold, Laura Liu')}
    resolve_relays(relays, [], {}, athletes, {})
    penfold = [a for a in athletes if a['name'] == 'Brendan Penfold']
    assert len(penfold) == 1 and penfold[0]['gender'] == 'Boys' and len(penfold[0]['relays']) == 2


def test_leg_matches_the_spelling_printed_for_that_team_first():
    # Ellsworth 2019: freshman Sarah Shea, and Sara Shea (a junior) whom the middle school
    # printed 'Sarah'; the high-school leg 'Sarah Shea' is the freshman
    from collections import Counter
    from backend.athlete_catalog import resolve_relays
    ents = {'s1': dict(members=Counter({'sara-ehs': 9}), toks=['sara', 'shea'], ays=[2019], unit='ehs', g='Girls'),
            's2': dict(members=Counter({'sara-ehs': 3}), toks=['sarah', 'shea'], ays=[2016], unit='ems', g='Girls'),
            'h': dict(members=Counter({'sarah-ehs': 1}), toks=['sarah', 'shea'], ays=[2019], unit='ehs', g='Girls')}
    athletes = [dict(id='sara-ehs', name='Sara Shea', rows=12), dict(id='sarah-ehs', name='Sarah Shea', rows=1)]
    relays = {'x': dict(unit='ehs', gender='Girls', events=Counter({'Girls 4x800 Meter Relay': 1}),
                        members=Counter({'rel-x': 1}), names=Counter({'Amie Lupo, Sarah Shea': 1}),
                        teams=Counter({'EHS': 1}), seasons={'Outdoor'}, ays={2019})}
    out, n, placed = resolve_relays(relays, [['s1', 's2'], ['h']], ents, athletes, {})
    assert 'sarah-ehs' in out[0]['legs']
    assert not any(a['id'].endswith('--relay') for a in athletes)
