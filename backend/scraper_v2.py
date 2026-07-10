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
    TEAMS_DIR, SCRAPE_STATE_PATH
)
from backend.event_canon import canonical_event

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
    # Cross country: legacy FrontPage tree 2003-2013, WP pages 2015-2025
    [{"year": f"20{n:02d}", "season": "XC",
      "url": (f"https://sub5.com/wp-content/xcresults/results{n:02d}/results{n:02d}.htm"
              if n >= 11 else
              f"https://sub5.com/wp-content/xcresults/results{n:02d}/results.htm")}
     for n in range(3, 14)] +
    [{"year": str(y), "season": "XC",
      "url": f"https://sub5.com/youth-pages/cross-country/{y}-xc-results/"}
     for y in range(2015, 2026)]
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

        # Retry chain: the detector's choice, then the robust column parser,
        # then the loose-list parser for hand-typed / collapsed-PDF formats.
        # First parser to produce results wins.
        from backend.parsers.column import ColumnStrategyParser
        from backend.parsers.looselist import LooseListParser
        from backend.parsers.placegrid import PlaceGridParser
        parser_instance = _WORKER_DETECTOR.get_parser(text, filename)
        chain = [parser_instance]
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
        chain.append(PlaceGridParser(_WORKER_DETECTOR.scraper))
        chain.append(ParagraphNewsParser(_WORKER_DETECTOR.scraper))
        chain.append(AgateParser(_WORKER_DETECTOR.scraper))
        chain.append(MangledStreamParser(_WORKER_DETECTOR.scraper))
        chain.append(VerticalTokensParser(_WORKER_DETECTOR.scraper))
        from backend.parsers.pipegrid import PipeGridParser
        chain.append(PipeGridParser(_WORKER_DETECTOR.scraper))
        from backend.parsers.xcsheet import XCDualSheetParser
        chain.append(XCDualSheetParser(_WORKER_DETECTOR.scraper))

        # Accept the first parser yielding a real result set (>=5 rows);
        # otherwise keep whichever produced the most.
        def _run_chain(txt, strict=False):
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
                if n >= 5:
                    return candidate, n
                if n > best_n:
                    best, best_n = candidate, n
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

        data_to_save = results
        if isinstance(results, list) and results and 'event' in results[0]:
            data_to_save = {'events': results, 'date': results[0].get('date')} if 'date' in results[0] else results
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=4, ensure_ascii=False)
        return (filename, _count(results), None)
    except Exception as e:
        return (filename, 0, str(e))


class Sub5ScraperV2:
    def __init__(self, progress_callback=None):
        self.headers = {'User-Agent': 'Mozilla/5.0'}
        self.manual_fixes = self.load_manual_fixes()
        self.web_date_mapping = self.load_web_date_mapping()
        self.team_registry = self.load_team_registry()
        self.progress_callback = progress_callback
        self.session = requests.Session()
        self.session.headers.update(self.headers)

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

    MARK_STATUS_CODES = {"DQ", "NH", "FOUL", "NM", "DNS", "DNF", "SCR", "ND", "NT"}

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

    def _get_with_retry(self, url, max_retries=3):
        for i in range(max_retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                # 4xx is permanent (dead legacy links) — retrying wastes ~7s each
                if e.response is not None and 400 <= e.response.status_code < 500:
                    raise
                if i == max_retries - 1:
                    print(f"Failed to fetch {url} after {max_retries} attempts: {e}")
                    raise
                import time
                time.sleep(2 ** i)
            except Exception as e:
                if i == max_retries - 1:
                    print(f"Failed to fetch {url} after {max_retries} attempts: {e}")
                    raise
                import time
                time.sleep(2 ** i)
        return None

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
            except:
                pass
        return {}

    def parse_web_date(self, date_str):
        if not date_str: return None
        # Multi-day meets: "June 3-4, 2005" / "June 3 & 10, 2006" -> first day
        date_str = re.sub(r'(\d{1,2})\s*[-&]\s*\d{1,2}', r'\1', date_str)
        try:
            dt = datetime.strptime(date_str, "%B %d, %Y")
            return dt.strftime("%Y-%m-%d")
        except:
            try:
                dt = datetime.strptime(date_str, "%b %d, %Y")
                return dt.strftime("%Y-%m-%d")
            except:
                return None

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
            if not (h.endswith('.htm') or h.endswith('.html') or h.endswith('.pdf')): return False
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

        for row in soup.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) >= 2:
                date_text = cols[0].get_text(strip=True)
                for col in cols[1:]:
                    for a in col.find_all('a', href=True):
                        href = a['href']
                        if is_valid_result_link(href):
                            if not href.startswith('http'):
                                from urllib.parse import urljoin
                                href = urljoin(url, href)
                            mapping[href] = date_text
        for a in soup.find_all('a', href=True):
            href = a['href']
            if is_valid_result_link(href):
                if href not in mapping:
                    if not href.startswith('http'):
                        from urllib.parse import urljoin
                        href = urljoin(url, href)
                    mapping[href] = None
        return mapping

    def download_missing_files(self, index_url, archive_dir, synced_meets=None, curr_year=None, curr_season=None, workers=6):
        if not os.path.exists(archive_dir):
            os.makedirs(archive_dir)
        links_map = self.get_meet_links(index_url)
        saved_files = []
        mapping_changed = False
        to_fetch = []
        for link, date_str in links_map.items():
            filename = link.split('/')[-1]
            if '?' in filename: filename = filename.split('?')[0]
            # Preserve .pdf extension; only append .htm for non-typed links
            if not filename.lower().endswith(('.htm', '.html', '.pdf')):
                filename += ".htm"
            if date_str:
                # Scope by season: generic filenames (Results-1.htm, classaboys.htm)
                # recur across years and would otherwise clobber each other.
                self.web_date_mapping[f"{curr_year}/{curr_season}/{filename}"] = date_str
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
                    canon = canonical_event(event_name, gender or 'Boys', season=season)
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
                            p['course'] = (venue or meet_name).strip()
                        
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
        self.report_progress("Scrape Complete!", 100)
        return total_count

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scrape Track & Field data from sub5.com")
    parser.add_argument('--wipe', action='store_true', help="Force a full re-scrape, clearing all existing processed JSON state.")
    parser.add_argument('--years', help="Comma-separated years to scrape (default: all seasons in SEASONS).")
    parser.add_argument('--resync-only', action='store_true',
                        help="Skip download and parse; wipe and rebuild the store from existing parsed_results JSONs.")
    parser.add_argument('--repair-framesets', action='store_true',
                        help="Re-fetch Hy-Tek frameset stub meets (X_full.htm / stitched event pages).")
    args = parser.parse_args()

    selected = SEASONS
    if args.years:
        wanted = {y.strip() for y in args.years.split(',')}
        selected = [s for s in SEASONS if s['year'] in wanted]

    scraper = Sub5ScraperV2()
    if args.repair_framesets:
        scraper.repair_frameset_stubs(seasons=selected)
    elif args.resync_only:
        scraper.run_full_scrape(wipe=True, seasons=selected, download=False, parse=False)
    else:
        scraper.run_full_scrape(wipe=args.wipe, seasons=selected)
