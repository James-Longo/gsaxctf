"""Parser regression checks (no network, no archive files needed).

Run:  python3 backend/tests/test_parsers.py      (or pytest, if installed)

Fixtures are small synthetic copies of real sub5 layouts; athlete names are
made up. Each test names the layout and the bug it pins down.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'backend'))

from backend.parser import Sub5ColumnParser  # noqa: E402
from backend.parsers.xcscores import parse_xc_team_scores  # noqa: E402
from backend.parsers.meetreport import MeetReportParser  # noqa: E402
from backend.parsers.xcrun import XCRunParser  # noqa: E402
from backend.parsers.looselist import LooseListParser  # noqa: E402
from backend.scraper_v2 import split_gender_suffix, hytek_header_meta  # noqa: E402
import qaqc  # noqa: E402


# Hy-Tek .txt export: no "Name Year School" ruler, a per-mile pace column on
# some rows, record/annotation marks, a garbled grade, unplaced DNF rows and
# the official Team Scores block.
HEADERLESS_TXT = """\
                      2025 Southern Regional  XC Championships - 10/25/2025
                                            Twin Brook
                                             Results

  Event 2  Boys 2.1 Mile Run CC

  1 Alden Fairweather         12 Marshwood       5:10.1   16:13.74R   1  *course record
  2 Bram Holloway             12 Deering         5:14.0   16:26.70    2
  3 Cyrus Pembrook            11 Scarborough     5:20.0   16:56.26    3
  4 Dorian Wexley             11 Deering         5:22.0   17:05.89    4
  5 Emmett Quarles            12 Marshwood       5:24.0   17:10.05    5
  6 Felix Ashgrove  *          FR Scarborough     5:25.0   17:19.87    6
  7 Gideon Thornbury          11 Deering         5:26.0   17:19.98    7
  8 Hollis Vantreese           9 Marshwood       5:27.0   17:21.28    8
  9 Ivo Brackenridge          S0 Scarborough     5:28.0   17:25.97    9
 10 Jasper Kettleworth        10 Deering         5:29.0   17:31.24   10
 11 Kellan Mossgrove          12 Marshwood       5:30.0   17:40.27   11
 12 Lucan Featherstone        11 Scarborough     5:31.0   17:41.82   12
 13 Milo Danforth             11 Deering         5:32.0   17:44.26   13
 14 Nash Ellery               10 Marshwood       5:33.0   17:45.93   14
 15 Otto Ravensworth          10 Scarborough     5:34.0   17:47.00   15
 -- Piers Wainfleet            9 Deering                     DNF

                                   Team Scores

   *1 Deering High School         36    2    4    7   10   13
      Total Time:  1:25:31.27
         Average:    17:06.25
   *2 Marshwood High School       39    1    5    8   11   14
      Total Time:  1:26:09.00
         Average:    17:13.80
    3 Scarborough HS 2025         45    3    6    9   12   15
"""


def test_headerless_hytek_txt():
    res = Sub5ColumnParser('south-a-boys.txt', text=HEADERLESS_TXT).parse()
    assert len(res['events']) == 1, res['events']
    ev = res['events'][0]
    # "2.1 Mile Run" must not collapse to the standard "1 Mile Run"
    assert ev['event'] == '2.1 Mile Run CC', ev['event']
    rows = ev['results']
    assert len(rows) == 16, len(rows)                      # 15 finishers + DNF
    assert rows[0]['result'] == '16:13.74'                 # not the 5:10.1 pace
    assert rows[0]['school'] == 'Marshwood'                # pace kept out of school
    assert rows[0]['grade'] == '12'
    assert rows[5]['athlete'] == 'Felix Ashgrove'          # stray '*' dropped
    assert rows[5]['school'] == 'Scarborough' and rows[5]['grade'] == 'FR'
    assert rows[8]['school'] == 'Scarborough'              # garbled 'S0' grade cell
    assert rows[-1]['result'] == 'DNF' and rows[-1]['school'] == 'Deering'
    assert all(r['school'] in ('Marshwood', 'Deering', 'Scarborough') for r in rows)


def test_xc_team_scores_and_verification():
    blocks = parse_xc_team_scores(HEADERLESS_TXT)
    assert len(blocks) == 1 and blocks[0]['gender'] == 'Boys'
    teams = blocks[0]['teams']
    assert [t['score'] for t in teams] == [36, 39, 45]
    # a team name ending in digits keeps them; the total is found by the sum
    assert teams[2]['team'] == 'Scarborough HS 2025' and teams[2]['places'][0] == 3
    res = Sub5ColumnParser('south-a-boys.txt', text=HEADERLESS_TXT).parse()
    parsed = {'events': res['events'], 'team_rankings': blocks}
    v = qaqc.xc_verify_parsed(parsed)
    assert v['status'] == 'verified', v
    # dropping a runner must break verification
    parsed['events'][0]['results'].pop(3)
    assert qaqc.xc_verify_parsed(parsed)['status'] == 'mismatch'


MEET_REPORT = """\
TEST XC MEET                                                                    MEET OFFICIALS
Somewhere, ME                                                                   Timing:
Host: Test High School                                                                                      OFFICIAL MEET REPORT
Friday, September 06, 2024                                                                                     printed: 9/6/2024 6:28 PM

 Race #1
 MEN (Varsity) • 5 Kilometers (3.11 Miles)                                                              Final Results
TEAM SCORING SUMMARY
Final Standings                   Score     Scoring Order                        Total     Avg.    Spread
  1   Alpha High School           15      1-2-3-4-5                            1:25:00 17:00        1:00.0   6   ROWE, Ned (CJ)   JR Beta Academy      6   18:00.10 5:47.0   3:36.0
  2   Beta Academy                40      6-7-8-9-10                           1:31:00 18:12        1:00.0

INDIVIDUAL RESULTS
Athlete                            YR Team                       Score   Time     Avg. Mile       Avg. kM
  1   ABBOT, Al                    SR Alpha High School          1     16:24.37 5:16.5          3:16.9
  2   BAKER, Bo                    JR Alpha High School          2     16:25.81 5:17.0          3:17.2
  3   CARR, Cy                        Alpha High School          3     16:44.46 5:23.0          3:20.9
  4   DUNN, Di                     SO Alpha High School          4     16:50.38 5:24.9          3:22.1
  5   EVANS, Ed                    SR Alpha High School          5     16:51.22 5:25.1          3:22.2
  7   GRAY, Gus                    SR Beta Academy               7     18:02.95 5:48.9          3:36.6
  8   HART, Hal                    JR Beta Academy               8     18:03.35 5:49.0          3:36.7
  9   IVES, Ike                    SR Beta Academy               9     18:07.73 5:50.5          3:37.5
 10   JONES, Jo                    SO Beta Academy              10     18:08.73 5:50.8          3:37.7
 11   KING, Kit                    SO Gamma School               -     18:16.81 5:53.4          3:39.4
"""


def test_meet_report_two_column_and_pace():
    p = MeetReportParser()
    assert MeetReportParser.matches(MEET_REPORT)
    res = p.parse(MEET_REPORT, 'bangor6sept2024.pdf', 'XC')
    ev = res['events'][0]
    assert ev['gender'] == 'Boys' and ev['event'] == '5k Run CC Varsity'
    rows = ev['results']
    assert len(rows) == 11, len(rows)
    assert rows[0]['result'] == '16:24.37'                 # not the pace columns
    assert rows[5]['athlete'] == 'Rowe, Ned'                # right-hand column, nickname
    assert rows[0]['athlete'] == 'Abbot, Al'                # dropped, capitals re-cased
    assert rows[5]['school'] == 'Beta Academy'
    assert rows[2]['grade'] == '' and rows[2]['school'] == 'Alpha High School'
    v = qaqc.xc_verify_parsed(res)
    assert v['status'] == 'verified', v


XCRUN = """\
                                 TEST MIDDLE SCHOOL
                                          BOYS RACE

                                     OFFICIAL RESULTS
                                          09/16/2025
  Readfield, ME                                                             MAR-MS-2

PLC BIB    PTS          NAME                               TEAM            TIME         PACE
 1   179    1    ABEL ACORN                   8   WINDSOR               :11:52.8          6:36
 2   165    2    BEN BIRCH                    7   READFIELD             :11:56.7          6:38
 3   182    3    CAL CEDAR                    8   WINDSOR               :12:50.0          7:07
 4   155    4    DAN DOGWOOD                  8   READFIELD             :13:01.7          7:14
 5   158    5    ELI ELM                      8   READFIELD             :13:04.3          7:15
 6   156    6    FINN FIR                     8   WINDSOR               :13:11.0          7:19
 7   154    7    GUS GUM                      7   READFIELD             :13:34.3          7:32
 8   185    0    HAL HAZEL                    8   GARDINER              :14:13.8          7:54
 9   162    8    IAN IVY                      7   WINDSOR               :14:16.9          7:56
10   176    9    JON JUNIPER                  6   READFIELD             :14:35.7          8:06
11   180   10    KAI KAPOK                    8   WINDSOR               :14:50.1          8:14
       11 COMPETITORS

        Place TEAM               Points     SCORES                                      Ave Time       Spread
          1   READFIELD              27        2     4     5     7     9           :12:54         2:39
          2   WINDSOR                28        1     3     6     8    10           :12:58         2:57
"""


def test_xcrun_layout():
    assert XCRunParser.matches(XCRUN)
    res = XCRunParser().parse(XCRUN, '9-16-25-Maranacook-Boys.pdf', 'XC')
    ev = res['events'][0]
    assert ev['gender'] == 'Boys'
    rows = ev['results']
    assert len(rows) == 11
    assert rows[0]['school'] == 'Windsor' and rows[0]['result'] == '11:52.8'
    assert rows[0]['athlete'] == 'Abel Acorn'           # capitals re-cased
    assert res['date'] == '2025-09-16'
    v = qaqc.xc_verify_parsed(res)
    assert v['status'] == 'verified', v
    # a stray PDF glyph on a name ('KingstonÊ Lavallee', 'AbbyÊ\\ Hopkins') is not part of it
    first = XCRUN.split('ABEL', 1)
    glued = XCRunParser().parse(first[0] + 'ABEL\u00ca\\' + first[1], '9-16-25-Maranacook-Boys.pdf', 'XC')
    assert glued['events'][0]['results'][0]['athlete'] == 'Abel Acorn', glued['events'][0]['results'][0]


def test_gender_suffix_split():
    flat = {'events': [
        {'athlete_name': f'A{i}', 'school': f"Morse {'F' if i % 3 == 0 else 'M'}",
         'event': 'Boys 4k Run CC Varsity', 'mark': '15:00.0', 'gender': 'Boys'}
        for i in range(12)]}
    moved = split_gender_suffix(flat)
    assert moved == 4
    girls = [r for r in flat['events'] if r['event'].startswith('Girls')]
    assert len(girls) == 4 and all(r['school'] == 'Morse' for r in flat['events'])
    grouped = {'events': [{'event': '4k Run CC', 'gender': 'Boys', 'is_relay': False,
                           'results': [{'athlete': f'A{i}', 'school': f"Lawrence {'F' if i < 3 else 'M'}",
                                        'result': '15:00.0'} for i in range(8)]}]}
    assert split_gender_suffix(grouped) == 3
    assert [e['gender'] for e in grouped['events']] == ['Boys', 'Girls']
    # 2021 spelling: "Mt. Blue HS B" / "Mt. Blue HS G" / "Monmouth Girls"
    mixed = {'events': [{'event': '3900 Yard Run CC', 'gender': 'Boys', 'is_relay': False,
                         'results': [{'school': s} for s in
                                     ['Mt. Blue HS B', 'Mt. Blue HS G', 'Monmouth Girls',
                                      'Monmouth Boys', 'Morse B', 'Morse G', 'Gardiner B']]}]}
    assert split_gender_suffix(mixed) == 3
    assert {r['school'] for e in mixed['events'] for r in e['results']} == \
        {'Mt. Blue HS', 'Monmouth', 'Morse', 'Gardiner'}
    # an ordinary race with one "... M" school is left alone
    plain = {'events': [{'event': '5k', 'gender': 'Boys', 'is_relay': False,
                         'results': [{'school': 'Camden Hills'}] * 7 + [{'school': 'Team M'}]}]}
    assert split_gender_suffix(plain) == 0


def test_header_meta_without_license_line():
    meta = hytek_header_meta(HEADERLESS_TXT)
    assert meta['venue'] == 'Twin Brook'
    assert meta['meet'] == '2025 Southern Regional  XC Championships'


def test_looselist_three_digit_places_and_scores_block():
    # places >= 100 lose their leading space; the Team Scores block that
    # follows must not turn into rows (school "Average:")
    names = ['Gideon Walters', 'Ames Brook', 'Carl Dune', 'Dov Eton', 'Ed Fyfe',
             'Fay Gold', 'Gus Hale', 'Hal Ives', 'Ike Jones', 'Jo Kent']
    text = 'Boys 5k Run CC\n' + '\n'.join(
        f"{' ' if i < 100 else ''}{i} {n:24} 11 Portland   18:{i - 90:02d}.00"
        for i, n in zip(range(95, 105), names)) + \
        '\nTeam Scores\n1 Portland High School 75 10 12 16 18 19\nAverage: 17:45.74\n'
    res = LooseListParser().parse(text, 'x.htm', 'XC')
    rows = [r for e in res['events'] for r in e['results']]
    assert len(rows) == 10, len(rows)
    assert not any('Average' in (r.get('school') or '') for r in rows)


def test_proper_case():
    from backend.parsers.base import proper_case_name, proper_case_team
    assert proper_case_name('MCDONALD, Ryan') == 'McDonald, Ryan'
    assert proper_case_name("O'NEIL-SMITH, PAT") == "O'Neil-Smith, Pat"
    assert proper_case_name('KING III, Bob') == 'King III, Bob'
    assert proper_case_team('MT. ARARAT') == 'Mt. Ararat'
    assert proper_case_team('MDI') == 'MDI' and proper_case_team('Bates') == 'Bates'


def test_track_points_accounting():
    # "Eddies" (nickname) + the relay's full name = one official team
    raw = {'Eddies': 40.0, 'Edward Little High School': 10.0, 'Cony': 30.0}
    official = [{'team': 'Edward Little HS', 'score': 50.0},
                {'team': 'Cony High School', 'score': 30.0}]
    worst, aliases = qaqc._assign_by_points(raw, official)
    assert worst == 0.0 and aliases['Eddies'] == 'Edward Little HS', (worst, aliases)



# ---------------------------------------------------------------------------
# XC zero-failure round (2026-10): one fixture per distinct fix
# ---------------------------------------------------------------------------

def _verify(res, blocks):
    return qaqc.xc_verify_parsed({'events': res['events'], 'team_rankings': blocks})


# Junior Olympic export: the gender comes after the distance, a Year (birth
# year) and Avg Mile column, X-prefixed exhibition (unattached) finishers.
YOUTH = """\
 Brewer High School                                          Hy-Tek's Meet Manager
            2003 Region 1 USATF Junior Olympic XC Champs - 11/23/2003
                               Last Completed Event

Event 6  4k Run CC Youth Boys
==================================================================================
    Name                    Year Team                  Avg Mile     Finals  Points
==================================================================================
  1 Ari Quill                 89 Unattached LI           5:18.2     X13:11
  2 Bo Dace                   89 Bay Bullets             5:27.7      13:35    1
  3 Cy Erne                   89 Pal Cruisers            5:28.7      13:37    2
  4 Di Foss                   89 Bay Bullets             5:32.5      13:47    3
  5 Ed Gant                   89 Pal Cruisers            5:36.5      13:57    4
  6 Fy Holt                   90 Bay Bullets             5:38.0      14:01    5
  7 Gil Ivo                   89 Pal Cruisers            5:38.5      14:02    6
  8 Hal Jex                   89 Bay Bullets             5:39.1      14:03    7
  9 Ian Kell                  89 Pal Cruisers            5:39.4      14:04    8
 10 Jo Lusk                   89 Bay Bullets             5:40.2      14:06    9
 11 Kip Mott                  90 Pal Cruisers            5:40.4      14:07   10

                                   Team Scores
=================================================================================
Rank Team                      Total    1    2    3    4    5   *6   *7   *8   *9
=================================================================================
   1 Bay Bullets                  25    1    3    5    7    9
   2 Pal Cruisers                 30    2    4    6    8   10
"""


def test_late_gender_event_header_and_exhibition():
    res = Sub5ColumnParser('youthb.htm', text=YOUTH).parse()
    assert len(res['events']) == 1
    ev = res['events'][0]
    assert ev['gender'] == 'Boys' and ev['event'] == '4k Run CC Youth', ev
    r0 = ev['results'][0]
    assert r0['result'] == '13:11' and r0.get('exhibition') and r0['school'] == 'Unattached LI'
    assert ev['results'][1]['school'] == 'Bay Bullets' and ev['results'][1]['result'] == '13:35'
    assert _verify(res, parse_xc_team_scores(YOUTH))['status'] == 'verified'


# KVAC championship: per-class sections inside one event, places restart
# at 1; the Team Scores block is split the same way; a Mixed JV event
# splits by gender ("Class A Results - Women").
KVAC = """\
Event 3  Mixed 5k Run CC
=======================================================================
    Name                    Year School                  Finals  Points
=======================================================================
Class A Results - Women
  1 Ames, Ann                 FR Alpha High          20:00.00    1
  2 Bean, Bea                 SO Beta High           20:10.00    2
  3 Cole, Cat                 JR Alpha High          20:20.00    3
  4 Dodd, Di                  SR Beta High           20:30.00    4
  5 Eddy, Em - V              FR Alpha High          20:40.00    5
  6 Fisk, Flo                 SO Beta High           20:50.00    6
  7 Gale, Gia                 JR Alpha High          21:00.00    7
  8 Hart, Hal                 SR Beta High           21:10.00    8
  9 Ince, Ivy                 FR Alpha High          21:20.00    9
 10 Jory, Jo                  SO Beta High           21:30.00   10
Class A Results - Men
  1 Kay, Kit                  FR Beta High           17:00.00    1
  2 Lamb, Lu                  SO Beta High           17:10.00    2
  3 Moss, Mo                  JR Alpha High          17:20.00    3
  4 Nash, Ned                 SR Beta High           17:30.00    4
  5 Orr, Oz                   FR Beta High           17:40.00    5
  6 Pike, Pat-1               SO Alpha High          17:50.00    6
  7 Quin, Q                   JR Beta High           18:00.00    7
  8 Rusk, Ray                 SR Alpha High          18:10.00    8
  9 Sams, Sy                  FR Alpha High          18:20.00    9
 10 Tull, Ty                  SO Alpha High          18:30.00   10

                                   Team Scores
=================================================================================
Rank Team                      Total    1    2    3    4    5   *6   *7   *8   *9
=================================================================================
Class A Results - Men
   1 Beta High School             19    1    2    4    5    7
   2 Alpha High School            36    3    6    8    9   10
Class A Results - Women
   1 Alpha High School            25    1    3    5    7    9
   2 Beta High School             30    2    4    6    8   10
"""


def test_class_sections_split_and_pair():
    from backend.scraper_v2 import _pair_xc_blocks
    res = Sub5ColumnParser('kvac04jv.htm', text=KVAC).parse()
    assert [(e['gender'], e.get('section'), len(e['results'])) for e in res['events']] == \
        [('Girls', 'Class A', 10), ('Boys', 'Class A', 10)], res['events']
    girls = res['events'][0]['results']
    assert girls[4]['athlete'] == 'Eddy, Em'          # "- V" tag dropped
    assert res['events'][1]['results'][5]['athlete'] == 'Pike, Pat'   # "-1" tag: kept row
    blocks = parse_xc_team_scores(KVAC)
    assert [(b['gender'], b['section']) for b in blocks] == [('Boys', 'Class A'), ('Girls', 'Class A')]
    _pair_xc_blocks(res['events'], blocks)
    assert [b['event_idx'] for b in blocks] == [1, 0]
    assert _verify(res, blocks)['status'] == 'verified'


# 2010 WMC: no "Event N", a bib-first ruler between the title and the rule
BIBFIRST = """\
Boys 3 Mile Run CC Varsity
      Comp#  Name                            School                           Time Points
=========================================================================================
    1   654  Ames, Al                        Fryeburg Academy             16:18.80
    2   861  Bean, Bo                        Waynflete School             16:25.00
    3   579  Cole, Cy                        Falmouth High School         16:28.00
    4   713  Dunn, Di                        Greely High School           16:57.00
    5   777  Eck, Ed                         Fryeburg Academy             17:11.00
"""


def test_bib_first_layout():
    res = Sub5ColumnParser('wmcvboys.htm', text=BIBFIRST).parse()
    rows = res['events'][0]['results']
    assert len(rows) == 5 and rows[0]['athlete'] == 'Ames, Al', rows[0]
    assert rows[0]['school'] == 'Fryeburg Academy' and rows[0]['result'] == '16:18.80'


def test_most_rows_parser_prefers_column_for_flat_hytek():
    from backend.scraper_v2 import _MostRowsParser
    from backend.parsers.column import ColumnStrategyParser
    from backend.parsers.hytek import HyTekSMAAParser
    r = _MostRowsParser([ColumnStrategyParser(), HyTekSMAAParser()]).parse(BIBFIRST, 'x.htm', 'XC')
    assert r['parser'] == 'ColumnStrategyParser' and len(r['events'][0]['results']) == 5


# Hy-Tek ties ("32" twice) whose team-place order is only in the points
# column; an individual entry with a blank points cell; A/B squads.
TIES = """\
Event 5  Girls 5k Run CC Class A
=======================================================================
    Name                    Year School                  Finals  Points
=======================================================================
  1 Ames, Ann                    Alpha                 20:00.00    1
  2 Bean, Bea                    Beta                  20:10.00    2
  3 Cole, Cat                    Alpha                 20:20.00    3
  4 Dodd, Di                     Beta                  20:30.00    4
  5 Eddy, Em                     Alpha                 20:40.00    5
  6 Fisk, Flo                    Beta                  20:50.00    6
  7 Gale, Gia                    Alpha                 21:00.00    7
  8 Hart, Hal                    Beta                  21:10.00    8
  9 Ince, Ivy                    Beta                  21:15.00
  9 Jory, Jo                     Alpha                 21:20.00   10
  9 Kemp, Kai                    Beta                  21:20.00    9

                                   Team Scores
=================================================================================
Rank Team                      Total    1    2    3    4    5   *6   *7   *8   *9
=================================================================================
   1 Alpha                        26    1    3    5    7   10
   2 Beta                         29    2    4    6    8    9
