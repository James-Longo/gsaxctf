"""
qaqc.py - Data quality checks for the JSON-based track & field store.

Checks:
  1. Overall stats
  2. Season/year coverage
  3. Parser failures (archived files with empty parsed JSON output)
  4. Duplicate team slug files (same canonical name, different case slug)
  5. Athlete name anomalies (digits, full-row scrape leaks)
  6. Cross-type marks (time format in field events, distance format in running events)
  7. Duplicate is_pr flags across all team files for same athlete+event
  8. Mark plausibility (obvious outliers)
  9. Grade consistency (conflicting grades in same season)
 10. Performance ID collisions across team files
 11. Meet scoring verification (computed scores vs official Team Rankings)
"""

import json
import os
import re
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEAMS_DIR = os.path.join(BASE_DIR, 'ui', 'public', 'data', 'teams')
ATHLETES_PATH = os.path.join(BASE_DIR, 'ui', 'public', 'data', 'athletes.json')
ARCHIVE_BASE = os.path.join(BASE_DIR, 'backend', 'data', 'sub5_archive')
PARSED_BASE = os.path.join(BASE_DIR, 'backend', 'data', 'parsed_results')

BAD_MARKS = {'DQ', 'DNS', 'DNF', 'NH', 'NM', 'FOUL', 'SCR', 'ND', 'NT'}
FIELD_KEYWORDS = ['jump', 'put', 'throw', 'vault', 'discus', 'javelin', 'weight throw']
TRACK_KEYWORDS = ['dash', 'run', 'hurdles', 'mile', 'relay', '4x', 'walk']

IMPLAUSIBLE = {
    # Running: lo=world-record-ish, hi=very-slow-beginner (inclusive of disability/MS athletes)
    '100 meter dash':    (9.5,   45.0),   # secs; some disability/MS athletes run 33-40s
    '200 meter dash':    (19.0,  90.0),   # secs; slow beginner ~1:20
    '400 meter dash':    (43.0, 180.0),   # secs; slow beginner ~3 min
    '800 meter run':     (100.0, 480.0),  # secs; slow beginner ~8 min
    '1600 meter run':    (220.0, 1200.0), # secs; slow beginner ~20 min
    '3200 meter run':    (500.0, 2400.0), # secs; slow beginner ~40 min
    '55 meter dash':     (6.0,   22.0),   # secs; wheelchair/very slow beginners
    '110 meter hurdles': (12.0,  60.0),   # secs; beginner with hurdle issues
    '100 meter hurdles': (12.0,  60.0),
    '300 meter hurdles': (35.0, 150.0),
    # Field: lo=0 would cause divide-by-zero; hi=world-record-ish plus margin
    'shot put':   (12.0,  900.0),  # inches; 1ft min (~tiny frosh), ~75ft max
    'long jump':  (18.0,  362.0),  # inches; 1.5ft min, ~30ft max (world record)
    'high jump':  (18.0,  108.0),  # inches; 1.5ft min, 9ft max
    'pole vault': (18.0,  232.0),  # inches; 1.5ft min, ~19.3ft max (HS record)
    'triple jump': (36.0, 640.0),  # inches; 3ft min, ~53ft max (elite HS)
    'discus':     (36.0, 2520.0),  # inches; 3ft min, 210ft max
    'javelin':    (24.0, 3600.0),  # inches; 2ft min, 300ft max (beginner throws ok)
}

SEPARATOR = '-' * 60


def load_all_performances():
    """Load every performance from every team file. Returns (list_of_perfs, dict of fn->perfs)."""
    all_perfs = []
    by_file = {}
    if not os.path.exists(TEAMS_DIR):
        return all_perfs, by_file
    for fn in sorted(os.listdir(TEAMS_DIR)):
        if not fn.endswith('.json'):
            continue
        path = os.path.join(TEAMS_DIR, fn)
        try:
            perfs = json.load(open(path, encoding='utf-8'))
        except Exception as e:
            print(f'  [ERROR] Could not load {fn}: {e}')
            perfs = []
        by_file[fn] = perfs
        all_perfs.extend(perfs)
    return all_perfs, by_file


