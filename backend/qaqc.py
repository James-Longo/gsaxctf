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
    print('QA/QC complete.')


if __name__ == '__main__':
    run_qaqc()