"""


def test_tie_order_and_individual_entry():
    res = Sub5ColumnParser('ties.htm', text=TIES).parse()
    rows = res['events'][0]['results']
    assert [r.get('team_place') for r in rows] == [1, 2, 3, 4, 5, 6, 7, 8, None, 10, 9]
    blocks = parse_xc_team_scores(TIES)
    assert _verify(res, blocks)['status'] == 'verified'
    # losing a scorer still fails
    del rows[3]
    assert _verify(res, blocks)['status'] != 'verified'


def test_ab_squads_by_printed_places():
    rows = [{'athlete': f'R{i}', 'school': s, 'result': f'20:{i:02d}.00', 'place': i, 'team_place': tp}
            for i, (s, tp) in enumerate([('MTA', 1), ('MTA', 2), ('Morse', 3), ('MTA', 4), ('MTA', 5),
                                         ('MTA', 6), ('Morse', 7), ('MTA', 8), ('MTA', 9), ('MTA', 10),
                                         ('Morse', 11), ('Morse', 12), ('Morse', 13), ('MTA', 14)], 1)]
    block = {'kind': 'xc', 'gender': 'Boys', 'teams': [
        {'team': 'MTA HIGH SCHOOL A', 'score': 18.0, 'places': [1, 2, 4, 5, 6]},
        {'team': 'MORSE HIGH SCHOOL A', 'score': 46.0, 'places': [3, 7, 11, 12, 13]},
        {'team': 'MTA HIGH SCHOOL B', 'score': 49.0, 'places': [8, 9, 10, 14]}]}
    ev = {'event': '5k Run CC', 'gender': 'Boys', 'results': rows}
    v = qaqc.xc_verify_parsed({'events': [ev], 'team_rankings': [block]})
    assert v['status'] == 'verified', v
    # a gap in the printed places (a scorer lost) must fail
    del rows[3]
    assert qaqc.xc_verify_parsed({'events': [ev], 'team_rankings': [block]})['status'] != 'verified'


def test_checker_fillers_truncation_and_merged_spellings():
    # one team printed two ways ("Hall-Dale High Schoo" / "Hall-Dale High")
    schools = ['Alpha', 'Alpha', 'Beta', 'Hall-Dale High Schoo', 'Alpha', 'Beta', 'Alpha',
               'Hall-Dale High', 'Beta', 'Alpha', 'Beta', 'Hall-Dale High Schoo', 'Beta',
               'Hall-Dale High', 'Hall-Dale High Schoo']
    rows = [{'athlete': f'R{i}', 'school': s, 'result': f'20:{i:02d}.00', 'place': i}
            for i, s in enumerate(schools, 1)]
    merged = [dict(r, school='Hall-Dale High') for r in rows if r['school'].startswith('Hall')]
    places = qaqc._xc_team_places([dict(r, school='Hall-Dale High') if r['school'].startswith('Hall')
                                   else r for r in rows], 7, 5)
    assert len(merged) == 5 and places['Hall-Dale High'] == [4, 8, 12, 14, 15]
    block = {'kind': 'xc', 'gender': 'Boys', 'teams': [
        {'team': t, 'score': float(sum(v[:5])), 'places': v} for t, v in places.items()]}
    ev = {'event': '5k Run CC', 'gender': 'Boys', 'results': rows}
    assert qaqc.xc_verify_parsed({'events': [ev], 'team_rankings': [block]})['status'] == 'verified'
    # a fixed-width line that lost its last place ("... 33 34 3")
    blocks = parse_xc_team_scores("""
Event 2  Boys 5k Run CC
                                   Team Scores
   1 Alpha                        25    1    2    5    7   10   13   2
""")
    t = blocks[0]['teams'][0]
    assert t.get('truncated') and t['places'] == [1, 2, 5, 7, 10, 13], t
    # filler places for a short team ("1 2 3 16 16") are not runners
    short = {'kind': 'xc', 'gender': 'Boys', 'teams': [{'team': 'X', 'score': 38.0, 'places': [1, 2, 3, 16, 16]}]}
    rows2 = [{'athlete': f'Q{i}', 'school': 'X' if i < 4 else f'S{i}', 'result': f'19:{i:02d}.0', 'place': i}
             for i in range(1, 16)]
    assert qaqc._xc_verify_block(short, rows2)['status'] == 'verified'


# XCRun: girls page 2 (DNF only) then the boys race; ages not grades;
# PTS column; distance from time / PACE; junior-high meet level.
XCRUN_TWO = """\
                                       EDWARD LITTLE TEST MEET
  RACE ID: ELXC-1                                       GIRLS
                                              OFFICIAL RESULTS
PLC BIB     PTS              NAME                           TEAM                  TIME     PACE
  1    83     1    ANN AMES                   16   EL                         :19:07.7      6:10
  2    70     2    BEA BEAN                   15   MT ARARAT                  :20:44.3      6:41
  3    75     3    CAT COLE                   17   EL                         :21:28.7      6:55
  4    85     4    DI DODD                     0   MT ARARAT                  :21:49.2      7:02
  5   103     5    EM EDDY                     0   EL                         :21:57.5      7:05
  6    92     6    FLO FISK                    0   MT ARARAT                  :22:49.1      7:21
                                       EDWARD LITTLE TEST MEET
  RACE ID: ELXC-1                                       GIRLS
                                              OFFICIAL RESULTS
PLC BIB     PTS              NAME                           TEAM                  TIME
DNF   100     0    GIA GALE                    0   EL                         :   : 0.0
                                       EDWARD LITTLE TEST MEET
                                                                  BOYS
                                              OFFICIAL RESULTS
PLC BIB   PTS        NAME               TEAM              TIME
 1    7    1    HAL HART             MT ARARAT         :17:38.9
 2   23    2    IAN INCE             MT ARARAT         :17:51.7
 3    5    3    JO JORY              EL                :17:53.7
"""


def test_xcrun_race_split_ages_and_distance():
    res = XCRunParser().parse(XCRUN_TWO, 'elxc2018-2.pdf', 'XC')
    assert [(e['gender'], len(e['results'])) for e in res['events']] == [('Girls', 7), ('Boys', 3)]
    g = res['events'][0]
    assert (g['results'][-1]['athlete'], g['results'][-1]['result']) == ('Gia Gale', 'DNF')   # the DNF page joins its race
    assert g['event'] == '5k Run CC', g['event']            # 19:07.7 / 6:10 per mile
    assert all(r['grade'] == '' for r in g['results'])      # 15-17 = ages
    assert g['results'][0]['team_place'] == 1 and g['results'][0]['place'] == 1


XCRUN_JH = """\
                                      BRUNSWICK JUNIOR HIGH XC
 RACE ID: 20180918-1                              GIRLS RACE
                                             OFFICIAL RESULTS
PLC BIB    PTS              NAME                         TEAM                    TIME     PACE
 1   389     1    ZOE ADAMS                   8   BRUNSWICK                   :13:18.4     7:23
 2   374     2    KAY BELL                    7   BRUNSWICK                   :13:38.1     7:34
 3   362     3    GEN COLE                    7   MT ARARAT                   :13:50.5     7:41
 3   363     3    LIV DOW                     6   MT ARARAT                   :13:50.5     7:41
 5   388     5    HAN EVE                     8   BRUNSWICK                   :14:00.7     7:47
"""


def test_xcrun_junior_high_grades_distance_and_ties():
    res = XCRunParser().parse(XCRUN_JH, 'Girls-Results-9-18-18-1.pdf', 'XC')
    ev = res['events'][0]
    assert res.get('meet_level') == 'ms'
    assert ev['event'] == '1.8 Mile Run CC', ev['event']
    assert [r['grade'] for r in ev['results']] == ['8', '7', '7', '6', '8']
    assert len(ev['results']) == 5                          # tied place 3 kept twice


# Spreadsheet export: two sheets (boys, girls) each First | Last | School |
# Time, a summary sheet repeating the rows, a constant "TIME OUT" column.
SHEETS = """<html><body>
<h1>Sheet 1: <em>Ind. Boys</em></h1>
<table>
<tr><td>Place</td><td>First</td><td>Last</td><td>School</td><td>Time Out</td><td>Time</td></tr>
<tr><td>1</td><td>Jeremy</td><td>Sands</td><td>Fal</td><td>0:00:00</td><td>17:08</td></tr>
<tr><td>2</td><td>John</td><td>Auer</td><td>Fal</td><td>0:00:00</td><td>17:30</td></tr>
<tr><td>3</td><td>Benjamin</td><td>Wyman</td><td>Lew</td><td>0:00:00</td><td>17:35</td></tr>
<tr><td>4</td><td>Michael</td><td>Piers</td><td>Lew</td><td>0:00:00</td><td>0:17:38</td></tr>
</table>
<h1>Sheet 2: <em>Ind. Girls</em></h1>
<table>
<tr><td>Place</td><td>First</td><td>Last</td><td>School</td><td>Time</td></tr>
<tr><td>1</td><td>Sarah</td><td>Pasch</td><td>Fal</td><td>19:03</td></tr>
<tr><td>2</td><td>Emily</td><td>Teklu</td><td>Lew</td><td>19:33</td></tr>
<tr><td>3</td><td>Jessica</td><td>Wynn</td><td>Fal</td><td>19:58</td></tr>
</table>
<h1>Sheet 3: <em>Summary</em></h1>
<table>
<tr><td>1</td><td>Jeremy</td><td>Sands</td><td>Fal</td><td>17:08</td></tr>
<tr><td>2</td><td>John</td><td>Auer</td><td>Fal</td><td>17:30</td></tr>
<tr><td>3</td><td>Benjamin</td><td>Wyman</td><td>Lew</td><td>17:35</td></tr>
</table>
</body></html>"""


def test_spreadsheet_sheets_first_last_and_constant_columns():
    from backend.parsers.spreadsheet import SpreadsheetTableParser
    res = SpreadsheetTableParser().parse(SHEETS, 'meet.html', 'XC')
    assert [(e['gender'], len(e['results'])) for e in res['events']] == [('Boys', 4), ('Girls', 3)]
    b = res['events'][0]['results']
    assert b[0] == {'athlete': 'Sands, Jeremy', 'school': 'Fal', 'result': '17:08',
                    'grade': '', 'type': 'Finals', 'place': 1}, b[0]      # (the Place column, read)
    assert b[3]['result'] == '17:38'                        # 0:17:38 h:mm:ss


def test_event_gender_fixes_and_sibling_drop(tmp=None):
    import tempfile
    from backend.scraper_v2 import (fix_event_gender_from_label, fix_event_gender_from_names,
                                    drop_sibling_gender_events)
    data = {'events': [{'event': '3k Run CC 9-10 Division Boys', 'gender': 'Girls', 'results': []}]}
    fix_event_gender_from_label(data)
    assert data['events'][0]['gender'] == 'Boys'
    names = ['Ian Moss', 'Luca Reed', 'Cameron Holt', 'John Ames', 'Peter Bell', 'Ryan Cole',
             'Kevin Dodd', 'Thomas Eck', 'Mark Fisk']
    data = {'events': [{'event': '5K Cross Country', 'gender': 'Girls',
                        'results': [{'athlete': n} for n in names]}]}
    fix_event_gender_from_names(data)
    assert data['events'][0]['gender'] == 'Boys' and data['events'][0]['gender_from_names']
    d = tempfile.mkdtemp()
    for fn in ('falmouthboys_august26.html', 'falmouthgirls_august26.html'):
        open(os.path.join(d, fn), 'w').close()
    data = {'events': [{'event': 'x', 'gender': 'Boys', 'results': [{}] * 6},
                       {'event': 'x', 'gender': 'Girls', 'results': [{}] * 6},
                       {'event': 'x', 'gender': 'Girls', 'results': [{}]}], 'team_rankings': []}
    drop_sibling_gender_events(data, os.path.join(d, 'falmouthboys_august26.html'))
    # the sibling's whole race goes; a stray girl in the boys' race stays
    assert [e['gender'] for e in data['events']] == ['Boys', 'Girls']


# Page 2 of a Hy-Tek PDF: the column positions drift right, so the page-1
# ruler slices marks; a long name pushes year and school over; the event
# header repeats without the "...." continuation mark.
DRIFT = """\
  Event 3   Boys 3.1 Mile Run CC VARSITY
=======================================================================
    Name                    Year School                   Finals Points
=======================================================================
  1 Al Ames                   JR Orono High School     17:33.04    1
  2 Bo Bean                   JR Caribou High School   17:38.75    2
  3 Cy Cole                   SR Orono High School     17:46.57    3
  4 Di Dunn                   SR Caribou High School   17:56.31    4
  5 Ed Eck                    SO Orono High School     18:00.30    5
  6 Nicholas Dieffenbacher-Krall FR Caribou High School  18:10.30    6
Event 3    Boys 3.1 Mile Run CC VARSITY
  7 Fy Fisk                        SR Orono High School          18:20.23       7
  8 Gil Gale                       SR Caribou High School        18:30.58       8
  9 Hal Hart                       SR Orono High School          18:40.55       9
 10 Ian Ince                       JR Caribou High School        18:50.55      10
"""


def test_page_drift_overflow_and_split_header():
    res = Sub5ColumnParser('ot.pdf', text=DRIFT).parse()
    assert len(res['events']) == 1, [len(e['results']) for e in res['events']]
    rows = res['events'][0]['results']
    assert len(rows) == 10
    assert rows[5]['athlete'] == 'Nicholas Dieffenbacher-Krall' and rows[5]['school'] == 'Caribou High School'
    assert rows[5]['grade'] == 'FR'
    assert rows[6]['result'] == '18:20.23' and rows[6]['school'] == 'Orono High School'
    assert [r['team_place'] for r in rows] == list(range(1, 11))


UNTIMED = """\
Event 2  Boys 1 Mile Run CC 6TH
=======================================================================
    Name                    Year School                  Finals  Points
=======================================================================
  1 Chrimes, Luke                Wells
  2 Mann, Blake               FR York Middle School                1
  3 Stauble, Harper              Kittery                           2
  4 Fitz, Van                    Kittery                           3
  5 McKellar, Wyatt              Kennebunk
  6 Legere, Cale                 York Middle School                4
"""


def test_untimed_race_rows():
    res = Sub5ColumnParser('Results-F1.htm', text=UNTIMED).parse()
    rows = res['events'][0]['results']
    assert len(rows) == 6 and rows[1] == {'athlete': 'Mann, Blake', 'school': 'York Middle School',
                                          'result': '', 'grade': 'FR', 'type': 'Finals',
                                          'place': 2, 'team_place': 1}, rows[1]


RACETAB = """\
                    Varsity Boys Three Mile Run Finals
==========================================================================
    Name                      Yr Team                           Time   Pts
==========================================================================
  1 Tim Ames                     Falmouth                   16:12.00     1
  2 Tom Bean                     Cape Elizabeth             16:19.00     2
  3 Jon Cole                     Falmouth                   16:50.00     3

                 Varsity Boys Three Mile Run Team Scores
==========================================================================
                   Varsity Girls Three Mile Run Finals
==========================================================================
    Name                      Yr Team                           Time   Pts
==========================================================================
  1 Kel Dodd                  12 Cape Elizabeth             19:40.00     1
  2 Meg Eck                      Falmouth                   20:19.00     2
  3 Emma Fisk                    Cape Elizabeth             20:51.00     3
"""


def test_racetab_headers_and_number_words():
    res = Sub5ColumnParser('cape_sept3.html', text=RACETAB).parse()
    assert [(e['gender'], e['event'], len(e['results'])) for e in res['events']] == \
        [('Boys', '3 Mile Run Varsity', 3), ('Girls', '3 Mile Run Varsity', 3)], res['events']


ALUMNI = """\
  Event 1 Mixed 2.7 Mile Run CC
=======================================================================
    Name                     Age Team                    Finals Points
=======================================================================
  1 Teanne Ewings            W12 ghca                  12:05.10
  2 Thomas Beck              M40 Beck Strong           13:31.70
  3 Leanne Ross              W13 ghca                  14:44.10
  4 Dylan Marr               M18 Dark Tag              15:27.90
  5 Jamie Bell               M   Bells                 18:39.20
"""


def test_mixed_race_split_by_sex_cell():
    res = Sub5ColumnParser('alumni.pdf', text=ALUMNI).parse()
    assert [(e['gender'], [r['athlete'] for r in e['results']]) for e in res['events']] == [
        ('Girls', ['Teanne Ewings', 'Leanne Ross']),
        ('Boys', ['Thomas Beck', 'Dylan Marr', 'Jamie Bell'])], res['events']
    assert res['events'][0]['results'][0]['school'] == 'ghca'


def test_meet_report_team_place_suffix_and_quotes():
    text = MEET_REPORT.replace('SR Alpha High School          1     16:24',
                               'SR Alpha High School (1)      1     16:24').replace(
        'BAKER, Bo   ', 'O"DEA, Bo   ')
    res = MeetReportParser().parse(text, 'x.pdf', 'XC')
    rows = res['events'][0]['results']
    assert rows[0]['school'] == 'Alpha High School' and rows[0]['team_place'] == 1
    assert rows[1]['athlete'] == "O'Dea, Bo", rows[1]


def test_scores_block_bare_results_split():
    blocks = parse_xc_team_scores("""
                                    Team Scores
Results
   1 Bangor Christian Schools     38    3    5    8    9   13   20
   2 Orono High School            54    2    4   10   16   22   26
Results
   3 Lee Academy                 107   12   17   23   25   30   31
Results
   1 Caribou High School          41    4    5    8   10   14   22   28
   2 Ellsworth High School        46    1    9   11   12   13   16   18
