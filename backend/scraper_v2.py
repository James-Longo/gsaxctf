import requests
from bs4 import BeautifulSoup
import re
import os
import json
from datetime import datetime
from backend.parser import Sub5ColumnParser
from backend.parsers.detector import FormatDetector
from backend.json_store import (
    load_scrape_state, save_scrape_state, load_athletes, save_athletes,
    add_performances_for_team, rebuild_manifest, slugify_athlete, list_teams,
    TEAMS_DIR, SCRAPE_STATE_PATH, _chunk_files, _load_json, enrich_rows,
    canonical_team_name
)
from backend.event_canon import canonical_event
from backend import school_catalog

# Configuration
FIXES_PATH = os.path.join(os.path.dirname(__file__), 'manual_fixes.json')

# Every season index page hosted on sub5.com, oldest first.
# 2003-2013 live in the legacy FrontPage-era trees under wp-content
# (outdoor: outdoorresults/results/resultsNN/, indoor: indoorresults/resultsNN/).
# 2014+ are WordPress pages; a few years use non-standard slugs.
# There is no 2020 Outdoor season (COVID).
_LEGACY_OUT = "https://sub5.com/wp-content/outdoorresults/results"
_LEGACY_IN = "https://sub5.com/wp-content/indoorresults"
SEASONS = (
    [{"year": "2003", "season": "Indoor", "url": f"{_LEGACY_IN}/results03/meetresults.htm"}] +
    [{"year": f"20{n:02d}", "season": "Indoor",
      "url": f"{_LEGACY_IN}/results{' ' if n == 11 else ''}{n:02d}/results.htm"}
     for n in range(4, 14)] +
    [{"year": "2003", "season": "Outdoor", "url": f"{_LEGACY_OUT}/results03/meetresults.htm"}] +
    [{"year": f"20{n:02d}", "season": "Outdoor",
      "url": f"{_LEGACY_OUT}/results{n:02d}/meetresults{n:02d}.htm"}
     for n in range(4, 14)] +
    [
        {"year": "2014", "season": "Indoor", "url": "https://sub5.com/indoor-track-results-2014/"},
        {"year": "2014", "season": "Outdoor", "url": "https://sub5.com/2014-outdoor-results/"},
        {"year": "2015", "season": "Indoor", "url": "https://sub5.com/indoor-track-results-2015/"},
        {"year": "2015", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/meet-results/"},
        {"year": "2016", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/indoor-track-results/"},
        {"year": "2016", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2016-results/"},
        {"year": "2017", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2017-indoor-track-results/"},
        {"year": "2017", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2017-outdoor-results/"},
        {"year": "2018", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2018-indoor-results/"},
        {"year": "2018", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2018-outdoor-results/"},
        {"year": "2019", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2019-indoor-results/"},
        {"year": "2019", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2019-outdoor-results/"},
        {"year": "2020", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2020-indoor-results/"},
        {"year": "2021", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2021-indoor-results/"},
        {"year": "2021", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2021-outdoor-results/"},
    ] +
    [{"year": str(y), "season": s,
      "url": f"https://sub5.com/youth-pages/{s.lower()}-track/{y}-{s.lower()}-results/"}
     for y in range(2022, 2027) for s in ("Indoor", "Outdoor")] +
    # Cross country: legacy FrontPage tree 2003-2013, WP pages 2015-2026
    [{"year": f"20{n:02d}", "season": "XC",
      "url": (f"https://sub5.com/wp-content/xcresults/results{n:02d}/results{n:02d}.htm"
              if n >= 11 else
              f"https://sub5.com/wp-content/xcresults/results{n:02d}/results.htm")}
     for n in range(3, 14)] +
    [{"year": str(y), "season": "XC",
      "url": f"https://sub5.com/youth-pages/cross-country/{y}-xc-results/"}
     for y in range(2015, 2027)]
)

TEAM_MAPPING = {
    "George Steve": "George Stevens Academy",
    "George Stevens": "George Stevens Academy",
    "GSA": "George Stevens Academy",
    "Blue Hill Ha": "George Stevens Academy",
    "Blue Hill Harbor": "George Stevens Academy",
    "Mt. Desert I": "Mt. Desert Island High School",
    "Mount Desert": "Mt. Desert Island High School",
    "MDI": "Mt. Desert Island High School",
    "Mt. Ararat H": "Mt. Ararat High School",
    "Mt. Ararat": "Mt. Ararat High School",
    "Mt. Blue Hig": "Mt. Blue High School",
    "Mt. Blue": "Mt. Blue High School",
    "Old Town Hig": "Old Town High School",
    "Old Town": "Old Town High School",
    "John Bapst M": "John Bapst Memorial High School",
    "John Bapst": "John Bapst Memorial High School",
    "Hampden Acad": "Hampden Academy",
    "Hampden": "Hampden Academy",
    "Bangor Christian": "Bangor Christian Schools",
    "Bangor Chris": "Bangor Christian Schools",
    "Bangor High": "Bangor High School",
    "Bangor Hig": "Bangor High School",
    "Bangor": "Bangor High School",
    "Orono High S": "Orono High School",
    "Orono": "Orono High School",
    "Brewer High": "Brewer High School",
    "Brewer Hig": "Brewer High School",
    "Brewer": "Brewer High School",
    "Hermon High": "Hermon High School",
    "Hermon Hig": "Hermon High School",
    "Hermon": "Hermon High School",
    "Bucksport Hi": "Bucksport High School",
    "Bucksport": "Bucksport High School",
    "Ellsworth Hi": "Ellsworth High School",
    "Ellsworth": "Ellsworth High School",
    "Foxcroft Aca": "Foxcroft Academy",
    "Foxcroft": "Foxcroft Academy",
    "Sumner/Narra": "Sumner/Narragaugus",
    "Sumner": "Sumner/Narragaugus",
    "Central High": "Central High School",
    "Central Hig": "Central High School",
    "Central": "Central High School",
    "Presque Isle": "Presque Isle High School",
    "Piscataquis": "Piscataquis Community High School",
    "Penquis Vall": "Penquis Valley High School",
    "Maine Centra": "Maine Central Institute",
    "MCI": "Maine Central Institute",
    "Edward Littl": "Edward Little High School",
    "Edward Little": "Edward Little High School",
    "EL": "Edward Little High School",
    "Cony High Sc": "Cony High School",
    "Cony High": "Cony High School",
    "Cony": "Cony High School",
    "Lawrence Hig": "Lawrence High School",
    "Lawrence": "Lawrence High School",
    "Messalonskee": "Messalonskee High School",
    "Winslow High": "Winslow High School",
    "Winslow": "Winslow High School",
    "Leavitt Area": "Leavitt Area High School",
    "Leavitt": "Leavitt Area High School",
    "Lincoln Acad": "Lincoln Academy",
    "Lincoln": "Lincoln Academy",
    "Waterville H": "Waterville High School",
    "Waterville": "Waterville High School",
    "Belfast Area": "Belfast Area High School",
    "Belfast": "Belfast Area High School",
    "Morse High S": "Morse High School",
    "Morse High": "Morse High School",
    "Morse": "Morse High School",
    "Brunswick Hi": "Brunswick High School",
    "Gardiner": "Gardiner High School",
    "Nokomis High": "Nokomis High School",
    "Nokomis": "Nokomis High School",
    "Skowhegan Ar": "Skowhegan Area High School",
    "Skowhegan": "Skowhegan Area High School",
    "Erskine Acad": "Erskine Academy",
    "Erskine": "Erskine Academy",
    "Biddeford High": "Biddeford High School",
    "Biddeford Hi": "Biddeford High School",
    "Bonny Eagle High": "Bonny Eagle High School",
    "Cape Elizabeth High": "Cape Elizabeth High School",
    "Cape Elizabe": "Cape Elizabeth High School",
    "Cheverus High": "Cheverus High School",
    "Cheverus Hig": "Cheverus High School",
    "Deering High": "Deering High School",
    "Deering Hig": "Deering High School",
    "Falmouth High": "Falmouth High School",
    "Falmouth Hig": "Falmouth High School",
    "Freeport High": "Freeport High School",
    "Freeport Hig": "Freeport High School",
    "Fryeburg Acad": "Fryeburg Academy",
    "Gorham High": "Gorham High School",
    "Greely High": "Greely High School",
    "Kennebunk High": "Kennebunk High School",
    "Lewiston High": "Lewiston High School",
    "Marshwood High": "Marshwood High School",
    "Noble High": "Noble High School",
    "Oceanside High": "Oceanside High School",
    "Portland High": "Portland High School",
    "Scarborough High": "Scarborough High School",
    "South Portland High": "South Portland High School",
    "Thornton Acad": "Thornton Academy",
    "Windham High": "Windham High School",
    "Yarmouth High": "Yarmouth High School",
    "York High": "York High School",
    "Boothbay/Wis": "Boothbay/Wiscasset",
    "Boothbay Reg": "Boothbay/Wiscasset",
    "Camden Hills": "Camden Hills Regional High School",
    "Gray New Glo": "Gray New Gloucester High School",
    "Oxford Hills": "Oxford Hills Comprehensive High School",
    "Sacopee Vall": "Sacopee Valley High School",
    "St. Dominic": "St. Dominic Regional High School",
    "Thornton Academy MS": "Thornton Academy",
    "Winthrop Hig": "Winthrop High School",
    "Wiscasset Hi": "Boothbay/Wiscasset",
    "York High Sc": "York High School",
    "Medomak Vall": "Medomak Valley High School",
    "Mountain Val": "Mountain Valley High School",
    "Traip Academ": "Traip Academy",
    "Deer Isle St": "Deer Isle-Stonington High School",
    "DI- Stonington": "Deer Isle-Stonington High School",
    "DI Stonington": "Deer Isle-Stonington High School",
    "Spruce Mountain": "Spruce Mountain High School",
    "Mt. View": "Mt. View High School",
    "Mt View": "Mt. View High School",
    "Calais": "Calais High School",
    "Mt. Abram": "Mt. Abram High School",
    "Mt Abram": "Mt. Abram High School",
    "Madawaska": "Madawaska High School",
    "Penobscot Valley": "Penobscot Valley High School",
    "Richmond": "Richmond High School",
    "Easton": "Easton High School",
    "Vinalhaven": "Vinalhaven High School",
    "Greater Portland": "Greater Portland High School",
    "Chop Point": "Chop Point High School",
    "Old Orchard": "Old Orchard Beach High School",
    "Greater Houlton": "Houlton High School",
    "Houlton": "Houlton High School",
    "Maine Coast Waldorf": "NYA Maine Coast Waldorf",
    "Wiscasset": "Boothbay/Wiscasset",
    "Caribou High": "Caribou High School",
    "Caribou": "Caribou High School",
    "Lisbon High": "Lisbon High School",
    "Lisbon": "Lisbon High School",
    "Dexter Regional High": "Dexter Regional High School",
    "Dexter Regional": "Dexter Regional High School",
    "Dexter": "Dexter Regional High School",
    "Searsport District": "Searsport District High School",
    "Searsport High": "Searsport District High School",
    "Searsport": "Searsport District High School",
    "Maranacook Community": "Maranacook Community High School",
    "Maranacook": "Maranacook Community High School",
    "Poland Regional": "Poland Regional High School",
    "Poland": "Poland Regional High School",
    "Wells High": "Wells High School",
    "Wells": "Wells High School",
    "Foxcroft": "Foxcroft Academy",
    "Greely High": "Greely High School",
    "Greely": "Greely High School",
    "Greely Middle": "Greely Middle School",
    "Lawrence Junior": "Lawrence Junior High School",
    "Skowhegan Middle": "Skowhegan Middle School",
    "Kents Hill": "Kents Hill School",
    "Maranacook MS": "Maranacook Middle School",
    "LIS": "Lisbon High School",
    "MOR": "Morse High School",
    "FREE": "Freeport High School",
    "BOWI": "Bowdoin",
    "Scarborough": "Scarborough High School",
    # Hy-Tek club/program names used by schools in older files
    "York Indoor Track": "York High School",
    "Windham Boys Indoor Track": "Windham High School",
    "Windham Girls Indoor Track": "Windham High School",
    "Marshwood Indoor Track": "Marshwood High School",
    "Westbrook High School Boys": "Westbrook High School",
    "Westbrook High School Girls": "Westbrook High School",
    "Westbrook": "Westbrook High School",
    "WTVL": "Waterville High School",
    "OTHS": "Old Town High School",
    "Bonny Eagle": "Bonny Eagle High School",
    "Massabesic": "Massabesic High School",
    "Mattanawcook": "Mattanawcook Academy",
    "Sanford": "Sanford High School",
    "Kennebunk": "Kennebunk High School",
    "Marshwood": "Marshwood High School",
    "Fryeburg": "Fryeburg Academy",
    "Gorham": "Gorham High School",
    "Windham": "Windham High School",
    "Yarmouth": "Yarmouth High School",
    "Greely Hig": "Greely High School",
    "Camden Hill": "Camden Hills Regional High School",
    "North Yarmouth Academy": "North Yarmouth Academy",
    "NYA": "North Yarmouth Academy",
}

# ---------------------------------------------------------------------------
# Parallel parse worker (module-level so it pickles for ProcessPoolExecutor).
# Each worker process lazily builds one scraper+detector and reuses it.
# ---------------------------------------------------------------------------
_WORKER_DETECTOR = None

# Files whose text layer is damaged in ways that read as plausible junk
# (broken OCR layers in phone scans). Verified by hand: no reliable
# extraction exists, and letting them parse poisons the store.
SKIP_PARSE_FILES = {
    '12-16-meet-p1.pdf', '12-16-meet-pg-2.pdf', '12-16-Meet-p3.pdf',
    '12-16-Meet-p4.pdf', 'HM-pg1.pdf', 'hyde%20results%20all.pdf',
    'fryeburg5_21.pdf',
}

_HYTEK_STOP_RE = re.compile(
    r'^(results?|meet results|team rankings|team scores?|'
    r'complete results|final results|rankings)$', re.I)


def hytek_header_meta(text):
    """Meet name / venue / host from a Hy-Tek Meet Manager header.

    Hy-Tek exports open with a fixed four-line block:

        Licensed to Foxcroft Academy     HY-TEK's Meet Manager 9/20/2019
                 PVC Regular Season Meet - 9/20/2019
                        Dover-Foxcroft
                            Results

    Line 1 names the licensing host, line 2 the meet, and the line(s)
    between the meet and the 'Results' marker the venue. Returns a dict with
    whatever could be read; every key may be None.
    """
    out = {'meet': None, 'venue': None, 'host': None}
    if not text:
        return out
    # .htm archives arrive as raw markup; the header lives inside <pre>
    if '<' in text[:2000] and '</' in text[:8000].lower():
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text[:60000], 'html.parser')
            pres = soup.find_all('pre')
            text = "\n".join(p.get_text() for p in pres) if pres \
                else soup.get_text('\n')
        except Exception:
            pass
    lines = [l.strip() for l in text[:4000].splitlines()]
    lines = [l for l in lines if l]
    if not lines:
        return out
    if 'HY-TEK' not in lines[0]:
        # Hy-Tek .txt exports drop the license line and open with the
        # meet title itself:  "2025 Southern Regional XC Championships -
        # 10/25/2025" / "Twin Brook" / "Results"
        if 'HY-TEK' in text[:4000] or not re.search(
                r'\s-\s+\d{1,2}/\d{1,2}/\d{2,4}', lines[0]):
            return out
        lines = [''] + lines
    m = re.search(r'Licensed to\s+(.+?)\s{2,}HY-TEK', lines[0])
    if m:
        out['host'] = m.group(1).strip(' -')
    # locate the 'Results' marker inside the header block
    stop = None
    for i, l in enumerate(lines[1:7], 1):
        if _HYTEK_STOP_RE.fullmatch(l):
            stop = i
            break
    if stop is None:
        return out
    block = lines[1:stop]
    if not block:
        return out
    # meet name is first; anything after it and before 'Results' is the venue
    out['meet'] = re.sub(r'\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}.*$', '', block[0]).strip() or None
    for cand in reversed(block[1:]):
        # skip bare date lines ("9/16/2011", "10/24/2011 to 10/25/2011")
        if re.fullmatch(r'[\d/]{6,10}(\s+to\s+[\d/]{6,10})?', cand):
            continue
        out['venue'] = re.sub(r'^at\s+', '', cand, flags=re.I).strip()
        break
    return out


# (a 25-character school cell truncates the suffix: "Winslow High School   Boy",
# "Mount Blue High School Bo")
_MF_SUFFIX = re.compile(r'^(.*\S)\s+(M|F|B|G|Boys?|Bo|Girls?|Gi|Gir|Men|Women)$')
_MF_GIRLS = {'F', 'G', 'Girls', 'Girl', 'Gi', 'Gir', 'Women'}


def split_gender_suffix(data):
    """Mixed boys+girls lists that carry gender as a school suffix.

    The LaLiberte list exports head every page "Boys 4k Run CC Varsity" but
    rank both genders together, marking each runner's school "Morse M" /
    "Morse F" (2026) or "Mt. Blue HS B" / "Mt. Blue HS G" / "Monmouth Girls"
    (2021). When nearly every school in an event carries a suffix and both
    genders occur, move the girls' rows into a Girls event and strip the
    suffix (team-name resolution happens downstream). Works on grouped
    events and on flat Hy-Tek rows (gender read from the event prefix).
    Returns the number of rows moved to Girls."""
    if not isinstance(data, dict):
        return 0
    events = data.get('events') or []
    moved = 0

    def _split(rows):
        tags = [_MF_SUFFIX.match((r.get('school') or '').strip()) for r in rows]
        n_f = sum(1 for t in tags if t and t.group(2) in _MF_GIRLS)
        n_m = sum(1 for t in tags if t) - n_f
        if not n_m or not n_f or n_m + n_f < 0.5 * len(rows) or len(rows) < 6:
            return None
        from backend.parsers.namegender import name_gender
        boys, girls, unknown = [], [], []
        for r, t in zip(rows, tags):
            if t:
                # the scored entry ("Mt. Ararat HS B"): official team scores
                # rank boys' and girls' entries in one list
                r['team_entry'] = r.get('school')
                r['school'] = t.group(1)
                (girls if t.group(2) in _MF_GIRLS else boys).append(r)
                continue
            # a school cut before its suffix ("Messalonskee High School"):
            # a decisive first name, else the runner stays unassigned
            ng = name_gender(r.get('athlete') or r.get('athlete_name'))
            (girls if ng == 'Girls' else boys if ng == 'Boys' else unknown).append(r)
        if unknown and n_m + n_f >= 0.9 * len(rows) and len(unknown) <= 2:
            boys.extend(unknown)   # the old rule: a near-fully tagged list
            boys.sort(key=lambda r: rows.index(r))
            unknown = []
        return boys, girls, unknown

    if events and isinstance(events[0], dict) and 'results' in events[0]:
        out = []
        for ev in events:
            parts = _split(ev.get('results', [])) if not ev.get('is_relay') else None
            if not parts:
                out.append(ev)
                continue
            boys, girls, unknown = parts
            moved += len(girls)
            label = str(ev.get('event') or '')
            # one race for the team scores: QAQC re-merges the halves
            ev = dict(ev, combined_race=len(out))
            if boys:
                out.append(dict(ev, gender='Boys', results=boys,
                                event=re.sub(r'\b(Girls|Women)\b', 'Boys', label)))
            out.append(dict(ev, gender='Girls', results=girls,
                            event=re.sub(r'\b(Boys|Men)\b', 'Girls', label)))
            if unknown:
                out.append(dict(ev, gender='Mixed', results=unknown,
                                event=re.sub(r'\b(Boys|Men|Girls|Women)\b\s*', '', label).strip()))
        data['events'] = out
        return moved
    # flat rows: split per event label
    by_event = {}
    for r in events:
        if isinstance(r, dict):
            by_event.setdefault(r.get('event', ''), []).append(r)
    for label, rows in by_event.items():
        parts = _split(rows)
        if not parts:
            continue
        for r in parts[1]:   # (flat rows: unassigned ones keep the label)
            r['event'] = re.sub(r'^(Boys|Men)\b', 'Girls', label)
            r['gender'] = 'Girls'
            moved += 1
    return moved


_MS_MEET_TITLE = re.compile(
    r'junior\s+high|middle\s+school|\bjr\.?\s+high|\bm\.?s\.?\s+(?:xc|cross|meet|champ|invit|league)|'
    r'\bjh\b|elementary|\bgrades?\s+[5-8]\b|\b[5-8]th\s+grade', re.I)


class _MostRowsParser:
    """Run several parsers, keep the result with the most rows (the first
    parser wins ties)."""

    def __init__(self, parsers):
        self.parsers = parsers

    def parse(self, text, filename, season_label):
        best, best_n = None, -1
        for p in self.parsers:
            try:
                r = p.parse(text, filename, season_label)
            except Exception:
                continue
            ev = r.get('events', []) if isinstance(r, dict) else (r or [])
            n = sum(len(e.get('results', [])) if isinstance(e, dict) and 'results' in e else 1
                    for e in ev)
            if n > best_n:
                best, best_n = r, n
                if isinstance(r, dict):
                    r['parser'] = type(p).__name__
        return best if best is not None else []


_LABEL_BOYS = re.compile(r"\b(?:men|boys|male)'?s?\b", re.I)
_LABEL_GIRLS = re.compile(r"\b(?:women|girls|female)'?s?\b", re.I)
# a one-letter sex prefix on a hand-made sheet: "M 400m", "F High Jump"
_LABEL_SEX_LETTER = re.compile(r'^\s*([MFW])\s+(?=\d|[A-Za-z]{2})')


def strip_sex_prefix(data):
    """A sex cell read into the school ("W MTA", "M Mt. Ararat Middl"): when
    most of a race's schools open with one sex letter, it goes."""
    for e in data.get('events') or []:
        rows = e.get('results') if isinstance(e, dict) else None
        if not rows or len(rows) < 5:
            continue
        pre = [re.match(r'^([WMFBG]) (?=\S)', r.get('school') or '') for r in rows]
        letters = {m.group(1) for m in pre if m}
        if len(letters) == 1 and sum(1 for m in pre if m) >= 0.8 * len(rows):
            for r, m in zip(rows, pre):
                if m:
                    r['school'] = r['school'][2:]


def fix_wrapped_places(data):
    """A Hy-Tek page printed with a one-digit place field ("10" then "1",
    "2" ... for 11, 12): the list order is the finish order, so each row's
    place is its position."""
    for e in data.get('events') or []:
        rows = e.get('results') if isinstance(e, dict) else None
        if not rows or len(rows) <= 12:
            continue
        p = [r.get('place') for r in rows]
        if sum(1 for i, x in enumerate(p) if x == i % 10 + 1) >= 0.9 * len(p) and \
                sum(1 for i, x in enumerate(p) if x == i + 1) < 0.5 * len(p):
            for i, r in enumerate(rows):
                r['place'] = i + 1


def fix_event_gender_from_label(data):
    """An event label that names one gender ("3k Run CC 9-10 Division
    Boys") outranks the gender a parser carried over from an earlier header;
    the store's event canonicalization applies the same rule."""
    for ev in data.get('events') or []:
        if not isinstance(ev, dict) or 'results' not in ev:
            continue
        label = str(ev.get('event') or '')
        b, g = _LABEL_BOYS.search(label), _LABEL_GIRLS.search(label)
        letter = _LABEL_SEX_LETTER.match(label)
        if letter and not (b or g):
            b, g = letter.group(1) == 'M', letter.group(1) != 'M'
        if b and not g:
            ev['gender'] = 'Boys'
        elif g and not b:
            ev['gender'] = 'Girls'


def add_team_scores(data, input_path):
    """Official team scores read from the file itself (teamscores.py) for a
    parse that has none. Scores without a gender take the file's ("...boys")
    or, failing that, the only gender its events have."""
    from backend.parsers.teamscores import extract_team_scores, file_text
    stem = os.path.basename(input_path)
    fg = 'Girls' if re.search(r'girl|women|female|(?<![a-z])g(?:\.|_|$)', stem, re.I) else \
        'Boys' if re.search(r'boy|(?<!wo)men(?![a-z])|(?<![fe])male|(?<![a-z])b(?:\.|_|$)', stem, re.I) else None
    if fg is None:
        gs = {e.get('gender') for e in data.get('events') or [] if isinstance(e, dict)} - {None, '', 'Mixed'}
        fg = gs.pop() if len(gs) == 1 else None
    try:
        blocks = extract_team_scores(file_text(input_path), fg)
    except Exception:  # noqa: BLE001 - a scores reader failure never fails a parse
        blocks = []
    if blocks:
        data['team_rankings'] = blocks
        data['team_rankings_source'] = 'teamscores'


def merge_continued_events(data):
    """Two consecutive races with one label whose second part carries on
    from the first - places 53+ after 1-52 (a list printed in two columns),
    or, without places, times that start where the first part ended - are
    one race. A second race restarts at place 1 / a faster time."""
    from backend.json_store import parse_mark_value
    evs = data.get('events') or []
    if any(isinstance(b, dict) and isinstance(b.get('event_idx'), int)
           for b in data.get('team_rankings') or []):
        return  # score blocks already point at events by index
    out = []
    for ev in evs:
        prev = out[-1] if out else None
        if prev is not None and isinstance(ev, dict) and isinstance(prev, dict) \
                and 'results' in ev and 'results' in prev and ev['results'] and prev['results'] \
                and not ev.get('is_relay') and (ev.get('event'), ev.get('gender'), ev.get('section')) == \
                (prev.get('event'), prev.get('gender'), prev.get('section')) \
                and ev.get('combined_race') is None and prev.get('combined_race') is None:
            p1 = [r.get('place') for r in prev['results'] if r.get('place')]
            p2 = [r.get('place') for r in ev['results'] if r.get('place')]
            if p1 and p2:
                cont = p2[0] > 1 and p2[0] > p1[-1]
            else:
                a, _ = parse_mark_value(prev['results'][-1].get('result', ''), '')
                b, _ = parse_mark_value(ev['results'][0].get('result', ''), '')
                cont = a is not None and b is not None and b >= a
            if cont:
                prev['results'].extend(ev['results'])
                continue
        out.append(ev)
    data['events'] = out


def fix_event_gender_from_names(data, split=True):
    """Relabel a race whose runners' first names overwhelmingly belong to
    the other gender (>= 90% of 8+ decisive names): spreadsheets and
    hand-typed lists carry no gender, and parsers fall back on a filename
    hint or a default. Marks the event 'gender_from_names'.

    split: also split a list holding both sexes (split_mixed_by_names). Only
    for cross country: a track list that reads mixed is more often a girls'
    race with Cams and Maddoxes in it, or two events the parser ran
    together, than a combined race."""
    from backend.parsers.namegender import gender_evidence
    for ev in data.get('events') or []:
        if not isinstance(ev, dict) or 'results' not in ev or ev.get('is_relay'):
            continue
        b, g = gender_evidence(ev['results'])
        n = len(ev['results'])
        # (8+ decisive names; or a short list whose names all agree)
        if (b + g < 8 or b + g < 0.3 * n) and not (b + g >= 4 and min(b, g) == 0 and b + g >= 0.6 * n):
            continue
        want = 'Boys' if b >= 0.9 * (b + g) else 'Girls' if g >= 0.9 * (b + g) else None
        if want and ev.get('gender') != want:
            ev['gender'] = want
            ev['gender_from_names'] = True
            label = str(ev.get('event') or '')
            ev['event'] = re.sub(r'\b(Boys|Men|Girls|Women)\b', want, label)
    if split:
        split_mixed_by_names(data)


def drop_relay_team_totals(data, text, filename):
    """Relay meets post each team's combined time ("Cheverus  49:36") with
    the legs; a list of those is no race of runners. A race in a relay
    file whose median is 30+ minutes and whose "runners" are mostly bare
    team names (no school beside them) is dropped."""
    if not re.search(r'relay', (filename or '') + ' ' + (text or '')[:20000], re.I):
        return
    def secs(t):
        try:
            v = 0.0
            for x in str(t).split(':'):
                v = v * 60 + float(x)
            return v
        except ValueError:
            return 0.0
    keep = []
    for ev in data.get('events') or []:
        rows = ev.get('results') if isinstance(ev, dict) else None
        if rows:
            ts = sorted(secs(r.get('result')) for r in rows)
            bare = sum(1 for r in rows if not (r.get('school') or '').strip()
                       or len((r.get('school') or '').strip()) == 1)
            if ts[len(ts) // 2] >= 1800 and bare >= 0.6 * len(rows):
                continue
            # two-runner relays ("cyr / TANGUAY  19:01"): a team's time
            if sum(1 for r in rows if re.search(r'\S\s*/\s*\S', r.get('athlete') or '')) >= 0.6 * len(rows):
                ev['is_relay'] = True
                if 'relay' not in str(ev.get('event') or '').lower():
                    ev['event'] = (str(ev.get('event') or '') + ' Relay').strip()
        keep.append(ev)
    data['events'] = keep


def drop_duplicate_events(data):
    """A race listed twice: USATF JO pages re-rank the 15-18 race by age
    group ("5000 Meter Run Individual Girls / Results - Women 15-16"), team
    summary sheets repeat a race. An event whose runners (name and time)
    all appear in a larger event of the file is that event again."""
    evs = data.get('events') or []
    keys = []
    for e in evs:
        rows = e.get('results') if isinstance(e, dict) else None
        keys.append({((r.get('athlete') or '').strip().lower(), str(r.get('result')))
                     for r in rows or [] if r.get('athlete')})
    # (a "Top 10" / "JV Top 5" re-listing retypes a name or a time:
    # "Aryanna Benl" / "Aryanna Beal" - a row matches on name and time, on
    # school and time, or on name alone)
    alt = []
    for e in evs:
        rows = e.get('results') if isinstance(e, dict) else None
        alt.append(({((r.get('school') or '').strip().lower(), str(r.get('result'))) for r in rows or []},
                    {(r.get('athlete') or '').strip().lower() for r in rows or []}))
    drop = {}
    for i, ki in enumerate(keys):
        if len(ki) < 3 or evs[i].get('combined_race') is not None:
            continue
        for j, kj in enumerate(keys):
            # (or the same race printed twice in the file: the copy goes)
            if j != i and j not in drop and (len(kj) > len(ki) or j < i and kj == ki) and \
                    len(ki & kj) >= 0.9 * len(ki):
                drop[i] = j
                break
            if j != i and j not in drop and len(ki) >= 5 and len(kj) > len(ki):
                rows = evs[i].get('results') or []
                hit = sum(1 for r in rows if ((r.get('athlete') or '').strip().lower(), str(r.get('result'))) in kj
                          or ((r.get('school') or '').strip().lower(), str(r.get('result'))) in alt[j][0]
                          or (r.get('athlete') or '').strip().lower() in alt[j][1])
                if hit >= 0.8 * len(rows) and len(ki & kj) >= 0.5 * len(ki):
                    drop[i] = j
                    break
    if not drop:
        return
    new_idx, out = {}, []
    for i, e in enumerate(evs):
        if i not in drop:
            new_idx[i] = len(out)
            out.append(e)
    for b in data.get('team_rankings') or []:
        ei = b.get('event_idx') if isinstance(b, dict) else None
        if isinstance(ei, int):
            b['event_idx'] = new_idx.get(ei, new_idx.get(drop.get(ei)))
    data['events'] = out


def split_mixed_by_names(data):
    """A race list holding both sexes with nothing in the file to tell them
    apart (a "Mixed" Hy-Tek race, a combined LaLiberte list printed under
    one gender): runners whose first name decides it go to a Boys / Girls
    race; the rest stay in a "Mixed" race rather than be guessed. Only for
    lists where 20+ decisive names (40%+ of the runners) split 12-88%. The parts keep one
    combined_race id so QAQC can re-merge them for the team scores."""
    from backend.parsers.namegender import name_gender, gender_evidence, last_first_order
    out = []
    nxt = max([e.get('combined_race', -1) for e in data.get('events') or []
               if isinstance(e, dict) and isinstance(e.get('combined_race'), int)] + [99]) + 1
    for ev in data.get('events') or []:
        if not isinstance(ev, dict) or 'results' not in ev or ev.get('is_relay') \
                or ev.get('combined_race') is not None:
            out.append(ev)
            continue
        lf = last_first_order(ev['results'])
        b, g = gender_evidence(ev['results'], lf)
        # (a list typed with initials or surnames only decides too few
        # names to say anything: 40%+ of the runners must)
        if b + g < 20 or b + g < 0.4 * len(ev['results']) or not (0.12 <= b / (b + g) <= 0.88):
            out.append(ev)
            continue
        parts = {'Boys': [], 'Girls': [], None: []}
        for r in ev['results']:
            parts[name_gender(r.get('athlete'), last_first=lf)].append(r)
        label = re.sub(r'\b(Boys|Men|Girls|Women|Mixed)\b\s*', '', str(ev.get('event') or '')).strip()
        for gname in ('Girls', 'Boys', None):
            if parts[gname]:
                out.append(dict(ev, gender=gname or 'Mixed', event=label, results=parts[gname],
                                combined_race=nxt, gender_from_names=True))
        nxt += 1
    data['events'] = out


_FILE_GENDER = re.compile(r'(boys|girls|women|men)', re.I)
_GENDER_SWAP = {'boys': 'girls', 'girls': 'boys', 'men': 'women', 'women': 'men'}


def drop_sibling_gender_events(data, input_path):
    """falmouthboys_august26.html and falmouthgirls_august26.html are the
    same two-sheet workbook posted twice. When a file named for one gender
    has a sibling named for the other, the other gender's races belong to
    the sibling: keep only this file's own."""
    d, fn = os.path.split(input_path)
    m = None
    for m in _FILE_GENDER.finditer(fn):
        pass  # last gender word in the name
    if not m:
        return
    word = m.group(1)
    swap = _GENDER_SWAP[word.lower()]
    swap = swap.capitalize() if word[0].isupper() else swap
    swap = swap.upper() if word.isupper() else swap
    sib = fn[:m.start()] + swap + fn[m.end():]
    if not os.path.exists(os.path.join(d, sib)):
        return
    own = 'Girls' if word.lower() in ('girls', 'women') else 'Boys'
    evs = data.get('events') or []
    # (a stray runner or two of the other sex inside this file's own race
    # stays: only a whole race - the sibling's - is dropped)
    keep = [e for e in evs if not isinstance(e, dict) or 'results' not in e
            or e.get('gender') in (own, None, 'Mixed') or len(e['results']) < 5]
    if len(keep) == len(evs) or not any(isinstance(e, dict) and e.get('results') for e in keep):
        return
    data['events'] = keep
    data['team_rankings'] = [b for b in data.get('team_rankings') or []
                             if b.get('gender') in (own, None)]


def _pair_xc_blocks(events, blocks):
    """Point each official XC team-score block at its race (event_idx).

    Per-class sections ("CLASS A Results") of one race are separate events
    sharing gender and event name; their blocks carry the same section label.
    Only applied when every block finds its race, otherwise QAQC falls back
    to pairing by gender in order."""
    if not blocks or any(isinstance(b.get('event_idx'), int) for b in blocks):
        return
    # blocks labelled by division ("Small School", "Class B") pair with the
    # race whose name carries that label
    if all(b.get('division') for b in blocks) and not all(b.get('section') for b in blocks):
        idx, used = {}, set()
        for bi, b in enumerate(blocks):
            lab = re.sub(r'\s+', ' ', b['division']).lower()
            for ei, e in enumerate(events):
                if ei in used or not isinstance(e, dict) or not e.get('results'):
                    continue
                if b.get('gender') and e.get('gender') not in (b['gender'], None):
                    continue
                name = re.sub(r'\s+', ' ', ' '.join(str(e.get(k) or '') for k in ('event', 'section'))).lower()
                if lab in name:
                    idx[bi] = ei
                    used.add(ei)
                    break
        if len(idx) == len(blocks):
            for bi, ei in idx.items():
                blocks[bi]['event_idx'] = ei
        return
    if not all(b.get('section') for b in blocks):
        return
    idx = {}
    used = set()
    for bi, b in enumerate(blocks):
        for ei, e in enumerate(events):
            if ei in used or not isinstance(e, dict) or not e.get('results'):
                continue
            if e.get('section') != b['section']:
                continue
            if b.get('gender') and e.get('gender') not in (b['gender'], None):
                continue
            idx[bi] = ei
            used.add(ei)
            break
    if len(idx) == len(blocks):
        for bi, ei in idx.items():
            blocks[bi]['event_idx'] = ei


def _parse_one_file(args):
    """Worker: parse a single archive file to its output JSON.
    Returns (filename, result_count, error_message_or_None)."""
    input_path, output_path, season_label = args
    filename = os.path.basename(input_path)
    global _WORKER_DETECTOR
    if filename in SKIP_PARSE_FILES:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({'events': [], 'date': None, 'meet_name': None,
                       'team_rankings': [], 'skipped': 'damaged text layer'}, f)
        return (filename, 0, None)
    try:
        if _WORKER_DETECTOR is None:
            _WORKER_DETECTOR = FormatDetector(Sub5ScraperV2())
        if filename.lower().endswith('.pdf'):
            from backend.parser import Sub5ColumnParser
            raw = Sub5ColumnParser.pdf_to_text(input_path)
            if raw is None:
                return (filename, 0, 'pdftotext unavailable')
            text = Sub5ColumnParser.clean_pdf_text(raw)
        else:
            with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            if season_label == 'XC':
                # a Windows-1252 byte ("D\x92Orso") dropped by the utf-8 read
                # pulls the rest of a fixed-width row one column left
                raw_bytes = open(input_path, 'rb').read()
                try:
                    raw_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    # (only the curly quotes and dashes: other stray bytes are
                    # dropped as before - the exports' padding was built
                    # without them)
                    fixed = re.sub(rb'[\x91\x92]', b"'", re.sub(rb'[\x93\x94]', b'"',
                                   re.sub(rb'[\x96\x97]', b'-', raw_bytes)))
                    text = fixed.decode('utf-8', errors='ignore')
            # Word pages saved through a broken codepage carry U+FFFD for
            # every non-breaking space (KVACLeavittSept16boys.htm: 3,266 of
            # them): the column gaps are lost unless they read
            # as the non-breaking spaces they were
            if season_label == 'XC' and text.count('\ufffd') > 100:
                text = text.replace('\ufffd', '\xa0')
            elif season_label == 'XC':
                # (a few stray U+FFFD in table cells: "W \ufffd", "Noble \ufffd")
                text = re.sub(r'\s*\ufffd+\s*(?=<)', ' ', text)
        if season_label == 'XC':
            # (zero-width spaces between a PDF's words: "Matyas\u200b \u200bNachtigall")
            text = text.replace('\u200b', '')
            _o = r'(?i)(<td\b[^>]*>(?:\s*<(?:font|span|b)\b[^>]*>)*)\s*'
            _c = r'\s*((?:</(?:font|span|b)>\s*)*</td>)'
            if re.search(r'(?i)<t[dh]\b[^>]*>(?:\s*<(?:font|span|b)\b[^>]*>)*\s*time\s*<', text):
                # a sheet's Time cells typed "16 51" or "2128": minutes and seconds
                text = re.sub(_o + r'([1-5]?\d) ([0-5]\d)' + _c, r'\1\2:\3\4', text)
                text = re.sub(_o + r'((?:[89]|[1-5]\d))([0-5]\d)' + _c, r'\1\2:\3\4', text)
                # ("18.38": a dot for the colon, when no cell carries a colon time)
                if not re.search(_o + r'\d{1,2}:\d{2}', text):
                    text = re.sub(_o + r'((?:[89]|[1-5]\d))\.([0-5]\d)' + _c, r'\1\2:\3\4', text)
            # "22: 40": a space typed after the colon
            text = re.sub(r'(?m)(?<![\d:.])([1-5]?\d): ([0-5]\d)(?=[ \t]{2,}|[ \t]*$)', r'\1:\2', text)
            # "18;01": a hand-typed time with the semicolon key
            # ("18;28;89" / "18:37;82": minutes, seconds, hundredths)
            text = re.sub(r'(?<![\d;:.])(\d{1,2})[;:](\d{2});(\d{2})(?![\d;:])',
                          lambda m: f'{m.group(1)}:{m.group(2)}.{m.group(3)}' if int(m.group(1)) >= 4
                          else m.group(0), text)
            text = re.sub(r'(?<![\d;:.])(\d{1,2});(\d{2})(?![\d;:])', r'\1:\2', text)
            # an apostrophe for the colon ("16'41", "18'10 11" = 18:10.11)
            text = re.sub(r"(?<![\d'’])(\d{1,2})['’](\d{2})(?: (\d{2})(?=\s|<|$))?(?![\d'’])",
                          lambda m: f'{m.group(1)}:{m.group(2)}' + (f'.{m.group(3)}' if m.group(3) else ''), text)
            # "25m 23s" (no milliseconds)
            text = re.sub(r'\b(\d{1,2})m\s+(\d{1,2})s\b(?!\s+\d{1,3}ms)',
                          lambda m: f'{m.group(1)}:{int(m.group(2)):02d}', text)
            # a timer's "18m 4s 980ms" (kept in its column's width)
            text = re.sub(r'\b(\d{1,2})m\s+(\d{1,2})s\s+(\d{1,3})ms\b',
                          lambda m: f'{m.group(1)}:{int(m.group(2)):02d}.{m.group(3).rjust(3, "0")[:2]}'.rjust(len(m.group(0))),
                          text)
        def _count(res):
            if isinstance(res, dict):
                return sum(len(e.get('results', [])) for e in res.get('events', []))
            return len(res) if isinstance(res, list) else 0

        def _order_ok(res):
            """Results in source files are in finishing order, so parsed marks
            must be near-monotonic per event. A high inversion rate means the
            parser spliced columns — reject the parse."""
            if not isinstance(res, dict):
                return True
            from backend.json_store import parse_mark_value
            pairs = inversions = 0
            for ev in res.get('events', []):
                ev_name = ev.get('event', '')
                is_field = any(k in ev_name.lower() for k in
                               ('jump', 'put', 'vault', 'discus', 'javelin', 'throw'))
                vals = []
                for r in ev.get('results', []):
                    if r.get('type') == 'Seed' or r.get('exhibition'):
                        continue
                    v, _ = parse_mark_value(r.get('result', ''), ev_name)
                    if v is not None:
                        vals.append(v)
                for a, b in zip(vals, vals[1:]):
                    pairs += 1
                    if (is_field and b > a + 0.01) or (not is_field and b < a - 0.01):
                        inversions += 1
            if pairs < 10:
                return True
            return inversions / pairs <= 0.25

        def _xc_teams_ok(res):
            """A cross-country race has far fewer teams than runners. When a
            parser crosses the name and team columns (Last | First | Team
            sheets, team-first layouts), nearly every row gets its own
            "school" (a first name or surname) or school == athlete; those
            rows would become hundreds of fake teams in the store."""
            if isinstance(res, list):
                # flat Hy-Tek rows: one group per event label
                groups = {}
                for r in res:
                    if isinstance(r, dict) and 'athlete_name' in r:
                        groups.setdefault(r.get('event'), []).append(
                            {'athlete': r.get('athlete_name'), 'school': r.get('school')})
                res = {'events': [{'results': g} for g in groups.values()]}
            if not isinstance(res, dict):
                return True
            for ev in res.get('events', []):
                rows = ev.get('results', []) if isinstance(ev, dict) else []
                if len(rows) < 15:
                    continue
                schools = [(r.get('school') or '').strip().lower() for r in rows]
                names = [(r.get('athlete') or '').strip() for r in rows]
                same = sum(1 for n, s in zip(names, schools) if s and s == n.lower())
                # a bare surname in the name column + a per-row "school" =
                # a Last | First sheet read as name | team (open/JO/youth
                # races legitimately have many teams, but full names)
                bare = sum(1 for n in names if n and not re.search(r'[\s,]', n))
                if same > 0.3 * len(rows) or (
                        len(set(schools)) > 0.6 * len(rows) and bare > 0.7 * len(rows)):
                    return False
            return True

        # Retry chain: the detector's choice, then the robust column parser,
        # then the loose-list parser for hand-typed / collapsed-PDF formats.
        # First parser to produce results wins.
        from backend.parsers.column import ColumnStrategyParser
        from backend.parsers.looselist import LooseListParser
        from backend.parsers.placegrid import PlaceGridParser
        parser_instance = _WORKER_DETECTOR.get_parser(text, filename)
        from backend.parsers.hytek import HyTekStandardParser, HyTekSMAAParser
        if season_label == 'XC' and isinstance(parser_instance, (HyTekStandardParser,
                                                                 HyTekSMAAParser)):
            # The flat Hy-Tek row parsers drop most XC rows (bib columns,
            # pace columns, blank grades); the column parser reads the same
            # layouts whole. Keep whichever reads more rows.
            parser_instance = _MostRowsParser([ColumnStrategyParser(_WORKER_DETECTOR.scraper),
                                               parser_instance])
        chain = [parser_instance]
        # XC "OFFICIAL MEET REPORT" exports: two-column pages with pace
        # columns that every generic parser misreads
        from backend.parsers.meetreport import MeetReportParser
        if MeetReportParser.matches(text):
            chain.insert(0, MeetReportParser(_WORKER_DETECTOR.scraper))
        # XCRun "PLC BIB PTS NAME TEAM TIME PACE" exports, same problem
        from backend.parsers.xcrun import XCRunParser
        if XCRunParser.matches(text):
            chain.insert(0, XCRunParser(_WORKER_DETECTOR.scraper))
        # Randy Easter's MVC pages: overall list + team table with places
        from backend.parsers.easter import EasterParser
        if EasterParser.matches(text):
            chain.insert(0, EasterParser(_WORKER_DETECTOR.scraper))
        # DirectAthletics MeetPro text (college meets): header-word columns
        from backend.parsers.directathletics import DirectAthleticsParser
        if DirectAthleticsParser.matches(re.sub(r'<[^>]+>', '', text[:20000])):
            chain.insert(0, DirectAthleticsParser(_WORKER_DETECTOR.scraper))
        # RunScore-style "=====" ruler tables: columns cut by the ruler
        from backend.parsers.rulertable import RulerTableParser
        if RulerTableParser.matches(re.sub(r'<[^>]+>', '', text[:200000])):
            chain.insert(0, RulerTableParser(_WORKER_DETECTOR.scraper))
        if not isinstance(parser_instance, ColumnStrategyParser):
            chain.append(ColumnStrategyParser(_WORKER_DETECTOR.scraper))
        if not filename.lower().endswith('.pdf'):
            from backend.parsers.htmltable import HtmlTableParser
            chain.append(HtmlTableParser(_WORKER_DETECTOR.scraper))
        from backend.parsers.newsprint import (AgateParser, ParagraphNewsParser,
                                               MangledStreamParser, VerticalTokensParser)
        # newspaper-agate signature ("1. Name (CODE) 12.3;") outranks the
        # loose-list parser, which would otherwise bleed entries across events
        if re.search(r'\d\.\s+[A-Z][\w.\' -]+\([A-Z][A-Za-z]{0,4}\)\s+[\d:.\-]+', text):
            chain.append(AgateParser(_WORKER_DETECTOR.scraper))
        chain.append(LooseListParser(_WORKER_DETECTOR.scraper))
        # plain "Place Name School Time" sheets with no event header
        from backend.parsers.headertable import HeaderTableParser
        chain.append(HeaderTableParser(_WORKER_DETECTOR.scraper))
        chain.append(PlaceGridParser(_WORKER_DETECTOR.scraper))
        chain.append(ParagraphNewsParser(_WORKER_DETECTOR.scraper))
        chain.append(AgateParser(_WORKER_DETECTOR.scraper))
        chain.append(MangledStreamParser(_WORKER_DETECTOR.scraper))
        chain.append(VerticalTokensParser(_WORKER_DETECTOR.scraper))
        from backend.parsers.pipegrid import PipeGridParser
        chain.append(PipeGridParser(_WORKER_DETECTOR.scraper))
        from backend.parsers.xcsheet import XCDualSheetParser
        chain.append(XCDualSheetParser(_WORKER_DETECTOR.scraper))
        # Spreadsheet exports (Excel / OpenOffice "Save as Web Page") carry no
        # structure the other table parsers key on; content-typed columns are
        # the only handle. Last resort, so it only sees what the rest missed.
        if not filename.lower().endswith('.pdf'):
            from backend.parsers.spreadsheet import SpreadsheetTableParser
            chain.append(SpreadsheetTableParser(_WORKER_DETECTOR.scraper))
        # hand-typed XC place lists (no event header, no ruler): last resort
        from backend.parsers.xclist import XCListParser
        chain.append(XCListParser(_WORKER_DETECTOR.scraper))

        # Accept the first parser yielding a real result set (>=5 rows);
        # otherwise keep whichever produced the most.
        def _dups(res):
            rows = [(r.get('athlete'), r.get('result')) for e in (res.get('events') or [])
                    if isinstance(e, dict) for r in e.get('results', [])] if isinstance(res, dict) else []
            return len(rows) - len(set(rows))

        def _cut_names(res):
            # names cut mid-word by a column split ("ea Ro", "ydia")
            return sum(1 for e in (res.get('events') or []) if isinstance(res, dict) and isinstance(e, dict)
                       for r in e.get('results', []) if re.match(r'[a-z]', r.get('athlete') or ''))

        def _holes(res):
            # places missing inside each race's numbered list
            n = 0
            for e in (res.get('events') or []) if isinstance(res, dict) else []:
                pl = {int(r['place']) for r in e.get('results', []) if isinstance(r.get('place'), (int, float))}
                if len(pl) >= 10:
                    n += max(pl) - len(pl)
            return n

        def _verified(res):
            from backend import qaqc
            try:
                v = qaqc.xc_verify_parsed(res) if isinstance(res, dict) else None
            except Exception:
                return False
            return bool(v) and v.get('status') == 'verified'

        _ROWLIKE = re.compile(r"(?<!\S)\d{1,3}[.)]?\s+[A-Za-z'][^\d:]{1,60}?\s\d{1,2}:\d{2}")

        def _run_chain(txt, strict=False):
            # XC: the first parser to give 5+ rows wins - unless the page
            # plainly holds many more runners ("1 Name School 18:16" rows)
            # than it kept and the parse does not verify; then the parser
            # keeping the most runners (not the same ones twice) wins.
            expect = 0
            if season_label == 'XC':
                plain = txt
                if '<' in txt[:3000]:
                    # (an HTML table row's cells sit on source lines of their
                    # own: one line per row, as the page shows it)
                    if not re.search(r'<pre\b', txt, re.I) and re.search(r'<tr\b', txt, re.I):
                        plain = re.sub(r'[\r\n]+', ' ', plain)
                        plain = re.sub(r'(?i)</tr>|<br\s*/?>|</p>', '\n', plain)
                    plain = re.sub(r'<[^>]+>', ' ', plain).replace('&nbsp;', ' ')
                expect = sum(len(_ROWLIKE.findall(l)) for l in plain.splitlines())
                if not expect:
                    # (a list with no place column: one runner per timed line)
                    expect = sum(1 for l in plain.splitlines()
                                 if re.search(r'(?<![\d:.])\d{1,2}:\d{2}(?:\.\d+)?(?![\d:])', l)
                                 and len(re.findall(r'[A-Za-z]{2,}', l)) >= 2)
            first = None
            effective = chain
            # OCR'd table grids keep their borders as pipes — try the
            # pipe-grid parser first for that signature
            if sum(1 for l in txt.splitlines() if l.count('|') >= 2) >= 5:
                from backend.parsers.pipegrid import PipeGridParser
                effective = [PipeGridParser(_WORKER_DETECTOR.scraper)] + chain
            best, best_n = [], -1
            rejected, rejected_n = [], -1
            for p in effective:
                try:
                    candidate = p.parse(txt, filename, season_label)
                except Exception:
                    continue
                n = _count(candidate)
                if strict and n > 0 and not _ocr_quality_ok(candidate):
                    continue
                if not _order_ok(candidate):
                    # spliced columns: results out of finishing order.
                    # Keep as a last resort only (QAQC will flag it).
                    if n > rejected_n:
                        rejected, rejected_n = candidate, n
                    continue
                if season_label == 'XC' and not _xc_teams_ok(candidate):
                    continue  # name/team columns crossed: never keep
                if season_label == 'XC' and isinstance(candidate, dict):
                    rows = [r for e in candidate.get('events') or [] if isinstance(e, dict)
                            for r in e.get('results', [])]
                    if rows and sum(1 for r in rows if (r.get('athlete') or '').strip()) < 0.5 * len(rows):
                        continue  # relay-team rows with no runner: not an XC result
                    if any(re.search(r'(?i)\bdash\b|hurdle|jump|vault|\bshot\b|discus|javelin',
                                     str(e.get('event') or '')) for e in candidate.get('events') or []
                           if isinstance(e, dict)) and \
                            not re.search(r'(?i)\bdash\b|hurdle|jump|vault|discus|javelin', txt[:3000]):
                        continue  # a track event label the page never prints: a misread
                    if rows and sum(1 for r in rows if re.match(r'\d{1,3}[.)]|\d{1,3}\s+\d', r.get('athlete') or '')) > 0.3 * len(rows):
                        continue  # the place left in the name ("1.Tiffany Tanner", "1    1 2   169  Casey")
                    # a sheet read with its team column lost (cells shifted by
                    # a spanning header cell) when the sheet names a team column
                    if type(p).__name__ == 'SpreadsheetTableParser' and rows and \
                            sum(1 for r in rows if not (r.get('school') or '').strip()) > 0.5 * len(rows) and \
                            re.search(r'(?i)>\s*(team|school)\s*<', txt) and \
                            not re.search(r'(?i)relay', txt[:20000] + filename):
                        if n > rejected_n:      # (kept only if nothing else reads it)
                            rejected, rejected_n = candidate, n
                        continue
                if isinstance(candidate, dict) and not candidate.get('parser'):
                    candidate['parser'] = type(p).__name__  # provenance
                if n >= 5:
                    if first is None:
                        if n >= 0.8 * expect or _verified(candidate):
                            return candidate, n
                        first = [candidate, n, candidate, n]
                    elif n > 1.15 * first[3] and _dups(candidate) <= _dups(first[0]) + 2:
                        first[2:] = [candidate, n]
                    continue
                if n > best_n:
                    best, best_n = candidate, n
            if first is not None:
                return first[2], first[3]
            if best_n <= 0 and rejected_n > best_n:
                return rejected, 0  # report 0 so PDF fallbacks still try
            return best, best_n

        def _ocr_quality_ok(res):
            """OCR text can splice into plausible-looking junk; only keep an
            OCR-derived parse when names and events are overwhelmingly clean."""
            if not isinstance(res, dict):
                return False
            names = []
            ev_labels = []
            evs = res.get('events', []) if isinstance(res, dict) else res
            for ev in evs or []:
                if not isinstance(ev, dict):
                    continue
                if 'results' in ev:
                    ev_labels.append(str(ev.get('event', '')))
                    for r in ev['results']:
                        names.append(str(r.get('athlete') or r.get('school') or ''))
                else:  # flat HyTek row
                    ev_labels.append(str(ev.get('event', '')))
                    names.append(str(ev.get('athlete_name') or ev.get('school') or ''))
            ev_ok = sum(1 for e in ev_labels if re.search(
                r'dash|mete?r?|relay|hurd|jump|vault|put|disc|jav|walk|mile|run|\d{2,4}', e, re.I))
            if len(names) < 8 or not ev_labels or ev_ok / len(ev_labels) < 0.8:
                return False
            clean = sum(1 for n in names
                        if re.fullmatch(r"[A-Za-z][A-Za-z ,.'&/-]{2,40}", n.strip()))
            return clean / len(names) >= 0.75


        results, best_n = _run_chain(text)

        # Scrambled-spreadsheet PDFs: retry with coordinate-rebuilt text,
        # then column-gap-split text, and finally OCR for image-only scans
        if best_n < 5 and filename.lower().endswith('.pdf'):
            from backend.parser import Sub5ColumnParser
            for extractor in (Sub5ColumnParser.pdf_words_to_text,
                              Sub5ColumnParser.pdf_column_text,
                              Sub5ColumnParser.pdf_ocr_text):
                alt = extractor(input_path)
                if not alt:
                    continue
                alt_results, alt_n = _run_chain(Sub5ColumnParser.clean_pdf_text(alt), strict=True)
                # compare by actual content: order-rejected keeps report n=0
                # but still carry (flagged) results worth more than nothing
                if _count(alt_results) > _count(results):
                    results, best_n = alt_results, max(alt_n, best_n)
                if alt_n >= 5:
                    break

        # An XC PDF whose parse holds far fewer runners than the page has
        # finish times: the column splitter may have cut a two-table page
        # apart (poland_sept2.pdf: girls' and boys' pages side by side, 38 of
        # ~96 runners kept). Retry on the uncut layout text and the other
        # extractions; keep whichever holds the most runners.
        elif season_label == 'XC' and filename.lower().endswith('.pdf'):
            n_times = sum(len(re.findall(r'(?<![\d:.])\d{1,2}:\d{2}(?:\.\d+)?(?![\d:])', l)) or
                          # (two lists side by side timed "21:50:00": both count)
                          (lambda k: k if k >= 2 else 0)(len(re.findall(
                              r'(?<![\d:.])(?:[89]|[1-5]\d):\d{2}:\d{2}(?![\d:])', l)))
                          for l in raw.splitlines() if re.search(r'[A-Za-z]{2}', l))
            if n_times >= 15 and _count(results) < 0.95 * n_times and not _verified(results) and \
                    not re.search(r'(?i)relay', filename):
                from backend.parser import Sub5ColumnParser
                best_c = _count(results)
                for alt in (raw, Sub5ColumnParser.pdf_words_to_text(input_path),
                            Sub5ColumnParser.pdf_column_text(input_path)):
                    if not alt:
                        continue
                    if alt is not raw:
                        alt = Sub5ColumnParser.clean_pdf_text(alt)
                    alt_results, alt_n = _run_chain(alt, strict=True)
                    # (more runners, not the same runners twice)
                    # (more runners, not the same runners twice; a list's
                    # last few rows lost to the column splitter count too)
                    if alt_n >= 5 and (_count(alt_results) > 1.1 * best_c and _count(results) < 0.75 * n_times or
                                       _count(alt_results) >= best_c + 3 and alt is raw and
                                       _dups(alt_results) <= _dups(results) and
                                       _cut_names(alt_results) <= _cut_names(results)) and \
                            _dups(alt_results) <= _dups(results) + 2:
                        results, best_n, best_c = alt_results, alt_n, _count(alt_results)

        # An XC PDF list with holes in its places (55, 56, 58, 59 missing):
        # the layout text split those rows' name from their school and time
        # ("55 K. McEwen" / "Car" / "20:12" on three lines). The PDF's
        # reading-order text keeps each row whole: keep it when it fills holes.
        if season_label == 'XC' and filename.lower().endswith('.pdf') and _holes(results) and \
                not _verified(results):
            try:
                import subprocess
                rt = subprocess.run(['pdftotext', '-raw', input_path, '-'], capture_output=True,
                                    text=True, timeout=60).stdout
            except Exception:
                rt = ''
            if rt:
                from backend.parser import Sub5ColumnParser
                alt_results, alt_n = _run_chain(Sub5ColumnParser.clean_pdf_text(rt), strict=True)
                if alt_n >= 5 and _holes(alt_results) < _holes(results) and \
                        _count(alt_results) > _count(results) and _dups(alt_results) <= _dups(results):
                    results, best_n = alt_results, max(alt_n, best_n)

        data_to_save = results
        if isinstance(results, list) and results and 'event' in results[0]:
            data_to_save = {'events': results, 'date': results[0].get('date')} if 'date' in results[0] else results
        if season_label == 'XC' and isinstance(data_to_save, list) and not data_to_save:
            data_to_save = {'events': [], 'date': None, 'meet_name': None, 'team_rankings': []}
        # The file's own Hy-Tek header is a second source of truth for the
        # venue; only fill what the parser could not supply itself.
        if isinstance(data_to_save, dict):
            split_gender_suffix(data_to_save)
            fix_event_gender_from_label(data_to_save)
            if season_label == 'XC':
                drop_relay_team_totals(data_to_save, text, filename)
                drop_duplicate_events(data_to_save)
                fix_wrapped_places(data_to_save)
                strip_sex_prefix(data_to_save)
                # (a non-breaking space inside a name or team: "Palmer,\xa0Eli")
                for _e in data_to_save.get('events') or []:
                    for _r in (_e.get('results') or []) if isinstance(_e, dict) else []:
                        for _f in ('athlete', 'school'):
                            if isinstance(_r.get(_f), str) and '\xa0' in _r[_f]:
                                _r[_f] = re.sub(r'\s+', ' ', _r[_f].replace('\xa0', ' ')).strip()
                            # (a soft hyphen and a typeset dash left on a name: "Morris-\xad\u2010")
                            if isinstance(_r.get(_f), str) and '\xad' in _r[_f]:
                                _r[_f] = re.sub(r'[-\u2010\xad\s]+$', '', _r[_f].replace('\xad', ''))
                            # ("Ted Warnquist | YORK": a typed column bar)
                            if isinstance(_r.get(_f), str) and re.match(r'\|\s|.*\s\|$', _r[_f]):
                                _r[_f] = _r[_f].strip(' |')
                merge_continued_events(data_to_save)
                fix_event_gender_from_names(data_to_save)
                pre_drop_events = list(data_to_save.get('events') or [])
                drop_sibling_gender_events(data_to_save, input_path)
            else:
                # track: a race whose names all belong to the other sex
                # (a sheet the parser read under one gender)
                fix_event_gender_from_names(data_to_save, split=False)
                # the official team scores, in every format a file prints
                # them (backend/parsers/teamscores.py), when the parser
                # read none: the score check needs them
                if not data_to_save.get('team_rankings'):
                    add_team_scores(data_to_save, input_path)
            meta = hytek_header_meta(text)
            if meta['venue'] and not data_to_save.get('venue'):
                data_to_save['venue'] = meta['venue']
            # (a parser that skips dated lines takes the venue for the title)
            if meta['meet'] and (not data_to_save.get('meet_name')
                                 or data_to_save.get('meet_name') == meta['venue']):
                data_to_save['meet_name'] = meta['meet']
            if meta['host'] and not data_to_save.get('host'):
                data_to_save['host'] = meta['host']
            # Junior-high / middle-school meets posted beside the high-school
            # results: told by the meet title, never by the venue (the
            # Festival of Champions is held at a middle school)
            if season_label == 'XC':
                title = meta['meet'] or data_to_save.get('meet_name') or ''
                if data_to_save.get('meet_level') == 'ms' or _MS_MEET_TITLE.search(title):
                    data_to_save['meet_level'] = 'ms'
                    for ev in data_to_save.get('events') or []:
                        for r in (ev.get('results') or []) if isinstance(ev, dict) else []:
                            if isinstance(r, dict) and not r.get('grade'):
                                r['grade'] = 'MS'
            # Official XC team scores ride along with any parser's rows: they
            # are what QAQC re-derives from the finish order
            # an "All Classes Combined" / New England qualifier list re-ranks
            # races posted on their own: kept out of 'events' (no runner is
            # stored twice) but read as 'aggregate_events' so its own team
            # scores can be checked against it
            if season_label == 'XC' and not data_to_save.get('events') and \
                    re.search(r'combin|qualif', filename + ' ' + text[:5000], re.I):
                try:
                    from backend.parser import Sub5ColumnParser
                    agg = Sub5ColumnParser(filename, text=text)
                    agg.allow_aggregate = True
                    ar = agg.parse()
                    aev = ar.get('events') if isinstance(ar, dict) else None
                    if not aev:
                        from backend.parsers.xclist import XCListParser
                        xl = XCListParser(_WORKER_DETECTOR.scraper)
                        xl.allow_aggregate = True
                        aev = xl.parse(text, filename, 'XC').get('events')
                    if aev:
                        data_to_save['aggregate_events'] = [dict(e, aggregate=True) for e in aev]
                except Exception:
                    pass
            if season_label == 'XC':
                # (a file holding only the team scores keeps them too: they
                # are checked against the race posted beside it)
                from backend.parsers.xcscores import parse_xc_team_scores
                xc_blocks = parse_xc_team_scores(text)
                if filename.lower().endswith('.pdf') and raw and raw is not text:
                    # (two score tables side by side, cut apart by the column
                    # splitter: the layout text keeps their rows whole)
                    alt_blocks = parse_xc_team_scores(raw)
                    if sum(len(b['teams']) for b in alt_blocks) > sum(len(b['teams']) for b in xc_blocks or []):
                        xc_blocks = alt_blocks
                if (not xc_blocks or all(b.get('totals_only') for b in xc_blocks)) and not any(
                        b.get('kind') == 'xc' for b in data_to_save.get('team_rankings') or []):
                    # team scores as a grid of places ("1st 14 1 5 / TOTAL"),
                    # or columns of places under the team names: these carry
                    # every place, so they win over a list of totals
                    from backend.parsers.teamgrid import team_grid_blocks, vertical_grid_blocks
                    plain = raw if filename.lower().endswith('.pdf') else \
                        re.sub(r'<[^>]+>', ' ', text).replace('&nbsp;', ' ')
                    fg = ('Girls' if re.search(r'girl|women', filename, re.I)
                          else 'Boys' if re.search(r'boy|\bmen', filename, re.I) else None)
                    grid = team_grid_blocks(plain, fg)
                    vgrid = vertical_grid_blocks(raw if filename.lower().endswith('.pdf') else text, fg)
                    # (a scorer-number column 1-5 beside team columns can read
                    # as an ordinal grid with one team: keep the fuller reading)
                    if vgrid and sum(len(b['teams']) for b in vgrid) > sum(len(b['teams']) for b in grid or []):
                        grid = vgrid
                    if grid:
                        xc_blocks = grid
                if xc_blocks:
                    # a block naming no gender in a file whose rows are one
                    # race plus a stray runner or two of the other sex (girls
                    # in a boys' race, split off by the sex column): that race
                    evs = [e for e in data_to_save.get('events') or [] if isinstance(e, dict)]
                    tot = sum(len(e.get('results') or []) for e in evs)
                    by_g = {}
                    for e in evs:
                        by_g[e.get('gender')] = by_g.get(e.get('gender'), 0) + len(e.get('results') or [])
                    if tot and len(by_g) > 1:
                        g0, n0 = max(by_g.items(), key=lambda kv: kv[1])
                        if n0 >= 0.9 * tot:
                            for b in xc_blocks:
                                if b.get('gender') is None:
                                    b['gender'] = g0
                    # a genderless block for the race this file left to its
                    # sibling ("...boys..." file printing both races' grids):
                    # the race it fits names its gender
                    kept_g = {e.get('gender') for e in data_to_save.get('events') or [] if isinstance(e, dict)}
                    gone = [e for e in locals().get('pre_drop_events') or []
                            if isinstance(e, dict) and e.get('results') and e.get('gender') not in kept_g]
                    live = [e for e in data_to_save.get('events') or [] if isinstance(e, dict) and e.get('results')]
                    # a race the parser gendered by default (two "Boys"
                    # sheets) whose results the other gender's score table
                    # reproduces exactly: that race is the other gender's
                    from backend import qaqc as _q
                    for b in xc_blocks:
                        g = b.get('gender')
                        if g not in ('Boys', 'Girls') or any(e.get('gender') == g for e in live):
                            continue
                        offs = sorted(((_q._xc_verify_block(b, e['results']) or {}).get('teams_off', 99), k)
                                      for k, e in enumerate(live))
                        # (the best fit, off by at most one team, and clearly best)
                        fit = [live[offs[0][1]]] if offs and offs[0][0] <= 1 and \
                            (len(offs) == 1 or offs[1][0] >= offs[0][0] + 2) else []
                        if len(fit) == 1 and sum(1 for e in live if e.get('gender') == fit[0].get('gender')) > 1:
                            fit[0]['gender'] = g
                            fit[0]['gender_from_scores'] = True
                    if gone or len({e.get('gender') for e in live}) > 1:
                        from backend import qaqc as _q
                        for b in xc_blocks:
                            if b.get('gender') is None:
                                fits = {e.get('gender') for e in gone + [e for e in data_to_save.get('events') or []
                                                                          if isinstance(e, dict) and e.get('results')]
                                        if (_q._xc_verify_block(b, e['results']) or {}).get('status') == 'verified'}
                                if len(fits) == 1:
                                    b['gender'] = fits.pop()
                    # (the other gender's table, whose race went to the
                    # sibling file: it is checked there)
                    gone_g = {e.get('gender') for e in gone} - {e.get('gender') for e in live} - {None}
                    if gone_g and live:
                        xc_blocks = [b for b in xc_blocks if b.get('gender') not in gone_g]
                    _pair_xc_blocks(data_to_save.get('events') or [], xc_blocks)
                    # each block's division / class label, from its race's name
                    # when the score table itself names none
                    evs_all = data_to_save.get('events') or []
                    for b in xc_blocks:
                        ei = b.get('event_idx')
                        if not b.get('division') and isinstance(ei, int) and 0 <= ei < len(evs_all):
                            md = re.search(r'\b(Class\s+[A-D]\b|Division\s+\w+|(?:Small|Large)\s+School|'
                                           r'Junior\s+Varsity|JV|Varsity|Freshman|Middle\s+School|Reserve)',
                                           str(evs_all[ei].get('event') or '') + ' ' + str(evs_all[ei].get('section') or ''), re.I)
                            if md:
                                b['division'] = md.group(1)
                    data_to_save['team_rankings'] = [
                        b for b in (data_to_save.get('team_rankings') or [])
                        if b.get('kind') != 'xc'] + xc_blocks
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=4, ensure_ascii=False)
        return (filename, _count(results), None)
    except Exception as e:
        return (filename, 0, str(e))


def write_meet_links(url_mapping=None):
    """ui/public/data/meet_links.json.gz: {'<year>_<season>': {meet_name:
    url}} for the site's meet links. sub5 files come from the scraper's URL
    map (meet_name is the archive filename without its extension, as the
    store files it); Five K Sport files link to their OneDrive document."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if url_mapping is None:
        try:
            with open(os.path.join(base, 'backend', 'web_url_mapping.json'), encoding='utf-8') as f:
                url_mapping = json.load(f)
        except (OSError, ValueError):
            url_mapping = {}
    out = {}
    for key, url in url_mapping.items():
        year, season, filename = key.split('/', 2)
        stem, ext = os.path.splitext(filename)
        meets = out.setdefault(f'{year}_{season}', {})
        meets[stem] = url
        if ext.lower() == '.pdf':
            # a PDF sharing its stem with an .htm is stored as '<stem>_pdf'
            meets[f'{stem}_pdf'] = url
    import glob
    for path in glob.glob(os.path.join(base, 'backend', 'data', 'parsed_results', '*', 'XC', 'fiveks-*.json')):
        try:
            with open(path, encoding='utf-8') as f:
                url = (json.load(f).get('source') or {}).get('url')
        except (OSError, ValueError):
            continue
        if url:
            year = path.split(os.sep)[-3]
            out.setdefault(f'{year}_XC', {})[os.path.splitext(os.path.basename(path))[0]] = url
    import gzip
    dest = os.path.join(base, 'ui', 'public', 'data', 'meet_links.json.gz')
    with gzip.open(dest, 'wb', compresslevel=9) as f:
        f.write(json.dumps(out, separators=(',', ':'), sort_keys=True).encode('utf-8'))
    return out


class Sub5ScraperV2:
    def __init__(self, progress_callback=None):
        self.headers = {'User-Agent': 'Mozilla/5.0'}
        self.manual_fixes = self.load_manual_fixes()
        self.web_date_mapping = self.load_web_date_mapping()
        self.web_meet_mapping = self.load_web_meet_mapping()
        self.web_url_mapping = self.load_web_url_mapping()
        self.team_registry = self.load_team_registry()
        self.progress_callback = progress_callback
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        # urllib3 owns the backoff, honours Retry-After, and retries only the
        # transient statuses; 4xx stays permanent because the legacy tree is
        # full of dead links that are not worth ~7s each to re-confirm.
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        retry = Retry(total=3, connect=3, read=3,
                      backoff_factor=1,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(['GET', 'HEAD']),
                      raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def load_team_registry(self):
        """Canonical team names + level-aware aliases, built by
        build_team_registry.py from name clustering and athlete-roster
        overlap. See backend/data/team_registry.json."""
        path = os.path.join(os.path.dirname(__file__), 'data', 'team_registry.json')
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {'teams': {}, 'aliases': {}, 'keys': {}}

    @staticmethod
    def registry_cluster_key(name):
        """Mirror of build_team_registry.cluster_key for runtime lookups."""
        from backend.build_team_registry import cluster_key
        return cluster_key(name)

    MARK_STATUS_CODES = {"DQ", "NH", "FOUL", "NM", "DNS", "DNF", "SCR", "ND", "NT", "FAIL", "FS"}

    def mark_is_valid_format(self, mark):
        """Strict mark validation for the sync stage.

        Accepts status codes, times (13.5 / 2:31.50 / 10:44), and
        feet-inches distances (5-0 / 33-04.25 / 19'9.5").  Rejects bare
        integers, truncated distances ("15-"), and anything else — those are
        parser artifacts, not results.
        """
        if not mark:
            return False
        m = str(mark).strip().upper()
        if m in self.MARK_STATUS_CODES:
            return True
        if re.fullmatch(r"\d{1,3}-\d{1,2}(\.\d+)?", m):       # 33-04.25
            return True
        if re.fullmatch(r"\d{1,2}'\d{1,2}(\.\d+)?\"?", m):    # 19'9.5"
            return True
        if re.fullmatch(r"(\d{1,2}:)?\d{1,2}[:.]\d{1,2}(\.\d+)?H?", m):  # 13.5 / 2:31.5 / 1:02:33
            return True
        if re.fullmatch(r"\d{1,3}(\.\d+)?M", m):                         # metric distance 11.58m
            return True
        return False

    _EVENT_METERS = re.compile(r'(\d{2,4})\s*(?:m\b|meter)', re.I)

    def repair_mark(self, mark, event):
        """Repair colon-loss in running-event times: an 800m '2.28' is 2:28.

        Returns (possibly repaired) mark, or None when the mark is physically
        impossible for the event even after repair."""
        ev = event.lower()
        if any(k in ev for k in ('jump', 'put', 'vault', 'discus', 'javelin', 'throw')):
            return mark
        meters = None
        m = self._EVENT_METERS.search(event)
        if m:
            meters = int(m.group(1))
            if '4x' in ev.replace(' ', ''):
                meters *= 4
        elif 'mile' in ev:
            meters = 1609 * (2 if '2 mile' in ev else 1)
        if not meters or meters < 50:
            return mark
        if 'pentathlon' in ev or 'heptathlon' in ev or 'decathlon' in ev:
            return mark
        floor = meters * 0.095  # slightly faster than world record pace
        mm = re.fullmatch(r'(\d{1,2})\.(\d{2})(?:\.\d+)?', str(mark).strip())
        val = None
        try:
            val = float(str(mark).strip()) if ':' not in str(mark) else None
        except ValueError:
            pass
        if val is not None and val < floor and mm and meters >= 400:
            repaired = int(mm.group(1)) * 60 + int(mm.group(2))
            if floor <= repaired <= meters * 0.7:
                return f'{mm.group(1)}:{mm.group(2)}'
        if val is not None and val < floor:
            return None  # impossible even after repair
        return mark

    def team_name_is_sane(self, team):
        """Reject 'team' names that are really leaked result rows or athlete names."""
        if not team or team == "Unknown":
            return False
        if len(team) > 45:
            return False
        if re.search(r'\d', team):          # no school has digits in its name; leaked row
            return False
        return True

    def mark_is_reasonable(self, mark, event):
        """Basic sanity check to avoid parsing junk like 'H# 1' as a result."""
        if not mark or len(mark) < 2: return False
        # Field event marks like "38-05" or "5-02"
        if '-' in mark: return True
        # Track marks like "4:55.22" or "10.55"
        if '.' in mark: return True
        # Standard status codes
        if mark.upper() in ["DQ", "NH", "FOUL", "NM", "DNS", "DNF", "SCR"]:
            return True
        return False

    def report_progress(self, message, progress=None):
        if self.progress_callback:
            self.progress_callback(message, progress)
        else:
            p_str = f" [{progress}%]" if progress is not None else ""
            elapsed = datetime.now().strftime("%H:%M:%S")
            print(f"[{elapsed}] {message}{p_str}")

    def load_web_date_mapping(self):
        mapping_path = os.path.join(os.path.dirname(__file__), 'web_date_mapping.json')
        if os.path.exists(mapping_path):
            try:
                with open(mapping_path, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def load_web_meet_mapping(self):
        """Meet name + venue harvested from the season index tables, keyed
        '<year>/<season>/<filename>'. The venue column is the only reliable
        course identity for the ~95% of result files that carry none."""
        mapping_path = os.path.join(os.path.dirname(__file__), 'web_meet_mapping.json')
        if os.path.exists(mapping_path):
            try:
                with open(mapping_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_web_meet_mapping(self):
        mapping_path = os.path.join(os.path.dirname(__file__), 'web_meet_mapping.json')
        try:
            with open(mapping_path, 'w', encoding='utf-8') as f:
                json.dump(self.web_meet_mapping, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving web_meet_mapping: {e}")

    def load_web_url_mapping(self):
        """Source URL of every result file, keyed '<year>/<season>/<filename>'
        like the date and meet maps. The site links each meet to it."""
        mapping_path = os.path.join(os.path.dirname(__file__), 'web_url_mapping.json')
        if os.path.exists(mapping_path):
            try:
                with open(mapping_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_web_url_mapping(self):
        mapping_path = os.path.join(os.path.dirname(__file__), 'web_url_mapping.json')
        try:
            with open(mapping_path, 'w', encoding='utf-8') as f:
                json.dump(self.web_url_mapping, f, indent=1, sort_keys=True)
        except Exception as e:
            print(f"Error saving web_url_mapping: {e}")

    @staticmethod
    def _archive_filename(link):
        """The archive filename a result link is saved under."""
        filename = link.split('/')[-1]
        if '?' in filename:
            filename = filename.split('?')[0]
        # Preserve .pdf extension; only append .htm for non-typed links
        if not filename.lower().endswith(('.htm', '.html', '.pdf')):
            filename += ".htm"
        return filename

    def record_source_urls(self, seasons=None):
        """Fill web_url_mapping from the season index pages alone (no result
        files are downloaded): one index request per season, the same pages
        a full scrape reads."""
        n = 0
        for config in (seasons if seasons is not None else SEASONS):
            for link in self.get_meet_links(config['url']):
                key = f"{config['year']}/{config['season']}/{self._archive_filename(link)}"
                if self.web_url_mapping.get(key) != link:
                    self.web_url_mapping[key] = link
                    n += 1
        self.save_web_url_mapping()
        return n

    def parse_web_date(self, date_str):
        """Parse a season-index date cell ("October 25, 2008", "Oct 25, 2008",
        "June 3-4, 2005"). dateutil handles the format variation; the only
        local rule is that a multi-day meet is dated to its first day."""
        if not date_str:
            return None
        # "June 3-4, 2005" / "June 3 & 10, 2006" / "January 9/10, 2015" -> first
        # day. The slash form must be collapsed before parsing or it reads as
        # month/day and silently takes the year from the wrong token.
        date_str = re.sub(r'(\d{1,2})\s*[-&/]\s*\d{1,2}(?=\s*,)', r'\1', date_str)
        date_str = re.sub(r'(\d{1,2})\s*[-&]\s*\d{1,2}', r'\1', date_str)
        try:
            from dateutil import parser as _dateparser
            dt = _dateparser.parse(date_str, fuzzy=True, dayfirst=False)
        except Exception:
            return None
        return dt.strftime("%Y-%m-%d")

    def web_date_days(self, date_str):
        """Every day a season-index date cell names: "January 9/10, 2015" ->
        both days, "June 3-4, 2005" -> June 3 and 4. One day for a plain date."""
        first = self.parse_web_date(date_str)
        if not first:
            return set()
        days = {first}
        m = re.search(r'(\d{1,2})\s*[-&/]\s*(\d{1,2})(?=\s*,|\s+\d{4})', date_str or '')
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a < b <= a + 6:
                from datetime import date as _d, timedelta
                d0 = _d.fromisoformat(first)
                days |= {(d0 + timedelta(days=i)).isoformat() for i in range(b - a + 1)}
        return days

    def _get_with_retry(self, url, max_retries=3):
        """Fetch a URL. Transient failures are retried by the session's
        urllib3 adapter; this only turns a final failure into an exception."""
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response

    def load_manual_fixes(self):
        if os.path.exists(FIXES_PATH):
            try:
                with open(FIXES_PATH, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"meet_corrections": [], "athlete_corrections": []}

    def normalize_team_name(self, name, all_teams=None, level='hs'):
        """Cached wrapper: school strings repeat constantly (same ~50 names per
        meet), and the fallback matching below is O(n log n) per call, so
        memoize per (name, level) and rebuild the lookup structures only when
        the known-team set grows.

        `level` is the meet context ('hs', 'ms', 'college'): bare town names
        resolve to a different school per level ("Falmouth" is Falmouth Middle
        School in an MS meet, Falmouth High School otherwise)."""
        if not name: return "Unknown"
        if all_teams is not None:
            if getattr(self, '_tc_size', -1) != len(all_teams):
                self._tc_size = len(all_teams)
                self._tc_lower = {t.lower(): t for t in all_teams}
                self._tc_sorted = sorted((t for t in all_teams if not re.search(r'\d', t)), key=len)
                self._tc_memo = {}
            hit = self._tc_memo.get((name, level))
            if hit is not None:
                return hit
        result = self._normalize_team_name_impl(name, all_teams, level)
        if all_teams is not None:
            self._tc_memo[(name, level)] = result
        return result

    def _registry_lookup(self, name, level):
        """Resolve via the team registry: exact alias first, then identity key.
        Prefers the meet-level's canonical, falls back to any level."""
        for table, key in (('aliases', name.lower()),
                           ('keys', self.registry_cluster_key(name))):
            entry = self.team_registry.get(table, {}).get(key)
            if entry:
                return entry.get(level) or entry.get('hs') or next(iter(entry.values()))
        return None

    def _normalize_team_name_impl(self, name, all_teams=None, level='hs'):
        name = name.strip()
        name = re.sub(r'^\d+[-\s]*', '', name)
        if "unattach" in name.lower() or name.lower() == "un":
            return "Unattached"
        name = re.sub(r'\s+\d{4}$', '', name)
        if re.match(r'^:?\d+[:.]\d+', name) or re.match(r'^\d+-\d+\.?\d*$', name):
            return "Unknown"
        name = re.sub(r'^(M|JR|W|FR|SO|SR)\s+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+J[\d\.\-\':]+.*', '', name)
        name = name.strip()
        if "," in name:
            name = name.split(',')[0].strip()
        # Strip trailing state suffixes: "Massabesic HS Waterboro ME", "Mattanawcook AcademyME"
        name = re.sub(r'[,\s]+(ME|MA|NH|VT|CT|RI)$', '', name)
        name = re.sub(r'(?<=[a-z])(ME|MA|NH|VT|CT|RI)$', '', name)
        # Trailing separators and relay-squad letters: "York -", "Scarboro A"
        name = re.sub(r'[\s\-–—*.]+$', '', name)
        name = re.sub(r'\s+[A-D]$', '', name)
        name = name.strip()

        # Team registry: canonical names + level-aware aliases built from
        # name clustering and athlete-roster overlap (build_team_registry.py)
        reg = self._registry_lookup(name, level)
        if reg:
            return reg
        
        # Exact case-insensitive match against known teams ("MUSTANGS" vs
        # "Mustangs" would otherwise create duplicate team files)
        if all_teams:
            hit = self._tc_lower.get(name.lower())
            if hit is not None:
                return hit

        # Dynamic Acronym Matching
        if all_teams and len(name) >= 2 and len(name) <= 5 and name.isupper():
            matches = []
            for fuller_name in all_teams:
                if len(fuller_name) <= len(name): continue
                if re.search(r'\d', fuller_name): continue  # never match into a leaked-row name
                acr_full = "".join(re.findall(r'\b\w', fuller_name)).upper()
                base = re.sub(r'\s+(High School|Academy|Regional High School|Area High School|Schools|Memorial High School|Comprehensive High School|Christian Schools)$', '', fuller_name, flags=re.IGNORECASE)
                acr_base = "".join(re.findall(r'\b\w', base)).upper()
                if name in [acr_full, acr_base]:
                    matches.append(fuller_name)
            unique_matches = list(set(matches))
            if len(unique_matches) == 1:
                return unique_matches[0]

        ms_tokens = ["ms", "middle", "junior high", "jh", "elementary", "elem", "elementa", "primary", "interme"]
        is_ms_token = any(f" {t}" in name.lower() or name.lower().endswith(f" {t}") or name.lower().endswith(t) for t in ms_tokens)
        
        for key, val in TEAM_MAPPING.items():
            if is_ms_token:
                if name.lower() == key.lower():
                    return val
                continue
            if name.lower().startswith(key.lower()):
                return val

        if all_teams and len(name) >= 4:
            # Prefer the SHORTEST sane candidate: junk names built from leaked
            # rows are long, so longest-first matching amplifies one bad row
            # into thousands of misassigned performances.
            name_lower = name.lower()
            for fuller_name in self._tc_sorted:
                if len(fuller_name) <= len(name):
                    continue
                if not fuller_name.lower().startswith(name_lower):
                    continue
                fuller_is_ms = any(f" {t}" in fuller_name.lower() or fuller_name.lower().endswith(t) for t in ms_tokens)
                if is_ms_token != fuller_is_ms:
                    continue
                return fuller_name
            
        return name

    def normalize_athlete_name(self, name):
        if not name: return ""
        name = name.strip()
        name = re.sub(r'^[\s#\-]*\d+[\s.\-]*', '', name).strip()
        
        # Check manual fixes on the raw cleaned name first
        for ac in self.manual_fixes.get('athlete_corrections', []):
            if ac['old_name'].lower() == name.lower():
                return ac['new_name']
                
        # Pre-clean duplicate/surrounding commas
        name = re.sub(r',+', ',', name).strip(', ')

        # Handle "Last, First" -> "First Last" format conversion
        if "," in name:
            parts = [p.strip() for p in name.split(',', 1)]
            if len(parts) == 2:
                last_name, first_name = parts[0], parts[1]
                # Remove leftover commas in names
                last_name = last_name.replace(',', '').strip()
                first_name = first_name.replace(',', '').strip()
                if last_name and first_name:
                    # Look for class year / suffix at the end of first_name (e.g., "JR", "SR", "SO", "FR", "II", "III")
                    suffix_match = re.search(r'\s+(JR|SR|SO|FR|I|II|III|IV|JR\.|SR\.)$', first_name, re.IGNORECASE)
                    if suffix_match:
                        suffix = suffix_match.group(0)
                        first_name_clean = first_name[:-len(suffix)].strip()
                        name = f"{first_name_clean} {last_name}{suffix}"
                    else:
                        name = f"{first_name} {last_name}"
                        
        # Check manual fixes again on the normalized name
        for ac in self.manual_fixes.get('athlete_corrections', []):
            if ac['old_name'].lower() == name.lower():
                return ac['new_name']
                
        return name


    def normalize_parsed_date(self, date):
        """Coerce parser-emitted dates ('2011-01-08', '1/8/11', 'Unknown Date')
        to ISO YYYY-MM-DD, or None if unparseable."""
        if not date:
            return None
        d = str(date).strip()
        if re.match(r'^\d{4}-\d{2}-\d{2}', d):
            return d[:10]
        m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{2,4})$', d)
        if m:
            mm, dd, yy = m.groups()
            if len(yy) == 2:
                yy = '20' + yy
            return f"{yy}-{mm.zfill(2)}-{dd.zfill(2)}"
        return None

    _MONTHS = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
               'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}

    def date_from_filename(self, stem, season, year):
        """Extract a meet date embedded in the filename, validated in-season.
        Handles 'boys_orono_meet_5.21.14', 'results-5-26-05-MVC', 'ham29april03',
        'emitl2a20dec2025'."""
        s = stem.lower()
        # numeric m.d.y / m-d-y / m_d_y
        for m in re.finditer(r'(\d{1,2})[._-](\d{1,2})[._-](\d{2,4})', s):
            mm, dd, yy = m.groups()
            if len(yy) == 2:
                yy = '20' + yy
            cand = f"{yy}-{mm.zfill(2)}-{dd.zfill(2)}"
            if self.is_date_in_season(cand, season, year):
                return cand
        # DDmonthYY / DDmonYYYY (e.g. 29april03, 20dec2025)
        for m in re.finditer(r'(\d{1,2})(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*(\d{2,4})', s):
            dd, mon, yy = m.groups()
            if len(yy) == 2:
                yy = '20' + yy
            cand = f"{yy}-{self._MONTHS[mon]:02d}-{dd.zfill(2)}"
            if self.is_date_in_season(cand, season, year):
                return cand
        return None

    def is_date_in_season(self, date_str, season, year):
        if not date_str: return False
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            year_val = int(year)
            if season == "Indoor":
                start_date = datetime(year_val - 1, 11, 1)
                end_date = datetime(year_val, 3, 31)
                return start_date <= dt <= end_date
            elif season == "Outdoor":
                start_date = datetime(year_val, 3, 1)
                end_date = datetime(year_val, 6, 30)
                return start_date <= dt <= end_date
            elif season == "XC":
                start_date = datetime(year_val, 8, 1)
                end_date = datetime(year_val, 12, 10)
                return start_date <= dt <= end_date
            return True
        except:
            return False

    def is_likely_athlete_name(self, name):
        if not name: return True
        name_clean = name.strip()
        school_keywords = ['High', 'School', 'Academy', 'Acad', 'Institute', 'MCI', 'GSA', 'MDI', 'GSA', 'EMITL', 'PVC', 'Relay', 'Track', 'Field', 'Team', 'Club', 'Middle', 'University', 'College', 'Mt.', 'Mountain', 'Valley', 'Point', 'Portland', 'Christian', 'Catholic', 'Prep', 'Charter', 'Regional', 'Community', 'Consolidated']
        if any(k.lower() in name_clean.lower() for k in school_keywords):
            return False
        short_keywords = ['EL', 'HS', 'MS', 'U VT']
        for sk in short_keywords:
            if re.search(r'\b' + re.escape(sk) + r'\b', name_clean, re.I):
                return False
        if re.match(r'^[A-Z][a-z.\']+\s+([A-Z][a-z.\']+\s*){1,2}$', name_clean):
            return True
        if ',' in name_clean:
            return True
        if re.search(r'\d', name_clean) and any(c in name_clean for c in '.:-\''):
            return False
        if '   ' in name_clean:
            return True
        if len(name_clean) < 3:
            return True
        return False

    def get_meet_links(self, year_url):
        try:
            response = self._get_with_retry(year_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            links_with_dates = {}
            frames = soup.find_all(['frame', 'iframe'], src=True)
            if frames:
                for frame in frames:
                    from urllib.parse import urljoin
                    frame_url = urljoin(year_url, frame['src'])
                    links_with_dates.update(self.get_meet_links_with_dates(frame_url))
            links_with_dates.update(self.get_meet_links_with_dates(year_url, soup))
            return links_with_dates
        except Exception as e:
            print(f"Error fetching meet links from {year_url}: {e}")
            return {}

    def get_meet_links_with_dates(self, url, soup=None):
        if not soup:
            try:
                res = self._get_with_retry(url)
                soup = BeautifulSoup(res.text, 'html.parser')
            except:
                return {}
        mapping = {}
        def is_valid_result_link(h):
            h = h.lower()
            if not (h.endswith('.htm') or h.endswith('.html') or h.endswith('.pdf') or h.endswith('.txt')): return False
            # Only follow sub5-hosted files (legacy pages link out to
            # coolrunning, nesportstiming, newenglandsports, etc.)
            if h.startswith('http') and 'sub5.com' not in h:
                return False
            # Legacy year-index pages (2003-2013 season tables of contents) are
            # crawled as their own seasons via SEASONS, never as meet results.
            if re.search(r'results\s*\d{2}/(meetresults\d{0,2}|results)\.htm$', h):
                return False
            junk = ['meetresults', 'resultspPVC', 'index.htm', 'contact.htm', 'about.htm',
                    'links.htm', 'home.htm', 'siteinfo', 'coachinfo', 'schedule',
                    'performanceupdate', 'top10', 'records', 'photos', 'summeryouth',
                    'email-protection', 'entries', 'entry', 'psych', 'heat-sheet',
                    'heatsheet', 'startlist', 'start-list']
            if any(x in h for x in junk):
                return False
            keywords = ['result', 'emitl', 'pvc', 'states', 'class', 'champ', 'meet', 'inv', 'scores', 'relays', 'festival', 'open', 'youth', 'ms', 'jh', 'middle', 'junior', 'boys', 'girls', 'kvac', 'wmc', 'smaa', 'mvc', 'frosh', 'freshman', 'bangor', 'gsa', 'bucksport', 'ellsworth', 'mdi', 'orono', 'oldtown', 'brewer', 'falmouth']
            if any(x in h for x in keywords): return True
            filename = h.split('/')[-1]
            if re.search(r'\d', filename): return True
            return False

        from urllib.parse import urljoin

        # Index rows are [date | meet name | venue]. The venue column is the
        # authoritative course identity for XC and exists for 2005+; 2003-04
        # tables are two-column and carry the venue inside the meet name
        # ("Marshwood, Bonny Eagle, Portland at Scarborough").
        for row in soup.find_all('tr'):
            cols = row.find_all(['td', 'th'])
            if len(cols) < 2:
                continue
            cells = [c.get_text(' ', strip=True).replace('\xa0', ' ') for c in cols]
            # Skip the year-navigation rows ("2013", "2012", ...) that link to
            # other season indexes rather than to meets.
            if re.fullmatch(r'(19|20)\d\d', cells[1].strip()):
                continue
            date_text = cells[0].strip()
            meet_text = cells[1].strip()
            venue_text = cells[2].strip() if len(cells) > 2 else ''
            if not venue_text:
                m = re.search(r'\bat\s+([A-Z][\w.\'-]*(?:\s+[A-Z][\w.\'-]*){0,3})',
                              meet_text)
                if m:
                    venue_text = m.group(1).strip()
            for col in cols[1:]:
                for a in col.find_all('a', href=True):
                    href = a['href']
                    if is_valid_result_link(href):
                        if not href.startswith('http'):
                            href = urljoin(url, href)
                        mapping[href] = {'date': date_text or None,
                                         'meet': meet_text or None,
                                         'venue': venue_text or None}
        for a in soup.find_all('a', href=True):
            href = a['href']
            if is_valid_result_link(href):
                if not href.startswith('http'):
                    href = urljoin(url, href)
                if href not in mapping:
                    mapping[href] = {'date': None, 'meet': None, 'venue': None}
        return mapping

    def download_missing_files(self, index_url, archive_dir, synced_meets=None, curr_year=None, curr_season=None, workers=6):
        if not os.path.exists(archive_dir):
            os.makedirs(archive_dir)
        links_map = self.get_meet_links(index_url)
        saved_files = []
        mapping_changed = False
        to_fetch = []
        for link, info in links_map.items():
            if not isinstance(info, dict):   # legacy shape: bare date string
                info = {'date': info, 'meet': None, 'venue': None}
            date_str = info.get('date')
            filename = self._archive_filename(link)
            # Scope by season: generic filenames (Results-1.htm, classaboys.htm)
            # recur across years and would otherwise clobber each other.
            scoped_key = f"{curr_year}/{curr_season}/{filename}"
            if self.web_url_mapping.get(scoped_key) != link:
                self.web_url_mapping[scoped_key] = link
                mapping_changed = True
            if date_str:
                self.web_date_mapping[scoped_key] = date_str
                mapping_changed = True
            if info.get('meet') or info.get('venue'):
                self.web_meet_mapping[scoped_key] = {
                    'meet': info.get('meet'), 'venue': info.get('venue')}
                mapping_changed = True
            save_path = os.path.join(archive_dir, filename)
            meet_name = os.path.splitext(filename)[0]
            meet_key = f"{curr_year}_{curr_season}_{meet_name}"
            if synced_meets and meet_key in synced_meets:
                continue
            if not os.path.exists(save_path):
                to_fetch.append((link, save_path))

        def _fetch(job):
            link, save_path = job
            try:
                res = self._get_with_retry(link)
                with open(save_path, 'wb') as f:
                    f.write(res.content)
                return save_path
            except Exception as e:
                print(f"Failed to download {link}: {e}")
                return None

        if to_fetch:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for result in ex.map(_fetch, to_fetch):
                    if result:
                        saved_files.append(result)
        if mapping_changed:
            self.save_web_date_mapping()
            self.save_web_meet_mapping()
            self.save_web_url_mapping()
        return saved_files

    def save_web_date_mapping(self):
        mapping_path = os.path.join(os.path.dirname(__file__), 'web_date_mapping.json')
        try:
            with open(mapping_path, 'w') as f:
                json.dump(self.web_date_mapping, f, indent=4)
        except Exception as e:
            print(f"Error saving web_date_mapping: {e}")

    def parse_all_files(self, archive_dir, json_dir, force=False, workers=None):
        if not os.path.exists(json_dir):
            os.makedirs(json_dir)
        files = [f for f in os.listdir(archive_dir) if f.lower().endswith(('.htm', '.html', '.pdf'))]
        season_label = os.path.basename(archive_dir) or "Indoor"

        # Files sharing a stem (Results.htm + Results.pdf) must not overwrite
        # each other's parse output
        stem_counts = {}
        for filename in files:
            stem = os.path.splitext(filename)[0]
            stem_counts[stem] = stem_counts.get(stem, 0) + 1

        jobs = []
        for filename in files:
            input_path = os.path.join(archive_dir, filename)
            stem = os.path.splitext(filename)[0]
            if stem_counts[stem] > 1 and not filename.lower().endswith('.htm'):
                stem = stem + '_' + os.path.splitext(filename)[1].lstrip('.').lower()
            output_path = os.path.join(json_dir, stem + ".json")
            if not force and os.path.exists(output_path) and \
                    os.path.getmtime(output_path) >= os.path.getmtime(input_path):
                continue
            jobs.append((input_path, output_path, season_label))
        if not jobs:
            return 0

        if workers is None:
            workers = max(1, (os.cpu_count() or 4) - 2)
        parsed_count = 0
        total = len(jobs)
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for i, (filename, n, err) in enumerate(ex.map(_parse_one_file, jobs, chunksize=4)):
                if err:
                    print(f"Error parsing {filename}: {err}")
                else:
                    parsed_count += 1
                if (i + 1) % 100 == 0 or i == total - 1:
                    self.report_progress(f"Parsed {i+1}/{total} files", int((i + 1) / total * 100))
        return parsed_count

    def sync_json_to_store(self, json_dir, season="Indoor", year="2026", athletes=None,
                           scrape_state=None, collector=None, all_known_teams=None):
        """Gather performances for one season into `collector` (team -> [perfs]).

        When called standalone (collector=None) it also commits to the store;
        run_full_scrape passes a shared collector across all seasons and
        commits once at the end so each team file is written exactly once.
        """
        if not os.path.exists(json_dir):
            return 0
        files = [f for f in os.listdir(json_dir) if f.endswith('.json')]
        standalone = collector is None
        all_teams_data = {} if standalone else collector

        synced_meets = scrape_state.get('synced_meets', {})

        if all_known_teams is None:
            # Seed with the canonical names from TEAM_MAPPING so truncated
            # names resolve correctly even on a fresh wipe when no team files
            # exist yet (otherwise resolution depends on sync order).
            all_known_teams = set(TEAM_MAPPING.values()) | set(list_teams())

        for i, filename in enumerate(files):
            file_path = os.path.join(json_dir, filename)
            meet_name = os.path.splitext(filename)[0]
            meet_key = f"{year}_{season}_{meet_name}"
            if meet_key in synced_meets:
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                
                if isinstance(file_data, dict) and "events" in file_data:
                    parsed_events = file_data.get("events", [])
                    date = file_data.get("date")
                    venue = file_data.get("venue")
                else:
                    parsed_events = file_data if isinstance(file_data, list) else []
                    date = None
                    venue = None

                # Course identity, best source first. The season index table on
                # sub5 carries an explicit venue column, which beats anything
                # recoverable from the result file itself; the file's own venue
                # (parser- or Hy-Tek-supplied) is the second source of truth.
                # The filename stem is the last resort and names no place at
                # all for generic slugs like "Results-F1-3".
                idx_meta = {}
                for _cand in (filename, meet_name + ".htm", meet_name + ".html",
                              meet_name + ".pdf"):
                    idx_meta = self.web_meet_mapping.get(f"{year}/{season}/{_cand}") or {}
                    if idx_meta:
                        break
                course_name = (idx_meta.get('venue') or venue
                               or idx_meta.get('meet') or meet_name)

                # Date resolution hierarchy — every source is validated against
                # the season window (year/season come from the index page the
                # link was found on, which is authoritative):
                #   1. date column from the season index page (web date)
                #   2. date parsed from the file content
                #   3. date embedded in the filename
                stem = os.path.splitext(filename)[0]
                candidates = [stem + ext for ext in (".htm", ".html", ".pdf")]
                web_date_raw = None
                for cand in candidates:
                    web_date_raw = self.web_date_mapping.get(f"{year}/{season}/{cand}")
                    if web_date_raw: break
                if not web_date_raw:  # legacy unscoped keys from earlier scrapes
                    for cand in [filename] + candidates:
                        web_date_raw = self.web_date_mapping.get(cand)
                        if web_date_raw: break

                date = self.normalize_parsed_date(date)
                if date and not self.is_date_in_season(date, season, year):
                    date = None
                if web_date_raw:
                    parsed_d = self.parse_web_date(web_date_raw)
                    # a multi-day meet ("December 28/29, 2021") is dated by
                    # its own file when that names one of the days
                    if date and date in self.web_date_days(web_date_raw):
                        parsed_d = date
                    # A file whose own date is more than a few days BEFORE
                    # the index's keeps it: the index is keyed by file name
                    # ("Results1.htm" is reused across a season) and lags
                    # ("PVC meet #3 - 5/2/03" listed on 5/9). Only earlier: a
                    # file with no title date has only its Hy-Tek print
                    # stamp, which is on or after the meet.
                    if date and parsed_d and season != 'XC':
                        try:
                            from datetime import date as _d
                            if (_d.fromisoformat(parsed_d) - _d.fromisoformat(date)).days > 3:
                                parsed_d = date
                        except ValueError:
                            pass
                    if self.is_date_in_season(parsed_d, season, year):
                        date = parsed_d
                if not date:
                    date = self.date_from_filename(stem, season, year)

                # Manual fixes
                for mc in self.manual_fixes.get('meet_corrections', []):
                    if mc['meet_name_fragment'].lower() in meet_name.lower() or mc['meet_name_fragment'].lower() in filename.lower():
                        date = mc['new_date']
                        break

                if not date: date = "Unknown"
                meet_url = filename

                # Meet level context for team-name resolution: bare town names
                # mean a different school in an MS meet than an HS meet.
                low = re.sub(r'[-_.]+', ' ', f"{filename} {meet_name}".lower())
                if re.search(r'\bms\b|\bjh\b|middle school|junior high|elementary|\bmiddle\b|[a-z]ms(\b|\d)', low):
                    meet_level = 'ms'
                elif re.search(r'\bcollege\b|university|collegiate|gnac|nescac', low):
                    meet_level = 'college'
                else:
                    meet_level = 'hs'
                # The parser reads the level from the results header itself
                # ("BRUNSWICK JUNIOR HIGH XC") and grade columns; trust it over
                # the filename guess when it has one.
                if isinstance(file_data, dict) and file_data.get('meet_level') in ('ms', 'hs', 'college'):
                    meet_level = file_data['meet_level']

                for event_block in parsed_events:
                    if isinstance(event_block, dict) and "results" in event_block:
                        gender = event_block.get("gender", "")
                        event_name = event_block.get("event", "")
                        is_relay = event_block.get("is_relay", False)
                        results_list = event_block.get("results", [])
                    else:
                        raw_ev = event_block.get("event", "").strip()
                        m_g = re.match(r'^(Girls|Boys|Women|Men)\s+(.*)$', raw_ev, re.I)
                        gender = m_g.group(1).capitalize() if m_g else ''
                        gender = {'Women': 'Girls', 'Men': 'Boys'}.get(gender, gender)
                        event_name = m_g.group(2) if m_g else raw_ev
                        is_relay = "Relay" in raw_ev or "4x" in raw_ev.lower()
                        results_list = [event_block]

                    # Canonicalize: one spelling per event, corrected gender,
                    # junk/out-of-scope labels dropped (see event_canon.py)
                    canon = canonical_event(event_name, gender or 'Boys', season=season,
                                            level=meet_level)
                    if canon is None:
                        continue
                    gender, event_canon_name = canon
                    full_event = f"{gender} {event_canon_name}"
                    is_relay = is_relay or 'Relay' in event_canon_name

                    for r in results_list:
                        # Seed-type rows come from entry/heat sheets, not results
                        if r.get("type") == "Seed":
                            continue
                        athlete_name = r.get("athlete") or r.get("athlete_name") or ""
                        school = r.get("school") or r.get("team") or ""
                        mark = r.get("result") or r.get("mark") or ""
                        relay_athletes = r.get("athletes", [])
                        if is_relay:
                            if relay_athletes:
                                # Drop legs that are leaked result rows (contain times/marks)
                                clean_legs = []
                                for ra in relay_athletes:
                                    leg = self.normalize_athlete_name(ra)
                                    leg = re.sub(r'\s+(Relay|[A-D])$', '', leg).strip()
                                    if leg and not re.search(r'\d+[:.]\d+|\d{3,}', leg):
                                        clean_legs.append(leg)
                                athlete_name = ", ".join(clean_legs) if clean_legs else f"{school} Relay"
                            elif not athlete_name: athlete_name = f"{school} Relay"
                            # Reject relay records whose school field looks like "LastName, FirstName ..."
                            # — these are individual-event rows from two-column PDFs that bled into
                            # the relay section during parsing.
                            if re.match(r'^[A-Za-z][A-Za-z\'-]+,\s+[A-Za-z]', school):
                                continue

                        if not is_relay:
                            athlete_name = self.normalize_athlete_name(athlete_name)
                            # Reject leaked rows: individual athlete names never contain marks
                            if re.search(r'\d+[:.]\d+', athlete_name):
                                continue
                        if not athlete_name or not mark or mark.upper() in ["DNS", "SCR"]: continue
                        # a hand time cut at its column edge: "13:14.0h" -> "13:14."
                        mark = re.sub(r'(?<=\d)\.$', '', mark)
                        if not self.mark_is_valid_format(mark): continue
                        mark = self.repair_mark(mark, full_event)
                        if mark is None: continue

                        # Reject marks whose format contradicts the event type:
                        # time-format (M:SS.ss) in a field event, or distance-format (F-I) in a running event.
                        _ev_low = full_event.lower()
                        _is_field_ev = any(k in _ev_low for k in ('jump', 'put', 'throw', 'vault', 'discus', 'javelin'))
                        _is_track_ev = any(k in _ev_low for k in ('dash', 'run', 'hurdles', 'mile', 'relay', '4x', 'walk'))
                        _has_time_fmt = ':' in mark and '.' in mark
                        _has_dist_fmt = bool(re.match(r'^\d+-\d+', mark))
                        if _is_field_ev and _has_time_fmt and not _has_dist_fmt:
                            continue
                        if _is_track_ev and _has_dist_fmt and not _has_time_fmt:
                            continue

                        team_norm = None
                        if school:
                            # Results are filed under the school catalog: every
                            # spelling of a school (truncations, codes, mascots,
                            # M/F suffixes) lands on one team, filed under the
                            # co-op it raced as, so one runner keeps one athlete
                            # id. Strings the catalog cannot place fall back to
                            # the registry resolution below, which fuzzy-matches
                            # against the teams already stored ("WIND" ->
                            # Windsor), so it is the last resort.
                            unit = school_catalog.store_unit(
                                school, year=str(year), season=season, gender=gender,
                                meet_name=filename, grade=r.get('grade'))
                            if unit:
                                team_norm = school_catalog.store_name(unit)
                        if team_norm is None:
                            team_norm = self.normalize_team_name(school, all_teams=all_known_teams, level=meet_level)
                        if not self.team_name_is_sane(team_norm) or self.is_likely_athlete_name(team_norm): continue
                        if is_relay and athlete_name == f"{school} Relay":
                            athlete_name = f"{team_norm} Relay"
                        
                        athlete_id = slugify_athlete(athlete_name, team_norm)
                        performance_date = f"{date}T12:00:00" if date != "Unknown" else "Unknown"
                        
                        p = {
                            'athlete_name': athlete_name,
                            'athlete_id': athlete_id,
                            'event': full_event,
                            'mark': mark,
                            'grade': r.get("grade", ""),
                            'team': team_norm,
                            'date': performance_date,
                            'season': season,
                            'year': year,
                            'meet_name': meet_name,
                            'splits': r.get("splits", [])
                        }
                        if season == 'XC':
                            p['course'] = (course_name or meet_name).strip()
                        
                        team_slug = team_norm # Will be slugified in json_store
                        if team_slug not in all_teams_data:
                            all_teams_data[team_slug] = []
                            all_known_teams.add(team_norm)
                        all_teams_data[team_slug].append(p)
                
                # Mark as synced
                synced_meets[meet_key] = date if date != "Unknown" else datetime.now().strftime("%Y-%m-%d")
                
            except Exception as e:
                print(f"Error syncing {filename}: {e}")

        if standalone:
            total_performances = 0
            for team_name, perfs in all_teams_data.items():
                athletes, count = add_performances_for_team(team_name, perfs, athletes)
                total_performances += count
            return total_performances
        return 0  # collector mode: caller commits and counts

    def repair_frameset_stubs(self, seasons=None):
        """Replace Hy-Tek multi-page frameset stubs with real results.

        The downloader saves files by basename, losing subdirectories, so
        frameset children ("X_full.htm" etc., often in a subdir like pvc/)
        were never fetched. This re-resolves each stub against its season
        index link and pulls the single-page "_full.htm" export (preferred)
        or stitches the per-event pages from "_index.htm"."""
        from urllib.parse import urljoin
        base_dir = os.path.dirname(os.path.dirname(__file__))
        repaired, failed = 0, 0
        for cfg in seasons or SEASONS:
            year, season, index_url = cfg['year'], cfg['season'], cfg['url']
            archive_dir = os.path.join(base_dir, f'backend/data/sub5_archive/{year}/{season}')
            if not os.path.isdir(archive_dir):
                continue
            stubs = []
            for fn in os.listdir(archive_dir):
                if not fn.lower().endswith(('.htm', '.html')):
                    continue
                path = os.path.join(archive_dir, fn)
                if os.path.getsize(path) > 20000:
                    continue
                head = open(path, encoding='utf-8', errors='ignore').read(3000).lower()
                if '<frameset' in head:
                    stubs.append(fn)
            if not stubs:
                continue
            links_map = self.get_meet_links(index_url)
            by_base = {}
            for link in links_map:
                base = link.split('/')[-1].split('?')[0]
                if not base.lower().endswith(('.htm', '.html', '.pdf')):
                    base += '.htm'
                by_base[base] = link
            for fn in stubs:
                link = by_base.get(fn)
                if not link:
                    failed += 1
                    continue
                stem = os.path.splitext(fn)[0]
                dir_url = link.rsplit('/', 1)[0]
                content = None
                try:
                    res = self._get_with_retry(f'{dir_url}/{stem}_full.htm')
                    if res is not None and len(res.content) > 2000:
                        content = res.content
                except Exception:
                    pass
                if content is None:
                    try:
                        idx = self._get_with_retry(f'{dir_url}/{stem}_index.htm')
                        parts = []
                        for h in re.findall(r'href="([^"]+\.html?)"', idx.text, re.I):
                            if h.startswith('http') or h.startswith('#'):
                                continue
                            try:
                                child = self._get_with_retry(urljoin(dir_url + '/', h))
                                parts.append(child.text)
                            except Exception:
                                continue
                        if parts:
                            content = '\n'.join(parts).encode('utf-8', 'ignore')
                    except Exception:
                        pass
                if content is None:
                    # last resort: follow the literal frame src attributes
                    # (Excel "save as web page" exports: X_files/sheet001.htm)
                    stub_html = open(os.path.join(archive_dir, fn), encoding='utf-8', errors='ignore').read()
                    parts = []
                    for src in re.findall(r'src="([^"]+\.html?)"', stub_html, re.I):
                        if src.startswith('http') or 'tabstrip' in src.lower():
                            continue
                        try:
                            child = self._get_with_retry(urljoin(dir_url + '/', src))
                            parts.append(child.text)
                        except Exception:
                            continue
                    if parts:
                        content = '\n'.join(parts).encode('utf-8', 'ignore')
                if content:
                    with open(os.path.join(archive_dir, fn), 'wb') as f:
                        f.write(content)
                    repaired += 1
                else:
                    failed += 1
            self.report_progress(f'{year} {season}: repaired {repaired} total so far ({failed} failed)')
        self.report_progress(f'Frameset repair complete: {repaired} repaired, {failed} unrecoverable')
        return repaired, failed

    @staticmethod
    def _stored_meet_rows(season_keys):
        """(year, season) -> {meet_name: {(athlete_id, event, mark)}} for the
        meets already in the store, in the same shape the dedup compares."""
        out = {}
        chunk_keys = {f'{y}_{s}': (y, s) for y, s in season_keys}
        for fn in os.listdir(TEAMS_DIR):
            full = os.path.join(TEAMS_DIR, fn)
            if not os.path.isdir(full):
                continue
            team = canonical_team_name(fn)
            for key, chunk in _chunk_files(full):
                if key not in chunk_keys:
                    continue
                for p in enrich_rows(team, key, _load_json(os.path.join(full, chunk), [])):
                    out.setdefault(chunk_keys[key], {}).setdefault(
                        p.get('meet_name'), set()).add(
                        (p['athlete_id'], p['event'], p['mark']))
        return out

    def run_full_scrape(self, wipe=False, seasons=None, download=True, parse=True):
        """Full pipeline: download -> parse -> sync -> manifest.

        download=False / parse=False skip those stages and rebuild the store
        from the existing parsed_results JSONs (fast path for iterating on
        sync/normalization logic without re-parsing 6000 HTML files).
        """
        seasons_to_scrape = seasons if seasons is not None else SEASONS

        scrape_state = load_scrape_state()
        athletes = load_athletes()
        base_dir = os.path.dirname(os.path.dirname(__file__))
        
        if wipe:
            self.report_progress("Wiping scrape state and athletes for full re-sync...")
            scrape_state['synced_meets'] = {}
            athletes = {}
            teams_dir = os.path.join(base_dir, 'ui', 'public', 'data', 'teams')
            if os.path.exists(teams_dir):
                import shutil
                for filename in os.listdir(teams_dir):
                    full = os.path.join(teams_dir, filename)
                    if os.path.isdir(full):
                        shutil.rmtree(full)
                    elif filename.endswith(".json"):
                        os.remove(full)
                        
        total_count = 0

        # Shared across seasons: performances accumulate in memory and each
        # team file is written (and PR-recalculated) exactly once at the end.
        collector = {}
        all_known_teams = set(TEAM_MAPPING.values()) | set(list_teams())

        for config in seasons_to_scrape:
            year, season, index_url = config["year"], config["season"], config["url"]
            self.report_progress(f"Processing {season} {year}...")
            archive_dir = os.path.join(base_dir, f'backend/data/sub5_archive/{year}/{season}')
            json_dir = os.path.join(base_dir, f'backend/data/parsed_results/{year}/{season}')
            if download:
                self.download_missing_files(index_url, archive_dir, synced_meets=scrape_state['synced_meets'], curr_year=year, curr_season=season)
            if parse:
                self.parse_all_files(archive_dir, json_dir, force=wipe)
            self.sync_json_to_store(json_dir, season=season, year=year, athletes=athletes,
                                    scrape_state=scrape_state, collector=collector,
                                    all_known_teams=all_known_teams)

        # Apply manual performance corrections / injections
        self.report_progress("Applying manual performance corrections...")
        for pc in self.manual_fixes.get('performance_corrections', []):
            team_name = pc['team_name']
            athlete_name = pc['athlete_name']
            athlete_id = slugify_athlete(athlete_name, team_name)

            p = {
                'athlete_name': athlete_name,
                'athlete_id': athlete_id,
                'event': pc['event'],
                'mark': pc['mark'],
                'grade': pc.get('grade', ''),
                'team': team_name,
                'date': f"{pc['date']}T12:00:00" if pc.get('date') else "Unknown",
                'season': pc.get('season', 'Outdoor'),
                'year': pc.get('year', '2026'),
                'meet_name': pc.get('meet_name', 'Manual Correction'),
                'splits': pc.get('splits', [])
            }
            collector.setdefault(team_name, []).append(p)

        # Drop double-ingested meets: the same meet posted under two filenames
        # (Results.htm + Results-1.htm, corrected_* reposts, boys/girls copies
        # of a combined file) shares most rows — keep the larger file.
        meet_rows = {}
        for perfs in collector.values():
            for p in perfs:
                key = (p['year'], p['season'], p['meet_name'])
                meet_rows.setdefault(key, set()).add((p['athlete_id'], p['event'], p['mark']))
        by_season = {}
        for key, rows in meet_rows.items():
            if len(rows) >= 20:
                by_season.setdefault(key[:2], []).append((key, rows))
        drop_meets = set()
        # A file that contains two or more other meets is a combined
        # re-ranking (the New England qualifier list pools the Class A/B/C
        # state races), not a race: drop it and keep the races themselves.
        for pairs in by_season.values():
            for k1, r1 in pairs:
                inside = sum(1 for k2, r2 in pairs
                             if k2 != k1 and len(r2) < len(r1)
                             and len(r1 & r2) / len(r2) >= 0.6)
                if inside >= 2:
                    drop_meets.add(k1)
        # An incremental run only holds the NEW meets, so a re-post of a meet
        # already in the store (an overall .txt next to the by-section .htm it
        # duplicates) has nothing to collide with above. Compare against the
        # stored meets of the same seasons too, and keep the stored copy.
        if not wipe:
            stored = self._stored_meet_rows({k for k in by_season})
            for skey, pairs in by_season.items():
                for (k1, r1) in pairs:
                    for k2, r2 in stored.get(skey, {}).items():
                        if k2 == k1[2] or len(r2) < 20:
                            continue
                        smaller = min(len(r1), len(r2))
                        if len(r1 & r2) / smaller >= 0.6:
                            drop_meets.add(k1)
                            break
        for pairs in by_season.values():
            for i in range(len(pairs)):
                for j in range(i + 1, len(pairs)):
                    (k1, r1), (k2, r2) = pairs[i], pairs[j]
                    if k1 in drop_meets or k2 in drop_meets:
                        continue
                    smaller = min(len(r1), len(r2))
                    if smaller and len(r1 & r2) / smaller >= 0.6:
                        loser = k1 if len(r1) < len(r2) or \
                            (len(r1) == len(r2) and k1[2] < k2[2]) else k2
                        drop_meets.add(loser)
        if drop_meets:
            self.report_progress(f'Dropping {len(drop_meets)} double-ingested meets '
                                 f'(e.g. {sorted(m[2] for m in drop_meets)[:3]})')
            for team in collector:
                collector[team] = [p for p in collector[team]
                                   if (p['year'], p['season'], p['meet_name']) not in drop_meets]

        # Single commit: one load + dedup + PR recalc + write per team.
        self.report_progress(f"Committing {sum(len(v) for v in collector.values()):,} performances to {len(collector)} team files...")
        for i, (team_name, perfs) in enumerate(sorted(collector.items())):
            athletes, count = add_performances_for_team(team_name, perfs, athletes)
            total_count += count
            if (i + 1) % 50 == 0:
                self.report_progress(f"Committed {i+1}/{len(collector)} teams")

        save_scrape_state(scrape_state)
        save_athletes(athletes)
        rebuild_manifest()
        write_meet_links(self.web_url_mapping)
        # athlete identity: code layer + reviewed decisions -> one id per
        # runner; PR flags over whole careers and the athlete registry
        from backend import athlete_catalog
        self.report_progress("Building athlete catalog...")
        athlete_catalog.build(quiet=True)
        athlete_catalog.apply(quiet=True)
        self.report_progress("Scrape Complete!", 100)
        return total_count

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scrape Track & Field data from sub5.com")
    parser.add_argument('--wipe', action='store_true', help="Force a full re-scrape, clearing all existing processed JSON state.")
    parser.add_argument('--years', help="Comma-separated years to scrape (default: all seasons in SEASONS).")
    parser.add_argument('--season', choices=['Indoor', 'Outdoor', 'XC'],
                        help="Limit to one season type (default: all).")
    parser.add_argument('--resync-only', action='store_true',
                        help="Skip download and parse; wipe and rebuild the store from existing parsed_results JSONs.")
    parser.add_argument('--record-urls', action='store_true',
                        help="Read the season index pages and record each result file's source URL (no downloads).")
    parser.add_argument('--repair-framesets', action='store_true',
                        help="Re-fetch Hy-Tek frameset stub meets (X_full.htm / stitched event pages).")
    args = parser.parse_args()

    selected = SEASONS
    if args.years:
        wanted = {y.strip() for y in args.years.split(',')}
        selected = [s for s in SEASONS if s['year'] in wanted]
    if args.season:
        selected = [s for s in selected if s['season'] == args.season]

    scraper = Sub5ScraperV2()
    if args.record_urls:
        n = scraper.record_source_urls(seasons=selected)
        write_meet_links(scraper.web_url_mapping)
        print(f'{n} source URLs recorded')
    elif args.repair_framesets:
        scraper.repair_frameset_stubs(seasons=selected)
    elif args.resync_only:
        scraper.run_full_scrape(wipe=True, seasons=selected, download=False, parse=False)
    else:
        scraper.run_full_scrape(wipe=args.wipe, seasons=selected)