def parse_mark_value(mark, event_name=''):
    """Returns (numeric_value, is_distance) or (None, None)."""
    if not mark:
        return None, None
    m = str(mark).strip().upper()
    if m in BAD_MARKS or any(m.startswith(b) for b in BAD_MARKS):
        return None, None

    is_field = any(k in event_name.lower() for k in FIELD_KEYWORDS)
    has_dash = bool(re.search(r'\d-\d', m)) and ':' not in m
    has_quote = "'" in m or '"' in m

    if is_field or has_dash or has_quote:
        feet = re.match(r'^(\d+)[\'\\-]', m)
        inches = re.search(r"['\-\s](\d+(?:\.\d+)?)", m)
        total = 0.0
        if feet:
            total += int(feet.group(1)) * 12
        if inches:
            total += float(inches.group(1))
        return (total if total > 0 else None), True

    cleaned = re.sub(r'[A-Z]+$', '', m)
    parts = cleaned.split(':')
    try:
        nums = [float(p) for p in parts if p]
        if len(nums) == 1:
            val = nums[0]
        elif len(nums) == 2:
            val = nums[0] * 60 + nums[1]
        elif len(nums) == 3:
            val = nums[0] * 3600 + nums[1] * 60 + nums[2]
        else:
            return None, None
        return (val if val > 0 else None), False
    except (ValueError, IndexError):
        return None, None


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------

def check_overall_stats(all_perfs, by_file):
    print('1. OVERALL STATS')
    print(f'   Team files : {len(by_file)}')
    print(f'   Performances: {len(all_perfs):,}')
    athletes = json.load(open(ATHLETES_PATH)) if os.path.exists(ATHLETES_PATH) else []
    print(f'   Athletes   : {len(athletes):,}')
    print()


def check_season_coverage(all_perfs):
    print('2. SEASON / YEAR COVERAGE')
    counts = defaultdict(int)
    for p in all_perfs:
        counts[(p.get('year', '?'), p.get('season', '?'))] += 1
    for key in sorted(counts, reverse=True):
        print(f'   {key[0]} {key[1]}: {counts[key]:,}')
    print()


def check_parser_failures():
    """Compare archive files to parsed JSON files; flag archives with zero-result parses."""
    print('3. PARSER FAILURES (archive files with empty/missing parsed output)')
    if not os.path.exists(ARCHIVE_BASE):
        print('   [SKIP] Archive directory not found.')
        print()
        return

    empty = []
    missing = []
    total = 0
    for year in sorted(os.listdir(ARCHIVE_BASE)):
        year_path = os.path.join(ARCHIVE_BASE, year)
        if not os.path.isdir(year_path):
            continue
        for season in sorted(os.listdir(year_path)):
            season_path = os.path.join(year_path, season)
            if not os.path.isdir(season_path):
                continue
            parsed_dir = os.path.join(PARSED_BASE, year, season)
            for fn in sorted(os.listdir(season_path)):
                if not fn.lower().endswith(('.htm', '.html', '.pdf')):
                    continue
                total += 1
                stem = os.path.splitext(fn)[0]
                json_path = os.path.join(parsed_dir, stem + '.json')
                if not os.path.exists(json_path):
                    missing.append(f'{year}/{season}/{fn}')
                    continue
                try:
                    data = json.load(open(json_path, encoding='utf-8'))
                    events = data if isinstance(data, list) else data.get('events', [])
                    result_count = sum(len(ev.get('results', [])) for ev in events if isinstance(ev, dict))
                    if result_count == 0:
                        empty.append(f'{year}/{season}/{fn}')
                except Exception:
                    empty.append(f'{year}/{season}/{fn}  [parse error]')

    print(f'   Total archived files: {total}')
    if missing:
        print(f'   [ALERT] {len(missing)} archive files have no corresponding parsed JSON:')
        for f in missing[:10]:
            print(f'     - {f}')
        if len(missing) > 10:
            print(f'     ... and {len(missing)-10} more.')
    else:
        print('   [OK] All archive files have a parsed JSON.')

    if empty:
        print(f'   [WARN] {len(empty)} archive files parsed to 0 results (may be score sheets, MS meets, or format mismatch):')
        for f in empty[:15]:
            print(f'     - {f}')
        if len(empty) > 15:
            print(f'     ... and {len(empty)-15} more.')
    else:
        print('   [OK] No archive files parsed to 0 results.')
    print()