""")
    assert [[t['team'] for t in b['teams']] for b in blocks] == [
        ['Bangor Christian Schools', 'Orono High School', 'Lee Academy'],
        ['Caribou High School', 'Ellsworth High School']]


def test_normalize_grade_middle_school():
    from backend.parser import normalize_grade
    assert [normalize_grade(g) for g in ('6', '7', '8t', '8th', '16', 'Jr', '4')] == \
        ['6', '7', '8', '8', '', 'JR', '']



# ---------------------------------------------------------------------------
# Long-tail layouts (zero-error round 2)

def _rows(res, i=0):
    return res['events'][i]['results']


def test_ruler_table_columns_and_sex_split():
    """RunScore "=====" ruler: columns cut by the ruler; a co-ed list with a
    sex column becomes a Girls and a Boys race; distance from the title."""
    from backend.parsers.rulertable import RulerTableParser
    text = (
        "                 County Middle School XC Festival\n"
        "                              2 Miles\n"
        "Place TmPl No.  Name                          G School                    Mtime\n"
        "===== ==== ==== ============================= = ========================= =====\n"
        "    1    1  738 ANDREW WILSOM                 M BRUNSWICK MIDDLE SCHOOL   12:35\n"
        "    2    1  691 CLARA JACKMOND                F BRUNSWICK MIDDLE SCHOOL   13:24\n"
        "    3    2  692 PETER JACKMOND                M FALMOUTH MIDDLE SCHOOL    13:30\n")
    res = RulerTableParser(None).parse(text, 'festival.htm', 'XC')
    by_g = {e['gender']: e for e in res['events']}
    assert by_g['Boys']['event'] == '2 Mile Run CC', by_g['Boys']['event']
    assert [r['place'] for r in by_g['Boys']['results']] == [1, 3]
    assert by_g['Girls']['results'][0]['athlete'] == 'Clara Jackmond'
    assert by_g['Boys']['results'][0]['team_place'] == 1


def test_easter_team_table_block():
    """Randy Easter pages: the team table lists every team's scoring places,
    paired to the race (event_idx 0); distance read off time / pace."""
    from backend.parsers.easter import EasterParser
    text = (
        "Leavitt Boys / Sept. 14, 2007 / Sunny Results by Randy Easter\n"
        "PLACE  TEAM       POINTS  PLACES OF FINISHERS     AVG. TIME  SPREAD\n"
        "  1   Mt. Blue      15    1    2    3    4    5   18:08   2:01\n"
        "  2   Leavitt       40    6    7    8    9   10   19:08   2:01\n"
        "      PLACE SCORE     FINISHER          TIME    PACE        TEAM\n"
        + ''.join(f"  {300 + k}  {k}  {k}  Runner{chr(65 + k)} Smith   {16 + k}:00   {5 + k // 10}:{(k * 7) % 60:02d}  "
                  f"{'Mt. Blue' if k <= 5 else 'Leavitt'}\n" for k in range(1, 11)))
    res = EasterParser(None).parse(text, 'leavittboys.htm', 'XC')
    assert res['events'][0]['gender'] == 'Boys'
    assert len(_rows(res)) == 10 and _rows(res)[0]['team_place'] == 1
    b = res['team_rankings'][0]
    assert b['event_idx'] == 0 and b['teams'][0]['places'] == [1, 2, 3, 4, 5]


def test_header_table_implicit_place_finish_and_dotted_times():
    """Sheets with no place header ("First Name Last Name School TIME"),
    a FINISH place column beside TIME, and minutes.seconds typed with dots."""
    from backend.parsers.headertable import HeaderTableParser
    h = HeaderTableParser(None)
    a = ("            First Name Last Name          School               TIME\n"
         "       1    Jilly       Richards          Edward Little      12:29:00\n"
         "       2    Molly       McGrain           Maranacook         12:51:00\n"
         "       3    Kara        Cullen            Mt. Blue           12:58:00\n")
    r = h.parse(a, 'relaysgirls.pdf', 'XC')
    assert [(x['place'], x['athlete'], x['result']) for x in _rows(r)][:2] == [
        (1, 'Richards, Jilly', '12:29'), (2, 'McGrain, Molly', '12:51')], _rows(r)
    b = ("FINISH      ATHLETE                 SCHOOL        TIME         SCORES\n"
         "          1 Erin Jensen             Waterville           10.02 Carrabec 53\n"
         "          2 Bria Lespere            Carrabec             10.51 Sandy River 54\n"
         "          3 Jade Grey               Lawrence              11.3 Waterville 67\n")
    r = h.parse(b, 'msgirls.pdf', 'XC')
    assert [(x['athlete'], x['school'], x['result']) for x in _rows(r)] == [
        ('Erin Jensen', 'Waterville', '10:02'), ('Bria Lespere', 'Carrabec', '10:51'),
        ('Jade Grey', 'Lawrence', '11:30')], _rows(r)


def test_header_table_fixed_width_wrap_and_side_by_side():
    """Hy-Tek individual report: names run into the school (one space or
    none), long names wrap the row; and two lists side by side that both
    start at 1 are two races, gendered by the titles over them."""
    from backend.parsers.headertable import HeaderTableParser
    h = HeaderTableParser(None)
    a = (" Place   Name     Year   School                                                 Final        Points\n"
         "   1     Erin Jensen     Waterville Junior High School                      10:32.40            1\n"
         "   2     Regan Billings Skowhegan Middle School                             13:56.25            2\n"
         "   3     Elizabeth Morrisset\n"
         "                         Waterville Junior High School                      14:16.88            3\n"
         "   4     Miranda SullivanWaterville Junior High School                      16:35.34            4\n")
    r = h.parse(a, 'msgirls_oct12.pdf', 'XC')
    got = [(x['athlete'], x['school'], x.get('team_place')) for x in _rows(r)]
    assert got == [('Erin Jensen', 'Waterville Junior High School', 1),
                   ('Regan Billings', 'Skowhegan Middle School', 2),
                   ('Elizabeth Morrisset', 'Waterville Junior High School', 3),
                   ('Miranda Sullivan', 'Waterville Junior High School', 4)], got
    b = ("  Girls Results                                     Boys Results\n"
         "  Name                 School      Time             Name                  School      Time\n"
         " 1 Rhia LaPlant        Skowhegan      22:10:00    1 Eben Hodgkin          EA           16:32:00\n"
         " 2 Marisa Bovey        EA             22:33:00    2 Jarod Lenfast         EA           18:48:00\n"
         " 3 Tess Morin          MCI            23:01:00    3 Sam Gachaga           MCI          18:50:00\n"
         "                                                  4 Ted Wiles             EA           19:02:00\n")
    r = h.parse(b, 'erskine.pdf', 'XC')
    assert [(e['gender'], len(e['results'])) for e in r['events']] == [('Girls', 3), ('Boys', 4)], r['events']


def test_xclist_columns_pages_and_typed_times():
    """Hand-typed lists: a girls' title heading the right column of a
    two-column page; a race continued over a page break under its title
    again; "20;03" and "23:07:00" times; team code first ("M-W  J. Pierce")."""
    from backend.parsers.xclist import XCListParser
    x = XCListParser(None)
    left = [f"  {k} Runner{chr(64 + k)}, Bob      Y {17 + k // 3}:{(k * 7) % 60:02d}" for k in range(1, 10)]
    right = ["", "GIRLS' RESULTS", ""] + [f"  {k} Lady{chr(64 + k)}, Ann     T {22 + k}:1{k}" for k in range(1, 7)]
    page = ["BOYS' RESULTS"] + [l.ljust(40) + (right[i] if i < len(right) else '') for i, l in enumerate(left)]
    r = x.parse('\n'.join(page), 'meet.pdf', 'XC')
    assert [(e['gender'], len(e['results'])) for e in r['events']] == [('Boys', 9), ('Girls', 6)], r['events']
    text = ("Boys\n" + ''.join(f"{k}. Runner{chr(64 + k)}  Gorham   {16 + k}:{10 + k}\n" for k in range(1, 6))
            + "\fBoys\n" + ''.join(f"{k}. Runner{chr(64 + k)}  Gorham   {16 + k}:{10 + k}\n" for k in range(6, 9)))
    r = x.parse(text, 'gorham.pdf', 'XC')
    assert len(r['events']) == 1 and len(_rows(r)) == 8
    text = ("Place  Points  Team   Name           Time\n"
            " 1      1       W     A. Hororr      16:52\n"
            " 2      2      M-W    J. Pierson     16;54\n"
            " 3      3      NYA    E. Kendal      17:06:00\n"
            " 4      4      NYA    C. Regin       17:48\n"
            " 5      5       W     J. Espey       17:51\n")
    r = x.parse(text, 'nyaboys.pdf', 'XC')
    assert [(q['athlete'], q['school'], q['result']) for q in _rows(r)][:3] == [
        ('A. Hororr', 'W', '16:52'), ('J. Pierson', 'M-W', '16:54'), ('E. Kendal', 'NYA', '17:06')], _rows(r)


def test_xclist_relay_totals_and_name_team_cells():
    """Relay meets: the teams' combined times are no runners; the legs'
    "Name, Team" cells split at the comma."""
    from backend.parsers.xclist import XCListParser
    text = ("2006 SMAA Relays\n"
            "       Girls Team Results            Girls Indiv. Results\n"
            "      Team         Time              Name,Team Time\n"
            "1.     Scarboro         49:47   1. Jessemin, Scarboro            8:47\n"
            "2.     McAuly           53:06   2. Pagani, Bonny Eagle           9:20\n"
            "3.     Kennebunk        53:26   3. Saldana, Scarboro             9:31\n"
            "4.     Cheverus         54:12   4. Lemay, Thornton Academy       9:40\n"
            "5.     Westbrook        56:14   5. Groth, Cheverus               9:52\n")
    r = XCListParser(None).parse(text, 'smaarelaysteam.pdf', 'XC')
    assert len(r['events']) == 1, r['events']
    assert [(q['athlete'], q['school']) for q in _rows(r)][:2] == [('Jessemin', 'Scarboro'), ('Pagani', 'Bonny Eagle')]


def test_direct_athletics_college_results():
    from backend.parsers.directathletics import DirectAthleticsParser
    text = (
        "Brewer Timing Services                                   DirectAthletics MeetPro\n"
        "                     State Cross-Country Championship\n"
        "Women's 5000 Meters\n"
        "   1 Bates                     15       18:00      1:30:00      0:20.0   1    2    3    4    5\n"
        "   2 Colby                     40       19:00      1:35:00      0:20.0   6    7    8    9   10\n"
        "==========================================================================================\n"
        "  Pl Athlete                 Yr Team                      Score       Time  Avg. Mile    Avg. kM\n"
        "==========================================================================================\n"
        + ''.join(f"  {k:2d} {'RUNNER, Ann' + chr(64 + k):23s} SO {'Bates' if k <= 5 else 'Colby':25s}{k:5d}   "
                  f"{17 + k // 2}:{10 + k}.00     5:40.0     3:30.0\n" for k in range(1, 11))
        + "  -- LATE, Kim                FR Colby                                 DNS        ---        ---\n")
    r = DirectAthleticsParser(None).parse(text, 'Womens-State.txt.htm', 'XC')
    ev = r['events'][0]
    assert ev['gender'] == 'Girls' and ev['event'] == '5k Run CC' and len(ev['results']) == 10
    assert ev['results'][0]['athlete'].startswith('Runner, Ann') and ev['results'][0]['grade'] == 'SO'
    assert ev['results'][0]['team_place'] == 1 and ev['results'][0]['school'] == 'Bates'
    assert r['team_rankings'][0]['teams'][1]['places'] == [6, 7, 8, 9, 10]


def test_team_place_grid_blocks():
    """Team scores printed as a grid of places ("1st 14 1 5 / TOTAL"),
    one column per team; a team name may run one space into the next."""
    from backend.parsers.teamgrid import team_grid_blocks
    text = (
        "PLACE   NAME            SCHOOL        TIME            TEAM SCORES\n"
        "1       Southerd        Gorham        18:41    SCHOOL Gorham Bonny Eagle   Cheverus\n"
        "2       Foshey          Cheverus      18:57    1st    1       5            2\n"
        "3       Fostor          Gorham        18:59    2nd    3       6            4\n"
        "4       Dundes          Cheverus      19:00    3rd    7       15           10\n"
        "5       Swet            Bonny Eagle   19:15    4th    8       18           12\n"
        "6       Hugo            Bonny Eagle   19:33    5th    9       19           14\n"
        "7       Colett          Gorham        19:42\n"
        "8       Rossignal       Gorham        19:55    TOTAL   28     63           42\n")
    b = team_grid_blocks(text, 'Boys')
    assert len(b) == 1 and b[0]['gender'] == 'Boys'
    assert [(t['team'], t['places']) for t in b[0]['teams']] == [
        ('Gorham', [1, 3, 7, 8, 9]), ('Cheverus', [2, 4, 10, 12, 14]), ('Bonny Eagle', [5, 6, 15, 18, 19])]


def test_xcrun_oa_location_layout_sections():
    """XCRun "PLC NAME LOCATION BIB OA-PLC TEAM TIME BEHIND" pages split by
    "HSG - H.S. GIRLS" sections; a one-runner wheelchair section printed
    last does not take the race's team-score page."""
    text = (
        "  OFFICIAL RESULTS\n  TRIPP MIDDLE SCHOOL\n  BOYS RACE                                09/28/2017\n"
        "                                                  OA\n"
        "PLC     NAME                 LOCATION      BIB    PLC TEAM                    TIME            BEHIND\n"
        "\n                         MSB - MIDDLE SCHOOL BOYS\n"
        + ''.join(f" {k}    RUNNER NUMBER{chr(64 + k)}                      {200 + k}     {k} "
                  f"{'BRUNSWICK' if k % 2 else 'AUBURN':20s}:1{k}:08.8        : 1:14.0\n" for k in range(1, 9))
        + "\n                         WCH - Wheelchair Divison\n"
          "  1   ROLLING RUNNER                        253     9 TRIPP               :20:01.6        :    : 0.0\n"
          "\n 09/28/2017                              BOYS RACE\n"
          "        Place TEAM              Points     SCORES                                    Ave Time       Spread\n"
          "          1   BRUNSWICK             25      1      3     5         7      9           :12:27         2:01\n")
    r = XCRunParser(None).parse(text, 'TrippBoysResults.pdf', 'XC')
    assert [len(e['results']) for e in r['events']] == [8, 1], r['events']
    assert r['events'][0]['results'][0]['athlete'] == 'Runner Numbera' or \
        r['events'][0]['results'][0]['athlete'].lower() == 'runner numbera'
    assert r['team_rankings'][0]['event_idx'] == 0


def test_spreadsheet_block_split_under_race_heading():
    """An Excel sheet with VARSITY GIRLS | VARSITY BOYS side by side and the
    JV races below under "JV girls" / "JV boys": four races, each gendered
    by the heading over its columns."""
    from backend.parsers.spreadsheet import SpreadsheetTableParser
    def tr(cells):
        return '<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>'
    rows = [tr(['', 'VARSITY GIRLS', '', '', '', '', 'VARSITY BOYS', '', '']),
            tr(['place', 'name', 'school', 'time', '', 'place', 'name', 'school', 'time'])]
    sch = ['matt', 'Schenck', 'La', 'Stearns', 'PCHS']
    for k in range(1, 5):
        rows.append(tr([k, f'Ann {chr(64 + k)}lder', sch[k], f'2{k}:00', '', k, f'Bob {chr(64 + k)}lder', sch[k - 1], f'1{k + 5}:00']))
    rows.append(tr(['JV girls', '', '', '', '', 'JV boys', '', '', '']))
    rows.append(tr(['place', 'name', 'school', 'time', '', 'place', 'name', 'school', 'time']))
    for k in range(1, 4):
        rows.append(tr([k, f'Cat {chr(64 + k)}lden', sch[k + 1], f'22:{k}0', '', k, f'Dan {chr(64 + k)}lden', sch[k], f'17:{k}5']))
    html = '<html><body><table>' + ''.join(rows) + '</table></body></html>'
    r = SpreadsheetTableParser(None).parse(html, 'lynxinvitational.htm', 'XC')
    got = sorted((e['gender'], len(e['results'])) for e in r['events'])
    assert got == [('Boys', 3), ('Boys', 4), ('Girls', 3), ('Girls', 4)], got


def test_late_gender_division_header_and_mile_typo():
    """USATF JO Hy-Tek: "2000 Meter Run CC 8 & Under Division Girls" with no
    "Event N"; a meet report's "5000 Miles" is 5,000 m."""
    text = ("2000 Meter Run CC 8 & Under Division Girls\n"
            "===================================================================================\n"
            "    Name                    Year Team                    Seed     Finals  H# Points\n"
            "===================================================================================\n"
            "Results - Women\n"
            "  1 Lindon, Bree              07 New York Nov                    7:21.91   1\n"
            "  2 Flake, Emma               07 Scarborough                     7:48.38   1\n"
            "  3 Simon, Dani               08 Foundation T                    7:50.09   1\n")
    r = Sub5ColumnParser('jo.htm', text='<pre>' + text + '</pre>').parse()
    ev = r['events'][0]
    assert ev['gender'] == 'Girls' and ev['event'].startswith('2000 Meter Run CC'), ev['event']
    assert len(ev['results']) == 3
    from backend.parsers.meetreport import _event_name
    assert _event_name('5000 Miles (8046.7 Kilometers)', '').startswith('5k'), _event_name('5000 Miles (8046.7 Kilometers)', '')


def test_post_processing_relays_duplicates_and_name_order():
    """Two-runner relays are relay events; a race re-listed by age group is
    dropped (block indices kept); a "Surname Given" list is read from its
    last word for gender; a partly suffixed mixed list splits by suffix,
    then names, the rest Mixed."""
    from backend.scraper_v2 import (drop_relay_team_totals, drop_duplicate_events,
                                    split_mixed_by_names)
    from backend.parsers.namegender import last_first_order, gender_evidence
    data = {'events': [{'event': '1.5 Mile Run CC', 'gender': 'Boys', 'results': [
        {'athlete': f'smith{k} / JONES{k}', 'school': 'MSSM', 'result': f'19:{k:02d}'} for k in range(6)]}]}
    drop_relay_team_totals(data, 'Houlton Relays', 'HoultonRelayResults.pdf')
    assert data['events'][0]['is_relay'] and data['events'][0]['event'].endswith('Relay')
    full = [{'athlete': f'Runner{k}, Al', 'result': f'1{k}:00'} for k in range(8)]
    data = {'events': [{'event': 'Age 15-16', 'gender': 'Girls', 'results': full[:4]},
                       {'event': '5k 15-18', 'gender': 'Girls', 'results': full}],
            'team_rankings': [{'kind': 'xc', 'event_idx': 1, 'teams': []}]}
    drop_duplicate_events(data)
    assert [e['event'] for e in data['events']] == ['5k 15-18'] and data['team_rankings'][0]['event_idx'] == 0
    rows = [{'athlete': n} for n in ['Ek Josephine', 'Fortin Heidi', 'Horne Lily', 'Lorrey Amelia',
                                     'Chidsey Ellie', 'Mayone Sophia']]
    assert last_first_order(rows) and gender_evidence(rows)[1] >= 5
    names = ['John', 'Mary', 'Peter', 'Sarah', 'Michael', 'Emily', 'David', 'Hannah'] * 3 + ['Zzyx'] * 2
    data = {'events': [{'event': 'Mixed 4k Run CC', 'gender': 'Mixed',
                        'results': [{'athlete': f'{n} Smith', 'result': f'1{k % 10}:00'} for k, n in enumerate(names)]}]}
    split_mixed_by_names(data)
    got = sorted((e['gender'], len(e['results'])) for e in data['events'])
    assert got == [('Boys', 12), ('Girls', 12), ('Mixed', 2)], got
    assert len({e['combined_race'] for e in data['events']}) == 1



def test_header_table_rosters_bib_and_clock_hundredths():
    """"Count | Last | First | Grade | B/G | Team | Bib # | Race Time" pages:
    the roster by bib (times in no order) is dropped, the finish list kept and
    split by the B/G column; "Finish Order  BIB#" and 19:01:18 (mm:ss:hh)."""
    from backend.parsers.headertable import HeaderTableParser
    h = HeaderTableParser(None)
    hdr = "Count     Last Name           First Name    Grade   B/G     Team       Bib #   Race Time\n"
    roster = [("Brown", "Al", 10, "Boys", 101, "22:15.1"), ("Cumming", "Cal", 11, "Boys", 105, "16:57.0"),
              ("Dees", "Hay", 12, "Boys", 106, "23:21.8"), ("Fey", "Nol", 9, "Boys", 107, "18:45.3"),
              ("Hend", "Reed", 12, "Boys", 108, "16:58.7"), ("Lehm", "Jo", 12, "Boys", 110, "17:13.7")]
    def rows(rs):
        return ''.join(f"  {k + 1:<9} {a:<19} {b:<13} {g:<7} {x:<7} Gorham     {bib:<7} {t}\n"
                       for k, (a, b, g, x, bib, t) in enumerate(rs))
    fin = sorted(roster, key=lambda r: r[5]) + [("Loran", "Liz", 11, "Girls", 120, "20:44.5"),
                                                  ("Cum", "Rachel", 10, "Girls", 121, "20:46.4"),
                                                  ("Libb", "Tess", 9, "Girls", 122, "21:27.4")]
    text = hdr + rows(roster) + "\nRunners\n" + hdr + rows(fin)
    r = h.parse(text, 'meet.pdf', 'XC')
    got = [(e['gender'], [x['athlete'] for x in e['results']][:2]) for e in r['events']]
    assert got == [('Boys', ['Cumming, Cal', 'Hend, Reed']), ('Girls', ['Loran, Liz', 'Cum, Rachel'])], got
    text = ("  Finish Order        BIB#   Name                    School   Finish Time\n"
            "        1               86   Joe Crocket             MON             19:01:18\n"
            "        2               88   Bros Comeau             MON            19:47:36\n"
            "        3               97   James Cogna             WIN            20:31:42\n")
    r = h.parse(text, 'Boys-Results.pdf', 'XC')
    assert [(x['athlete'], x['result']) for x in r['events'][0]['results']][:2] == [
        ('Joe Crocket', '19:01.18'), ('Bros Comeau', '19:47.36')], r['events']



def test_team_score_coverage_formats():
    """Score tables beyond the Hy-Tek block: a 'Results - Men <Division>'
    line splits one Team Scores section into division blocks; RunScore
    '*** BOYS TEAM SCORE ***' sections; totals-only lists ("1 Yarmouth 26",
    "18:12 Morse 36" beside runners, inline "Team scores- Matt 17 , Schenck
    38"); columns of places under team names; checked by totals."""
    from backend.parsers.teamgrid import vertical_grid_blocks
    hy = ("                                   Team Scores\n"
          "=================================================================================\n"
          "Rank Team                      Total    1    2    3    4    5   *6   *7   *8   *9\n"
          "=================================================================================\n"
          "Results - Men Large School\n"
          "   1 Brewer High School           20    1    2    4    6    7\n"
          "   2 Bangor High School           35    3    5    8    9   10\n"
          "Results - Men Small School\n"
          "   1 Orono High School            15    1    2    3    4    5\n"
          "   2 Bucksport High School        40    6    7    8    9   10\n")
    b = parse_xc_team_scores(hy)
    assert [(x['gender'], x.get('division'), x['teams'][0]['score']) for x in b] == [
        ('Boys', 'Large School', 20.0), ('Boys', 'Small School', 15.0)], b
    rs = ("                     *********** BOYS TEAM SCORE **********\n"
          "  1. Falmouth\n            3    4    5    6    9  (13) (16) =    27\n"
          "         Sean Soucy, Ben Wyman\n"
          "  2. Greely\n            2    7    8   10   11  (12) (15) =    38\n")
    b = parse_xc_team_scores(rs)
    assert b[0]['gender'] == 'Boys' and b[0]['teams'][1]['places'] == [2, 7, 8, 10, 11, 12, 15]
    tot = ("12  Ann Bee   Cony   18:12   Morse 36\n13  Cy Dee   Cony  18:20   Cony 39\n" )
    b = parse_xc_team_scores("TEAM SCORES\n" + tot + "\nNotes\n")
    assert b and b[0].get('totals_only') and [t['score'] for t in b[0]['teams']] == [36.0, 39.0], b
    b = parse_xc_team_scores("Team scores- Matt 17 , Schenck 38\n1 Ann Bee matt 20:27\n")
    assert [(t['team'], t['score']) for t in b[0]['teams']] == [('Matt', 17.0), ('Schenck', 38.0)], b
    grid = ("Place Name   School  Time    Team Scores\n"
            "  1 Al Ames   MW   18:00      Marshwood Cheverus\n"
            + ''.join(f"  {k} Runner{chr(64 + k)}   MW   1{k}:00      {a:<10}{c}\n"
                      for k, (a, c) in enumerate([(1, 3), (2, 5), (4, 6), (7, 9), (8, 10)], start=2)))
    b = vertical_grid_blocks(grid)
    assert [(t['team'], t['places']) for t in b[0]['teams']] == [
        ('Marshwood', [1, 2, 4, 7, 8]), ('Cheverus', [3, 5, 6, 9, 10])], b
    rows = [{'athlete': f'R{k}', 'school': s, 'result': f'1{k // 10}:{k % 10}0', 'place': k}
            for k, s in enumerate(['A', 'A', 'B', 'A', 'B', 'A', 'B', 'A', 'B', 'B'], start=1)]
    v = qaqc._xc_verify_block({'totals_only': True, 'teams': [
        {'team': 'A', 'score': 21.0, 'places': []}, {'team': 'B', 'score': 34.0, 'places': []}]}, rows)
    assert v['status'] == 'verified', v


