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


def test_squad_letter_dropped_from_surname():
    import types
    from backend.scraper_v2 import Sub5ScraperV2 as RS
    me = types.SimpleNamespace(manual_fixes={})
    assert RS.normalize_athlete_name(me, 'Wilcox - A, Jessie') == 'Jessie Wilcox'
    assert RS.normalize_athlete_name(me, 'Landry -B, Moneca') == 'Moneca Landry'
    # the squad letter typed again as the first name: no first name was entered
    assert RS.normalize_athlete_name(me, 'Handcock - A-C, A') == 'Handcock'
    assert RS.normalize_athlete_name(me, 'Floster - A, A') == 'Floster'
    assert RS.normalize_athlete_name(me, 'Sweeney - A-C, AC') == 'Sweeney'
    assert RS.normalize_athlete_name(me, 'Hunter - A, Cynthia') == 'Cynthia Hunter'
    assert RS.normalize_athlete_name(me, 'Penney -, Bobby') == 'Bobby Penney'
    assert RS.normalize_athlete_name(me, 'Smith-Jones, Ann') == 'Ann Smith-Jones'
    # what PDFs and web pages leave in names
    for raw, want in (("Indra\u00c2 O'Donnell", "Indra O'Donnell"), ('Aiden Ho\ufb00man', 'Aiden Hoffman'),
                      ('Ashley\u2020 Lister\u2020\u2020', 'Ashley Lister'), ('Cormier \u2013', 'Cormier'), ('Leonardi\u2010', 'Leonardi'),
                      ('Booth-\u2010Howe', 'Booth-Howe'), ('Burgess \u2013 MacDonald', 'Burgess-MacDonald'),
                      ('Wilcox \u2013 A, Jessie', 'Jessie Wilcox'), ('Henry O\u201dShaughnessy', "Henry O'Shaughnessy"),
                      ('Sylvester\u00c2\u00a0Larsen', 'Sylvester Larsen'), ('Jos\u00e9 Pe\u00f1a', 'Jos\u00e9 Pe\u00f1a')):
        assert RS.normalize_athlete_name(me, raw) == want, (raw, RS.normalize_athlete_name(me, raw))


if __name__ == '__main__':
    for k, f in list(globals().items()):
        if k.startswith('test_'):
            f()
    print('ok')