def check_duplicate_team_slugs(by_file):
    """Detect team files where the same canonical name resolves to two different slugs (e.g. case differences)."""
    print('4. DUPLICATE TEAM SLUG FILES')
    canonical = defaultdict(list)
    for fn in by_file:
        # Normalize: lowercase, collapse underscores and spaces, drop .json
        key = re.sub(r'[_\s]+', '', fn[:-5].lower())
        canonical[key].append(fn)

    dupes = {k: v for k, v in canonical.items() if len(v) > 1}
    if not dupes:
        print('   [OK] No duplicate team slug files found.')
    else:
        print(f'   [ALERT] {len(dupes)} duplicate slug pairs detected (will cause split PRs):')
        for k, fns in sorted(dupes.items()):
            counts = [len(by_file[f]) for f in fns]
            print(f'     {fns}  ({counts} records each)')
    print()


def check_athlete_name_anomalies(all_perfs):
    """Flag athlete names that contain digits (often relay-row scrape leaks)."""
    print('5. ATHLETE NAME ANOMALIES')
    digit_names = []
    relay_leaks = []
    for p in all_perfs:
        name = p.get('athlete_name', '')
        if not name:
            continue
        # Names that contain digits are suspicious (unless relay comma-list)
        if re.search(r'\d', name):
            # Relay comma-lists with team abbreviations like "55.44" are expected
            # but names like "Curry, Natalie Belfast 31.12 5 Waterville A Relay" are not
            if len(name) > 60 or (re.search(r'\d+\.\d+', name) and ',' in name and len(name) > 30):
                relay_leaks.append((name[:80], p.get('meet_name')))
            elif not re.search(r',\s*[A-Z][a-z]', name):  # not a relay list
                digit_names.append((name[:80], p.get('meet_name')))

    unique_leaks = list({x[0]: x for x in relay_leaks}.values())
    unique_digits = list({x[0]: x for x in digit_names}.values())

    if unique_leaks:
        print(f'   [ALERT] {len(unique_leaks)} relay-row scrape leaks (full result row in athlete_name):')
        for n, m in unique_leaks[:8]:
            print(f'     [{m}] {n}')
        if len(unique_leaks) > 8:
            print(f'     ... and {len(unique_leaks)-8} more.')
    else:
        print('   [OK] No relay-row scrape leaks found.')

    if unique_digits:
        print(f'   [WARN] {len(unique_digits)} athlete names contain digits:')
        for n, m in unique_digits[:8]:
            print(f'     [{m}] {n}')
        if len(unique_digits) > 8:
            print(f'     ... and {len(unique_digits)-8} more.')
    else:
        print('   [OK] No unexpected digits in athlete names.')
    print()


def check_cross_type_marks(all_perfs):
    """Flag time-format marks stored under field events (and vice versa)."""
    print('6. CROSS-TYPE MARKS (wrong format for event type)')
    time_in_field = []
    dist_in_track = []
    for p in all_perfs:
        ev = p.get('event', '').lower()
        m = str(p.get('mark', '')).strip()
        if not m or m.upper() in BAD_MARKS:
            continue
        is_field_ev = any(k in ev for k in FIELD_KEYWORDS)
        is_track_ev = any(k in ev for k in TRACK_KEYWORDS)

        has_time_fmt = ':' in m and '.' in m
        has_dist_fmt = bool(re.match(r'^\d+-\d+', m))

        if is_field_ev and has_time_fmt and not has_dist_fmt:
            time_in_field.append((p.get('athlete_name', ''), p.get('event'), m, p.get('meet_name')))
        if is_track_ev and has_dist_fmt and not has_time_fmt:
            dist_in_track.append((p.get('athlete_name', ''), p.get('event'), m, p.get('meet_name')))

    # Deduplicate by (event, mark) pattern
    by_meet_field = defaultdict(int)
    for _, ev, _, mn in time_in_field:
        by_meet_field[(mn, ev)] += 1
    by_meet_track = defaultdict(int)
    for _, ev, _, mn in dist_in_track:
        by_meet_track[(mn, ev)] += 1

    if time_in_field:
        print(f'   [ALERT] {len(time_in_field)} field event records have time-format marks (parser column error):')
        shown = set()
        for name, ev, m, mn in time_in_field[:12]:
            key = (mn, ev)
            if key not in shown:
                print(f'     [{mn}] {ev}: {m}  (x{by_meet_field[key]})')
                shown.add(key)
            if len(shown) >= 8:
                remaining = len({(mn2, ev2) for _, ev2, _, mn2 in time_in_field} - shown)
                if remaining:
                    print(f'     ... and {remaining} more meet/event combos.')
                break
    else:
        print('   [OK] No time-format marks in field events.')

    if dist_in_track:
        print(f'   [WARN] {len(dist_in_track)} track event records have distance-format marks:')
        for name, ev, m, mn in dist_in_track[:5]:
            print(f'     [{mn}] {ev}: {m}')
    else:
        print('   [OK] No distance-format marks in track events.')
    print()