def test_round5_team_score_layouts():
    """Score-table layouts read this round (each from a real sub5 page)."""
    from backend.parsers.xcscores import (_split_side_tables, parse_team_totals, _team_lists,
                                          _indented_team_lists, _html_scores_grid)
    # two tables side by side under their own titles; a column's second
    # column of teams (WMC 2020); the plain list stops at the runner rows
    side = ("         BOYS TEAM SCORES                          GIRLS TEAM SCORES\n"
            "Greely     38    Poland   172                Cape       62    York     91\n"
            "Cape       58    GNG      177                Yarmouth 64      GNG      166\n"
            "York       115                                1   101 Ann Bee   19:49.18 6:24 Cape   9\n"
            "1    13 Al Ames    16:26.34 5:18 Greely   12  2   37 Cy Dee  20:16.73 6:32 Yarmouth 12\n")
    b = parse_team_totals(side)
    assert [(x['gender'], [t['score'] for t in x['teams']]) for x in b] == [
        ('Boys', [38.0, 58.0, 115.0, 172.0, 177.0]), ('Girls', [62.0, 64.0, 91.0, 166.0])], b
    # "Team Scores: Deering: 15    Portland: 52 Cheverus: 59" / "Girls:  JB 25, Her 30"
    b = parse_team_totals("Team Scores: Deering: 15    Portland: 52 Cheverus: 59\n")
    assert [t['score'] for t in b[0]['teams']] == [15.0, 52.0, 59.0], b
    b = parse_team_totals("Team Scores: Girls:  JB 25, Her 30\n")
    assert b[0]['gender'] == 'Girls' and [t['team'] for t in b[0]['teams']] == ['JB', 'Her'], b
    # score first: "Team Score: 32 Hermon, 34 Schenck, 63 Lee."; "1-LEW 24  2 LEAV 41 ... TEAM SCORE"
    b = parse_team_totals("Team Score: 32 Hermon, 34 Schenck, 63 Lee.\n")
    assert [(t['team'], t['score']) for t in b[0]['teams']] == [('Hermon', 32.0), ('Schenck', 34.0), ('Lee', 63.0)]
    b = parse_team_totals("1-LEW 24   2 LEAV 41   3 POL 65   TEAM SCORE\n")
    assert [t['score'] for t in b[0]['teams']] == [24.0, 41.0, 65.0], b
    # ordinal place words, "NO SCORE", typeset hyphens, "points" suffix
    b = parse_team_totals("Team scores:\n1.) JB: First Place, 26\n2.) SU: Second Place, 62\n"
                          "3.) GSA: NO SCORE\nBoys Team Scores\n1 Orono – 25 points\n2 Lee Academy- 43 points\n")
    assert [[t['score'] for t in x['teams']] for x in b] == [[26.0, 62.0], [25.0, 43.0]], b
    # rank, team, places then the total ("1  PIMS  2, 4, 5, 8, 9, (10, 11)  28") and
    # dash places with bracketed displacers, the total first
    b = parse_xc_team_scores("Team Results\n1. MSSM   1, 2, 6, 9, 10, 11, 12   28\n"
                             "2. Houlton/GHCA   3, 4, 5, 7, 16   35\n")
    assert [(t['score'], t['places'][:5]) for t in b[0]['teams']] == [(28.0, [1, 2, 6, 9, 10]), (35.0, [3, 4, 5, 7, 16])], b
    b = parse_xc_team_scores("******* Team Scores *******\n 1.   Bonny Eagle   35   4-5-6-7-13-[17-20]\n"
                             " 2.   Gorham   48   3-9-10-11-15-[18-24]\n 1.   Windham   54   8-9-10-12-15-[17-19]\n"
                             " 2.   Noble   99   1-14-22-26-36-[37-38]\n")
    assert [[t['score'] for t in x['teams']] for x in b] == [[35.0, 48.0], [54.0, 99.0]], b
    # RunScore two-line rows without stars; "WOMEN'S TEAM SCORE"; two teams, one slip
    b = parse_xc_team_scores("TEAM SCORES\n1. YORK\n2    4    5    6    9 (11) (12) =     26\n"
                             "2. Greely\n1    7    8   10    14 (15) (17) =    40\n")
    assert [t['score'] for t in b[0]['teams']] == [26.0, 40.0], b
    b = parse_xc_team_scores("   *********** WOMEN'S TEAM SCORE **********\n  1. Endicott\n"
                             "       2    4    6    8    9  (10) (12) =    29\n  2. Colby\n"
                             "       1    3    5    7   15  (16) (18) =    30\n")
    assert b and b[0]['gender'] == 'Girls' and [t['score'] for t in b[0]['teams']] == [29.0, 31.0 - 1], b
    # a side table right of the runner rows, its rows only from its own column
    rows = ("18:17   16   10    Tuttle, Stephanie   GHCA     -                               Team Scores\n"
            "18:20   17   26    Walsh, Makenna      PIMS     -                Boys\n"
            "18:24   18   1      Drake, Amelia      GHCA     -          1          PIMS    2, 4, 5, 8, 9, (10, 11)     28\n"
            "18:27   19   24    O'Donnell, Neve     PIMS     -          2       GHCA       1, 3, 6, 7, 12, (13)        29\n")
    b = parse_xc_team_scores(rows)
    assert b and b[0]['gender'] == 'Boys' and [t['score'] for t in b[0]['teams']] == [28.0, 29.0], b
    # per-team runner lists beside the finish list ("Bangor / Name Points / ... / Total 26")
    tl = ["Place Name     Team   Time    Points          Team Score"]
    tl += [f"  {k} Runner{k}   BAN   1{k}:00  {k}          {'Bangor' if k == 1 else 'Name     Points' if k == 2 else ''}"
           for k in range(1, 3)]
    tl += ["                                              Al Ames      2", "                                              Bo Bee       4",
           "                                              Cy Cee       5", "                                              Di Dee       6",
           "                                              Ed Eee       9", "                                              Total        26",
           "                                              Messalonskee", "                                              Fa Eff       1",
           "                                              Gi Gee       7", "                                              Ha Hay      13",
           "                                              Io Eye      18", "                                              Ju Jay      22",
           "                                              Total        61"]
    b = _team_lists(tl)
    assert [(t['team'], t['score']) for t in b[0]['teams']] == [('Bangor', 26.0), ('Messalonskee', 61.0)], b
    # "Team Scores   Scores" with the scorers indented under each team
    il = ["Boys Team Scores", "Team Scores           Scores", "  Cony                         35",
          "    Casey Gallant               2", "    Jacob Pelletier             5", "    Jack Begin                  8",
          "    Sam Coffin                  9", "    Aidan Coulombe             11", "  MESS                         21",
          "   Dylan Flewelling             1", "   Caden Cote                   3", "   Tieran Croft                 4",
          "   Evan DeMott                  6", "   Zach Ross                    7"]
    b = _indented_team_lists(il)
    assert [(t['team'], t['places']) for t in b[0]['teams']] == [('MESS', [1, 3, 4, 6, 7]), ('Cony', [2, 5, 8, 9, 11])], b
    # an HTML SCORES column: a team's name in one row, its places and total in the next
    html = ("<table><tr><td>Boys</td><td>Time</td><td>Name</td><td>Team</td><td>SCORES</td></tr>"
            "<tr><td>1</td><td>17:54</td><td>A</td><td>BE</td><td></td></tr>"
            "<tr><td>2</td><td>18:29</td><td>B</td><td>P</td><td>Bonny Eag le</td></tr>"
            "<tr><td>3</td><td>18:50</td><td>C</td><td>TA</td><td></td><td>1</td><td>7</td><td>14</td><td>24</td><td>25</td><td></td><td>71</td></tr>"
            "<tr><td>4</td><td>19:29</td><td>D</td><td>S</td><td>Sanford</td></tr>"
            "<tr><td>5</td><td>19:48</td><td>E</td><td>P</td><td></td><td>2</td><td>5</td><td>8</td><td>11</td><td>15</td><td></td><td>41</td></tr>"
            "</table>")
    b = _html_scores_grid(html)
    assert [(t['team'], t['score']) for t in b[0]['teams']] == [('Sanford', 41.0), ('Bonny Eag le', 71.0)], b
    # two unlabelled total columns under "See below team scores:"
    lines = ["  See below team scores:", "Erskine Academy:       28                     Erskine Academy:        15",
             "Skowhegan              57                     Gardiner:               58",
             "Gardiner:              62                     MCI:                    87",
             "MCI:                   84                     Skowhegan:             130"]
    out = _split_side_tables(lines)
    b = parse_team_totals("\n".join(lines))
    assert [[t['score'] for t in x['teams']] for x in b] == [[28.0, 57.0, 62.0, 84.0], [15.0, 58.0, 87.0, 130.0]], (out, b)


def test_round5_grids_and_checker_variants():
    from backend.parsers.teamgrid import vertical_grid_blocks
    # a totals row inside the grid, the 6th runner under it; right-aligned
    # numbers under one-space team names ("Telstar St. Dom's Dirigo")
    t = ("         Boys Team\n          Telstar St. Dom's Dirigo   Madison Carrabec\n"
         + "".join(f"       {k}    {a:>2}        {b:>2}      0        0        0\n"
                   for k, (a, b) in enumerate([(1, 3), (2, 4), (5, 7), (6, 8), (10, 9)], start=1))
         + "Total:      24        31      0        0        0\n       6    11\n")
    b = vertical_grid_blocks(t)
    assert [(x['team'], x['score'], x['places'][:5]) for x in b[0]['teams']] == [
        ('Telstar', 24.0, [1, 2, 5, 6, 10]), ("St. Dom's", 31.0, [3, 4, 7, 8, 9])], b
    # a single-letter team in the header after a runner's cells
    g = ("Place    Time     Name     Team   Scores\n        1 16:53   Morris   SC\n"
         "        2 16:37   Nadeau   B      Deering        Scarb.        Sanford        B\n"
         + "".join(f"        {k} 1{k}:00   R{k}       SC  {a:>13}{b:>14}{c:>15}{d:>9}\n"
                   for k, (a, b, c, d) in enumerate([(4, 1, 3, 2), (9, 5, 12, 10), (13, 6, 17, 24),
                                                    (15, 7, 18, 25), (16, 8, 19, 26)], start=3)))
    b = vertical_grid_blocks(g)
    assert sorted((x['team'], x['score']) for x in b[0]['teams']) == [
        ('B', 87.0), ('Deering', 57.0), ('Sanford', 69.0), ('Scarb.', 27.0)], b
    # checker: time order for a hand-timed list printed out of order, only the
    # table's teams placing, a transposed-letter code, 4 scorers
    rows = [{'athlete': f'R{k}', 'school': s, 'result': f'{t}', 'place': k}
            for k, (s, t) in enumerate([('A', '18:00'), ('B', '18:10'), ('A', '18:30'), ('B', '18:20'),
                                        ('A', '18:40'), ('B', '18:50'), ('A', '19:00'), ('B', '19:10'),
                                        ('A', '19:20'), ('B', '19:30')], start=1)]
    v = qaqc._xc_verify_totals({'teams': [{'team': 'A', 'score': 25.0}, {'team': 'B', 'score': 30.0}]}, rows)
    assert v['status'] == 'verified', v          # (B's 18:20 runner ahead of A's 18:30 one)
    rows = [{'athlete': f'R{k}', 'school': s, 'result': f'1{k:02d}:00'[-5:], 'place': k}
            for k, s in enumerate(['BC', 'LA', 'X', 'BC', 'LA', 'BC', 'X', 'BC', 'LA', 'BC', 'X',
                                   'LA', 'X', 'LA', 'X'], start=1)]
    blk = {'teams': [{'team': 'Bangor Christian', 'score': 1 + 3 + 5 + 6 + 8.0},
                     {'team': 'Lee Academy', 'score': 2 + 4 + 7 + 9 + 10.0}]}
    assert qaqc._xc_listed_teams_rows(blk, rows) is not None
    assert qaqc._xc_verify_totals(blk, rows)['status'] == 'verified'
    rows = [{'athlete': f'R{k}', 'school': s, 'result': '', 'place': k}
            for k, s in enumerate(['GHCA', 'FK', 'GCHA', 'FK', 'GHCA', 'FK', 'GHCA', 'FK', 'GHCA', 'FK'], start=1)]
    mc = qaqc._xc_merge_codes(rows)
    assert mc and mc[2]['school'] == 'GHCA', mc


def test_round5_row_readers():
    from backend.parsers.xclist import XCListParser
    from backend.parsers.headertable import HeaderTableParser, _header_fields
    from backend.parsers.spreadsheet import SpreadsheetTableParser
    x = XCListParser.__new__(XCListParser)
    # "1.) Name - Team - 15:12", "58 . Name", a pace before the finish time
    r = x.parse("Results:\n" + "".join(f"{k}.) Runner {chr(64 + k)} - Sumner - 1{k}:12\n" for k in range(1, 7)),
                'b.htm', 'XC')
    assert [y['place'] for y in r['events'][0]['results']] == [1, 2, 3, 4, 5, 6], r
    r = x.parse("".join(f"{k} . Runner {chr(64 + k)}     Lee      1{k}:05\n" for k in range(1, 7)), 'b.pdf', 'XC')
    assert len(r['events'][0]['results']) == 6, r
    r = x.parse("".join(f"  {k} Runner {chr(64 + k)}   SR Hampden Academy   5:3{k}.0   17:1{k}.44   2   {k}\n"
                        for k in range(1, 7)), 'ne.htm', 'XC')
    assert r['events'][0]['results'][0]['result'] == '17:11.44', r
    # "time  name  place  team" rows; "place bib name time pace team grade" side by side
    r = x.parse("Time   Name   Place   School\n" + "".join(
        f"{10 + k}:11       Runner {chr(64 + k)}             {k}          Calais\n" for k in range(1, 11)), 'l.pdf', 'XC')
    assert [y['place'] for y in r['events'][0]['results']][:3] == [1, 2, 3], r
    # two unlabelled sheets: the faster one is the boys' race
    two = ("".join(f"{k}. Girl{chr(64 + k)}   YAR   2{k}:00\n" for k in range(1, 7)) + "\n\n" +
           "".join(f"{k}. Boy{chr(64 + k)}   YAR   1{k}:00\n" for k in range(1, 7)))
    r = x.parse(two, 'gnggirls_sept21.pdf', 'XC')
    g = {e['results'][0]['athlete'][:3]: e['gender'] for e in r['events']}
    assert g in ({'Gir': 'Girls', 'Boy': 'Boys'}, {'Gir': 'Girls'}), g
    # HeaderTable: "Overall"-less "Boys  Time  Name  Team" place column, a
    # second "team" column = team points
    assert _header_fields('place  time  name  school  team') == ['place', 'time', 'name', 'school', 'team_place']
    assert HeaderTableParser._headers('Boys    Time    Name    Team    SCORES')[0][1][:4] == ['place', 'time', 'name', 'school']
    # spreadsheet: a Place column left of the name is read; a surname-only
    # Last/First row is kept
    html = ("<table><tr><td>Place</td><td>Name</td><td>High School</td><td>Time</td></tr>"
            + "".join(f"<tr><td>{k}</td><td>Runner {chr(64 + k)}</td><td>Winslow</td><td>2{k}:26</td></tr>"
                      for k in range(1, 6)) + "</table>")
    res = SpreadsheetTableParser().parse(html, 'w.html', 'XC')
    assert [y['place'] for y in res['events'][0]['results']] == [1, 2, 3, 4, 5], res


def test_track_sex_letter_labels_and_name_relabel():
    """A hand-made dual-meet sheet ("M 400m" / "F 400m") read entirely as
    girls; a truncated "oys 800 Meter Run" header; an initial is not a first
    name; on track a list that reads mixed is relabelled, never split."""
    from backend.scraper_v2 import fix_event_gender_from_label, fix_event_gender_from_names
    from backend.parsers.namegender import name_gender
    data = {'events': [{'event': 'M 400m', 'gender': 'Girls', 'results': []},
                       {'event': 'F 400m', 'gender': 'Boys', 'results': []},
                       {'event': 'Mile Run', 'gender': 'Girls', 'results': []}]}
    fix_event_gender_from_label(data)
    assert [e['gender'] for e in data['events']] == ['Boys', 'Girls', 'Girls']
    assert name_gender('B Bradley') is None and name_gender('J. Smith') is None
    assert name_gender('Bradley, B') is None and name_gender('Ian Moss') == 'Boys'
    boys = ['Ian Moss', 'Luca Reed', 'Cameron Holt', 'John Ames', 'Peter Bell']
    girls = ['Emma Ames', 'Olivia Bell', 'Sophia Cole', 'Grace Dodd', 'Hannah Eck',
             'Abigail Fisk', 'Chloe Gale', 'Lily Hart', 'Ella Ince', 'Ava Jory',
             'Mia Kemp', 'Zoe Lane', 'Julia Moss', 'Sarah Nye', 'Anna Orr']
    data = {'events': [{'event': 'oys 800 Meter Run', 'gender': 'Girls',
                        'results': [{'athlete': n} for n in boys]},
                       {'event': '100 Meter Hurdles', 'gender': 'Girls',
                        'results': [{'athlete': n} for n in girls + boys]}]}
    fix_event_gender_from_names(data, split=False)
    assert [e['gender'] for e in data['events']] == ['Boys', 'Girls']
    assert len(data['events']) == 2


def test_multi_day_web_date_keeps_the_files_own_day():
    """The season index dates a two-day meet "December 28/29, 2021"; the file
    for day two says 12/29 and keeps it (KVAC 4C), day one keeps 12/28."""
    from backend.scraper_v2 import Sub5ScraperV2
    s = Sub5ScraperV2.__new__(Sub5ScraperV2)
    assert s.web_date_days('December 28/29, 2021') == {'2021-12-28', '2021-12-29'}
    assert s.web_date_days('June 3-4, 2005') == {'2005-06-03', '2005-06-04'}
    assert s.web_date_days('October 25, 2008') == {'2008-10-25'}
    assert s.web_date_days('June 3 & 10, 2006') == {'2006-06-03'}


def test_team_scores_reader_formats():
    """Score blocks the parser missed: a meet label inside the Hy-Tek header,
    a 'Through Event' table with a code column and a split decimal, an
    inline list, a number on its own line."""
    from backend.parsers.teamscores import extract_team_scores
    t = """
                 Women - 2B - Team Rankings - 14 Events Scored
===============================================================================
    1) Alpha High School         111        2) Beta High School         97
    3) Gamma HS                   28
"""
    b = extract_team_scores(t)
    assert [(x['gender'], [(y['team'], y['score']) for y in x['teams']]) for x in b] == \
        [('Girls', [('Alpha High School', 111.0), ('Beta High School', 97.0), ('Gamma HS', 28.0)])]
    t = """Team Rankings - Through Event 38
                    Female Team Scores
    Place   School                                 Points
      1     Alpha High School         ALP              99
      2     Beta Track Team           BETA             64 .50
                    Male Team Scores
      1     Beta Track Team           BETA            103 .50
      2     Alpha High School         ALP              59
"""
    b = {x['gender']: [(y['team'], y['score']) for y in x['teams']] for x in extract_team_scores(t)}
    assert b == {'Girls': [('Alpha High School', 99.0), ('Beta Track Team', 64.5)],
                 'Boys': [('Beta Track Team', 103.5), ('Alpha High School', 59.0)]}, b
    b = extract_team_scores('Girls Team Scores: Alpha 116, Beta Academy 46.5, Gamma 37.5')
    assert [(y['team'], y['score']) for y in b[0]['teams']] == [('Alpha', 116.0), ('Beta Academy', 46.5), ('Gamma', 37.5)]
    b = extract_team_scores('Male Team Scores\n1 Alpha High School  -\n162\n2 Beta High School -\n129\n')
    assert [(y['team'], y['score']) for y in b[0]['teams']] == [('Alpha High School', 162.0), ('Beta High School', 129.0)]


def test_printed_points_by_column():
    """The Points column, not the mark or a wind reading next to it."""
    from backend.parser import printed_points
    h = '    Name                    Year School                  Finals  Wind  H#  Points'
    assert printed_points('  1 Al Ames                    Alpha                     12.30   +1.2   1      10', h) == 10.0
    assert printed_points('  9 Bo Bean                    Beta                      13.03   -0.4   3', h) is None
    h = '    Name                    Year School                  Finals  Points'
    assert printed_points('  3 Cy Cole                    Gamma                     20.67     2.50', h) == 2.5


def test_track_audit_fixes_event_names():
    """From the 2026-10 track audit: a 500m is not a 50 Meter Dash, yard
    races (440, 880) are kept, a 3x relay is not a 4x."""
    from backend.event_canon import canonical_event
    assert canonical_event('Men 500 Meter Dash', 'Boys') == ('Boys', '500 Meter Run')
    assert canonical_event('55 Meter Dash', 'Boys') == ('Boys', '55 Meter Dash')
    assert canonical_event('880 Yard Run', 'Girls') == ('Girls', '880 Yard Run')
    assert canonical_event('440 Yard Dash In-7th', 'Girls') == ('Girls', '440 Yard Dash')
    assert canonical_event('3x1600 Meter Relay', 'Boys') == ('Boys', '3x1600 Meter Relay')
    assert canonical_event('4x800 Meter Relay', 'Boys') == ('Boys', '4x800 Meter Relay')


TRACK_AUDIT = """\
                    Hy-Tek's Meet Manager 5/5/2013 06:39 AM
                            KVAC Meet #3 - 5/3/2013
Event 1  Girls 1760 Sprint Medley Long
==========================================================================
    School                                               Finals  H# Points
==========================================================================
  1 Alpha High School  'A'                              4:37.12   2   10
     1) Ann Ames                        2) Bea Bean
  2 Beta High School  'A'                               4:45.86   2    8
     1) Cat Cole                        2) Di Dodd
Event 2  Girls 100 Meter Dash
=======================================================================
    Name                    Year School                  Finals  Points
=======================================================================
  1 Haji-Hersi, Mairiam          Alpha                    12.00     10
 2 Massengale, Lacey            Beta                     12.10      8
Event 3  Boys Discus Throw
=======================================================================
    Name                    Year School                    Seed    Finals  Points
=======================================================================
  1 Al Ames                   12 Alpha                   110-02    120-04    10
 -- Bo Ellington              11 Beta                    105-02     XFOUL
"""


def test_track_audit_fixes_parser():
    """A medley relay is a relay; a row printed one column left keeps the
    first letter of its name; XFOUL is a foul, not the seed mark; the
    meet date is the title's, not the Hy-Tek print stamp's."""
    res = Sub5ColumnParser('audit.htm', text='<pre>' + TRACK_AUDIT + '</pre>').parse()
    ev = {e['event']: e for e in res['events']}
    med = [e for k, e in ev.items() if 'Medley' in k][0]
    assert med['is_relay'] and [r['school'] for r in med['results']] == ['Alpha High School', 'Beta High School']
    assert [r['athlete'] for r in ev['100 Meter Dash']['results']] == ['Haji-Hersi, Mairiam', 'Massengale, Lacey']
    assert [r['result'] for r in ev['Discus']['results']] == ['120-04', 'FOUL']
    assert res.get('date') == '2013-05-03', res.get('date')


def test_split_mark_sheet():
    """Telstar 2010-11 sheets: the mark split over Min/Ft and Sec/Inchs."""
    from backend.parsers.splitmark import SplitMarkParser
    t = """Place Athlete                  Team       Event        Min/Ft Sec/Inchs   Points
  1 Ames, Al                    StD     Racewalk            9 04.0          8
  1 Bean, Bo                    MtV     100 Dash                 11.7        8
  2 Cole, Cy                    Lis     400 Dash            0 57.1          6
  1 Dodd,Eck,Fisk,Gale          Lis     1600 Relay          3 54.8          8
  3 Hart, Hal                   StD     Long Jump          16 04.5          4
  8                                     Racewalk
"""
    assert SplitMarkParser.matches(t)
    r = SplitMarkParser(None).parse(t, 'telstarboys_may3.pdf', 'Outdoor')
    got = {e['event']: [(x.get('athlete') or x['school'], x['result']) for x in e['results']] for e in r['events']}
    assert got == {'1600 Meter Race Walk': [('Ames, Al', '9:04.0')], '100 Meter Dash': [('Bean, Bo', '11.7')],
                   '400 Meter Dash': [('Cole, Cy', '57.1')], '4x400 Meter Relay': [('Lis', '3:54.8')],
                   'Long Jump': [('Hart, Hal', '16-04.50')]}, got
    assert all(e['gender'] == 'Boys' for e in r['events'])


def test_score_divisions_and_checker_races():
    """Divisions scored on their own keep one block each; the checker sums
    them. A prelim section is not a race when the event has finals, and a
    report printed twice is one race."""
    from backend.parsers.teamscores import extract_team_scores
    from backend.track_verify import _races
    t = """Men - Junior Division - Team Rankings - 5 Events Scored
==============================================
    1) Alpha High School         37        2) Beta High School   20
Men - Senior Division - Team Rankings - 5 Events Scored
==============================================
    1) Beta High School         50        2) Alpha High School   12
"""
    b = extract_team_scores(t)
    assert [(x['division'], x['teams'][0]['score']) for x in b] == [('Junior Division', 37.0), ('Senior Division', 50.0)]
    fin = [{'athlete': 'A', 'school': 'X', 'result': '11.0', 'type': 'Finals', 'place': 1}]
    pre = [{'athlete': 'A', 'school': 'X', 'result': '11.2', 'type': 'Prelims', 'place': 1}]
    parsed = {'events': [{'event': '100 Meter Dash', 'gender': 'Boys', 'results': pre},
                         {'event': '100 Meter Dash', 'gender': 'Boys', 'results': fin},
                         {'event': '100 Meter Dash', 'gender': 'Boys', 'results': list(fin)}]}
    races = _races(parsed)
    assert list(races.values()) == [fin], races