def check_duplicate_is_pr(all_perfs):
    """Each (athlete_id, event) should have exactly one is_pr=True across all team files."""
    print('7. DUPLICATE is_pr FLAGS')
    pr_holders = defaultdict(list)
    for p in all_perfs:
        if p.get('is_pr'):
            pr_holders[(p['athlete_id'], p['event'])].append(
                {'mark': p['mark'], 'date': p['date'], 'team': p.get('team')}
            )
    dupes = {k: v for k, v in pr_holders.items() if len(v) > 1}
    if not dupes:
        print('   [OK] No duplicate is_pr flags found.')
    else:
        print(f'   [ALERT] {len(dupes)} athlete+event pairs have multiple is_pr=True records:')
        print('   (Usually caused by duplicate team slug files)')
        for (aid, ev), records in list(dupes.items())[:8]:
            marks = ', '.join(r['mark'] for r in records)
            print(f'     {aid[:50]}  |  {ev}  |  marks: {marks}')
        if len(dupes) > 8:
            print(f'     ... and {len(dupes)-8} more.')
    print()


def check_mark_plausibility(all_perfs):
    """Flag marks that are outside realistic ranges for their event."""
    print('8. MARK PLAUSIBILITY (obvious outliers)')
    flags = []
    for p in all_perfs:
        ev = p.get('event', '').lower()
        mark = p.get('mark', '')
        val, is_dist = parse_mark_value(mark, ev)
        if val is None:
            continue
        for ev_key, (lo, hi) in IMPLAUSIBLE.items():
            if ev_key in ev:
                if val < lo or val > hi:
                    flags.append((p.get('athlete_name'), p.get('event'), mark, val, p.get('meet_name')))
                break

    if not flags:
        print('   [OK] All sampled marks are within plausible ranges.')
    else:
        print(f'   [WARN] {len(flags)} marks outside plausible ranges:')
        for name, ev, mark, val, mn in flags[:15]:
            print(f'     [{mn}] {name}  {ev}: {mark}  (parsed={val:.1f})')
        if len(flags) > 15:
            print(f'     ... and {len(flags)-15} more.')
    print()


def check_grade_consistency(all_perfs):
    """Flag athletes who have two different grades recorded in the same season+year."""
    print('9. GRADE CONSISTENCY')
    grades_seen = defaultdict(set)
    for p in all_perfs:
        g = p.get('grade', '')
        if not g:
            continue
        key = (p.get('athlete_id'), p.get('year'), p.get('season'))
        grades_seen[key].add(g)

    conflicts = {k: v for k, v in grades_seen.items() if len(v) > 1}
    missing_total = sum(1 for p in all_perfs if not p.get('grade'))

    if conflicts:
        print(f'   [ALERT] {len(conflicts)} athletes have conflicting grades in the same season:')
        for (aid, yr, ssn), gs in list(conflicts.items())[:8]:
            print(f'     {aid[:50]}  {yr} {ssn}: grades={gs}')
        if len(conflicts) > 8:
            print(f'     ... and {len(conflicts)-8} more.')
    else:
        print('   [OK] No conflicting grades within a season.')
    total = len(all_perfs)
    pct = missing_total / total * 100 if total else 0
    print(f'   [INFO] {missing_total:,} / {total:,} ({pct:.1f}%) performances have no grade recorded.')
    print()


def check_perf_id_collisions(by_file):
    """Verify no performance ID appears in more than one team file."""
    print('10. PERFORMANCE ID COLLISIONS (cross-team)')
    id_to_files = defaultdict(list)
    for fn, perfs in by_file.items():
        for p in perfs:
            pid = p.get('id')
            if pid:
                id_to_files[pid].append(fn)
    collisions = {k: v for k, v in id_to_files.items() if len(set(v)) > 1}
    if not collisions:
        print('   [OK] No performance ID collisions across team files.')
    else:
        print(f'   [ALERT] {len(collisions)} performance IDs appear in multiple team files:')
        for pid, fns in list(collisions.items())[:8]:
            print(f'     {pid}: {fns}')
        if len(collisions) > 8:
            print(f'     ... and {len(collisions)-8} more.')
    print()