ROUND2_STATUS = """Boys 100 Meter Dash 7th/8th grade
===================================================================
    Name                    Year Team                    Finals  H#
===================================================================
  1 Ellis, Issac                 MDI Elementa             13.61   1
  2 Smith, Carter                Brewer CS                13.69   1
 -- Bernaiche, Isaiah            Brewer CS                   NT   3
Boys Long Jump 7th/8th grade
================================================================
    Name                    Year Team                    Finals
================================================================
  1 Leies, Isaac                 MDI Elementa          14-04.00
  2 Look, Jacob                  Brewer CS             14-00.00
 -- Avellar, Colby               Piscataquis                 ND
"""

GLUED_HEADER = """Event 43  Girls 200 Meter Dash Meet B
==========================================================================
EMITL Record: R 25.61  2/11/2013   Teal Jackson, Brewer                            Name                    Year School                  Finals  H# Points
==========================================================================
  1 Ashley Anderson           SR Mt. Desert               27.00   7  10
  2 Mackenzie Lambert         SO Bangor                   28.40   7   8
Event 47  Girls 4x200 Meter Relay
=======================================================================
    School                                               Finals  Points
=======================================================================
  1 Mt.  Desert Island H.S.  'A'                       1:38.19      10
     1) Ann Ames SO  2) Bea Bean JR
"""


def test_round2_status_rows_glued_header_and_relay_names():
    """Unplaced rows keep their status (NT, ND); a column header that a Word
    export ran onto the record line still finds its columns; a school
    printed with a double space ("Mt.  Desert") stays whole."""
    res = Sub5ColumnParser('brewerms.htm', text='<pre>' + ROUND2_STATUS + '</pre>').parse()
    got = {e['event']: [r['result'] for r in e['results']] for e in res['events']}
    assert got['100 Meter Dash'] == ['13.61', '13.69', 'NT'], got
    assert got['Long Jump'] == ['14-04.00', '14-00.00', 'ND'], got
    word = '<html xmlns:o="urn:schemas-microsoft-com:office:office"><body>'   # (a Word export)
    res = Sub5ColumnParser('emitl.htm', text=word + '<pre>' + GLUED_HEADER + '</pre></body></html>').parse()
    ev = {e['event']: e for e in res['events']}
    assert [(r['athlete'], r['school'], r['result']) for r in ev['200 Meter Dash']['results']] == [
        ('Ashley Anderson', 'Mt. Desert', '27.00'), ('Mackenzie Lambert', 'Bangor', '28.40')]
    relay = ev['4x200 Meter Relay']['results'][0]
    assert relay['school'] == 'Mt. Desert Island H.S.', relay
    from backend.scraper_v2 import strip_leg_grades, split_glued_grades
    d = {'events': [{'results': [{'athlete': 'McKechnic, Nicholas SR', 'grade': ''},
                                 {'athlete': '--- Fillion, Cam SO', 'grade': '', 'result': 'DNF'}]}]}
    split_glued_grades(d)
    assert [(r['athlete'], r['grade']) for r in d['events'][0]['results']] == [
        ('McKechnic, Nicholas', 'SR'), ('Fillion, Cam', 'SO')]
    d = {'events': [{'results': [dict(relay, athletes=['Ann Ames SO', 'Bea Bean JR'])]}]}
    strip_leg_grades(d)
    assert d['events'][0]['results'][0]['athletes'] == ['Ann Ames', 'Bea Bean']



FIELD_RELAYS = """Event 2  Boys Pole Vault Relay
================================================================
    Name                    Year School                  Finals
================================================================
Finals
  1 Alec James                JR Scarborough           12-00.00
  2 Alex Johnson              JR Gorham                11-00.00
  3 Troy Lambert              JR Gorham               J11-00.00
 -- Thomas White              JR Winslow                     NH
Event 32  Boys Shot Put Relay
=======================================================================
    Name                    Year School                  Finals  Points
=======================================================================
  1 Central A   (Rob Hall/Brett White/Rob Musinski)   107-08.75    10
  2 Bangor A                     Bangor               107-03.25     8
  3 Brewer A                     Brewer               105-02.50     6
"""


def test_field_relay_jumpers_keep_their_names():
    """A field "relay" that lists each jumper is individual marks; one that
    lists team totals ("Bangor A") stays a relay."""
    res = Sub5ColumnParser('usmrelays.htm', text='<pre>' + FIELD_RELAYS + '</pre>').parse()
    ev = {e['event']: e for e in res['events']}
    pv = ev['Pole Vault']
    assert not pv['is_relay'] and [(r['athlete'], r['result']) for r in pv['results']] == [
        ('Alec James', '12-00.00'), ('Alex Johnson', '11-00.00'), ('Troy Lambert', '11-00.00'),
        ('Thomas White', 'NH')], pv
    assert ev['Shot Put']['is_relay']


def test_meet_level_ignores_milesplit_prefix():
    """'ms-<slug>' names a MileSplit transcription, not a middle-school meet; real MS names still read as MS,
    and 'St. Doms' is a school, not an MS code."""
    from backend import school_catalog as sc
    assert sc.meet_level('ms-smaa-boys-portland-thornton-academy-bonny-eagle-2014') is None
    assert sc.meet_level('ms-mvc-st-doms-carrabec-madison-mt-valley-telstar-2014') is None
    assert sc.meet_level('ms-madison-junior-high-cross-country-invitational-meet-2026') == 'ms'
    assert sc.meet_level('MS_MEET_10_12_2017') == 'ms'
    assert sc.meet_level('ms-girls-78 Southern Maine Middle School XC Festival Meet') == 'ms'
    # Waterville's junior-high files put XC before JH ('XCJH21.09.29results-1', '19.09.11XCJHBOYS')
    assert sc.meet_level('XCJH21.09.29results-1 GIRLS RESULTS') == 'ms'
    assert sc.meet_level('19.09.11XCJHBOYS') == 'ms'
    assert sc.meet_level('XCHSWtvlWins22.09.09GIRLSFINAL') is None
    assert sc.meet_level('watervilljuniorhigh_sept11') == 'ms'


def test_xc_course_model_keeps_milesplit_meets():
    """The course model / postseason predictions drop middle-school meets by name; a MileSplit file's 'ms-' prefix
    is not one (it dropped every 2026 MileSplit meet from the predictions)."""
    from backend import xc_course_model as cm
    assert not cm.NON_HS_MEET.search('ms-ellsworth-invitational-2026')
    assert cm.NON_HS_MEET.search('ms-tripp-ms-meet-2026')
    assert cm.NON_HS_MEET.search('ms-madison-junior-high-cross-country-invitational-meet-2026')


def test_milesplit_racetab_xc():
    """RaceTab sheets: the level leads the race title, points can carry a flag letter ("z7"), "--" marks a
    non-scoring runner, and "<title> Team Scores" heads that race's team block."""
    from backend import milesplit as ms
    text = '''RaceTab 3 by MileSplit                    Registered to: x

                Middle School Boys 3000 Meter Run
=================================================================
    Name                  Yr Team                      Time   Pts
-----------------------------------------------------------------
  1 Daniel Lyons             Brunswick Jr. High    11:10.00     1
  2 Shaub Noh                Oxford Hills Middle   11:16.20     2
  3 Temple Miller-Hodgkin    Mt. Ararat Middle Sc  12:03.90    z3
  4 Aiden Simmons            Unattached            12:39.49    --

          Middle School Boys 3000 Meter Run Team Scores
=================================================================
    Team                   Pts     1    2    3    4    5   (6)  (7)
=================================================================
  1 Brunswick Jr. High     25      1    3    4    8    9   10   12
      Total Time: 57:54      Average: 11:34.68      1-5 Split: 55
'''
    ev, rk = ms.parse_xc_any(text)
    assert len(ev) == 1 and ev[0]['gender'] == 'Boys' and 'Middle School' in ev[0]['event']
    rows = ev[0]['results']
    assert [r['athlete'] for r in rows] == ['Daniel Lyons', 'Shaub Noh', 'Temple Miller-Hodgkin', 'Aiden Simmons']
    assert rows[2]['team_place'] == 3 and 'team_place' not in rows[3]
    assert rk and rk[0]['teams'][0]['team'] == 'Brunswick Jr. High' and rk[0]['teams'][0]['score'] == 25
    assert ms.xc_header('Varsity Girls Three Mile Run') == ('Girls', '3 Mile', 'Varsity')


def test_milesplit_xc_race_continued_over_pages():
    """A Hy-Tek race split over pages repeats its title as '....Event 2 Boys 3k Run CC'; the pages are one race."""
    from backend import milesplit
    row = lambda p, n, s: f'{p:3d} {n:<26}7 {s:<20}{"12:%02d.00" % p:>11}{p:>5}'
    text = '\n'.join([
        '  Event 2  Boys 3k Run CC', '=' * 60, '    Name                    Year School                  Finals  Points', '=' * 60,
        'Results - Men', row(1, 'Doe, John', 'Yarmouth Mid'), row(2, 'Roe, Jim', 'Greely Middl'),
        '  ....Event 2  Boys 3k Run CC', row(3, 'Poe, Ed', 'Yarmouth Mid'), row(4, 'Moe, Al', 'Greely Middl'),
    ])
    events, _ = milesplit.parse_xc(text)
    assert len(events) == 1 and [r['place'] for r in events[0]['results']] == [1, 2, 3, 4]


def test_event_sections_flag_fields_not_runners():
    """qaqc check 16 judges a whole event at one meet by its median: a slow
    field and one runner's freak mark pass; 800 times filed under the 200
    and an unreadable "7:70" are flagged."""
    def field(meet, event, marks):
        return [dict(year='2020', season='Outdoor', meet_name=meet, event=event,
                     athlete_name=f'Pat {n}', team='Some High School', mark=m)
                for n, m in zip(['Ames', 'Bell', 'Cote', 'Dube', 'Ely'], marks)]
    perfs = []
    for i in range(40):
        perfs += field(f'meet{i}', 'Girls 200 Meter Dash', ['28.10', '29.40', '30.20', '31.00', '32.50'])
        perfs += field(f'meet{i}', 'Girls 800 Meter Run', ['2:30.1', '2:38.4', '2:45.0', '2:52.3'])
    perfs += field('kids', 'Girls 200 Meter Dash', ['41.20', '44.80', '46.10'])          # slow but real
    perfs += field('freak', 'Girls 200 Meter Dash', ['29.00', '30.10', '2:31.00'])       # one bad mark
    perfs += field('swapped', 'Girls 200 Meter Dash', ['2:31.20', '2:40.80', '2:44.00'])  # the 800
    perfs += field('typo', 'Girls 800 Meter Run', ['7:70'])
    flags = []
    qaqc.check_event_sections(perfs, flags)
    odd = [(f['meet'], f.get('looks_like')) for f in flags if f['check'] == 'event-section']
    assert odd == [('swapped', 'Girls 800 Meter Run')], odd
    assert [f['mark'] for f in flags if f['check'] == 'malformed-time'] == ['7:70']


def test_pdf_columns_keep_right_header_whole():
    """Two-column Hy-Tek PDF pages print the right column's "Event N" line
    one character left of where its rows' "Name" sits minus six; the split
    cut "Event 7" to "vent 7" (meet-@-bowdoin-12-11-21-1-c.pdf), so the
    mile's rows joined the 55 dash."""
    left = ['Event 5  Girls 55 Meter Dash', '    Name                    School         Finals',
            '  1 Doe, Ann                 Belfast         7.80']
    right = ['Event 7  Girls 1 Mile Run', '    Name                    School         Finals',
             '  1 Roe, Bea                Camden          5:41.20']
    col = 60
    lines = []
    for i, (l, r) in enumerate(zip(left, right)):
        start = col - 7 if i == 0 else col - 4   # the header one left of Name - 6
        lines.append(l.ljust(start) + r)
    out = Sub5ColumnParser.split_pdf_columns('\n'.join(lines))
    assert 'Event 7  Girls 1 Mile Run' in out.splitlines(), out
    assert all(not l.rstrip().endswith(' E') for l in out.splitlines()), out


def test_age_group_labels():
    """USATF divisions go on the event as its age group; the event keeps
    its standard name (backend/sub5_summer.py)."""
    from backend.parser import age_group_of, strip_age_group
    cases = {'Girls 8&U Long Jump': '8 & Under', 'Women 15-16 Shot Put': '15-16',
             '100 Meter Dash Bantam Girls': 'Bantam', 'Boys 4x100 Meter Relay': None,
             'Boys 1600 Meter Run 7th/8th grade': None}
    for label, want in cases.items():
        assert age_group_of(label) == want, (label, age_group_of(label))
    assert strip_age_group('Girls 9-10 800 Meter Race Walk') == 'Girls 800 Meter Race Walk'
    # old Junior Olympic files: the parser takes the sex off the end first
    assert age_group_of('100 Meter Dash Youth') == 'Youth'
    # metres with no unit only where the whole event is metric
    from backend.sub5_summer import _value
    assert _value('3.45', 'Long Jump', metric=True) == 3.45
    assert _value('3.45', 'Long Jump', metric=False) is None
    assert _value('12-06.00', 'Shot Put') == 3.81


def test_colon_typed_for_decimal():
    """wiscassetgirls_may10.pdf typed "5:50:4" and a hurdles "19:91"; a mile
    time filed under the 100 stays as printed."""
    from backend.scraper_v2 import fix_colon_decimals
    data = {'events': [{'event': '1600 Meter Run', 'results': [{'result': '5:50:4'}]},
                       {'event': '100 Meter Hurdles', 'results': [{'result': '19:91'}]},
                       {'event': '100 Meter Dash', 'results': [{'result': '5:46'}]}]}
    fix_colon_decimals(data)
    assert [e['results'][0]['result'] for e in data['events']] == ['5:50.4', '19.91', '5:46']


def test_looselist_column_title_row_is_not_an_event():
    """A Hy-Tek relay's column titles ("Team    Relay    Finals",
    "Lane Team    Relay") read as an event header once the captions were
    stripped, filing every relay under "Team Relay" (smaa-1-1.pdf); a
    hand-typed header with captions ("DISCUS   HAND FAT PT") still reads."""
    ll = LooseListParser()
    assert ll._event_header('Team                       Relay       Finals', None) is None
    assert ll._event_header('Lane Team                  Relay', None) is None
    assert ll._event_header('DISCUS   HAND FAT PT', None) is not None


def test_usatf_division_headers_with_gender_last():
    """USATF Junior Olympic Hy-Tek prints "100 Meter Dash 8 & Under Division
    Girls" (no event number, sex last); only the CC form was read, so
    LooseList won ResultsREG1JOTF7-9-12-1.htm with marks in the club."""
    text = '\n'.join([
        '100 Meter Dash 8 & Under Division Girls',
        '=' * 70,
        '    Name                    Year Team                    Seed    Finals',
        '=' * 70,
        '  1 Golden, Princess             Westchester            15.71      15.14',
        '  2 Moore, Alana                 Metro Eagles           15.68      15.16',
        '',
        'Long Jump 11-12 Division Boys',
        '=' * 70,
        '    Name                    Year Team                    Seed    Finals',
        '=' * 70,
        '  1 Flint, Allan                 Glencadia Bu         3.03m      3.30m',
    ])
    evs = Sub5ColumnParser('jo.htm', text=text).parse()['events']
    assert [(e['gender'], e['event_name'] if 'event_name' in e else e['event'], e.get('age_group')) for e in evs] == \
        [('Girls', '100 Meter Dash', '8 & Under'), ('Boys', 'Long Jump', '11-12')], evs
    assert evs[0]['results'][0]['school'] == 'Westchester'


def test_looselist_header_with_division_phrase():
    """"4x100 Meter Relay 17-18 Division Men" was over the 35-character
    header limit, so the relay rows joined the previous race (2016
    Resultsmaine.htm)."""
    assert LooseListParser()._event_header('4x100 Meter Relay 17-18 Division Men', None) is not None
    assert LooseListParser()._event_header('4x100 Meter Relay Intermediate Girls', None) is not None


def test_points_one_space_after_the_mark():
    """Tie points printed one space after a field mark ("16-04.00 2.33333",
    caribouboys_may9.htm) were run into it: "16-04.002"."""
    text = '\n'.join([
        'Event 28  Boys Long Jump',
        '=' * 71,
        '    Name                    Year School                  Finals  Points',
        '=' * 71,
        '  1 Al Ames                      Alpha                 19-07.00    10  ',
        '  4 Bo Bean                      Beta                  16-04.00 2.33333',
        '  4 Cy Cole                      Gamma                 16-04.00 2.33333',
        '  7 Di Dunn                      Beta                  15-08.00 .333333',
    ])
    rows = Sub5ColumnParser('hj.htm', text=text).parse()['events'][0]['results']
    assert [(r['result'], r.get('points')) for r in rows] == \
        [('19-07.00', 10.0), ('16-04.00', 2.33), ('16-04.00', 2.33), ('15-08.00', 0.33)], rows


def test_racetab_time_relays_and_mark_field_events():
    """RaceTab 3 headers: relays "Team ... Time Pts", field events "Name Yr
    Team Mark Wind H# Pts". The column parser read only the running events,
    so it won with half the meet (winthrop_april28.html: 152 of 307 rows)."""
    text = '\n'.join([
        '               Varsity Boys 4x800 Meter Relay               ',
        '=' * 60,
        '    Team                                          Time   Pts',
        '=' * 60,
        '  1 Alpha High School                         9:12.7     8',
        '  2 Beta High School A                        9:37.5     6',
        '                    Varsity Boys 1600 Meter Race Walk                     ',
        '=' * 74,
        '    Name                      Yr Team                           Time   Pts',
        '=' * 74,
        '  1 Al Ames                    9 Alpha High School           8:45.80     8',
        '  2 Bo Bean                      Beta High School            9:08.20     6',
        '                            Varsity Girls Discus Throw                             ',
        '=' * 83,
        '    Name                      Yr Team                           Mark  Wind H#   Pts',
        '=' * 83,
        '  1 Cy Cole                   10 Alpha High School            72-00   NWI  1     8',
        '  2 Di Dunn                      Beta High School             62-04   NWI  2     6',
    ])
    evs = Sub5ColumnParser('racetab.htm', text=text).parse()['events']
    got = [(e['gender'], e['event'], [(r.get('school'), r['result']) for r in e['results']]) for e in evs]
    assert got == [
        ('Boys', '4x800 Meter Relay', [('Alpha High School', '9:12.7'), ('Beta High School A', '9:37.5')]),
        ('Boys', '1600 Meter Race Walk', [('Alpha High School', '8:45.80'), ('Beta High School', '9:08.20')]),
        ('Girls', 'Discus', [('Alpha High School', '72-00'), ('Beta High School', '62-04')]),
    ], got


def test_layout_columns_near_the_left_edge_and_three_wide():
    """A coach's two-column sheet whose right column starts at x=37
    (april%2014%20at%20York.pdf) was never split (only x>=40 counted); a
    three-column sheet (york_may3.pdf) split once. A Hy-Tek row's grade
    column ("Al Ames   12 Alpha") still never counts."""
    left = ['100 METER DASH', '1 REASER  TH  13.7', '2 LOMASNEY  Y  14.2', '3 SPENCER  Y  14.2']
    right = ['200 METERS', '1 BENNETT  Y  23.6', '2 JANDREAU  TH  24.0', '3 MARTIN  Y  24.3']
    third = ['DISCUS', '1 Logan Archer  S  8  117-3', '2 Chase Gendron  NY  6  114-6', '3 Jack Neary  Y  4  104-01']
    rows = [f'{a:<37}{b:<40}{c}' for a, b, c in zip(left * 4, right * 4, third * 4)]
    out = Sub5ColumnParser.split_layout_columns('\n'.join(rows)).splitlines()
    assert [l.strip() for l in out if l.strip()] == \
        [l for l in left * 4] + [l for l in right * 4] + [l for l in third * 4], out
    hytek = '\n'.join(f'  {i} Al Ames{i:<20}   12 Alpha High School      {12 + i / 10:.2f}' for i in range(1, 20))
    assert Sub5ColumnParser.split_layout_columns(hytek) == hytek


def test_looselist_coach_sheet_rows():
    """Two-column York sheets: "4 X 400" is a relay, "LASSARD  TH 11:36.0"
    (code one space from the mark), "11.6--tie", a typed half inch, a
    winner's 8 points after the code ("Kayla Gray  L  8 8.36.6"), "TM P
    MARK" captions and an "800 WC" wheelchair race."""
    text = '\n'.join([
        'GIRLS MEET AT YORK',
        'YORK 129, LAKE 103, SEACOAST 66',
        '  4 X 800             TM P MARK',
        '1 York                Y  8 12.02.7',
        '2 Lake                L  6 12.48.4',
        '  RACEWALK',
        '1 Kayla Gray          L  8 8.36.6',
        '3 LASSARD              TH 11:36.0',
        '  100 DASH',
        '1 BENNETT, C          Y    11.6--tie',
        '  TRIPLE JUMP',
        '1   Sesmith             S    8   32-2 ½',
        '5   Thompson            S    1   17- ½',
        '  800 WC',
        '1   Kristina Kouros     C    1   2:57.4h',
    ])
    evs = LooseListParser().parse(text, 'york.pdf', 'Outdoor')['events']
    got = [(e['event'], e['is_relay'], [(r.get('athlete'), r['school'], r['result']) for r in e['results']])
           for e in evs]
    assert got == [
        ('4x800 Meter Relay', True, [(None, 'York', '12.02.7'), (None, 'Lake', '12.48.4')]),
        ('1600 Meter Race Walk', False, [('Kayla Gray', 'Lake', '8.36.6'), ('LASSARD', 'TH', '11:36.0')]),
        ('100 Meter Dash', False, [('BENNETT, C', 'York', '11.6')]),
        ('Triple Jump', False, [('Sesmith', 'Seacoast', '32-2.5'), ('Thompson', 'Seacoast', '17-0.5')]),
        ('800 Meter Run Wheelchair', False, [('Kristina Kouros', 'C', '2:57.4h')]),
    ], got


def test_agate_labels_on_their_own_lines():
    """MaineToday agate (wellsboys4_30.htm, greelyboys_may3.pdf,
    cheverusboys_may14.pdf): "1,600" and "3,200" labels, a label on its own
    line after a wrapped score line, 3-digit field marks, feet'inches,
    "18-5 1/2", a note on the label, relays with no places."""
    from backend.parsers.newsprint import AgateParser
    text = '\n'.join([
        'MaineToday.com',
        'Cape 92.66, Fryeburg 91.66, Wells 67 , Greater Portland',
        'Christian 17.66',
        '3,200 relay',
        '1. Fryeburg, 9:59.8; 2. Cape, 10:09.0.',
        '100',
        '1. Vigent (W) 11.0; 2. Lail (FA) 12.6.',
        '1,600',
        '1. Moody (CE) 4:37.3; 2. Even (FA) 4:53.7.',
        'Discus 1. Tomkins (FA) 106-07; 2. Beaulieu (W) 91-08.',
        "Long jump (names jumbled): King, G, 17'11; N. Fortier, SV, 17'6.5.",
        'Triple jump 1. Howland (K) 36-11; 2. Hays (K) 34-9 1/2.',
        '4 x 100 Relay: NYA, 48.2; Greely, 48.6',
    ])
    evs = AgateParser().parse(text, 'wellsboys4_30.htm', 'Outdoor')['events']
    got = [(e['event'], [r['result'] for r in e['results']]) for e in evs]
    assert got == [('4x800 Meter Relay', ['9:59.8', '10:09.0']), ('100 Meter Dash', ['11.0', '12.6']),
                   ('1600 Meter Run', ['4:37.3', '4:53.7']), ('Discus', ['106-07', '91-08']),
                   ('Long Jump', ['17-11', '17-6.5']), ('Triple Jump', ['36-11', '34-9.5']),
                   ('4 x 100 Relay', ['48.2', '48.6'])], got


def test_field_relay_jumper_points_share_and_relay_continuation_page():
    """Results.htm-Relays "Boys Long Jump Relay B - LJ - IN": the team
    points share after a jumper's mark ("21-07.50    2.66") was read as the
    mark. New England indoor 4x400: a continuation page's rows sit right of
    the first page's columns, and every one was lost."""
    text = '\n'.join([
        'Event 18  Boys Long Jump Relay B - LJ - IN',
        '=' * 73,
        '    Name                    Year School                  Seed     Finals ',
        '=' * 73,
        '  1 Al Ames                      Alpha                          21-07.50    2.66',
        '  2 Bo Bean                      Beta                           19-09.00    2   ',
        '',
        '  Girls 4x400 Meter Relay',
        '=' * 67,
        '    School                                               Finals H#',
        '=' * 67,
        "  1 Alpha-MA 'A'                                       3:55.70    5",
        ' ....Girls 4x400 Meter Relay',
        "  2 Beta-CT 'A'                                                       3:57.44   5",
        '    1) Williams, Kiylah 12                               2) Duncan, Ann 11',
        "  3 Gamma-RI 'A'                                                      4:01.22   4",
    ])
    evs = Sub5ColumnParser('relays.htm', text=text).parse()['events']
    got = [(e['event'], [(r.get('school'), r['result']) for r in e['results']]) for e in evs]
    assert got[0] == ('Long Jump', [('Alpha', '21-07.50'), ('Beta', '19-09.00')]), got
    assert got[1] == ('4x400 Meter Relay', [("Alpha-MA 'A'", '3:55.70'), ("Beta-CT 'A'", '3:57.44'),
                                            ("Gamma-RI 'A'", '4:01.22')]), got


def test_collateral_guards_for_the_column_and_agate_fixes():
    """Found by the run_all / compare2 check: a collapsed single-space relay
    row is not read past the column (KVAC-Small-Medium-May-28-2021.pdf, where
    the loose-list reading is whole); a left list's points cell is no
    column start when a farther column has the votes (APR-14-RESULTS.pdf);
    "Boys 4 x 100" is a relay header; agate text wrapped mid-label still
    reads ("High" / "jump:1."), and an entry is not taken for a label
    ("C. King, G, 5-2. Shot Put:")."""
    from backend.parsers.newsprint import AgateParser
    text = '\n'.join([
        'Event 1 Girls 4x800 Meter Relay',
        '=' * 80,
        'School Seed Finals Points',
        '=' * 80,
        "1 Morse High School 'A' 11:16.66 10:47.74 10",
    ])
    evs = Sub5ColumnParser('kvac.pdf', text=text).parse()['events']
    assert sum(len(e['results']) for e in evs) == 0, evs
    rows = []
    for i in range(1, 16):
        rows.append(f'    NAME{i:<14}  TH   1:04.{i:02d}   5       DOW{i:<10}  TH   31.{i:02d}')
        rows.append(f'{"":42}{i}   PINETTE{i:<8} W    24.{i:02d}     6')
    cols = Sub5ColumnParser.split_layout_columns('\n'.join(rows)).splitlines()
    assert any(l.rstrip().endswith('1:04.01   5') for l in cols), cols[:3]
    assert LooseListParser()._event_header('Boys 4 x 100', None) == ('Boys', '4 x 100')
    # (an exhibition relay with no place: kept, flagged)
    assert LooseListParser()._parse_unranked_row('x   YORK B         Y    54.34', True) == \
        {'school': 'YORK', 'result': '54.34', 'athletes': [], 'grade': '', 'type': 'Finals', 'exhibition': True}
    text = '\n'.join([
        'Gray', 'Gray-New Gloucester 70', 'Lake Region 65 Greely 44',
        '3200 relay:1. Greely 8:55;', '2. Lake Region 9:37. High', 'jump:1. Burke (Gr) 6-0; 2.',
        "OGrady (LR) 5-10. Long jump:1. Brookes", '(GNG) 17-4; 2. C. King, G, 5-2. Shot Put: M. Burgess, G, 52-6.',
    ])
    evs = AgateParser().parse(text, 'gray15april04b.htm', 'Outdoor')['events']
    assert [(e['event'], len(e['results'])) for e in evs] == \
        [('4x800 Meter Relay', 2), ('High Jump', 2), ('Long Jump', 2), ('Shot Put', 1)], evs


def test_milesplit_xc_title_variants_and_tight_columns():
    """Hy-Tek / RaceTab sheets the MileSplit queue left unread: level and class prefixes and typed slips in
    the race title, a school cut to its column one space before the time, a name filling its column one
    space before the year, a course-record flag on the time, RaceTab 2008 "mm:ss:hh" times, "Wells  High
    School" printed with a double space, typed "14.55" for 14:55, relay events closing the race above."""
    from backend import milesplit as ms
    assert ms.xc_header('Junior High Boys 1.5 Mile Run') == ('Boys', '1.5 Mile', 'Middle School')
    assert ms.xc_header('Division 1             Varsity Boys 5000 Meter Run ') == ('Boys', '5k', 'Division 1')
    assert ms.xc_header('Varsrity Boys 2.93 Mile Run') == ('Boys', '2.93 Mile', 'Varsity')
    assert ms.xc_header('Class B Boys 5K Run') == ('Boys', '5k', 'Class B')
    assert ms.xc_header('Mens 3,000 Meters Middle School Results') == ('Boys', '3k', 'Middle School')
    assert ms.xc_header('Boys 1.5 Mile Run CC 6TH GRADE') == ('Boys', '1.5 Mile', '6th Grade')
    assert ms.xc_header('Event 1  Boys 5k Combinded Results') is None          # an all-classes re-ranking
    assert ms.xc_header('Event 3  Girls 3 x 1.7 Mile Relay') is None          # team times
    assert ms.xc_header('Event 2  Boys JV') is None and ms.xc_header('Event 2  Boys JV', True) == ('Boys', '', 'JV')
    text = '\n'.join([
        '                   Varsity Girls 5000 Meter Run                   ',
        '=================================================================',
        '    Name                  Yr Team                      Time   Pts',
        '-----------------------------------------------------------------',
        '  1 Tristan Butterfield   SO Orono                 14:24.01R     1',
        '  2 Jillian Richardson    10 Edward Little High S 21:47.00      2',
        '  3 Maquila Dimasrantonio 11 Massabesic High Scho  21:48.00     3',
        ' 78 Tristan Brown            Wells  High School    21:03.14   78',
        ' 98 Abendroth,               Wells                24:02:00     33 ',
        ' 99 Max Knutsen              SP                      15.36     --',
        'Event 3  Girls 3 x 1.7 Mile Relay',
        '  1 George Stevens Academy  \'A\'                        34:58.14  ',
    ])
    ev, _ = ms.parse_xc(text)
    rows = ev[0]['results']
    assert [(r['place'], r['school'], r['result']) for r in rows] == [
        (1, 'Orono', '14:24.01'), (2, 'Edward Little High S', '21:47.00'), (3, 'Massabesic High Scho', '21:48.00'),
        (78, 'Wells High School', '21:03.14'), (98, 'Wells', '24:02.00'), (99, 'SP', '15:36')], rows
    assert rows[2]['athlete'] == 'Maquila Dimasrantonio' and rows[2]['grade'] == '11'


def test_milesplit_xc_ruler_sheets_and_mixed_events():
    """Five K Sport / SparkFlashGap sheets under an "=====" ruler (a name run past its column, a header
    typed off its ruler, "*** TEAM SCORE ***" blocks), a Hy-Tek Mixed event printed by sex under
    "Results - Women ...", and Run In A Race "Time Pace Year Team" rows."""
    from backend import milesplit as ms
    ruler = '\n'.join([
        'Parker Pruett Middle School XC meet - 1.71 MILES',
        'Boyss 1.71 Mile Run',
        'Place TmPl No.  Name                   G G School           Time  ',
        '===== ==== ==== ====================== = = ================ ===== ',
        '    1    1  192 Joshua Bell            M 8 Blue Hill        11:22 ',
        '    2    2  314 Sean Murray            M 8 Tremont          11:30 ',
        '    3       292 Ian Brenner-Simpson    M   Mountain View    11:31 ',
        '                  *********** BOYS TEAM SCORE **********',
        '  1. Blue Hill       ',
        '            1    5   10   13   14  (20) (27) =    43',
    ])
    ev, rk = ms.parse_xc_ruler(ruler)
    assert [(e['event'], e['gender'], len(e['results'])) for e in ev] == [('1.71 Mile Run CC', 'Boys', 3)], ev
    assert ev[0]['results'][2]['school'] == 'Mountain View' and rk[0]['teams'][0]['score'] == 43
    cols = [(0, 5, 'place'), (6, 10, 'tmpl'), (11, 15, 'na'), (16, 34, 'yr'), (35, 38, 'yr'), (39, 59, 'school'), (60, 65, 'time')]
    r = ms._ruler_cut('   11    9  268 Evan Schneider         Loranger Memorial Sc 15:46 ', cols)
    assert (r['place'], r['team_place'], r['athlete'], r['school'], r['result']) == (11, 9, 'Evan Schneider', 'Loranger Memorial Sc', '15:46')
    hy = '\n'.join([
        'Event 8 Mixed 2.6 Mile Run Race # 8',
        '================================================================',
        '    Name                    Year School                  Finals',
        '================================================================',
        'Results - Women 2.6 Mile Run',
        '  1 Johnson, Margaret        WJR BRUN                  19:29.60',
        'Results - Men 2.6 Mile Run',
        '  1 Shaughnessy, Will        MSR BRUN                  13:22.68',
    ])
    ev, _ = ms.parse_xc_any(hy)
    assert [(e['event'], e['gender'], len(e['results'])) for e in ev] == \
        [('2.6 Mile Run CC Race 8', 'Girls', 1), ('2.6 Mile Run CC Race 8', 'Boys', 1)], ev
    ria = '\n'.join([
        'Boys 4k Run',
        'Place     Bib # Name                      Time        Pace  Year  Team           ',
        '    1      90   Henry Horne               12:55.32    5:12  11    Freeport            ',
        '    1  351 Sands, Jeremiah 17:13.19 3',
    ])
    ev, _ = ms.parse_xc_any(ria)
    assert [(r['athlete'], r['grade'], r['school']) for r in ev[0]['results']] == [('Henry Horne', '11', 'Freeport')]


def test_milesplit_xc_tab_lists_and_team_rows():
    """Loose tab sheets (a header whose first cell is the race, "Place`", "9.26" typed for 9:26, a
    "Place Team Time" relay-total table that is no race), typed "1 Name (School) 22:57" lists, and a team
    row whose score sits one space after a cut name."""
    from backend import milesplit as ms
    tab = '\n'.join(['Freshman Boys 1.7 Mile Run\t\t\t\t', '\tBoys Freshman\tName\tSchool\tTime',
                     '\t1\tDowning\tGorham\t10:30', '\t2\tHowland\tScarborough\t10.34'])
    ev, _ = ms.parse_xc_tab(tab, loose=True)
    assert [(e['event'], e['gender'], [r['result'] for r in e['results']]) for e in ev] == \
        [('1.7 Mile Run CC Freshman', 'Boys', ['10:30', '10:34'])], ev
    ev, _ = ms.parse_xc_tab('Place\tTeam\t\tTime\n1\tBrunswick \'A\'\t\t58:38:00', loose=True)
    assert not any(e['results'] for e in ev)
    ev, _ = ms.parse_xc_lists('Girls\n1 Alexa Johnson (Narraguagus) 22:57\n14 Jack Farnsworth (Sumner)22:29')
    assert [(r['place'], r['athlete'], r['school']) for r in ev[0]['results']] == \
        [(1, 'Alexa Johnson', 'Narraguagus'), (14, 'Jack Farnsworth', 'Sumner')]
    text = '\n'.join([
        'Event 2  Boys 2 Mile Run CC', '    Name                    Year School                  Finals  Points',
        '  1 A B                    Presque Isle Middle Sc     12:00.00     1',
        '                                   Team Scores',
        ' 4 Presque Isle Middle Schoo 102    9    21    22     24    26    27',
    ])
    _, rk = ms.parse_xc(text)
    t = rk[0]['teams'][0]
    assert (t['team'], t['score'], t['places']) == ('Presque Isle Middle Schoo', 102, [9, 21, 22, 24, 26, 27]), t


def test_milesplit_xc_scoring_place_columns_names_and_coops():
    """"SCORING PLACE FIRST NAME LAST NAME TEAM TIME" (place in the second column, unscored rows 'x');
    'Lutters,, Eliana'; a name cut at 20 characters that runs into the grade; co-op labels kept."""
    from backend import milesplit as ms
    tab = '\n'.join(['Boys 2 Mile Run', 'SCORING\tPLACE\tFIRST NAME\tLAST NAME\tTEAM\tTIME',
                     '1\t1\tTodd\tKenny\tBath\t12:59', 'x\t2\tAl\tBee\tTripp\t13:10'])
    ev, _ = ms.parse_xc_tab(tab, loose=True)
    assert [(r['place'], r['athlete'], r.get('team_place')) for r in ev[0]['results']] == \
        [(1, 'Todd Kenny', 1), (2, 'Al Bee', None)], ev
    assert ms.xc_name('Lutters,, Eliana') == 'Eliana Lutters'
    assert ms.canon('Houlton/GHCA') == 'Houlton/GHCA' and ms.canon('Boothbay/Wiscasset') == 'Boothbay/Wiscasset'
    assert ms.canon('Maine School of') == 'Maine School of Science and Mathematics'


def test_hytek_record_line_is_not_the_meet_date():
    """'Meet: * 17:56.69  9/29/2012  Name' is when a record was set; the title dates the meet,
    and a title's session time ('Week 2:55 - 1/15/05') is not a record."""
    from backend.parser import Sub5ColumnParser
    text = '\n'.join([
        '             2013 Maine XC Festival of Champions - 10/5/2013', '                               Belfast, ME',
        '  Event 1  Girls 5k Run CC', '=' * 60,
        '      Course: # 17:48.00  10/30/2004  Cassie Hintz, Old Town',
        '        Meet: * 17:56.69  9/29/2012   Bethanie Brown, Waterville',
        '    Name                    Year School                  Finals  Points', '=' * 60,
        '  1 Kialeigh Marston          SO Bonny Eagle           18:42.94    1',
        '  2 Shannon Conley            SR South Portland        18:59.21    2'])
    assert Sub5ColumnParser('foc13girlsoverall.txt', text=text).parse()['date'] == '2013-10-05'


def test_audit_fixes_2026_10_21():
    """Heats restarting at place 1 under one event ("Results - Unseeded A", "Grade 9/10 - Men") are
    races of their own; a place typed twice takes the next; XCRun DNF rows are kept; an untitled
    RunScore team list is read; a wrapped Hy-Tek license line and a mixed-case "Hy-Tek's" header."""
    from backend.parser import _SECTION2_RE
    assert _SECTION2_RE.match('Results - Unseeded A') and _SECTION2_RE.match('Grade 9/10 - Men')
    assert not _SECTION2_RE.match('Results - Women') and not _SECTION2_RE.match('Results - Men Large School')
    from backend.parsers.xcrun import _ROW_DNF
    assert _ROW_DNF.match('DNF    34    0    ALEXANDRA CULP                     WINTHROP                  :   : 0.0')
    from backend.parsers.xcscores import parse_xc_team_scores
    rs = '\n'.join(['  157       142 PATRICK COX                   M OLD ORCHARD BEACH         36:33', '',
                     '  1. YARMOUTH HIGH SCHOOL     ', '            2    3    4    5    7  (19) (26) =    21',
                     '  2. FREEPORT HIGH SCHOOL     ', '            1    8   10   11   31  (56) (70) =    61'])
    b = parse_xc_team_scores(rs)
    assert [(t['team'], t['score'], t['places'][:5]) for t in b[0]['teams']] == \
        [('YARMOUTH HIGH SCHOOL', 21.0, [2, 3, 4, 5, 7]), ('FREEPORT HIGH SCHOOL', 61.0, [1, 8, 10, 11, 31])], b
    from backend.scraper_v2 import hytek_header_meta, not_a_title
    h = hytek_header_meta('Licensed to Down East Sports Timing - Contractor License\n'
                          "                 HY-TEK's Meet Manager 10/24/2025 07:06 AM\n"
                          '        YORK COUNTY XC FESTIVAL 10 23 - 10/23/2025\n             NOBLE\n           Results\n')
    assert (h['meet'], h['venue']) == ('YORK COUNTY XC FESTIVAL 10 23', 'NOBLE'), h
    h = hytek_header_meta("Caribou High School          Hy-Tek's MEET MANAGER 2:33 PM 9/13/2025 Page 1\n"
                          '2025 Caribou XC Invitational - 9/13/2025\n9/13/2025\nResults\n')
    assert h['meet'] == '2025 Caribou XC Invitational', h
    assert not_a_title('at Bucksport High School') and not_a_title('Event 4 Boys 5k Run CC') and \
        not_a_title('Biddeford   Bonny Eagle   Cheverus   Deering') and not not_a_title('Bucksport Invitational')


def test_milesplit_bulk_printed_points_and_held_races():
    """milesplit_bulk: a recount that misses the sheet's tie rule is accepted only when every team's places
    are its runners' printed team points (no scorer lost); a race already held at the same times is not
    stored twice."""
    from backend import milesplit_bulk as mb
    rows = [{'place': p, 'athlete': 'R%d' % p, 'school': s, 'result': '20:%02d' % p, 'team_place': tp}
            for p, s, tp in [(1, 'A', 1), (2, 'A', 2), (3, 'B', 3), (4, 'A', 4), (5, 'A', 5), (6, 'B', 6),
                             (7, 'A', 7), (8, 'B', 8), (9, 'B', 9), (10, 'B', 10)]]
    doc = {'events': [{'event': '5k Run CC', 'gender': 'Boys', 'results': rows}],
           'team_rankings': [{'kind': 'xc', 'gender': 'Boys', 'event_idx': 0, 'teams': [
               {'team': 'A', 'score': 19, 'places': [1, 2, 4, 5, 7]}, {'team': 'B', 'score': 36, 'places': [3, 6, 8, 9, 10]}]}]}
    assert mb.printed_points_agree(doc)
    doc['team_rankings'][0]['teams'][0].update(score=20, places=[1, 2, 4, 5, 8])   # not A's printed points
    assert not mb.printed_points_agree(doc)
    mb._HELD_RUNNERS[(1999, 'XC')] = {'held': mb._near({'events': [{'results': [dict(r, result='20:%02d.4' % r['place']) for r in rows]}]})}
    assert mb.race_homes(doc, 1999, 'XC') == ['held']


# XCRun team pages posted without the overall list (Boothbay 2012, Auburn MS
# 2021): each team's runners under "TEAM  Places: N", two teams per line, a
# long name wrapped onto the next line, a team's first runner printed on the
# other block's header line.
XCRUN_TEAM_PAGES = """\
                                 PINE RIDGE CROSS COUNTRY
 09/12/2012                            BOYS RACE
        Place TEAM                Points     SCORES                                        Ave Time       Spread
          1    ASHFORD               15       1     2     3         4      5                :17:10        0:40
          2    BELMONT               40       6     7     8         9     10                :18:30        0:30

      ASHFORD                   Places:  15                             BELMONT                       Places:  40
1     ARLO VANTREE         11      0:16:50        5:25        6         CODY MARLOWE            11       0:18:10     5:51
2     BENNETT ROSSI        10      0:17:00        5:28        7         DEXTER                  12       0:18:20     5:54
3     CALEB ORMSBY          9      0:17:10        5:31                  FAIRWEATHER-HOLM
4     DARIUS PELL          12      0:17:20        5:35        8         EZRA QUILL               9       0:18:30     5:57
5     EAMON TRASK          11      0:17:30        5:38        9         FINN GALLOWAY           10       0:18:40     6:00
      CARVER                    Places:   0                   10        GUS HARTWELL            10       0:18:50     6:03
11    HUGO LARK            10      0:19:30        6:17        12        IAN MOSS                11       0:19:40     6:20
"""


def test_xcrun_team_pages_rebuild_the_race_in_place_order():
    from backend.parsers.xcrun import XCRunTeamPagesParser
    assert XCRunTeamPagesParser.matches(XCRUN_TEAM_PAGES)
    out = XCRunTeamPagesParser().parse(XCRUN_TEAM_PAGES, 'BoysScores.pdf', 'XC')
    ev, = out['events']
    rows = ev['results']
    assert ev['gender'] == 'Boys' and [r['place'] for r in rows] == list(range(1, 13))
    assert rows[6]['athlete'] == 'Dexter Fairweather-Holm'          # (the wrapped name)
    assert rows[10]['school'] == 'Carver' and rows[11]['school'] == 'Belmont'
    assert rows[0]['result'] == '16:50' and rows[0]['grade'] == '11'
    assert out['date'] == '2012-09-12'
    assert qaqc.xc_verify_parsed(out)['status'] == 'verified'
    # (a page that also holds the overall PLC BIB PTS list is XCRunParser's)
    assert not XCRunTeamPagesParser.matches('PLC BIB    PTS   NAME   TEAM   TIME\n' + XCRUN_TEAM_PAGES)