# ---------------------------------------------------------------------------
# 11. Meet Scoring Verification
# ---------------------------------------------------------------------------

# Standard HY-TEK scoring table (places 1-6)
SCORING_TABLE = {0: 10, 1: 8, 2: 6, 3: 4, 4: 2, 5: 1}

# Lazy-loaded by _ensure_team_mapping() inside check_meet_scoring(),
# after sys.path is configured.
TEAM_MAPPING = {}
KNOWN_TEAMS_MAP = {}

# Cache for normalized school names (cleared when TEAM_MAPPING is loaded)
_school_cache = {}


def _ensure_team_mapping():
    """Lazily load TEAM_MAPPING from scraper_v2 and KNOWN_TEAMS_MAP from database."""
    global TEAM_MAPPING, KNOWN_TEAMS_MAP
    if TEAM_MAPPING and KNOWN_TEAMS_MAP:
        return

    # Load KNOWN_TEAMS_MAP from JSON store database
    try:
        from json_store import list_teams
        KNOWN_TEAMS_MAP = {t.lower().strip(): t for t in list_teams()}
    except Exception as e:
        print(f"DEBUG: Failed to load KNOWN_TEAMS_MAP: {e}")

    # scraper_v2 uses "from backend.parser import ..." which needs the
    # project root on sys.path.  Ensure both project root and backend/
    # are available.
    import sys as _sys
    backend_dir = os.path.join(BASE_DIR, 'backend')
    for p in (BASE_DIR, backend_dir):
        if p not in _sys.path:
            _sys.path.insert(0, p)
    for mod_name in ('scraper_v2', 'backend.scraper_v2'):
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            if hasattr(mod, 'TEAM_MAPPING'):
                TEAM_MAPPING = mod.TEAM_MAPPING
                _school_cache.clear()
                return
        except Exception as e:
            print(f"DEBUG: Failed to import {mod_name}: {e}")
            import traceback
            traceback.print_exc()


def _normalize_school(name):
    """Resolve an abbreviated school name to its canonical form via TEAM_MAPPING or KNOWN_TEAMS_MAP.

    Uses a prioritized search:
      1. Exact case-insensitive match in TEAM_MAPPING.
      2. Forward startswith match in TEAM_MAPPING (input starts with key) - longest key wins.
      3. Backward startswith match in TEAM_MAPPING (key starts with input) - shortest key wins.
      4. Fallback: prefix match in KNOWN_TEAMS_MAP (canonical starts with input) prioritized by word boundary.
    """
    if not name:
        return name
    if name in _school_cache:
        return _school_cache[name]

    # Pre-process comma-split (e.g. "Scarborough,ME, ME" -> "Scarborough")
    if ',' in name:
        name_clean = name.split(',')[0]
    else:
        name_clean = name

    stripped = name_clean.strip()
    # Normalize dashes to spaces (e.g. "Gray-New" -> "Gray New")
    stripped_lower = stripped.lower().replace('-', ' ')

    # 1. Exact case-insensitive match
    for key, val in TEAM_MAPPING.items():
        if stripped_lower == key.lower().replace('-', ' '):
            _school_cache[name] = val
            return val

    # 2. Forward matches (input starts with key) -> longest key wins
    best_val = None
    best_key_len = 0
    for key, val in TEAM_MAPPING.items():
        key_lower = key.lower().replace('-', ' ')
        if stripped_lower.startswith(key_lower):
            if len(key) > best_key_len:
                best_key_len = len(key)
                best_val = val

    # 3. Backward matches (key starts with input) -> shortest key wins
    if not best_val:
        best_key_len = float('inf')
        for key, val in TEAM_MAPPING.items():
            key_lower = key.lower().replace('-', ' ')
            if key_lower.startswith(stripped_lower):
                if len(key) < best_key_len:
                    best_key_len = len(key)
                    best_val = val

    # 4. Fallback: check prefix match in KNOWN_TEAMS_MAP
    if not best_val and KNOWN_TEAMS_MAP:
        candidates = []
        for known_lower, known_canonical in KNOWN_TEAMS_MAP.items():
            known_clean = known_lower.replace('-', ' ')
            if known_clean.startswith(stripped_lower):
                is_word_boundary = (len(known_clean) == len(stripped_lower) or 
                                     not known_clean[len(stripped_lower)].isalnum())
                diff = abs(len(known_clean) - len(stripped_lower))
                candidates.append((is_word_boundary, diff, known_canonical))
        if candidates:
            # Sort by is_word_boundary (True first), then by smallest diff
            candidates.sort(key=lambda x: (not x[0], x[1]))
            best_val = candidates[0][2]

    result = best_val if best_val else stripped
    _school_cache[name] = result
    return result