# Hand-made sheets with the place column after the name (Caribou 2005,
# Cheverus / SMAA second-seven 2008, Lee Academy 2020): typed cells matched to
# the header's fields; a team-score table beside the list is dropped.
PLACE_LATER = """\
      BOYS Cross Country Meet 9-14-05
                     NAME       C       TEAM   TIME IN   PLACE
Arlo Vantree                            AVE     15:05      1
Bennett Rossi                           BEL     15:37      2
Caleb Ormsby                            AVE     15:43      3
Darius Pell                              BEL    15:48      4
Eamon Trask     AVE    16:01   5
"""

PLACE_LATER_SCORES = """\
First     Last             School   Place        Score        Time                    Score
Arlo      Vantree          A                 1            1   16:11 Ashford       A      17
Bennett   Rossi            B                 2            2   16:17 Belmont       B      40
Caleb     Ormsby           A                 3            3   16:49
Darius    St. Pell         A                 4                16:53
Eamon     Trask            B                 5            4   16:58
"""


def test_place_later_tables():
    from backend.parsers.headertable import PlaceLaterTableParser
    out = PlaceLaterTableParser().parse(PLACE_LATER, 'caribou9_14b.pdf', 'XC')
    rows = out['events'][0]['results']
    assert out['events'][0]['gender'] == 'Boys'
    assert [(r['place'], r['athlete'], r['school'], r['result']) for r in rows][::4] == [
        (1, 'Arlo Vantree', 'AVE', '15:05'), (5, 'Eamon Trask', 'AVE', '16:01')]
    out = PlaceLaterTableParser().parse(PLACE_LATER_SCORES, 'XC_8_28_boys.pdf', 'XC')
    rows = out['events'][0]['results']
    assert [r['place'] for r in rows] == [1, 2, 3, 4, 5]
    assert rows[0]['athlete'] == 'Vantree, Arlo' and rows[0]['school'] == 'A' and rows[0]['team_place'] == 1
    assert rows[3]['athlete'] == 'St. Pell, Darius' and 'team_place' not in rows[3]
    assert rows[1]['result'] == '16:17'                 # ("16:17 Belmont": the side table set apart)
    assert rows[4]['team_place'] == 4                   # (not the side table's 17 / 40)


# A timer's field names over a place-first sheet (MVC preview 2013):
# "ovrallplc lname fname ltime team pts", the clock's zero hour, 0 points for
# a non-scorer, points run into the team.
TIMER_FIELDS = """\
ovrallplc   lname           fname      ltime         team          pts
    1       VANTREE         ARLO       00:17:24.26                  0
    2       ROSSI           BENNETT    00:17:55.46   ASHFORD       1
    3       ORMSBY          CALEB      00:18:03.68   BELMONT       2
    4       PELL            DARIUS 00:18:10.57       ASHFORD       3
    5       TRASK           EAMON      00:18:19.83   CEDAR VALLEY0
    6       QUILL           EZRA       00:18:26.27   CEDAR VALLEY 4
"""


def test_header_table_timer_fields():
    from backend.parsers.headertable import HeaderTableParser
    out = HeaderTableParser().parse(TIMER_FIELDS, 'mvcpreviewboys_sept25.pdf', 'XC')
    rows = out['events'][0]['results']
    assert [r['place'] for r in rows] == [1, 2, 3, 4, 5, 6]
    assert rows[0]['result'] == '17:24.26' and 'team_place' not in rows[0]
    assert rows[1]['athlete'] == 'Rossi, Bennett' and rows[1]['team_place'] == 1
    assert rows[3]['athlete'] == 'Pell, Darius' and rows[3]['result'] == '18:10.57'
    assert rows[4]['school'] == 'Cedar Valley' and rows[5]['school'] == 'Cedar Valley'
    assert rows[5]['team_place'] == 4


UNPLACED_LIST = """\
Medfield 29, Belmont 66

Arlo Vantree (MED) 16:38
Bennett Rossi (Bel) 16:55
Caleb O’Mara (MED) 16:58
Darius Pell ((MED) 17:08
Eamon Trask (Bel) 17:32
Ezra Quill (Bel) 17:33
Finn Gall (MED) 17:38
Gus Hart (Bel) 17:41
Hugo Lark (MED) 17:53
"""

UNPLACED_PARAGRAPH = """<p>Girls` meet results: Ashford-27, Belmont-40</p><p> Vantree(A)-19:34, L. Rossi(B)-19:53,
Ormsby(A)-21:11, Pell(A)-21:42, Trask(B)-21:44, Quill(B)-21:45, ME
Gall(A)-21:57</p><p>Boys` Meet Results: Ashford-19</p><p> Hart(A)-16:43, Lark(B)-17:02, Moss(A)-17:34,
Nash(A)-17:40, Oake(B)-17:45</p>"""

COMMA_LIST = """\
Boys Results
1, Vantree, Ash Hill 17:11.79;
2, Bennett Rossi, North Bay 17:29.36;
3, Caleb Ormsby, Ash Hill 17:45.49;
4, Darius Pell, Cedar 18:05.39;
5, Eamon Trask, North Bay 18:37.91;
6, Ezra Quill, Cedar 18:44.48;
7, Finn Gall, Ash Hill 19:07.45;
8, Gus Hart, Cedar 19:17.99;
"""

TEAM_FIRST = """\
     Team    #          Name             Time               Team    #           Name              Time
1     Ash   303     Vantree, Arlo       0:16:23      9     Bel    295      Rossi, Ben           0:19:37
2     Bel   452     Ormsby, Cal         0:17:09      10    Ash    293     Pell, Dan            0:19:40
3     Ash   456   Trask, Eamon          0:17:31      11    Bel    351    Quill, Ezra           0:19:47
4     Ash   301       Gall, Finn        0:17:42      12    Ash    287     Hart, Gus            0:20:12
5     Bel   292      Lark, Hugo         0:17:42      13    Bel    305      Moss, Ian            0:20:49
6     Bel   451     Nash, Jon           0:17:58      14    Ash    Unk      Oake, Kit            0:26.:38
7     Ash   458    Pike, Lou            0:18:05      15    Bel    300       Reed, Max           0:34.22
8     Bel   280 Abdirahman, Ned         0:18:11      16    Ash    442     Shaw, Nat            0:35:22
"""

PLACE_TIME_NAME = """\
Boys Results
   1    18:09 Arlo Vantree SP               9      21:45 Ian Moss SC
   2    18:43 Ben Rossi SP                  10     27 :45 Jon Nash SC
   3    19:09 Cal Ormsby S                  11     29:07 Kit Oake
   4    19:13 Dan Pell S
   5    19:18 Eamon Trask SP
   6    19:20 Ezra Quill SP
   7    19:29 Finn Gall SC
   8    19:52 Gus Hart SP
"""


def test_xclist_lists_without_places_and_odd_row_orders():
    from backend.parsers.xclist import XCListParser
    rows = XCListParser().parse(UNPLACED_LIST, 'medfieldboys9_21.pdf', 'XC')['events'][0]['results']
    assert len(rows) == 9 and [(r['place'], r['athlete'], r['school']) for r in rows][:4] == [
        (1, 'Arlo Vantree', 'MED'), (2, 'Bennett Rossi', 'Bel'), (3, 'Caleb O’Mara', 'MED'),
        (4, 'Darius Pell', 'MED')]
    evs = XCListParser().parse(UNPLACED_PARAGRAPH, 'ashford9_16.htm', 'XC')['events']
    assert [(e['gender'], len(e['results'])) for e in evs] == [('Girls', 7), ('Boys', 5)]
    assert evs[0]['results'][1]['athlete'] == 'L. Rossi' and evs[0]['results'][6]['school'] == 'A'
    rows = XCListParser().parse(COMMA_LIST, 'ashinvite.pdf', 'XC')['events'][0]['results']
    assert (rows[1]['athlete'], rows[1]['school'], rows[1]['result']) == ('Bennett Rossi', 'North Bay', '17:29.36')
    rows = XCListParser().parse(TEAM_FIRST, 'ashboys.pdf', 'XC')['events'][0]['results']
    assert [r['place'] for r in rows] == list(range(1, 17))
    assert (rows[0]['athlete'], rows[0]['school'], rows[0]['result']) == ('Vantree, Arlo', 'Ash', '16:23')
    assert rows[7]['athlete'] == 'Abdirahman, Ned' and rows[13]['athlete'] == 'Oake, Kit'
    assert rows[13]['result'] == '26:38' and rows[14]['result'] == '34:22'     # (the sheet's typos)
    rows = XCListParser().parse(PLACE_TIME_NAME, 'sanfordboys_oct2.pdf', 'XC')['events'][0]['results']
    assert [r['place'] for r in rows] == list(range(1, 12))
    assert (rows[0]['athlete'], rows[0]['school'], rows[0]['result']) == ('Arlo Vantree', 'SP', '18:09')
    assert rows[9]['result'] == '27:45' and rows[10]['athlete'] == 'Kit Oake'