def _fuzzy_team_match(abbrev, full_candidates):
    """Match a (possibly truncated) team name from rankings to our scored schools.

    HY-TEK truncates team names in the rankings section (e.g. "Medomak Valley
    High Schoo") so we use startswith matching.  Returns the best matching
    canonical name from *full_candidates*, or the original *abbrev* if no
    match is found.
    """
    # First, try to normalize the ranking name through TEAM_MAPPING
    normalized = _normalize_school(abbrev)
    if normalized in full_candidates:
        return normalized

    abbrev_lower = abbrev.lower().strip()
    norm_lower = normalized.lower().strip()

    # Exact match
    for c in full_candidates:
        if c.lower() == abbrev_lower or c.lower() == norm_lower:
            return c

    # Startswith match (either direction — ranking name may be truncated,
    # or our canonical name may be a prefix of the ranking name)
    best = None
    best_len = 0
    for c in full_candidates:
        c_lower = c.lower()
        for needle in (abbrev_lower, norm_lower):
            if c_lower.startswith(needle) and len(needle) > best_len:
                best = c
                best_len = len(needle)
            if needle.startswith(c_lower) and len(c_lower) > best_len:
                best = c
                best_len = len(c_lower)
    return best or abbrev


def _score_meet_from_parsed(parsed_data, ind_table=None, relay_table=None):
    """Score a meet from its parsed event results.

    Uses the specified individual and relay scoring tables (defaulting to standard 10-8-6-4-2-1).
    Returns a dict of {gender: {school: total_points}}.

    School names are normalized through TEAM_MAPPING before scoring so that
    abbreviated names (individual events) and full names (relay events)
    resolve to the same canonical team.

    Each event's results are sorted by parsed mark, then points are
    awarded to the top scorable finishers (max 3 per team for
    individual events, max 1 per team for relays).  Ties are averaged.
    """
    if ind_table is None:
        ind_table = SCORING_TABLE
    if relay_table is None:
        relay_table = SCORING_TABLE

    events = parsed_data.get('events', [])
    scores = defaultdict(lambda: defaultdict(float))  # gender -> school -> points

    for ev_block in events:
        gender = ev_block.get('gender', '')
        event_name = ev_block.get('event', '')
        is_relay = ev_block.get('is_relay', False)
        results = ev_block.get('results', [])

        table = relay_table if is_relay else ind_table

        # Build (mark_value, school) list with normalized school names
        marks = []
        for r in results:
            school_raw = r.get('school', '')
            mark_str = r.get('result', '')
            if not mark_str or not school_raw:
                continue
            if mark_str.upper() in BAD_MARKS:
                continue
            val, _ = parse_mark_value(mark_str, event_name)
            if val is None:
                continue
            school = _normalize_school(school_raw)
            marks.append((val, school))

        if not marks:
            continue

        # Determine sort direction: lower is better for track, higher for field
        ev_lower = event_name.lower()
        is_time = any(k in ev_lower for k in TRACK_KEYWORDS)
        marks.sort(key=lambda x: x[0], reverse=not is_time)

        # Award points with tie-averaging and per-team limits
        scoring_limit = 1 if is_relay else 3
        team_counts = defaultdict(int)
        scoring_idx = 0
        i = 0
        while i < len(marks) and scoring_idx < len(table):
            # Collect tied group
            j = i
            while j < len(marks) and marks[j][0] == marks[i][0]:
                j += 1
            tied = marks[i:j]

            # Filter to scorable entries (under per-team limit)
            scorable = [m for m in tied if team_counts[m[1]] < scoring_limit]
            if not scorable:
                i = j
                continue

            # Average tie points
            num_to_award = min(len(scorable), len(table) - scoring_idx)
            total_pts = sum(table.get(scoring_idx + k, 0) for k in range(num_to_award))
            avg_pts = total_pts / len(scorable)

            for _, school in scorable:
                scores[gender][school] += avg_pts
                team_counts[school] += 1
            scoring_idx += num_to_award
            i = j

    return scores