def test_unplaced_hytek_rows_and_shifted_font_text():
    from backend.scraper_v2 import number_unplaced_hytek, unshift_font_text
    rows = '\n'.join('    Runner %s          %s Ashford             1%d:%02d.65 F        5:17.17'
                     % (chr(65 + k) + chr(97 + k) * 3, 'SR' if k % 2 else '17', 3 + k // 6, 10 + k)
                     for k in range(12))
    out = number_unplaced_hytek('  1  Boys   2.6 Mile Run\n====\n    Name                     Age Team\n====\n' + rows)
    lines = out.splitlines()[4:]
    assert lines[0].startswith('  1 Runner Aaaa') and lines[11].startswith(' 12 Runner Llll')
    assert ' 17 ' not in lines[0] and ' SR ' in lines[1]        # (an age is no grade: left blank)
    assert number_unplaced_hytek(rows.splitlines()[0]) == rows.splitlines()[0]
    plain = 'Team  Name  Time\n' + '\n'.join('%d  Ash  Vantree, Arlo  1%d:2%d' % (k, k, k) for k in range(10))
    shifted = ''.join(c if c in ' \n' else chr(ord(c) - 29) for c in plain)
    assert unshift_font_text(shifted) == plain
    assert unshift_font_text(plain) == plain


def test_team_cut_by_a_double_space_and_bib_after_place():
    from backend.scraper_v2 import complete_cut_teams
    from backend.parsers.xclist import XCListParser
    rows = [{'athlete': 'R%d' % k, 'school': s} for k, s in enumerate(
        ['Ashford', 'John Bapst', 'John', 'John Bapst', 'John Bapst', 'Spruce Mt', 'Spruce', 'Spruce Mt', 'Spruce Mt'])]
    data = {'events': [{'results': rows}]}
    complete_cut_teams(data, '  3 R2       FR <span class=GramE>John<span>&nbsp; </span>Bapst</span>  20:32\n'
                             '  7 R6       6 SPRUCE                :17:41.0\n')
    assert rows[2]['school'] == 'John Bapst'        # (printed "John  Bapst": one team)
    assert rows[6]['school'] == 'Spruce'            # (printed "SPRUCE" alone: another entry)
    bib = ('Finish                                                     Finish\n'
           'Order       BIB#   Name                     School         Time\n' +
           ''.join('  %2d         %d   Runner %s          Ashford        1%d:%02d.4\n'
                   % (k, 340 + 3 * k, chr(64 + k) * 4, 8 + k // 6, 10 + k) for k in range(1, 11)))
    rows = XCListParser().parse(bib, 'leavitt_boys.pdf', 'XC')['events'][0]['results']
    assert [r['place'] for r in rows] == list(range(1, 11)) and rows[0]['athlete'] == 'Runner AAAA'


def test_windows_1252_nbsp_padding_in_a_hytek_txt(tmp=None):
    """Latin-1 non-breaking spaces typed as a fixed-width row's padding
    ("Diego\\xa0Villamarin\\xa0\\xa0\\xa0JR St. Dominic"): read as spaces; a
    stray one beside an ordinary space ("Calvin\\xa0 Nelson") is dropped."""
    import tempfile
    from backend.scraper_v2 import _parse_one_file
    import json as _json
    head = (b'Boys 5000 Meter Run Class C\r\n\r\nResults - Men Class C\r\n'
            b'  1 Arlo Vantree              SR Ashford               17:19.64    1\r\n')
    body = b''.join(b' %2d %s%s%s %s Cedar Valley Academy  1%d:%02d.%02d    %d\r\n' % (
        k, b'Runner', b'\xa0', (b'X' * k).ljust(18, b'\xa0'), b'JR', 7 + k // 8, 20 + k, k, k)
        for k in range(2, 12))
    stray = b' 12 Calvin\xa0 Nelson             SO Ashford               19:59.10   12\r\n'
    d = tempfile.mkdtemp()
    src, out = os.path.join(d, 'class-c-boys.txt'), os.path.join(d, 'out.json')
    open(src, 'wb').write(head + body + stray + b'\x92')     # (\x92: not utf-8)
    _parse_one_file((src, out, 'XC'))
    rows = _json.load(open(out))['events'][0]['results']
    assert len(rows) == 12
    assert rows[1]['athlete'] == 'Runner XX' and rows[1]['school'] == 'Cedar Valley Academy'
    assert rows[1]['grade'] == 'JR'
    assert rows[11]['athlete'] == 'Calvin Nelson' and rows[11]['school'] == 'Ashford'


# PVC Hy-Tek: one event, two class/size sections ("Large School Results" with
# AB- schools, "Small school Results" with CD-; the 2008 sheets say
# "Class C School Results" / "Class B  School Results"), each with its own
# places and its own Team Scores table. Each section is its own race, its
# team table is tied to it, and the class prefix is not part of the school.
def _pvc_sections(head1, head2, p1, p2, s1, s2):
    def rows(prefix, teams):
        out = []
        for k in range(10):
            t = teams[k % 2]
            out.append(f"{k + 1:>3} {'Runner' + chr(65 + k) + ' Test':<24}SR {prefix}-{t:<18} "
                       f"{5 + k // 4}:{10 + k:02d}.0   {17 + k}:{10 + k:02d}.00 {k + 1:>4}")
        return out

    def scores(prefix, teams):
        return [f"   1 {prefix}-{teams[0]:<24}25    1    3    5    7    9",
                "      Total Time:  1:29:03.64",
                f"   2 {prefix}-{teams[1]:<24}30    2    4    6    8   10",
                "      Total Time:  1:30:03.64"]
    return "\n".join([
        "                     PVC Championship - 10/16/2004", "                          Results",
        "  Event 4  Boys 3.06 Mile Run CC Varsity",
        "=" * 82, "    Name                    Year School                Avg Mile     Finals  Points",
        "=" * 82, head1] + rows(p1, s1[0]) + ["", head2] + rows(p2, s2[0]) + [
        "", "                                   Team Scores", "=" * 81,
        "Rank Team                      Total    1    2    3    4    5   *6   *7   *8   *9", "=" * 81,
        head1] + scores(p1, s1[0]) + [head2] + scores(p2, s2[0])) + "\n"


def test_pvc_size_and_class_sections_are_races():
    from backend.scraper_v2 import _pair_xc_blocks
    for h1, h2, p1, p2, lab1, lab2 in (
            ("Large School Results", "Small school Results", "AB", "CD", "Large School", "Small School"),
            ("Class C School Results", "Class B  School Results", "C", "B", "Class C", "Class B")):
        text = _pvc_sections(h1, h2, p1, p2, (("Alpha High", "Beta High"),), (("Gamma Academy", "Delta High"),))
        res = Sub5ColumnParser('pvc04bvsl.txt.htm', text=text).parse()
        evs = res['events']
        assert [(e['event'], e['gender'], e.get('section'), len(e['results'])) for e in evs] == \
            [('3.06 Mile Run CC Varsity', 'Boys', lab1, 10), ('3.06 Mile Run CC Varsity', 'Boys', lab2, 10)], evs
        assert [r['place'] for r in evs[1]['results']] == list(range(1, 11))
        assert {r['school'] for r in evs[0]['results']} == {'Alpha High', 'Beta High'}
        assert {r['school'] for r in evs[1]['results']} == {'Gamma Academy', 'Delta High'}
        blocks = parse_xc_team_scores(text)
        assert [b.get('section') for b in blocks] == [lab1, lab2], blocks
        assert [t['team'] for t in blocks[1]['teams']] == ['Gamma Academy', 'Delta High']
        _pair_xc_blocks(evs, blocks)
        assert [b['event_idx'] for b in blocks] == [0, 1]
        assert _verify(res, blocks)['status'] == 'verified'


# Cape Elizabeth (2009): the Team column is cut at 25 characters and runs
# into the time with one space; a Poland scorer line ends in a "-" (no 7th).
CAPE_CUT = """\
         WMC - A, B @ Cape - 2009-09-11
         Cape Elizabeth XC Course, Cape Elizabeth, ME

                       Varsity Boys Three Mile Run

=========================================================================
    Name                      Yr Team                          Time   Pts
=========================================================================
  1 Alan Test                    York High School          15:27.10     1
  2 Reid Sample               11 Cape Elizabeth High Schoo 16:39.00     2
  3 Peter Example             12 Cape Elizabeth High Schoo 16:50.00     3
  4 Thom Fake                 10 Poland Regional High Scho 16:56.00     4
  5 Dan Madeup                   York High School          16:59.00     5
  6 Tris Nobody                  York High School          17:03.00     6
  7 Bobby Pretend             12 Cape Elizabeth High Schoo 17:25.00     7
  8 Cam Imaginary                North Yarmouth Academy    17:32.00     8
  9 Eli Notreal                  York High School          17:40.00     9
 10 Sam Fictional                York High School          17:45.00    10
 11 Max Invented                 North Yarmouth Academy    17:50.00    11

                 Varsity Boys Three Mile Run Team Scores
=========================================================================
    Team                        Pts     1    2    3    4    5   (6)  (7)
=========================================================================
  1 Cape Elizabeth High Schoo   26      2    3    4    7   10   15   18
      Total Time: 1:25:41      Average: 17:08.20      1-5 Split: 1:12
  2 Poland Regional High Scho   67      3   13   14   18   19   24    -
      Total Time: 1:47:14      Average: 21:26.80      1-5 Split: 3:54
"""


def test_truncated_team_column_runs_into_time():
    res = Sub5ColumnParser('cape_sept11.txt.htm', text=CAPE_CUT).parse()
    rows = res['events'][0]['results']
    assert [(r['school'], r['grade'], r['result']) for r in rows[:4]] == [
        ('York High School', '', '15:27.10'),
        ('Cape Elizabeth High Schoo', '11', '16:39.00'),
        ('Cape Elizabeth High Schoo', '12', '16:50.00'),
        ('Poland Regional High Scho', '10', '16:56.00')], rows[:4]
    assert rows[6]['school'] == 'Cape Elizabeth High Schoo' and rows[7]['school'] == 'North Yarmouth Academy'
    blocks = parse_xc_team_scores(CAPE_CUT)
    assert [(t['team'], t['score']) for t in blocks[0]['teams']] == [
        ('Cape Elizabeth High Schoo', 26.0), ('Poland Regional High Scho', 67.0)]


# 2013 PVC (Word export, &nbsp; padding): a long name fills its column and
# runs into the year; a double space inside a school name ("John  Bapst").
def _pvc13_row(place, name, grade, school, time, pts):
    return f"{place:>3} {name:<24}{grade:<3}{school:<20}{time}{pts:>5}"


PVC13 = "\n".join([
    "                       PVC Championship - 10/19/2013", "                                Results",
    "Event 2  Boys 3.1 Mile Run CC JV", "=" * 71,
    "    Name                    Yr School                   Finals  Points", "=" * 71, "Results - Men",
    _pvc13_row(1, "Mitchell Test", "JR", "Caribou", "19:22.92", 1),
    _pvc13_row(2, "Alex Sample", "JR", "John  Bapst", "20:13.22", 2),
    "  3 Nicholas Dieffenbacher-KrallSO Old Town           21:45.80   21",
    _pvc13_row(4, "George Example", "JR", "Lee  Academy", "23:54.64", 3),
    _pvc13_row(5, "Ben Pretend", "SO", "Caribou", "24:00.00", 4)]) + "\n"


def test_name_runs_into_year_and_double_space_school():
    res = Sub5ColumnParser('boys_jv_pvc_xc_results_10.19.2013.htm', text=PVC13).parse()
    rows = res['events'][0]['results']
    assert [(r['athlete'], r['grade'], r['school']) for r in rows] == [
        ('Mitchell Test', 'JR', 'Caribou'), ('Alex Sample', 'JR', 'John Bapst'),
        ('Nicholas Dieffenbacher-Krall', 'SO', 'Old Town'), ('George Example', 'JR', 'Lee Academy'),
        ('Ben Pretend', 'SO', 'Caribou')], rows


def test_xc_record_marks_ties_tabs_question_teams_and_dnf_rows():
    """2007-2023 hand-typed XC sheets: a course-record mark after a time
    ("17:07 CR" in its own cell, "19:23.59R" glued), a tied place printed
    twice with a blank grade, tab-separated name and school, a team typed as
    "?" over 4-digit times, and DNF lines that are rows, not titles."""
    from backend.parsers.looselist import LooseListParser
    from backend.parsers.headertable import HeaderTableParser
    from backend.parsers.xclist import XCListParser
    # LooseList: "R" glued to the time, places kept, "--" DNF rows
    names = ['Ada Quill', 'Bea Marsh', 'Cy Dunn', 'Di Frost', 'Ed Lowe', 'Flo Pike']
    body = ''.join(f"  {k + 1} {n:<22}Old Town \t{20 + k}:1{k}.4{k}{'R' if k == 0 else ' '} \t {k + 1}\n"
                   for k, n in enumerate(names))
    text = ("58th Test Invitational - 9/22/2007\n Girls VARSITY 3.1 Mile Race\n"
            "  ==========\n      Name   \t School   \t Finals \t\tPoints\n  ==========\n" + body +
            "   -- Gia Holt                 Schenck         \tDNF\n"
            "   -- Hal Penn                 Caribou   DNF\n\n Team Scores\n")
    rows = LooseListParser().parse(text, 'ot girls var.txt', 'XC')['events'][0]['results']
    assert [(r['place'], r['result']) for r in rows[:2]] == [(1, '20:10.40'), (2, '21:11.41')], rows[:2]
    assert rows[0]['athlete'] == 'Ada Quill' and len(rows) == 8
    assert [(r['athlete'], r['school'], r['result'], r['place']) for r in rows[6:]] == [
        ('Gia Holt', 'Schenck', 'DNF', None), ('Hal Penn', 'Caribou', 'DNF', None)]
    # HeaderTable with tabs: columns at tab stops
    text = ("TEST INVITATIONAL RESULTS    9-28-04\t\t\nJV BOYS\t\t\t\nPLACE\tNAME\t\tSCHOOL\t\tTIME\tPACE\t\t\n"
            "1\tMatt Scott\tLee Academy\t20:33\t7:01\t\n2\tBJ Head\t\tM.A.\t\t21:25\t7:19\t\n"
            "3\tNikki Slevinsky\tLee Academy\t22:23\t7:38\t\n4\tAndrew Russell\tM.A.\t\t22:36\t7:43\t\n"
            "5\tAl Roy\t\tGSA\t\t23:01\t7:50\t\n6\tZed Ko\t\tOrono\t\t23:40\t8:03\t\n")
    rows = HeaderTableParser(None).parse(text, 'jv.htm', 'XC')['events'][0]['results']
    assert [(r['athlete'], r['school']) for r in rows[:3]] == [
        ('Matt Scott', 'Lee Academy'), ('BJ Head', 'M.A.'), ('Nikki Slevinsky', 'Lee Academy')], rows[:3]
    # HeaderTable: DNF lines under the list are rows, not the meet title
    text = ("PLACE        TIME         NAME                   SCHOOL\n" + ''.join(
        f"{k:>10}          {20 + k}.{k:02d} {n:<20}  Mt. Blue\n"
        for k, n in enumerate(['Nora Mc', 'Maddy Ka', 'Dylan Bu', 'Addi Pe', 'Anne Pe'], 1)) +
        "DNF              Isa Cote            Skowhegan\nDNF              Bay Erl             Gardiner\n")
    r = HeaderTableParser(None).parse(text, 'XC23FINALRESULTS.pdf', 'XC')
    rows = r['events'][0]['results']
    assert len(rows) == 7 and not (r['meet_name'] or '').startswith('DNF')
    assert [(x['athlete'], x['school'], x['result'], x['place']) for x in rows[5:]] == [
        ('Isa Cote', 'Skowhegan', 'DNF', None), ('Bay Erl', 'Gardiner', 'DNF', None)]
    # XCList: tab-separated fields, a tied place with a blank grade, "?" teams
    text = "Girls\n" + ''.join(f"{k}. {n}\t{sc}\t{17 + k}:1{k}\n" for k, (n, sc) in enumerate(
        [('Moody-Roberts', 'Cape'), ('Egan', 'Falmouth'), ('Floster', 'LR'), ('Shaw', 'Cape'),
         ('Hatton', 'Falmouth'), ('Wilson', 'Cape')], 1))
    rows = XCListParser(None).parse(text, 'fry.txt', 'XC')['events'][0]['results']
    assert [(r['athlete'], r['school']) for r in rows[:2]] == [('Moody-Roberts', 'Cape'), ('Egan', 'Falmouth')]
    pdf = ("   23   Rion     Nicole    12   YORK   23:21\n   24   Lambert   Antonia   12   FAL    23:28\n"
           "   25   Turkin    Mia        9   POL    23:34\n   26   Meyer     Heidi     11   FAL    24:09\n"
           "   26   Neuhaus   Jonna          YORK   24:09\n   27   Schimel   Ally      12   FAL    24:10\n"
           "   28   LeBlanc   Jynes     10   YORK   24:15\n   29   Auger     Alex      11   YAR    24:15\n")
    rows = XCListParser(None).parse(pdf, 'SEP.-9-GIRLS.pdf', 'XC')['events'][0]['results']
    assert [r['place'] for r in rows] == [23, 24, 25, 26, 26, 27, 28, 29], rows
    assert rows[4]['athlete'].startswith('Neuhaus') and rows[4]['school'] == 'YORK'
    unk = ("10/02/09 BOYS RACE\nTEAM SCORES\nGREELY 26, YORK 52\n"
           "92 M. RITCHIE        W           2352\n93 D. GALLANTE      Y           2407\n"
           "94 UNKNOWN           ?           2408\n95 P. STEIN         W           2410\n"
           "96 D. DEPERRIO       Y           2456\n97 Z. HALLOWELL      Y           2507\n"
           "99 A. GAMBLE         ?           2512\n100 D. FULTON       F           2519\n")
    rows = XCListParser(None).parse(unk, 'greelyboys_oct2.htm', 'XC')['events'][0]['results']
    got = {r['place']: (r['school'], r['result']) for r in rows}
    assert got[94] == ('?', '24:08') and got[99] == ('?', '25:12') and got[93] == ('Y', '24:07'), got


def _score_sets(blocks):
    return [[(t['team'], t['score']) for t in b['teams']] for b in blocks]


def test_team_scores_ranked_with_dash_and_ordinal_suffix_on_its_own_line():
    """SMAA meet: the score column printed beside the runner rows as "1st -
    Bonny Eagle 32" with the "nd" / "rd" / "th" of the later ranks on a line
    of its own; each row's score cell must not take the stray rank, and the
    "Team Scoring" lines under it (displacers in parentheses) add no team."""
    from backend.parsers.headertable import HeaderTableParser
    names = ['Ash', 'Birch', 'Cedar', 'Dale', 'Elm', 'Fir', 'Gale', 'Holt']
    sch = ['SP', 'BE', 'M', 'D']
    lines = ['   SPXC - SMAA Meet 2', 'Place Name           School Time Score']
    suffix = {2: 'nd', 3: 'rd', 4: 'th'}
    teams = [('Bonny Eagle', 32), ('Massabesic', 43), ('South Portland', 61), ('Deering', 93)]
    for k in range(1, 9):
        if k == 3:      # (the next page: the score table beside the header and the first rows)
            lines += ['        Girls Individual Results                     Girls Team Scores',
                      'Place Name           School Time Score   1st \u2013 Bonny Eagle                     32']
        rank = k - 1    # (rows 3-5 sit beside the 2nd-4th teams)
        if 2 <= rank <= 4:
            lines.append('                                          ' + suffix[rank])
        row = ' %2d   %-13s  %-4s %d:%02d    %d' % (k, names[k - 1], sch[k % 4], 16 + k, 10 + k, k)
        if 2 <= rank <= 4:
            row = row.ljust(58) + '%d \u2013 %-18s %d' % (rank, teams[rank - 1][0], teams[rank - 1][1])
        lines.append(row)
    lines += ['', '                                     Girls Team Scoring',
              '                                     Bonny Eagle 2-3-8-9-10-(17-26)        32',
              '                                     Massabesic      5-6-7-12-13 (14-16)   43',
              '                                     South Portland 1-4-15-18-23-(24-25)   61',
              '                                     Deering        11-19-20-21-22         93']
    text = '\n'.join(lines) + '\n'
    blocks = parse_xc_team_scores(text)
    assert _score_sets(blocks) == [[('Bonny Eagle', 32.0), ('Massabesic', 43.0),
                                    ('South Portland', 61.0), ('Deering', 93.0)]]
    rows = HeaderTableParser(None).parse(text, 'smaa.pdf', 'XC')['events'][0]['results']
    assert [r.get('team_place') for r in rows] == [1, 2, 3, 4, 5, 6, 7, 8]


def test_team_scores_with_double_dash_and_division_in_event_names():
    """Bucksport: "GSA -- 26 / ORO--40" (a space before a double dash) keeps
    its first team, a two-team block is kept, and JV and Varsity races of one
    gender are told apart in the event name."""
    from backend.parsers.headertable import HeaderTableParser

    def race(gender, div, n, t0):
        out = ['                 Bucksport Invitational X-Country Meet',
               '%-20s %s' % (gender, div), 'Place                  Name                        School     Time']
        out += ['  %2d Runner %-12s           %-8s  %d:%02d' % (k, chr(64 + k) * 3, ['Orono', 'GSA'][k % 2], t0 + k // 6, 10 + k)
                for k in range(1, n + 1)]
        return out
    text = '\n'.join(race('Boys', 'JV', 8, 20) + ['', '        Team Scores', '        GSA -- 26', '        ORO--40',
                                                  '        LEE-- 66', ''] +
                     race('Boys', 'Varsity', 8, 17) + ['', '  Team Scores', '  Orono       29', '  GSA     40',
                                                       '  Lee    83', ''] +
                     race('Girls', 'JV', 8, 23) + ['', '        Team Scores', '        GSA -- 23', '        OR -- 36', ''] +
                     race('Girls', 'Varsity', 8, 19)) + '\n'
    sets = _score_sets(parse_xc_team_scores(text))
    assert [('GSA', 26.0), ('ORO', 40.0), ('LEE', 66.0)] in sets
    assert [('GSA', 23.0), ('OR', 36.0)] in sets
    res = HeaderTableParser(None).parse(text, 'bucksport.pdf', 'XC')
    assert [(e['gender'], e['event']) for e in res['events']] == [
        ('Boys', 'Run CC JV'), ('Boys', 'Run CC Varsity'), ('Girls', 'Run CC JV'), ('Girls', 'Run CC Varsity')]
    # (a lone race of its gender keeps its plain name)
    one = HeaderTableParser(None).parse('\n'.join(race('Boys', 'Varsity', 8, 17)) + '\n', 'x.pdf', 'XC')
    assert one['events'][0]['event'] == 'Run CC'


def test_team_scores_list_in_two_columns_with_no_score_entries():
    """Belfast: "1. Medomak - 28         Belfast - no score" - a second column
    of the list on each line; the scoring teams of both columns count."""
    text = """\
XC Meet @ Belfast - September 12, 2008

Boys - Team Scores
1. Morse - 55                   8. Islesboro - no score
2. Medomak - 57                 9. Fox Island - no score
3. Winslow - 99
4. Erskine - 103
5. Rockland - 106
6. Lincoln - 112
7. Belfast - 131

Girls - Team Scores:
1. Medomak - 28         Belfast - no score
2. Winslow - 65         Isleboro - no score
3. Erskine - 78
4. Lincoln - 83
5. Morse - 107
"""
    sets = _score_sets(parse_xc_team_scores(text))
    assert [t[0] for t in sets[0]] == ['Morse', 'Medomak', 'Winslow', 'Erskine', 'Rockland', 'Lincoln', 'Belfast']
    assert sets[1] == [('Medomak', 28.0), ('Winslow', 65.0), ('Erskine', 78.0), ('Lincoln', 83.0), ('Morse', 107.0)]
    text2 = text.replace('Belfast - no score', 'Camden - 140').replace('Isleboro - no score', 'Wells - 150')
    assert _score_sets(parse_xc_team_scores(text2))[1][-2:] == [('Camden', 140.0), ('Wells', 150.0)]


def test_team_score_title_holding_the_first_team():
    """York: "GIRLS TEAM SCORE: 1. YORK 23" with the other teams on the lines
    below - the first team sits on the title line."""
    text = """\
3 miles @ YORK vs. Falmouth, Lake Region, Traip, and Wells

GIRLS TEAM SCORE: 1. YORK 23
                  2. FALMOUTH 33
                  3. LAKE REGION 85
                  Traip, Wells NS

   1. Michaela Swiatek 18:42 Y
BOYS TEAM SCORE: 1. FALMOUTH 20
                 2. YORK       37
                 3. LAKE REGION 84
                 4. WELLS     104
                 Traip NS

1. Alex Moser 15:18 Y
"""
    sets = _score_sets(parse_xc_team_scores(text))
    assert sets[0] == [('YORK', 23.0), ('FALMOUTH', 33.0), ('LAKE REGION', 85.0)]
    assert sets[1] == [('FALMOUTH', 20.0), ('YORK', 37.0), ('LAKE REGION', 84.0), ('WELLS', 104.0)]


def test_team_scores_dashed_totals_left_of_runner_rows():
    """Mattanawcook: the girls' "MAT - 17 / ORO - 42" totals sit in the first
    cells of runner rows, below "girls team scores" printed beside a runner."""
    text = """\
1   Runner AAA   MAT   15:11
2   Runner BBB   ORO   15:12
3   Runner CCC   MAT   15:13
girls team scores   26   Nick Alessi   MAT   25:44:00

MAT - 17   27   Gabriel Susen   MAT   26:29:00

ORO - 42   28   Dan Jandreau   SNK   32:04:00

boys team scores

MAT - 27

ORO - 35

SCHENCK - 80
"""
    sets = _score_sets(parse_xc_team_scores(text))
    assert [('MAT', 17.0), ('ORO', 42.0)] in sets
    assert [('MAT', 27.0), ('ORO', 35.0), ('SCHENCK', 80.0)] in sets


def test_html_team_scores_cells_stacking_two_entries():
    """Lee: a Team Scores table row whose cells each hold two <p> entries
    ("79" / "87" beside "Central" / "MA") is two teams."""
    def tr(a, b):
        return '<tr><td>%s</td><td>%s</td><td><p><br/></p></td></tr>\n' % (a, b)
    html = ('<html><body><table>\n<tr><td><p>Team Scores</p></td><td><p>Team</p></td><td><p><br/></p></td></tr>\n' +
            tr('<p>15</p>', '<p>Orono</p>') + tr('<p>65</p>', '<p>Lee</p>') +
            tr('<p>79</p>\n<p>87</p>', '<p>Central</p>\n<p>MA</p>') + '</table></body></html>')
    want = [[('Orono', 15.0), ('Lee', 65.0), ('Central', 79.0), ('MA', 87.0)]]
    assert _score_sets(parse_xc_team_scores(html)) == want
    html_br = html.replace('<p>79</p>\n<p>87</p>', '79<br/>87').replace('<p>Central</p>\n<p>MA</p>', 'Central<br/>MA')
    assert _score_sets(parse_xc_team_scores(html_br)) == want



def test_short_name_store_id_per_season_and_sex():
    """'Bonsey' in a boys' race and 'Bonsey' in a girls' race of one season are two
    runners (Sam and Kourtney): a surname-only or initial name's store id carries the
    season and the race's sex; a full name and a relay keep the plain id."""
    from backend.json_store import store_athlete_id
    b = store_athlete_id('Bonsey', 'Falmouth High School', 2006, 'XC', 'Boys 3 Mile Cross Country')
    g = store_athlete_id('Bonsey', 'Falmouth High School', 2006, 'XC', 'Girls 3 Mile Cross Country')
    assert b == 'bonsey-falmouth-high-school--2006-xc-b' and g.endswith('--2006-xc-g'), (b, g)
    assert store_athlete_id('J Smith', 'York', 2010, 'Outdoor', 'Girls 100 Meter Dash') == 'j-smith-york--2010-outdoor-g'
    assert store_athlete_id('Kourtney Bonsey', 'Falmouth High School', 2006, 'XC', 'Girls 5K') == 'kourtney-bonsey-falmouth-high-school'
    assert store_athlete_id('Bonsey', 'Falmouth', 2006, 'XC', 'Boys 4x800 Meter Relay', True) == 'bonsey-falmouth'
    assert store_athlete_id('Blackwell-Orr', 'South Portland', 2009, 'XC', 'Boys 5K').endswith('--2009-xc-b')
    assert store_athlete_id('Janey Blackwell-Orr', 'South Portland', 2009, 'XC', 'Girls 5K') == 'janey-blackwell-orr-south-portland'



def test_transcription_xc_team_scores_marked_xc():
    """A reader's XC team scores without 'kind' still reach the XC score check."""
    import json
    import tempfile
    import backend.scraper_v2 as sv
    old = sv.TRANSCRIBED
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, '2017', 'XC'))
        with open(os.path.join(d, '2017', 'XC', 'meet.json'), 'w') as f:
            json.dump({'events': [], 'team_rankings': [
                {'gender': 'Boys', 'teams': [{'rank': 1, 'team': 'York', 'score': 20}]},
                {'kind': 'xc', 'gender': 'Girls', 'teams': [{'rank': 1, 'team': 'York', 'score': 25}]}]}, f)
        sv.TRANSCRIBED = d
        try:
            bs = sv.load_transcription('archive/2017/XC/meet.pdf')['team_rankings']
        finally:
            sv.TRANSCRIBED = old
    assert all(b['kind'] == 'xc' and b['totals_only'] is True for b in bs)


def test_web_date_iso_and_filename_month_day():
    """An index date written as ISO is read as itself (the day-range collapse
    used to eat "-09"); a file name's "sept27" dates an XC meet in its season."""
    import backend.scraper_v2 as sv
    s = sv.Sub5ScraperV2.__new__(sv.Sub5ScraperV2)
    assert s.parse_web_date('2013-09-18') == '2013-09-18'
    assert s.parse_web_date('June 3-4, 2005') == '2005-06-03'
    assert s.date_from_filename('traip_sept27', 'XC', '2013') == '2013-09-27'
    assert s.date_from_filename('marshwoodboys_oct18', 'XC', '2013') == '2013-10-18'
    assert s.date_from_filename('marshwood18', 'Outdoor', '2013') is None
    assert s.date_from_filename('pims%20track%20meet%2050113-01-may-13results2', 'Outdoor', '2013') == '2013-05-01'


def test_transcription_no_team_scores_flag():
    """A race cut out of a combined ranking says so: the page's scores stay off it."""
    import json
    import tempfile
    import backend.scraper_v2 as sv
    old = sv.TRANSCRIBED
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, '2014', 'XC'))
        for name, extra in (('cut.json', {'no_team_scores': True}), ('plain.json', {})):
            with open(os.path.join(d, '2014', 'XC', name), 'w') as f:
                json.dump(dict({'events': [], 'team_rankings': []}, **extra), f)
        sv.TRANSCRIBED = d
        try:
            cut = sv.load_transcription('archive/2014/XC/cut.txt')
            plain = sv.load_transcription('archive/2014/XC/plain.txt')
        finally:
            sv.TRANSCRIBED = old
    assert cut.get('no_team_scores') is True and 'no_team_scores' not in plain


def test_every_parsed_season_is_synced():
    """The resync reads only the seasons in SEASONS: a parsed season left out
    (2014 XC, recovered with no sub5 index page) never reaches the store."""
    from backend.scraper_v2 import SEASONS
    listed = {(s['year'], s['season']) for s in SEASONS}
    parsed = os.path.join(ROOT, 'backend', 'data', 'parsed_results')
    missing = [(y, s) for y in os.listdir(parsed) if os.path.isdir(os.path.join(parsed, y))
               for s in os.listdir(os.path.join(parsed, y))
               if s in ('Indoor', 'Outdoor', 'XC') and (y, s) not in listed]
    assert not missing, missing


def test_paragraph_news_separators():
    """Paragraph results split on '; N.' (Ellsworth 5/4/07), after a qualifier
    mark '5.00q.' (SMAA 2009) and after a no-height 'FAIL.' (2010 freshmen)."""
    from backend.parsers.newsprint import ParagraphNewsParser
    text = ("2007 PVC Regular Season Meet 2 - 5/4/2007\nEllsworth High School\n"
            "Girls 100 Meter Dash:\n"
            " 1. Hutchins, Danielle, MDI, 13.17; 2. Hutchins, Marcelle, MDI, 14.12; 3. \n"
            " Bartlett, Kristin, MDI, 14.26.\n"
            "Boys 55 Meter Dash Preliminaries\n"
            "1, Atkins, N, Bonny Eagle, 5.00q. 2, Russell, D, Biddeford, 5.10q. 3, Scenna, A, Thornton, 5.12.\n"
            "Girls High Jump Finals\n"
            "1, Kremer, Kelsey, MTA, 5-00. --, Moody, Johanna, POL, FAIL. --, Pelkey, Robin, GNG, FAIL. "
            "2, Ball, Deirdre, LEW, 4-10.\n")
    ev = ParagraphNewsParser().parse(text, '', 'Outdoor')['events']
    rows = [[(r['athlete'], r['school'], r['result']) for r in e['results']] for e in ev]
    assert rows[0] == [('Danielle Hutchins', 'MDI', '13.17'), ('Marcelle Hutchins', 'MDI', '14.12'),
                       ('Kristin Bartlett', 'MDI', '14.26')], rows[0]
    assert [r[1] for r in rows[1]] == ['Bonny Eagle', 'Biddeford', 'Thornton'], rows[1]
    assert rows[2] == [('Kelsey Kremer', 'MTA', '5-00'), ('Johanna Moody', 'POL', 'FAIL'),
                       ('Robin Pelkey', 'GNG', 'FAIL'), ('Deirdre Ball', 'LEW', '4-10')], rows[2]


def test_milesplit_senior_junior_headers():
    """SMMSAC 2026 prints 'Senior Boys 1.5 Mile Run' / 'Junior Girls 1.5 Mile Run' (the converter read no
    events); 'Junior Varsity' and 'Junior High' keep their own divisions."""
    from backend.milesplit import xc_header
    assert xc_header('Event 1  Senior Boys 1.5 Mile Run ') == ('Boys', '1.5 Mile', 'Senior')
    assert xc_header('Junior Girls 1.5 Mile Run') == ('Girls', '1.5 Mile', 'Junior')
    assert xc_header('Junior Varsity Boys 5k') == ('Boys', '5k', 'JV')
    assert xc_header('Junior High Boys 1.5 Mile Run') == ('Boys', '1.5 Mile', 'Middle School')


def test_looselist_judged_ties_and_second_mark():
    """Hy-Tek field rows: a judged-tie mark 'J4-08.00' is the mark (was dropped, or the seed taken
    instead); 'Finals Points Prelim' rows keep the Finals mark (KVAC 2024 indoor, KVAC 5/28/21)."""
    from backend.parsers.looselist import is_mark, clean_mark
    assert is_mark('J4-08.00') and clean_mark('J4-08.00') == '4-08.00'
    p = LooseListParser()
    assert p._parse_row('2 Phoebe FitzPatrick 12 Mt. Ararat H J14-02.75 6 13-04.00', False)['result'] == '14-02.75'
    assert p._parse_row('1 Islah Godo 11 Mt. Ararat H 14-02.75 8 13-04.75', False)['result'] == '14-02.75'
    assert p._parse_row('2 # 15 Flagg, Hunter NOKO 5-02.00 J5-00.00 7', False)['result'] == '5-00.00'


def test_team_scores_without_decimal_point():
    """WMC indoor 2008-09 score sheets print 65.67 as '6567' (and 251.50 as '25150'); the printed
    Total confirms the reading. Without a matching total such rows are dropped, not believed."""
    from backend.parsers.teamscores import extract_team_scores
    sheet = """                                       Female Team Scores
  Place        School                                                                 Points
      1        Falmouth High School                         FAL                         25150
      2        York                                         YORK                        16733
      3        Cape Elizabeth High School                   CAPE                         82
      4        Poland                                       POL                          6567
      5        North Yarmouth Academy                       NYA                          4750
      6        Freeport High School                         FREE                         23
                                                                              Total   637.00
"""
    b = extract_team_scores('Team Rankings - Through Event 85\n' + sheet)[0]
    assert [t['score'] for t in b['teams']] == [251.5, 167.33, 82.0, 65.67, 47.5, 23.0], b
    b = extract_team_scores('Team Rankings - Through Event 85\n' + sheet.replace('637.00', '640.00'))[0]
    assert [t['score'] for t in b['teams']] == [82.0, 23.0], b

if __name__ == '__main__':
    qaqc._ensure_team_mapping()
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print('PASS', name)
            except Exception as e:  # noqa: BLE001
                failed += 1
                import traceback
                traceback.print_exc()
                print('FAIL', name, e)
    sys.exit(1 if failed else 0)