def check_meet_scoring():
    """Compare our computed scoring against official Team Rankings.

    For each archive file that has a Team Rankings section, re-parse the
    file, score it from our parsed results, and compare against the official
    totals.  Discrepancies indicate parsing issues.
    """
    print('11. MEET SCORING VERIFICATION')
    if not os.path.exists(ARCHIVE_BASE):
        print('   [SKIP] Archive directory not found.')
        print()
        return

    # Lazy imports — sys.path must be set before importing backend modules
    import sys
    sys.path.insert(0, os.path.join(BASE_DIR, 'backend'))
    from parser import Sub5ColumnParser
    from json_store import list_teams
    _ensure_team_mapping()
    _school_cache.clear()

    # Load known canonical team names in lowercase
    known_teams = set(t.lower().strip() for t in list_teams())

    total_meets = 0
    meets_with_rankings = 0
    exact_matches = 0
    mismatches = []
    no_ranking_files = 0

    # Define candidate scoring configurations to fit
    configs = [
        ("standard_10", {0: 10, 1: 8, 2: 6, 3: 4, 4: 2, 5: 1}, {0: 10, 1: 8, 2: 6, 3: 4, 4: 2, 5: 1}),
        ("standard_8", {0: 8, 1: 6, 2: 4, 3: 2, 4: 1}, {0: 8, 1: 6, 2: 4, 3: 2, 4: 1}),
        ("standard_8_6pt", {0: 8, 1: 6, 2: 4, 3: 3, 4: 2, 5: 1}, {0: 8, 1: 6, 2: 4, 3: 3, 4: 2, 5: 1}),
        ("standard_6", {0: 6, 1: 4, 2: 3, 3: 2, 4: 1}, {0: 6, 1: 4, 2: 3, 3: 2, 4: 1}),
        ("dual_tri_5_3_1", {0: 5, 1: 3, 2: 1}, {0: 5}),
        ("tri_quad_5_3_2_1", {0: 5, 1: 3, 2: 2, 3: 1}, {0: 5, 1: 3}),
        ("tri_5_3_2_1_rel_5", {0: 5, 1: 3, 2: 2, 3: 1}, {0: 5}),
        ("large_8_places", {0: 10, 1: 8, 2: 6, 3: 5, 4: 4, 5: 3, 6: 2, 7: 1}, {0: 10, 1: 8, 2: 6, 3: 5, 4: 4, 5: 3, 6: 2, 7: 1}),
    ]

    for year in sorted(os.listdir(ARCHIVE_BASE)):
        year_path = os.path.join(ARCHIVE_BASE, year)
        if not os.path.isdir(year_path):
            continue
        for season in sorted(os.listdir(year_path)):
            season_path = os.path.join(year_path, season)
            if not os.path.isdir(season_path):
                continue
            for fn in sorted(os.listdir(season_path)):
                if not fn.lower().endswith(('.htm', '.html')):
                    continue
                total_meets += 1
                filepath = os.path.join(season_path, fn)

                try:
                    p = Sub5ColumnParser(filepath)
                    parsed = p.parse()
                except Exception as e:
                    continue

                rankings = parsed.get('team_rankings', [])
                if not rankings:
                    no_ranking_files += 1
                    continue

                meets_with_rankings += 1

                # Precompute scores under each configuration
                computed_by_config = {}
                for name, ind_t, rel_t in configs:
                    computed_by_config[name] = _score_meet_from_parsed(parsed, ind_t, rel_t)

                meet_label = f'{year}/{season}/{fn}'
                meet_ok = True

                for block in rankings:
                    gender = block['gender']
                    official_teams = block.get('teams', [])
                    if not official_teams:
                        continue

                    # Select the configuration with the minimum sum of absolute errors for this gender
                    best_name = None
                    best_score_diff = float('inf')
                    best_scores = {}

                    for name, _, _ in configs:
                        our_scores = computed_by_config[name].get(gender, {})
                        all_our_schools = list(our_scores.keys())

                        total_abs_diff = 0.0
                        for entry in official_teams:
                            official_name = entry['team']
                            official_score = entry['score']
                            matched = _fuzzy_team_match(official_name, all_our_schools)
                            our_score = our_scores.get(matched, 0.0)
                            total_abs_diff += abs(our_score - official_score)

                        if total_abs_diff < best_score_diff:
                            best_score_diff = total_abs_diff
                            best_name = name
                            best_scores = our_scores

                    # Now perform the actual comparison using the best configuration's scores
                    all_our_schools = list(best_scores.keys())
                    for entry in official_teams:
                        official_name = entry['team']
                        official_score = entry['score']

                        matched = _fuzzy_team_match(official_name, all_our_schools)
                        our_score = best_scores.get(matched, 0.0)

                        if abs(our_score - official_score) > 0.5:
                            meet_ok = False
                            # A team is unmapped if its matched canonical name is not in our known teams database
                            is_unmapped = (matched.lower().strip() not in known_teams)
                            mismatches.append({
                                'meet': meet_label,
                                'gender': gender,
                                'team': official_name,
                                'official': official_score,
                                'computed': our_score,
                                'matched_as': matched if matched != official_name else None,
                                'delta': our_score - official_score,
                                'unmapped': is_unmapped,
                                'scoring_system': best_name
                            })

                if meet_ok:
                    exact_matches += 1

    print(f'   Total archive files scanned: {total_meets}')
    print(f'   Files with Team Rankings: {meets_with_rankings}')
    print(f'   Files without rankings: {no_ranking_files}')
    print(f'   Exact scoring matches: {exact_matches} / {meets_with_rankings}')

    if mismatches:
        unmapped = [m for m in mismatches if m['unmapped']]
        genuine = [m for m in mismatches if not m['unmapped']]

        # Summarize unmapped teams
        unmapped_teams = set(m['team'] for m in unmapped)
        unmapped_meets = set(m['meet'] for m in unmapped)
        if unmapped:
            print(f'   [INFO] {len(unmapped_teams)} unmapped team names across {len(unmapped_meets)} meets '
                  f'(not in TEAM_MAPPING, add them to resolve):')
            # Show unique unmapped team names
            for t in sorted(unmapped_teams)[:15]:
                print(f'     - {t}')
            if len(unmapped_teams) > 15:
                print(f'     ... and {len(unmapped_teams) - 15} more.')

        # Summarize genuine scoring mismatches
        meet_mismatch_counts = defaultdict(int)
        for m in genuine:
            meet_mismatch_counts[m['meet']] += 1

        meets_with_issues = len(meet_mismatch_counts)
        total_genuine = len(genuine)

        if genuine:
            print(f'   [ALERT] {meets_with_issues} meets have genuine scoring discrepancies '
                  f'({total_genuine} team-level mismatches):')

            # Show worst offenders (largest absolute delta first)
            genuine.sort(key=lambda x: abs(x['delta']), reverse=True)
            shown = set()
            for m in genuine:
                if len(shown) >= 20:
                    break
                key = (m['meet'], m['gender'], m['team'])
                if key in shown:
                    continue
                shown.add(key)
                match_note = f" (matched: {m['matched_as']})" if m['matched_as'] else ""
                print(f"     [{m['meet']}] {m['gender']} {m['team']}{match_note}: "
                      f"official={m['official']:.0f}  computed={m['computed']:.0f}  "
                      f"Δ={m['delta']:+.0f} (fit: {m['scoring_system']})")
            if total_genuine > 20:
                print(f'     ... and {total_genuine - 20} more.')
        else:
            print('   [OK] No genuine scoring mismatches (all discrepancies are from unmapped team names).')
    else:
        print('   [OK] All computed scores match official rankings.')
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_qaqc():
    print('=== Track & Field JSON Store QA/QC Report ===')
    print()

    all_perfs, by_file = load_all_performances()

    check_overall_stats(all_perfs, by_file)
    print(SEPARATOR)
    check_season_coverage(all_perfs)
    print(SEPARATOR)
    check_parser_failures()
    print(SEPARATOR)
    check_duplicate_team_slugs(by_file)
    print(SEPARATOR)
    check_athlete_name_anomalies(all_perfs)
    print(SEPARATOR)
    check_cross_type_marks(all_perfs)
    print(SEPARATOR)
    check_duplicate_is_pr(all_perfs)
    print(SEPARATOR)
    check_mark_plausibility(all_perfs)
    print(SEPARATOR)
    check_grade_consistency(all_perfs)
    print(SEPARATOR)
    check_perf_id_collisions(by_file)
    print(SEPARATOR)
    check_meet_scoring()
    print(SEPARATOR)
    print('QA/QC complete.')


if __name__ == '__main__':
    run_qaqc()
