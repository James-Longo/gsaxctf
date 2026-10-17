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
 16. Event sections whose median mark belongs to another event; unreadable times
"""

import json
import os
import glob
import re
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEAMS_DIR = os.path.join(BASE_DIR, 'ui', 'public', 'data', 'teams')
ATHLETES_PATH = os.path.join(BASE_DIR, 'ui', 'public', 'data', 'athletes.json.gz')
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
    """Load every performance from every team (chunked dirs or legacy flat
    files). Returns (list_of_perfs, dict of team_key->perfs)."""
    all_perfs = []
    by_file = {}
    if not os.path.exists(TEAMS_DIR):
        return all_perfs, by_file
    import sys as _sys
    _sys.path.insert(0, os.path.join(BASE_DIR, 'backend'))
    from json_store import enrich_rows, canonical_team_name
    for fn in sorted(os.listdir(TEAMS_DIR)):
        path = os.path.join(TEAMS_DIR, fn)
        perfs = []
        try:
            if os.path.isdir(path):
                team_name = canonical_team_name(fn)
                from json_store import _chunk_files, _load_json
                for key, chunk in _chunk_files(path):
                    rows = _load_json(os.path.join(path, chunk), [])
                    perfs.extend(enrich_rows(team_name, key, rows))
                by_file[fn + '.json'] = perfs
            elif fn.endswith('.json'):
                perfs = json.load(open(path, encoding='utf-8'))
                by_file[fn] = perfs
            else:
                continue
        except Exception as e:
            print(f'  [ERROR] Could not load {fn}: {e}')
            by_file.setdefault(fn if fn.endswith(".json") else fn + '.json', [])
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
    import gzip as _gz
    athletes = json.load(_gz.open(ATHLETES_PATH, 'rt')) if os.path.exists(ATHLETES_PATH) else []
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


def count_parsed_results(data):
    """Count result rows in a parsed-meet JSON, handling BOTH shapes:
    nested ({'events': [{'results': [...]}, ...]}) and flat
    ({'events': [row, row, ...]} from the HyTek line parsers)."""
    evs = data.get('events', data) if isinstance(data, dict) else data
    if not isinstance(evs, list):
        return 0
    n = 0
    for e in evs:
        if not isinstance(e, dict):
            continue
        if 'results' in e:
            n += len(e.get('results') or [])
        elif 'athlete_name' in e or 'mark' in e:
            n += 1
    return n


def classify_unparsed_file(path):
    """Heuristically classify WHY an archive file parsed to zero results.

    Categories:
      frameset      - frameset wrapper page, real results live in the frame src
      html-table    - results in an HTML table grid (e.g. old SMAA format)
      agate         - newspaper-style one-liner summaries ("100:1. Biggs (MV) 13.39;")
      paragraph     - comma-separated prose results ("1, Greely High School 'A' 9:59.23.")
      score-sheet   - team scores only, no individual results
      nav/index     - navigation or schedule page, no results at all
      tiny          - trivially small file (broken download / placeholder)
      pdf           - PDF that produced no results
      unknown       - none of the above; needs a human look
    """
    try:
        if path.lower().endswith('.pdf'):
            return 'pdf'
        raw = open(path, encoding='utf-8', errors='ignore').read()
    except Exception:
        return 'unreadable'
    low = raw.lower()
    if '<frameset' in low:
        return 'frameset'
    if 'http-equiv="refresh"' in low:
        return 'redirect'
    # score stubs are usually small — check content before size
    if 'team rankings' in low or 'team scores' in low or \
            re.search(r'scores?', os.path.basename(path), re.I):
        return 'score-sheet'
    if len(raw) < 1500:
        return 'tiny'
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw, 'html.parser')
        pres = soup.find_all('pre')
        txt = "\n".join(p.get_text() for p in pres) if pres else soup.get_text(separator='\n')
    except Exception:
        return 'unreadable'
    if re.search(r'\b\d+:\s*1\.\s+\S+.*?\([A-Za-z]{1,4}\)\s+[\d:.]+', txt) or \
       re.search(r'(jump|put|vault|discus|javelin)\s*:\s*1\.\s', txt, re.I):
        return 'agate'
    if re.search(r'^\s*\d+,\s+\w+.*?\d[\d:.]+[QqJj]?\.\s', txt, re.M):
        return 'paragraph'
    if soup.find('table') and len(soup.find_all('tr')) > 15:
        return 'html-table'
    event_kw = re.search(r'(meter|mile|hurdle|relay|jump|vault|shot put|discus|javelin)', txt, re.I)
    mark_kw = re.search(r'\d+[:.]\d\d', txt)
    if not event_kw or not mark_kw:
        if re.search(r'\bscore', txt, re.I):
            return 'score-sheet'
        return 'nav/index'
    return 'unknown'


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
                    result_count = count_parsed_results(data)
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
        # Classify each zero-result file by probable cause so the list is actionable
        by_cat = defaultdict(list)
        for f in empty:
            rel = f.split('  ')[0]
            path = os.path.join(ARCHIVE_BASE, rel)
            by_cat[classify_unparsed_file(path)].append(rel)
        pct = len(empty) / total * 100 if total else 0
        print(f'   [WARN] {len(empty)} / {total} ({pct:.1f}%) archive files parsed to 0 results, by cause:')
        for cat, files in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
            print(f'     {cat:12s}: {len(files)}')
            for f in files[:4]:
                print(f'        - {f}')
            if len(files) > 4:
                print(f'        ... and {len(files)-4} more.')
    else:
        print('   [OK] No archive files parsed to 0 results.')
    print()


def check_season_pipeline_coverage(all_perfs):
    """Per-season funnel: archived files -> nonempty parses -> synced performances.

    A season with many archived files but few synced performances points at a
    parsing or syncing problem for that era's format.
    """
    print('3b. SEASON PIPELINE COVERAGE (files -> parsed -> synced)')
    perf_counts = defaultdict(int)
    for p in all_perfs:
        perf_counts[(str(p.get('year', '?')), p.get('season', '?'))] += 1

    rows = []
    for year in sorted(os.listdir(ARCHIVE_BASE)):
        ypath = os.path.join(ARCHIVE_BASE, year)
        if not os.path.isdir(ypath):
            continue
        for season in sorted(os.listdir(ypath)):
            spath = os.path.join(ypath, season)
            if not os.path.isdir(spath):
                continue
            files = [f for f in os.listdir(spath) if f.lower().endswith(('.htm', '.html', '.pdf'))]
            parsed_dir = os.path.join(PARSED_BASE, year, season)
            nonempty = 0
            for fn in files:
                jp = os.path.join(parsed_dir, os.path.splitext(fn)[0] + '.json')
                try:
                    data = json.load(open(jp, encoding='utf-8'))
                    if count_parsed_results(data) > 0:
                        nonempty += 1
                except Exception:
                    pass
            rows.append((year, season, len(files), nonempty, perf_counts.get((year, season), 0)))

    print(f'   {"Season":16s} {"files":>6s} {"parsed":>7s} {"perfs":>8s}')
    for year, season, nfiles, nparsed, nperfs in rows:
        flag = ''
        if nfiles and nparsed / nfiles < 0.5:
            flag = '  <- low parse rate'
        elif nparsed and nperfs == 0:
            flag = '  <- parsed but nothing synced'
        print(f'   {year + " " + season:16s} {nfiles:6d} {nparsed:7d} {nperfs:8,d}{flag}')
    print()


def check_date_season_consistency(all_perfs):
    """Flag performances whose date falls outside their labeled season window.

    Indoor YYYY runs Nov (YYYY-1) through Mar YYYY; Outdoor YYYY runs Mar-Jul YYYY.
    A date outside the window means the parser grabbed the wrong date from the
    file (record lines, license dates, etc.).
    """
    print('3c. DATE / SEASON CONSISTENCY')
    from datetime import datetime as _dt
    bad = []
    unknown = 0
    for p in all_perfs:
        d = p.get('date', '')
        if not d or d == 'Unknown':
            unknown += 1
            continue
        try:
            dt = _dt.strptime(d[:10], '%Y-%m-%d')
            yr = int(p.get('year'))
        except (ValueError, TypeError):
            bad.append((d, p.get('meet_name'), p.get('year'), p.get('season')))
            continue
        season = p.get('season')
        if season == 'Indoor':
            ok = _dt(yr - 1, 11, 1) <= dt <= _dt(yr, 3, 31)
        elif season == 'Outdoor':
            ok = _dt(yr, 3, 1) <= dt <= _dt(yr, 7, 31)
        else:
            ok = True
        if not ok:
            bad.append((d[:10], p.get('meet_name'), p.get('year'), p.get('season')))

    total = len(all_perfs)
    print(f'   [INFO] {unknown:,} / {total:,} performances have no date.')
    if bad:
        by_meet = defaultdict(int)
        for d, mn, yr, ssn in bad:
            by_meet[(mn, yr, ssn, d)] += 1
        print(f'   [ALERT] {len(bad):,} performances have dates outside their season window '
              f'({len(by_meet)} meet/date combos):')
        for (mn, yr, ssn, d), n in sorted(by_meet.items(), key=lambda kv: -kv[1])[:10]:
            print(f'     [{yr} {ssn}] {mn}: date={d}  (x{n})')
        if len(by_meet) > 10:
            print(f'     ... and {len(by_meet)-10} more meet/date combos.')
    else:
        print('   [OK] All dated performances fall inside their season window.')
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


_STRIP_WORDS = {'high', 'school', 'schools', 'hs', 'academy', 'acad', 'regional',
                'area', 'community', 'memorial', 'district', 'institute',
                'comprehensive', 'consolidated', 'boys', 'girls', 'men', 'women',
                'mens', 'womens', 'indoor', 'outdoor', 'track', 'field', 'tf',
                'team', 'varsity', 'coed'}


def _compare_key(name):
    """Reduce a school name to a punctuation/synonym-insensitive key so
    'Mount Desert Island HS', 'Mt. Desert Island High Schoo' and
    'Mt. Desert Island High School' all compare equal.

    HY-TEK truncates rankings names mid-suffix ('Camden Rockport Middle Sch'),
    so trailing tokens that are a PREFIX of a strip word are dropped too.
    """
    # Strip glued/trailing state suffixes ("Mount Desert IslandME", "Bonny Eagle, ME")
    name = re.sub(r'(?<=[a-z])(ME|MA|NH|VT|CT|RI)\b', '', name)
    name = re.sub(r'[,\s]+(ME|MA|NH|VT|CT|RI)\s*$', '', name)
    n = name.lower().replace('.', ' ').replace('-', ' ').replace("'", '')
    n = re.sub(r'\bmount\b', 'mt', n)
    n = re.sub(r'\bsaint\b', 'st', n)
    n = re.sub(r'\b(19|20)\d{2}\b', '', n)          # season years in club names
    n = re.sub(r'\b\d{2}\s*/?\s*\d{2}\b', '', n)    # "17-18" style seasons
    toks = [t for t in n.split() if t not in _STRIP_WORDS]
    while toks and any(w.startswith(toks[-1]) for w in _STRIP_WORDS):
        toks.pop()
    return ' '.join(toks)


def _fuzzy_team_match(abbrev, full_candidates):
    """Match a (possibly truncated) team name from rankings to our scored
    schools via compare keys (see _compare_key). Returns the matched
    candidate or `abbrev` if no match."""
    normalized = _normalize_school(abbrev)
    if normalized in full_candidates:
        return normalized

    by_key = {}
    for c in full_candidates:
        by_key.setdefault(_compare_key(c), c)

    for needle_name in (abbrev, normalized):
        needle = _compare_key(needle_name)
        if needle and needle in by_key:
            return by_key[needle]
    return abbrev


def _assign_by_points(raw_scores, official_teams):
    """Match a block's scored schools to the official teams when the names
    do not resolve (nicknames like "Eddies" for Edward Little, relay names
    vs individual codes). Names first; then an unresolved school (or a pair
    of them) is given to the one team whose remaining deficit its points
    fill exactly. Returns (largest per-team deficit, aliases {raw: official});
    the deficit is inf when some school's points could not be credited.

    A meet that only verifies this way still proves the parse: every point
    the file awards is accounted for, team by team."""
    raw = {k: v for k, v in raw_scores.items() if v > 0}
    teams = [t['team'] for t in official_teams]
    deficit = {t['team']: float(t['score']) for t in official_teams}
    keys = {t: _compare_key(_normalize_school(t)) for t in teams}
    keys_raw = {t: _compare_key(t) for t in teams}
    aliases = {}
    for r in list(raw):
        kr = {_compare_key(r), _compare_key(_normalize_school(r))} - {''}
        hits = [t for t in teams if keys[t] in kr or keys_raw[t] in kr]
        if not hits:
            hits = [t for t in teams for k in kr
                    if len(k) >= 4 and len(keys_raw[t]) >= 4
                    and (keys_raw[t].startswith(k) or k.startswith(keys_raw[t]))]
        if len(set(hits)) == 1:
            aliases[r] = hits[0]
            deficit[hits[0]] -= raw.pop(r)
    changed = True
    while changed and raw:
        changed = False
        for r in list(raw):
            fit = [t for t in teams if abs(deficit[t] - raw[r]) <= 0.01]
            if len(fit) == 1:
                aliases[r] = fit[0]
                deficit[fit[0]] -= raw.pop(r)
                changed = True
        if changed or len(raw) < 2:
            continue
        rs = list(raw)
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                pts = raw[rs[i]] + raw[rs[j]]
                fit = [t for t in teams if abs(deficit[t] - pts) <= 0.01]
                if len(fit) == 1:
                    for r in (rs[i], rs[j]):
                        aliases[r] = fit[0]
                        deficit[fit[0]] -= raw.pop(r)
                    changed = True
                    break
            if changed:
                break
    if raw:  # points nobody could be credited with
        return float('inf'), aliases
    return max([abs(d) for d in deficit.values()] or [0.0]), aliases


def _score_meet_from_parsed(parsed_data, ind_table=None, relay_table=None, normalize=True,
                            split_divisions=False):
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

    # Group blocks by (gender, event): meets with Prelims AND Finals sections
    # produce two blocks for the same event, and scoring both double-counts.
    # Use only Finals-type results when any exist for the event.
    # split_divisions: Jr/Sr (or Small/Large school) divisions print as
    # repeated all-Finals blocks of one event and each scores on its own.
    grouped = {}
    for i, ev_block in enumerate(events):
        key = (ev_block.get('gender', ''), ev_block.get('event', ''), ev_block.get('is_relay', False))
        if split_divisions and key in grouped and all(
                r.get('type') == 'Finals' for r in ev_block.get('results', [])):
            key = key + (i,)
        grouped.setdefault(key, []).extend(ev_block.get('results', []))

    for (gender, event_name, is_relay, *_div), results in grouped.items():
        # Seed-type rows are entry lists, exhibition entries never score
        results = [r for r in results
                   if r.get('type') != 'Seed' and not r.get('exhibition')]
        finals = [r for r in results if r.get('type') == 'Finals']
        if finals:
            results = finals

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
            school = _normalize_school(school_raw) if normalize else school_raw.strip()
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


# ---------------------------------------------------------------------------
# 11b. Cross-country team-score verification
# ---------------------------------------------------------------------------

def _xc_team_places(results, cap=7, min_team=5, shared_ties=False):
    """Re-derive Hy-Tek XC team scoring from a race's finish order.

    Teams with >= `min_team` finishers score; their runners take TEAM places
    in finish order (everyone else is skipped), the top 5 count and runners
    6-`cap` displace. Meet Manager options vary by meet (some place every
    team's runners, some score plain overall places, some let all runners
    displace), so callers try several. Keyed by the raw school string, which is constant
    within one race. With `shared_ties`, scorers printed with the same
    place (a judged tie) share one team place and the next scorer skips
    ahead (XCRun scores ties that way), and plain overall scoring
    (min_team <= 0) uses the printed places, so a runner removed from the
    list leaves its gap. Returns {school: [team places...]}."""
    rows, tie_key = [], []
    for r in results:
        if r.get('exhibition') or r.get('type') == 'Seed':
            continue
        school = (r.get('team_entry') or r.get('school') or '').strip()
        mark = r.get('result', '')
        if not school or str(mark).upper() in BAD_MARKS:
            continue
        if not mark:
            # an untimed race (places and team points only): the printed
            # place orders it
            if r.get('place') is None:
                continue
        else:
            v, _ = parse_mark_value(mark, '')
            if v is None:
                continue
        rows.append(school)
        tie_key.append(r.get('place'))
    counts = defaultdict(int)
    for s in rows:
        counts[s] += 1
    if min_team <= 0:  # plain overall places: every finisher counts
        scoring = set(counts)
    else:
        scoring = {s for s, n in counts.items()
                   if n >= min_team and s.lower() not in ('unattached', 'unknown')}
    places = defaultdict(list)
    p = 0
    last_key, last_p = None, None
    for s, k in zip(rows, tie_key):
        if s not in scoring or len(places[s]) >= cap:
            continue
        p += 1
        if min_team <= 0 and shared_ties and k is not None:
            # plain overall places as printed: a removed runner leaves a gap
            places[s].append(k)
            continue
        if shared_ties and k is not None and k == last_key:
            places[s].append(last_p)
            continue
        last_key, last_p = k, p
        places[s].append(p)
    return places


def _xc_merge_truncations(results):
    """One team printed two ways in a race ("HALL-DALE HIGH SCHOO" and
    "HALL-DALE HIGH": a registration name and a cell truncation) is still
    one team. Returns the rows with each school string that extends a
    shorter one (8+ characters) renamed to it, or None when there is none."""
    names = sorted({(r.get('school') or '').strip() for r in results}, key=len)
    alias = {}
    for i, a in enumerate(names):
        for b in names[:i]:
            if len(b) >= 8 and a.lower().startswith(b.lower()) and a != b:
                alias[a] = alias.get(b, b)
                break
    if not alias:
        return None
    return [dict(r, school=alias.get((r.get('school') or '').strip(), r.get('school')))
            for r in results]


def _xc_merge_codes(results):
    """A hand-typed list coding one school two ways, one code the start of
    the other ("El" / "Ell" for Ellsworth, "Win" / "Wins" for Winslow): the
    rows with the shorter code renamed to the longer one, or None when there
    is none."""
    from collections import Counter
    cnt = Counter((r.get('school') or '').strip() for r in results)
    codes = [c for c in cnt if 2 <= len(c) <= 5 and c.isalpha()]
    alias = {}
    # ("lew" / "Lew": one code typed in two cases)
    for a in codes:
        same = [b for b in codes if b.lower() == a.lower()]
        top = max(same, key=lambda b: cnt[b])
        if a != top:
            alias[a] = top
    for a in codes:
        longer = {alias.get(b, b) for b in codes if len(b) > len(a) and b.lower().startswith(a.lower())}
        if len(longer) == 1:
            alias[a] = longer.pop()
    # ("Houtlon / GHCA" once among "Houlton / GHCA" rows: a typo of a long name)
    import difflib
    names = [c for c in cnt if len(c) >= 7]
    # ("GCHA" once among "GHCA" rows: two letters swapped in a code)
    for a in codes:
        if cnt[a] == 1 and a not in alias:
            near = [b for b in codes if b != a and cnt[b] >= 3 and len(b) == len(a) and len(a) >= 3
                    and sorted(a.lower()) == sorted(b.lower())
                    and sum(1 for x, y in zip(a.lower(), b.lower()) if x != y) == 2]
            if len(near) == 1:
                alias[a] = near[0]
    for a in names:
        if cnt[a] != 1:
            continue
        near = [b for b in names if b != a and cnt[b] >= 3 and
                difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.85 and
                sorted(a.lower()) == sorted(b.lower())]
        if len(near) == 1:
            alias[a] = near[0]
    if not alias:
        return None
    return [dict(r, school=alias.get((r.get('school') or '').strip(), r.get('school')))
            for r in results]


def _xc_tie_orders(results):
    """The finish order, plus re-orderings of printed ties. Hy-Tek prints
    a judged tie as two rows with the same place ("32 McCarthy ... 22:40.50
    33" / "32 Porter ... 22:40.50  32"); which of the two takes the lower
    team place is its own call, recorded only in the team-points column.
    Yields the order as printed, the tie groups sorted by printed team
    place, and the tie groups reversed."""
    yield results
    # a hand-timed list printed out of time order ("20:35, 20:56, 20:28"):
    # the meet scored its runners in time order
    def _t(r):
        m = re.match(r'^(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)$', str(r.get('result') or '').strip())
        return (int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) if m else None
    ts = [_t(r) for r in results]
    if len(results) >= 5 and all(t is not None for t in ts) and \
            any(b < a - 0.5 for a, b in zip(ts, ts[1:])):
        yield [r for _t0, _k, r in sorted((t, k, r) for k, (t, r) in enumerate(zip(ts, results)))]
    groups, i = [], 0
    while i < len(results):
        j = i
        p = results[i].get('place')
        while p is not None and j + 1 < len(results) and results[j + 1].get('place') == p:
            j += 1
        if j > i:
            groups.append((i, j + 1))
        i = j + 1
    if not groups:
        return
    by_tp, rev = list(results), list(results)
    for a, b in groups:
        by_tp[a:b] = sorted(results[a:b], key=lambda r: (r.get('team_place') is None,
                                                         r.get('team_place') or 0))
        rev[a:b] = results[a:b][::-1]
    yield by_tp
    yield rev


# squad designator ending an official team name: "MT. ARARAT HIGH SCHOOL B"
_AB_TEAM = re.compile(r"\s['\"]?[A-D]['\"]?$")


def _xc_printed_places_ok(official, results):
    """A/B squads ("MT. ARARAT HIGH SCHOOL A" / "... B"): which of a
    school's runners were entered on which squad is not in the results, so
    the squads' places cannot be re-derived from finish order. The rows'
    printed team-score places can still be checked: in finish order they
    must run 1, 2, 3, ... with no gap (no scoring runner lost or
    misordered) and every official squad's places must be printed places
    of runners of one school, no place used twice."""
    if not any(_AB_TEAM.search(t.get('team', '')) for t in official):
        return False
    printed = [(r.get('team_place'), (r.get('school') or '').strip()) for r in results
               if r.get('team_place') is not None and not r.get('exhibition')]
    if len(printed) < 5 or [tp for tp, _ in printed] != list(range(1, len(printed) + 1)):
        return False
    school_of = {tp: sch for tp, sch in printed}
    used = set()
    for t in official:
        schools = {school_of.get(p) for p in t['places']}
        if None in schools or len(schools) != 1 or used & set(t['places']):
            return False
        used |= set(t['places'])
    return True


# file context for the catalog-resolved variant (set by xc_verify_file)
_XC_CTX = {}


def _catalog_rows(rows, gender=None):
    """Rows with each school replaced by its catalog scoring unit, when the
    catalog resolves it ("SCK" / "SNK" / "Schenck" -> one team)."""
    if not _XC_CTX.get('year'):
        return None
    try:
        from backend import school_catalog as sc
    except Exception:
        return None
    out, hit = [], 0
    cache = {}
    for r in rows:
        raw = r.get('school') or ''
        if raw not in cache:
            try:
                sid = sc.resolve(raw, year=_XC_CTX['year'], season='XC', gender=gender,
                                 meet_name=_XC_CTX.get('meet'))
                cache[raw] = sc.team_unit(sid, _XC_CTX['year'], 'XC', gender) if sid else None
            except Exception:
                cache[raw] = None
        u = cache[raw]
        hit += bool(u)
        out.append(dict(r, school='cat:' + str(u)) if u else r)
    return out if hit >= 0.5 * len(rows) else None


def _xc_listed_teams_rows(block, results):
    """The rows of the teams the score table lists (by name, code or
    initials), when that leaves out a team of five or more finishers; else
    None."""
    fold = lambda x: re.sub(r'[^a-z]', '', (x or '').lower())
    names = [t.get('team') for t in block.get('teams', []) if t.get('team')]
    if len(names) < 2:
        return None
    keys = []
    for n in names:
        ini = ''.join(w[0] for w in re.findall(r'[A-Za-z]+', n)).lower()
        keys.append((fold(n), ini))

    def listed(school):
        f = fold(school)
        if not f:
            return False
        for fn, ini in keys:
            if f == fn or f == ini or (len(f) >= 3 and fn.startswith(f)) or (len(fn) >= 4 and f.startswith(fn[:4])):
                return True
        return False
    from collections import Counter
    cnt = Counter((r.get('school') or '').strip() for r in results)
    gone = [sc for sc, n in cnt.items() if n >= 5 and not listed(sc)]
    if not gone:
        return None
    kept = [r for r in results if listed(r.get('school'))]
    return kept if len({(r.get('school') or '').strip() for r in kept}) >= len(names) else None


def _xc_verify_totals(block, results):
    """A block printing only each team's total ("Yarmouth 26"): name-free,
    every official total must be some computed team's total under one
    scoring rule (displacer cap, which teams place, 4 or 5 scorers)."""
    off = sorted(t['score'] for t in block.get('teams', []) if t.get('score') is not None)
    if not off:
        return None
    best = None
    # (4 scorers: small fields - "Team scores based on 4 scoring runners":
    # fewer teams field five than the table scores)
    from collections import Counter
    fives = sum(1 for _s, c in Counter((r.get('school') or '').strip() for r in results).items() if _s and c >= 5)
    scorers = (5, 4) if min(off) < 15 or fives < len(off) else (5,)
    # hand-typed sheets spell one school two ways ("SP" / "Sp", "Lee Ac." /
    # "Lee Academy"): also score with the school folded
    def _fold(rows):
        out = []
        for r in rows:
            sc = re.sub(r'[^a-z]', '', (r.get('school') or '').lower())
            out.append(dict(r, school=sc[:4] if sc else r.get('school')))
        return out
    n_rows = len(results)
    orders = list(_xc_tie_orders(results))
    # (rows without a printed team-points cell take no team place: the
    # same variant the place-list check uses)
    if sum(1 for r in results if r.get('team_place') is not None) >= 5:
        orders += [[r for r in o if r.get('team_place') is not None] for o in orders]
    mc = _xc_merge_codes(results)
    if mc is not None:
        orders.append(mc)
    orders += [_fold(o) for o in orders]
    cat = _catalog_rows(results, block.get('gender'))
    if cat:
        orders.append(cat)
    only = _xc_listed_teams_rows(block, results)
    if only is not None:
        # (only the table's teams place: "Schenck ... NOT fielding full
        # teams" though five Schenck runners finished)
        orders.append(only)
    for order in orders:
        for k in scorers:
            for cap in (7, 5, 8, 9, 10, 10 ** 6):
                # (teams of 4+ placing: a meet whose 4-runner team scores
                # with a filler)
                for min_team in (k, 4, 3, 1, 0):
                    comp = _xc_team_places(order, cap, min_team)
                    tot = sorted(sum(v[:k]) for v in comp.values() if len(v) >= k)
                    pool = list(tot)
                    # a short team scored with filler places for its missing
                    # runners: consecutive from the next team place or from
                    # the field size + 1 ("Lawrence 108" = 9+11+19 + 34+35)
                    last = max((max(v) for v in comp.values() if v), default=0)
                    short = []
                    shorts = [v for v in comp.values() if 0 < len(v) < k and min_team < k and len(v) >= min_team]
                    # (several short teams can take the fillers in turn:
                    # Carrabec + 42, Madison + 43)
                    starts = set(range(last + 1, last + 2 + len(shorts))) | {n_rows + 1}
                    for v in shorts:
                        gap = k - len(v)
                        short.append({sum(v) + sum(range(f, f + gap)) for f in starts}
                                     | {sum(v) + f * gap for f in starts})
                    miss = 0
                    for x in off:
                        if x in pool:
                            pool.remove(x)
                        elif any(x in c for c in short):
                            short.remove(next(c for c in short if x in c))
                        else:
                            miss += 1
                    if best is None or miss < best[0]:
                        best = (miss, tot)
                    if not miss:
                        break
    miss, tot = best
    n = min(len(tot), len(off))
    return {'status': 'verified' if not miss else 'mismatch', 'teams_off': miss,
            'max_delta': max([abs(a - b) for a, b in zip(tot[:n], off[:n])] or [0]),
            'official_teams': len(off), 'computed_teams': len(tot), 'method': 'team_totals'}


def _xc_verify_block(block, results):
    """Compare one official Team Scores block against the parsed race.
    Name-free: each official team's places list must equal some computed
    team's list, so naming differences between the individual rows and the
    score block cannot cause false mismatches."""
    if block.get('totals_only'):
        return _xc_verify_totals(block, results)
    official = [t for t in block.get('teams', []) if t.get('places')]
    if not official:
        return None
    shown = max(5, max(len(t['places']) for t in official))
    # Meets differ on whether runners past the displayed scorers still take
    # team places (displace) and whether incomplete teams' runners do: try
    # each rule and keep the best fit.
    # Some meets score short teams with a filler place for each missing
    # runner (field size + 1, repeated): only the real places are checkable.
    n_rows = len(results)

    def _real(places):
        # sorted: two teammates in a judged tie can be printed 8, 7
        return tuple(sorted(p for p in places if p <= n_rows))

    best = None
    # runners per team that take places: 7 is standard; meets set 5-10
    caps = sorted({shown, 7, 8, 9, 10, 10 ** 6})
    orders = list(_xc_tie_orders(results))
    # Hy-Tek entries made as individuals run in their school's colours but
    # never score: their team-points cell is blank while teammates' are
    # filled. When the race prints that column, also score only the rows
    # that carry a team place.
    if sum(1 for r in results if r.get('team_place') is not None) >= 5:
        orders += [[r for r in o if r.get('team_place') is not None] for o in orders]
    merged = _xc_merge_truncations(results)
    if merged is not None:
        orders += [merged]
    mc = _xc_merge_codes(results)
    if mc is not None:
        orders += [mc]
    # a scored runner listed without a team ("19 13 816 UNKNOWN RUNNER"):
    # the official team whose places hold that team place, by its other rows
    blank = [r for r in results if r.get('team_place') is not None and not (r.get('school') or '').strip()]
    if blank:
        by_tp = {r['team_place']: (r.get('school') or '').strip() for r in results
                 if r.get('team_place') is not None and (r.get('school') or '').strip()}
        fill = {}
        for r in blank:
            owners = [t for t in official if r['team_place'] in t['places']]
            if len(owners) == 1:
                schools = {by_tp.get(pl) for pl in owners[0]['places']} - {None, ''}
                if len(schools) == 1:
                    fill[id(r)] = schools.pop()
        if fill:
            filled = [dict(r, school=fill[id(r)]) if id(r) in fill else r for r in results]
            orders += [filled, [r for r in filled if r.get('team_place') is not None]]
    # one school spelled two ways ("SCK" / "SNK"): the catalog's team
    cat = _catalog_rows(results, block.get('gender'))
    if cat:
        orders += [cat]
    # (only the table's teams place: a school of 5+ finishers the table
    # leaves out, or one spelled two ways "Brunswick" / "Brunswick High
    # School" folded to the table's name)
    only = _xc_listed_teams_rows(block, cat or results)
    if only is not None:
        orders += [only]
    # a race printed with a class column ("MSB" / "WCH"): a runner entered
    # in another division runs in the field but scores in that division
    divs = [r.get('division') for r in results if r.get('division')]
    if divs and len(set(divs)) > 1:
        main = max(set(divs), key=divs.count)
        orders += [[r for r in results if r.get('division') in (main, None)]]
    for order in orders:
        tied = any(a.get('place') is not None and a.get('place') == b.get('place')
                   for a, b in zip(order, order[1:])) or any(
            a.get('place') is not None and b.get('place') is not None
            and b['place'] > a['place'] + 1 for a, b in zip(order, order[1:]))
        for cap, min_team, shared in [(c, m, t) for t in ((False, True) if tied else (False,))
                                      for m in (5, 4, 3, 1, 0) for c in caps]:
            computed = _xc_team_places(order, cap, min_team, shared)
            lists = [tuple(v[:shown]) for v in computed.values() if len(v) >= 5]
            pool = [tuple(v[:shown]) for v in computed.values()]
            # a short team's missing scorers are padded with filler places
            # past the last real one (16, 17 after 15 scorers; or field+1).
            # Fillers only pad the five scoring slots, never displacers, so
            # a list with displacers keeps every place.
            last = max((max(v) for v in computed.values() if v), default=0)
            n_off = 0
            for t in official:
                tp = _real(t['places'])
                if len(t['places']) <= 5:
                    pl = list(t['places'])
                    # a run of one repeated value ends the list: fillers
                    # ("5 7 14 14 14"), whatever number Hy-Tek chose
                    while len(pl) >= 2 and pl[-1] == pl[-2]:
                        v = pl[-1]
                        while pl and pl[-1] == v:
                            pl.pop()
                    tp = tuple(p for p in _real(pl) if p <= last)
                if t.get('truncated') or 5 <= len(tp) < shown:
                    # the line lost its last place(s), or the team is printed
                    # with fewer displacers than it ran (left off the sheet)
                    tp = next((c for c in pool if c[:len(tp)] == tp), tp)
                if tp in pool:
                    pool.remove(tp)
                else:
                    n_off += 1
            if best is None or n_off < best[0]:
                best = (n_off, lists)
    off, comp_lists = best
    by_printed = bool(off) and _xc_printed_places_ok(official, results)
    if by_printed:
        off = 0
    comp_scores = sorted(sum(v[:5]) for v in comp_lists)
    off_scores = sorted(t['score'] for t in official)
    n = min(len(comp_scores), len(off_scores))
    max_delta = max([abs(a - b) for a, b in zip(comp_scores[:n], off_scores[:n])] or [0])
    if not off:
        status = 'verified'
    elif comp_scores[:len(off_scores)] == off_scores:
        status = 'verified_close'   # same team totals, a displacer differs
    else:
        status = 'mismatch'
    out = {'status': status, 'teams_off': off, 'max_delta': 0.0 if by_printed else max_delta,
           'official_teams': len(official), 'computed_teams': len(comp_lists)}
    if by_printed:
        out['method'] = 'printed_team_places'
    return out


def xc_verify_parsed(parsed):
    """Verdict for a parsed XC file carrying 'kind': 'xc' team_rankings.
    Returns None when the file has no XC team scores."""
    if not isinstance(parsed, dict):
        return None
    blocks = [b for b in parsed.get('team_rankings', []) or []
              if isinstance(b, dict) and b.get('kind') == 'xc']
    if not blocks:
        return None
    events = [e for e in parsed.get('events', [])
              if isinstance(e, dict) and e.get('results')]
    if not events and parsed.get('aggregate_events'):
        # a combined / qualifier re-ranking: its scores against its own list
        parsed = dict(parsed, events=parsed['aggregate_events'])
        events = [e for e in parsed['events'] if isinstance(e, dict) and e.get('results')]
    if not events:
        return {'status': 'xc_no_results'}
    # pair blocks with races: by the parser's explicit event_idx when it
    # recorded one, else by gender in order of appearance
    verdicts = []
    all_events = parsed.get('events', [])
    # a mixed list the parser split by gender ("Mt. Blue HS B" / "... G")
    # was scored as one race: verify against the halves re-merged by place
    combined = defaultdict(list)
    for e in events:
        if e.get('combined_race') is not None:
            combined[e['combined_race']].extend(e['results'])

    def _rows(e):
        cid = e.get('combined_race')
        if cid is None:
            return e['results']
        return sorted(combined[cid], key=lambda r: r.get('place') or 0)

    # a co-ed race the parser split by its sex column: its scores may have
    # been figured on the whole field (boys in the girls' race take places)
    mixed = defaultdict(list)
    for e in events:
        if e.get('mixed_race') is not None:
            mixed[e['mixed_race']].extend(e['results'])
    _rank = {'verified': 0, 'verified_close': 1, 'mismatch': 2}

    def _vb(b, e):
        cands = [_rows(e)]
        if e.get('mixed_race') is not None:
            cands.append(sorted(mixed[e['mixed_race']], key=lambda r: r.get('place') or 0))
        vs = [v for v in (_xc_verify_block(b, rows) for rows in cands) if v]
        return min(vs, key=lambda v: (_rank[v['status']], v['teams_off'])) if vs else None

    if all(isinstance(b.get('event_idx'), int) for b in blocks):
        for b in blocks:
            i = b['event_idx']
            if 0 <= i < len(all_events) and all_events[i].get('results'):
                v = _vb(b, all_events[i])
                if v:
                    verdicts.append(v)
        blocks = []
    for g in {b.get('gender') for b in blocks}:
        gb = [b for b in blocks if b.get('gender') == g]
        ge = [e for e in events if g is None or e.get('gender') == g]
        if g is None and len({e.get('gender') for e in events}) > 1:
            # a block that names no gender in a two-race file: each block
            # is checked against the race it fits (blocks in race order)
            if len(gb) <= len(events):
                rank = {'verified': 0, 'verified_close': 1, 'mismatch': 2}
                for b in gb:
                    vs = [v for v in (_vb(b, e) for e in events) if v]
                    if vs:
                        verdicts.append(min(vs, key=lambda v: (rank[v['status']], v['teams_off'])))
                continue
            return {'status': 'xc_unpaired'}
        if g is not None and not ge:
            continue        # (that race is posted in its own file)
        if len(gb) != len(ge):
            # one race posted per file but its block repeated, or a
            # combined file: pair each block with every race of the gender
            # and keep the best fit
            if len(ge) == 1 or len(gb) == 1:
                for b in gb:
                    best = None
                    for e in ge:
                        v = _vb(b, e)
                        if v and (best is None or v['teams_off'] < best['teams_off']):
                            best = v
                    if best:
                        verdicts.append(best)
                continue
            return {'status': 'xc_unpaired'}
        for b, e in zip(gb, ge):
            v = _vb(b, e)
            if v:
                verdicts.append(v)
    if not verdicts:
        return {'status': 'xc_unpaired'}
    rank = {'verified': 0, 'verified_close': 1, 'mismatch': 2}
    worst = max(verdicts, key=lambda v: rank[v['status']])
    return {'status': worst['status'], 'races': len(verdicts),
            'teams_off': sum(v['teams_off'] for v in verdicts),
            'max_delta': max(v['max_delta'] for v in verdicts),
            'scoring_system': 'xc'}


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
    verification = {}  # meet_key -> {status, config, max_delta}
    by_points = 0
    xc_counts = {}
    xc_mismatch = []

    def meet_label_of(y, s_, f):
        return f'{y}/{s_}/{f}'

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

    # every archive file, plus the hand transcriptions that have no archive
    # file (MileSplit "ms-", New England "ne-": parser *-manual)
    def _meet_files():
        for year in sorted(os.listdir(ARCHIVE_BASE)):
            year_path = os.path.join(ARCHIVE_BASE, year)
            if not os.path.isdir(year_path):
                continue
            for season in sorted(os.listdir(year_path)):
                season_path = os.path.join(year_path, season)
                if not os.path.isdir(season_path):
                    continue
                for fn in sorted(os.listdir(season_path)):
                    if fn.lower().endswith(('.htm', '.html', '.pdf')):
                        yield year, season, fn
        for jp_ in sorted(glob.glob(os.path.join(PARSED_BASE, '*', '*', '*.json'))):
            year, season, fn = jp_.split(os.sep)[-3:]
            if not fn.startswith(('ms-', 'ne-')):
                continue
            try:
                manual = str(json.load(open(jp_, encoding='utf-8')).get('parser', '')).endswith('-manual')
            except Exception:
                manual = False
            if manual:
                yield year, season, fn

    for year, season, fn in _meet_files():
                total_meets += 1

                # Read the persisted parse (team_rankings included) rather
                # than re-parsing the archive file — ~50x faster.
                stem = os.path.splitext(fn)[0]
                meet_key = f'{year}_{season}_{stem}'
                jp = os.path.join(PARSED_BASE, year, season, stem + '.json')
                try:
                    parsed = json.load(open(jp, encoding='utf-8'))
                except Exception:
                    verification[meet_key] = {'status': 'parse_missing'}
                    continue
                if not isinstance(parsed, dict):
                    no_ranking_files += 1
                    verification[meet_key] = {'status': 'no_rankings'}
                    continue

                # Cross country: official Team Scores re-derived from the
                # finish order (name-free, see xc_verify_parsed)
                xc_v = xc_verify_parsed(parsed)
                if xc_v is not None:
                    verification[meet_key] = xc_v
                    xc_counts[xc_v['status']] = xc_counts.get(xc_v['status'], 0) + 1
                    if xc_v['status'] == 'mismatch':
                        xc_mismatch.append((meet_label_of(year, season, fn), xc_v))
                    continue

                rankings = [b for b in parsed.get('team_rankings', []) or []
                            if b.get('kind') != 'xc']
                if not rankings:
                    no_ranking_files += 1
                    verification[meet_key] = {'status': 'no_rankings'}
                    continue

                # Legacy meets post genders in separate files but include both
                # genders' ranking blocks in each — only blocks whose gender
                # has results in THIS file are verifiable here.
                genders_present = {ev.get('gender') for ev in parsed.get('events', [])
                                   if isinstance(ev, dict) and ev.get('results')}
                rankings = [b for b in rankings
                            if b.get('gender') in genders_present and b.get('teams')]
                if not rankings:
                    no_ranking_files += 1
                    verification[meet_key] = {'status': 'rankings_other_gender'}
                    continue

                meets_with_rankings += 1

                # Precompute scores under each configuration
                computed_by_config = {}
                # repeated (gender, event) blocks = possible Jr/Sr divisions
                ev_keys = [(e.get('gender'), e.get('event'), e.get('is_relay', False))
                           for e in parsed.get('events', []) if isinstance(e, dict)]
                has_divisions = len(ev_keys) != len(set(ev_keys))
                for name, ind_t, rel_t in configs:
                    computed_by_config[name] = _score_meet_from_parsed(parsed, ind_t, rel_t)
                    if has_divisions:
                        computed_by_config[name + '+divisions'] = _score_meet_from_parsed(
                            parsed, ind_t, rel_t, split_divisions=True)

                meet_label = f'{year}/{season}/{fn}'
                meet_ok = True
                mm_start = len(mismatches)

                for block in rankings:
                    gender = block['gender']
                    official_teams = block.get('teams', [])
                    if not official_teams:
                        continue

                    # Aggregate each config's scores by compare key so name
                    # variants ("MDI" vs "Mount Desert Island HS") pool their
                    # points instead of splitting across two entries.
                    def _keyed(scores):
                        agg = {}
                        names = {}
                        for school, pts in scores.items():
                            k = _compare_key(_normalize_school(school))
                            agg[k] = agg.get(k, 0.0) + pts
                            names.setdefault(k, school)
                        return agg, names

                    def _lookup(agg, official_name):
                        # Exact compare-key equality only: suffix truncation is
                        # handled inside _compare_key, and looser prefix
                        # matching mismatches sibling schools (Bangor vs
                        # Bangor Christian).
                        for cand in (official_name, _normalize_school(official_name)):
                            k = _compare_key(cand)
                            if k in agg:
                                return k
                        return None

                    # Select the configuration with the minimum sum of absolute errors for this gender
                    best_name = None
                    best_score_diff = float('inf')
                    best_agg, best_names = {}, {}

                    for name in computed_by_config:
                        agg, names = _keyed(computed_by_config[name].get(gender, {}))
                        total_abs_diff = 0.0
                        for entry in official_teams:
                            k = _lookup(agg, entry['team'])
                            our_score = agg.get(k, 0.0) if k else 0.0
                            total_abs_diff += abs(our_score - entry['score'])
                        if total_abs_diff < best_score_diff:
                            best_score_diff = total_abs_diff
                            best_name = name
                            best_agg, best_names = agg, names

                    # Now perform the actual comparison using the best configuration's scores
                    for entry in official_teams:
                        official_name = entry['team']
                        official_score = entry['score']

                        k = _lookup(best_agg, official_name)
                        matched = best_names.get(k, official_name) if k else official_name
                        our_score = best_agg.get(k, 0.0) if k else 0.0

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

                resolved = None
                if not meet_ok:
                    # Names did not resolve (or TEAM_MAPPING merged schools):
                    # account for the points on the raw school strings instead
                    name_delta = max(abs(m['delta']) for m in mismatches[mm_start:])
                    for name, ind_t, rel_t, split in [(n, i_, r_, sp) for n, i_, r_ in configs
                                                       for sp in ((False, True) if has_divisions
                                                                  else (False,))]:
                        raw_scores = _score_meet_from_parsed(parsed, ind_t, rel_t,
                                                             normalize=False,
                                                             split_divisions=split)
                        if split:
                            name = name + '+divisions'
                        worst, aliases = 0.0, {}
                        for block in rankings:
                            d, al = _assign_by_points(
                                raw_scores.get(block['gender'], {}), block['teams'])
                            worst = max(worst, d)
                            aliases.update(al)
                        if worst < name_delta and (resolved is None or worst < resolved[2]):
                            resolved = (name, aliases, worst)
                    if resolved and resolved[2] <= 2.0:
                        del mismatches[mm_start:]
                        meet_ok = resolved[2] <= 0.5
                    else:
                        resolved = None
                if resolved and not meet_ok:
                    by_points += 1
                    verification[meet_key] = {
                        'status': 'verified_close', 'teams_off': None,
                        'max_delta': resolved[2], 'scoring_system': resolved[0],
                        'resolved_by': 'points',
                        'aliases': {k: v for k, v in sorted(resolved[1].items())
                                    if _compare_key(k) != _compare_key(v)},
                    }
                elif meet_ok:
                    exact_matches += 1
                    verification[meet_key] = {'status': 'verified'}
                    if resolved:
                        verification[meet_key].update({
                            'resolved_by': 'points',
                            'scoring_system': resolved[0],
                            'aliases': {k: v for k, v in sorted(resolved[1].items())
                                        if _compare_key(k) != _compare_key(v)},
                        })
                        by_points += 1
                else:
                    new_mm = mismatches[mm_start:]
                    max_delta = max(abs(m['delta']) for m in new_mm)
                    # <=2 points off is a tie-averaging / judge-call difference,
                    # not a parsing failure — still high confidence.
                    status = 'verified_close' if max_delta <= 2.0 else 'mismatch'
                    verification[meet_key] = {
                        'status': status,
                        'teams_off': len(new_mm),
                        'max_delta': max_delta,
                        'scoring_system': new_mm[0]['scoring_system'],
                    }

    # Persist per-meet verdicts: this is the confidence record for the store.
    verification_path = os.path.join(BASE_DIR, 'backend', 'data', 'meet_verification.json')
    try:
        with open(verification_path, 'w', encoding='utf-8') as f:
            json.dump(verification, f, indent=2, sort_keys=True)
    except Exception as e:
        print(f'   [WARN] Could not write {verification_path}: {e}')

    close_matches = sum(1 for d in verification.values() if d.get('status') == 'verified_close')
    print(f'   Total archive files scanned: {total_meets}')
    print(f'   Files with Team Rankings: {meets_with_rankings}')
    print(f'   Files without rankings: {no_ranking_files}')
    pct = exact_matches / meets_with_rankings * 100 if meets_with_rankings else 0
    pct_c = (exact_matches + close_matches) / meets_with_rankings * 100 if meets_with_rankings else 0
    print(f'   Exact scoring matches: {exact_matches} / {meets_with_rankings} ({pct:.1f}%)')
    print(f'   Verified incl. close (max 2pts off): {exact_matches + close_matches} / {meets_with_rankings} ({pct_c:.1f}%)')
    print(f'   ...of which verified by accounting for points (team names unresolved): {by_points}')
    xc_total = sum(xc_counts.values())
    if xc_total:
        xc_ok = xc_counts.get('verified', 0)
        xc_close = xc_counts.get('verified_close', 0)
        print(f'   Cross country (Team Scores re-derived from finish order): '
              f'{xc_ok} verified, {xc_close} close, {xc_counts.get("mismatch", 0)} mismatch '
              f'of {xc_total} ({(xc_ok + xc_close) / xc_total * 100:.1f}% verified incl. close); '
              f'{xc_counts.get("xc_no_results", 0) + xc_counts.get("xc_unpaired", 0)} unpairable')
        for label, v in sorted(xc_mismatch, key=lambda x: -x[1].get('max_delta', 0))[:8]:
            print(f"     [XC {label}] teams off {v.get('teams_off')}, max delta {v.get('max_delta')}")
    print(f'   Per-meet verdicts written to backend/data/meet_verification.json')

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
# 13-15. Incorrect-entry detection
# ---------------------------------------------------------------------------

def check_athlete_outliers(all_perfs, flags_out):
    """An athlete's marks in one event cluster tightly; a mark hugely better
    than their own median is usually a parse error (wrong column, dropped
    digit, misattributed row) — HS athletes don't improve 25%+ overnight."""
    print('13. PER-ATHLETE OUTLIER MARKS')
    groups = defaultdict(list)
    for p in all_perfs:
        ev = p.get('event', '')
        # combined-events "marks" mix leg times and points — not comparable
        if re.search(r'pentathlon|heptathlon|decathlon', ev, re.I):
            continue
        val, is_dist = parse_mark_value(p.get('mark', ''), ev)
        if val is not None:
            groups[(p.get('athlete_id'), ev)].append((val, is_dist, p))

    suspects = []
    for (aid, ev), rows in groups.items():
        if len(rows) < 4:
            continue
        vals = sorted(v for v, _, _ in rows)
        median = vals[len(vals) // 2]
        if median <= 0:
            continue
        for val, is_dist, p in rows:
            # flag only the "impossibly good" direction: much faster time or
            # much longer distance than the athlete's own median
            ratio = (val / median) if is_dist else (median / val)
            if ratio >= 1.30:
                suspects.append((p, val, median, ratio))

    if suspects:
        print(f'   [ALERT] {len(suspects)} marks are 30%+ better than the athlete\'s own median:')
        suspects.sort(key=lambda x: -x[3])
        for p, val, med, ratio in suspects[:10]:
            print(f"     {p.get('athlete_name','')[:28]:30s} {p.get('event','')[:26]:28s} "
                  f"{p.get('mark')}  (median {med:.1f}, {ratio:.2f}x)  [{p.get('year')} {p.get('meet_name','')[:24]}]")
        if len(suspects) > 10:
            print(f'     ... and {len(suspects)-10} more.')
        for p, val, med, ratio in suspects:
            flags_out.append({'check': 'athlete-outlier', 'athlete': p.get('athlete_name'),
                              'team': p.get('team'), 'event': p.get('event'),
                              'mark': p.get('mark'), 'median': round(med, 2),
                              'ratio': round(ratio, 2), 'meet': p.get('meet_name'),
                              'year': p.get('year'), 'season': p.get('season'),
                              'perf_id': p.get('id')})
    else:
        print('   [OK] No per-athlete outlier marks.')
    print()


def check_duplicate_meets(all_perfs, flags_out):
    """The same meet ingested twice under different filenames (Results.htm +
    Results-1.htm, corrected_* reposts) doubles performances and corrupts PRs.
    Two meets in the same season sharing most (athlete, event, mark) rows are
    duplicates."""
    print('14. DUPLICATE MEET INGESTION')
    meets = defaultdict(set)
    for p in all_perfs:
        key = (p.get('year'), p.get('season'), p.get('meet_name'))
        meets[key].add((p.get('athlete_id'), p.get('event'), p.get('mark')))

    by_season = defaultdict(list)
    for (year, season, meet), rows in meets.items():
        if len(rows) >= 20:
            by_season[(year, season)].append((meet, rows))

    dupes = []
    for (year, season), meet_list in by_season.items():
        for i in range(len(meet_list)):
            for j in range(i + 1, len(meet_list)):
                m1, r1 = meet_list[i]
                m2, r2 = meet_list[j]
                inter = len(r1 & r2)
                smaller = min(len(r1), len(r2))
                if smaller and inter / smaller >= 0.6:
                    dupes.append((year, season, m1, m2, inter, smaller))

    if dupes:
        print(f'   [ALERT] {len(dupes)} meet pairs look like double ingestion:')
        for year, season, m1, m2, inter, smaller in sorted(dupes, key=lambda x: -x[4])[:10]:
            print(f'     [{year} {season}] "{m1}" <-> "{m2}"  ({inter}/{smaller} identical rows)')
        if len(dupes) > 10:
            print(f'     ... and {len(dupes)-10} more.')
        for year, season, m1, m2, inter, smaller in dupes:
            flags_out.append({'check': 'duplicate-meet', 'year': year, 'season': season,
                              'meet_a': m1, 'meet_b': m2,
                              'shared_rows': inter, 'smaller_meet_rows': smaller})
    else:
        print('   [OK] No duplicate meet ingestion detected.')
    print()


def check_gender_bleed(all_perfs, flags_out):
    """The same athlete appearing in Girls AND Boys events within one meet
    means an event header's gender bled into the wrong section."""
    print('15. GENDER BLEED (same athlete in both genders in one meet)')
    seen = defaultdict(set)
    for p in all_perfs:
        ev = p.get('event', '')
        g = 'Girls' if ev.startswith('Girls') else 'Boys' if ev.startswith('Boys') else None
        if not g or ',' in (p.get('athlete_name') or ''):  # skip relay rosters
            continue
        seen[(p.get('athlete_id'), p.get('year'), p.get('season'), p.get('meet_name'))].add(g)

    bleeds = [k for k, gs in seen.items() if len(gs) == 2]
    if bleeds:
        by_meet = defaultdict(int)
        for aid, year, season, meet in bleeds:
            by_meet[(year, season, meet)] += 1
        print(f'   [WARN] {len(bleeds)} athletes appear in both genders within one meet '
              f'({len(by_meet)} meets):')
        for (year, season, meet), n in sorted(by_meet.items(), key=lambda kv: -kv[1])[:10]:
            print(f'     [{year} {season}] {meet}: {n} athletes')
        for (year, season, meet), n in by_meet.items():
            flags_out.append({'check': 'gender-bleed', 'year': year, 'season': season,
                              'meet': meet, 'athletes_affected': n})
    else:
        print('   [OK] No gender bleed detected.')
    print()


SECTION_MIN_ROWS = 3
SECTION_THROWS = re.compile(r'put|discus|javelin|hammer|weight', re.I)


def _section_bounds(event):
    """How far a section's median may sit from its event's typical section
    median before the section looks like another event. Neighbouring races
    are ~2x apart (200/400/800/mile/2 mile) and a triple jump is ~2x a long
    jump, while whole middle-school, kids' and championship fields stay
    within ~1.6x. Throws spread wider (lighter middle-school implements, New
    England finals at 2x). Slow fields are real more often than fast ones,
    so the low side is looser."""
    if SECTION_THROWS.search(event):
        return 1 / 2.6, 2.6
    return 0.4, 1.8


def check_event_sections(all_perfs, flags_out):
    """An event section at one meet whose median mark belongs to another
    event: a missed event header, a wrong gender header, meters read as
    feet-inches, or field-relay team totals filed under the individual
    event. Judged on the section's median, so one runner's great or bad day
    never trips it; only a whole section does. Also flags times that cannot
    be read ("7:70", seconds over 59). Flags only; nothing is dropped."""
    import math
    from backend.athlete_catalog import is_team_label
    print('16. EVENT SECTIONS THAT LOOK LIKE ANOTHER EVENT')
    sections = defaultdict(list)
    malformed = []
    for p in all_perfs:
        ev = p.get('event', '')
        if p.get('season') == 'XC' or not re.match(r'(Boys|Girls) ', ev) \
                or re.search(r'relay|athlon|walk', ev, re.I):
            continue
        mark = str(p.get('mark', '')).strip()
        m = re.fullmatch(r'\d+:(\d\d)(\.\d+)?', mark)
        if m and int(m.group(1)) >= 60:
            malformed.append(p)
            continue
        if is_team_label(p.get('athlete_name'), p.get('team')):
            continue  # field relay team totals: the catalog already sets them apart
        val, is_dist = parse_mark_value(mark, ev)
        if val:
            sections[(p.get('year'), p.get('season'), p.get('meet_name'), ev)].append(val)

    medians = {k: sorted(v)[len(v) // 2] for k, v in sections.items() if len(v) >= SECTION_MIN_ROWS}
    by_event = defaultdict(list)
    for k, med in medians.items():
        by_event[k[3]].append(med)
    typical = {ev: sorted(v)[len(v) // 2] for ev, v in by_event.items() if len(v) >= 30}

    def looks_like(event, med):
        """The same-gender event of the same kind whose typical median is nearest."""
        g = event.split(' ', 1)[0]
        dist = bool(SECTION_THROWS.search(event)) or 'Jump' in event or 'Vault' in event
        same = [e for e in typical if e.startswith(g + ' ')
                and (bool(SECTION_THROWS.search(e)) or 'Jump' in e or 'Vault' in e) == dist]
        best = min(same, key=lambda e: abs(math.log(med / typical[e])))
        lo, hi = _section_bounds(best)
        return best if lo <= med / typical[best] <= hi else 'no event (mark format?)'

    odd = []
    for k, med in medians.items():
        ev = k[3]
        if ev not in typical:
            continue
        lo, hi = _section_bounds(ev)
        ratio = med / typical[ev]
        if not lo <= ratio <= hi:
            odd.append((k, med, ratio, len(sections[k]), looks_like(ev, med)))

    if odd:
        print(f'   [WARN] {len(odd)} event sections whose median mark belongs to another event:')
        for (year, season, meet, ev), med, ratio, n, like in sorted(odd, key=lambda x: -abs(math.log(x[2])))[:15]:
            print(f'     [{year} {season}] {meet[:34]:36s} {ev[:24]:26s} median {med:8.2f} '
                  f'({ratio:.2f}x typical, n={n}) looks like {like}')
        if len(odd) > 15:
            print(f'     ... and {len(odd)-15} more.')
        for (year, season, meet, ev), med, ratio, n, like in odd:
            flags_out.append({'check': 'event-section', 'year': year, 'season': season,
                              'meet': meet, 'event': ev, 'median': round(med, 2),
                              'typical': round(typical[ev], 2), 'ratio': round(ratio, 2),
                              'rows': n, 'looks_like': like})
    else:
        print('   [OK] Every event section looks like its event.')
    if malformed:
        print(f'   [WARN] {len(malformed)} times that cannot be read (seconds over 59):')
        for p in malformed[:5]:
            print(f"     [{p.get('year')} {p.get('season')}] {p.get('meet_name','')[:34]:36s} "
                  f"{p.get('event','')[:24]:26s} {p.get('athlete_name','')[:24]} {p.get('mark')}")
        for p in malformed:
            flags_out.append({'check': 'malformed-time', 'year': p.get('year'), 'season': p.get('season'),
                              'meet': p.get('meet_name'), 'event': p.get('event'),
                              'athlete': p.get('athlete_name'), 'team': p.get('team'),
                              'mark': p.get('mark'), 'perf_id': p.get('id')})
    print()


# ---------------------------------------------------------------------------
# 12. Result order sanity
# ---------------------------------------------------------------------------

def check_result_order():
    """Results in a Hy-Tek file are listed in finishing order, so parsed marks
    should be monotonic within an event (ascending times / descending
    distances).  A high inversion rate means the parser read the wrong column.
    Works for every meet — no official rankings needed.  Augments
    meet_verification.json with an order_ok flag per meet.
    """
    print('12. RESULT ORDER SANITY (marks monotonic within events)')
    verification_path = os.path.join(BASE_DIR, 'backend', 'data', 'meet_verification.json')
    try:
        verification = json.load(open(verification_path, encoding='utf-8'))
    except Exception:
        verification = {}

    suspect = []
    checked = 0
    for year in sorted(os.listdir(PARSED_BASE)):
        ypath = os.path.join(PARSED_BASE, year)
        if not os.path.isdir(ypath):
            continue
        for season in sorted(os.listdir(ypath)):
            spath = os.path.join(ypath, season)
            if not os.path.isdir(spath):
                continue
            for fn in sorted(os.listdir(spath)):
                if not fn.endswith('.json'):
                    continue
                try:
                    data = json.load(open(os.path.join(spath, fn), encoding='utf-8'))
                except Exception:
                    continue
                events = data.get('events', []) if isinstance(data, dict) else data
                pairs = 0
                inversions = 0
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    ev_name = ev.get('event', '')
                    is_field = any(k in ev_name.lower() for k in FIELD_KEYWORDS)
                    vals = []
                    for r in ev.get('results', []):
                        if r.get('type') == 'Seed' or r.get('exhibition'):
                            continue
                        v, _ = parse_mark_value(r.get('result', ''), ev_name)
                        if v is not None:
                            vals.append(v)
                    if len(vals) < 4:
                        continue
                    for a, b in zip(vals, vals[1:]):
                        pairs += 1
                        if (is_field and b > a + 0.01) or (not is_field and b < a - 0.01):
                            inversions += 1
                if pairs < 10:
                    continue
                checked += 1
                rate = inversions / pairs
                meet_key = f'{year}_{season}_{os.path.splitext(fn)[0]}'
                entry = verification.setdefault(meet_key, {'status': 'no_rankings'})
                entry['order_ok'] = rate <= 0.25
                entry['inversion_rate'] = round(rate, 3)
                if rate > 0.25:
                    suspect.append((f'{year}/{season}/{fn}', rate))

    try:
        with open(verification_path, 'w', encoding='utf-8') as f:
            json.dump(verification, f, indent=2, sort_keys=True)
    except Exception as e:
        print(f'   [WARN] Could not update {verification_path}: {e}')

    print(f'   Meets checked: {checked}')
    if suspect:
        print(f'   [ALERT] {len(suspect)} meets have >25% mark-order inversions (wrong column parsed?):')
        for name, rate in sorted(suspect, key=lambda x: -x[1])[:12]:
            print(f'     {name}  ({rate:.0%} inverted)')
        if len(suspect) > 12:
            print(f'     ... and {len(suspect)-12} more.')
    else:
        print('   [OK] All meets have sane mark ordering.')
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
    check_season_pipeline_coverage(all_perfs)
    print(SEPARATOR)
    check_date_season_consistency(all_perfs)
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
    check_result_order()
    print(SEPARATOR)
    flags = []
    check_athlete_outliers(all_perfs, flags)
    print(SEPARATOR)
    check_duplicate_meets(all_perfs, flags)
    print(SEPARATOR)
    check_gender_bleed(all_perfs, flags)
    print(SEPARATOR)
    check_event_sections(all_perfs, flags)
    print(SEPARATOR)
    flags_path = os.path.join(BASE_DIR, 'backend', 'data', 'qaqc_flags.json')
    with open(flags_path, 'w', encoding='utf-8') as f:
        json.dump(flags, f, indent=1, ensure_ascii=False)
    print(f'{len(flags)} incorrect-entry flags written to backend/data/qaqc_flags.json')
    print(SEPARATOR)
    print('QA/QC complete.')


if __name__ == '__main__':
    run_qaqc()


_SIB_DROP = {'team', 'teams', 'score', 'scores', 'socres', 'scoring', 'results', 'result', 'txt',
             'htm', 'html', 'pdf', 'json', 'the', 'final', 'xc', 'cross', 'country', 'meet'}


def _sib_tokens(name):
    # ("camdenhillsTeamBoys": camel-case words too)
    stem = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', os.path.splitext(os.path.basename(name))[0])
    toks = set(re.findall(r'[a-z]+|\d+', stem.lower()))
    # ("winslowscores" / "winslowboys": the school word before a suffix)
    for t in list(toks):
        m = re.fullmatch(r'([a-z]{4,}?)(boys|girls|scores?|results?|team|varsity|jv)+', t)
        if m:
            toks.add(m.group(1))
            toks |= set(re.findall(r'boys|girls', t))
    return toks - _SIB_DROP


def _sib_gender(toks):
    g = set()
    for t in toks:
        if t in ('boys', 'boy', 'men', 'b'):
            g.add('B')
        elif t in ('girls', 'girl', 'women', 'g'):
            g.add('G')
    return g


def _xc_verify_with_first_page(path, parsed):
    """A page posted as its own file ("scarboroughboys2": places 53-76
    and the team scores) continues the race in the file beside it
    ("scarboroughboys": places 1-52): the two lists joined are the race."""
    evs = [e for e in parsed.get('events') or [] if isinstance(e, dict) and e.get('results')]
    firsts = [min((r.get('place') or 0) for r in e['results']) for e in evs]
    if not evs or min(firsts) <= 1:
        return None
    d = os.path.dirname(path)
    mine = _sib_tokens(path)
    for fn in sorted(os.listdir(d)):
        q = os.path.join(d, fn)
        if q == path or not fn.endswith('.json'):
            continue
        toks = _sib_tokens(fn)
        if not ({t for t in mine & toks if re.search(r'[a-z]{4}', t)}) or \
                (_sib_gender(mine) and _sib_gender(toks) and not (_sib_gender(mine) & _sib_gender(toks))):
            continue
        try:
            other = json.load(open(q))
        except Exception:
            continue
        joined, hit = [], False
        for e, f0 in zip(evs, firsts):
            prev = next((o for o in other.get('events') or [] if isinstance(o, dict) and
                         o.get('gender') == e.get('gender') and o.get('results') and
                         max((r.get('place') or 0) for r in o['results']) == f0 - 1), None)
            if prev:
                hit = True
                joined.append(dict(e, results=prev['results'] + e['results']))
            else:
                joined.append(e)
        if hit:
            w = xc_verify_parsed(dict(parsed, events=joined))
            if w and w.get('status') in ('verified', 'verified_close'):
                return dict(w, sibling=fn + ' (first page)')
    return None


def xc_verify_file(path):
    """xc_verify_parsed for one parsed file; a file that holds only the team
    scores ("...-Boys-Team.txt", "...Scores_sept11") is checked against the
    race posted beside it: the sibling file in the same folder whose name
    shares the most words (same gender word), whichever verifies best."""
    try:
        parsed = json.load(open(path))
    except Exception:
        return None
    _XC_CTX.clear()
    m = re.search(r'(\d{4})[/\\]XC[/\\]', path)
    if m:
        _XC_CTX.update(year=m.group(1), meet=os.path.basename(path))
    v = xc_verify_parsed(parsed)
    if v and v.get('status') not in ('verified', 'xc_no_results'):
        w = _xc_verify_with_first_page(path, parsed)
        if w:
            return w
    own_n = sum(len(e.get('results') or []) for e in parsed.get('events') or [] if isinstance(e, dict))
    # (a score sheet listing only each team's runners, "TEAM SCORE -> 35"
    # under them, beside the full results file: the full race checks it)
    upgrade = bool(v) and v.get('status') in ('mismatch', 'verified_close') and own_n and \
        re.search(r'(?i)scor|team', os.path.basename(path))
    if not upgrade and (not v or v.get('status') != 'xc_no_results'):
        return v
    orig = v
    d = os.path.dirname(path)
    mine = _sib_tokens(path)
    g_mine = _sib_gender(mine)
    cands = []
    for fn in os.listdir(d):
        q = os.path.join(d, fn)
        if q == path or not fn.endswith('.json'):
            continue
        toks = _sib_tokens(fn)
        g = _sib_gender(toks)
        if g_mine and g and not (g & g_mine):
            # (files posted under each other's names: "...3sept04boys.htm"
            # holding the girls' race) - the race inside decides
            try:
                evg = {str(e.get('gender') or '')[:1] for e in json.load(open(q)).get('events') or []
                       if isinstance(e, dict) and e.get('results')}
            except Exception:
                evg = set()
            if not (evg & g_mine):
                continue
        # (a shared year / generic word is no tie: "HS_MEET_9_11_2015")
        shared = {t for t in mine & toks if not re.fullmatch(r'\d{4}|boys?|girls?|men|women|home|hs|ms|varsity|v|jv|b|g|\d', t)}
        # (a name typed two ways: "scarbrough" / "scarborough")
        import difflib
        shared |= {a for a in mine for b2 in toks if a != b2 and len(a) >= 6 and len(b2) >= 6 and
                   difflib.SequenceMatcher(None, a, b2).ratio() >= 0.9}
        # (a shared date alone is no tie either: "biddefordgirls9_13" / "belfast9_13")
        common = len(shared) if any(re.search(r'[a-z]{3}', t) for t in shared) else 0
        if common:
            cands.append((common / len(mine | toks), q))
    best = v
    rank = {'verified': 0, 'verified_close': 1, 'mismatch': 2, 'xc_unpaired': 3, 'xc_no_results': 4}
    for _sim, q in sorted(cands, reverse=True)[:6]:
        try:
            other = json.load(open(q))
        except Exception:
            continue
        if not isinstance(other, dict) or not any(isinstance(e, dict) and e.get('results')
                                                  for e in other.get('events') or []):
            continue
        if upgrade and sum(len(e.get('results') or []) for e in other.get('events') or []
                           if isinstance(e, dict)) <= own_n:
            continue
        blocks = [{k: x for k, x in b.items() if k != 'event_idx'}
                  for b in parsed.get('team_rankings') or [] if isinstance(b, dict) and b.get('kind') == 'xc']
        w = xc_verify_parsed(dict(other, team_rankings=blocks))
        if w and rank.get(w['status'], 9) < rank.get(best['status'], 9):
            best = dict(w, sibling=os.path.basename(q))
            if w['status'] == 'verified':
                break
    # one score file for both races ("winslowscores9_5": BOYS and GIRLS
    # tables) beside one race file per gender: the two races together
    gens = {b.get('gender') for b in parsed.get('team_rankings') or [] if isinstance(b, dict)
            and b.get('kind') == 'xc'}
    if len(gens - {None}) >= 2 and len(cands) >= 2 and (best.get('races') or 0) < len(gens - {None}):
        # (a single sibling holds one race: the other block went unchecked)
        best = v
        top = sorted(cands, reverse=True)
        evs, names = [], []
        for _sim, q in top[:4]:
            try:
                other = json.load(open(q))
            except Exception:
                continue
            got = [e for e in (other.get('events') or []) if isinstance(e, dict) and e.get('results')]
            if got and not ({e.get('gender') for e in got} & {e.get('gender') for e in evs}):
                evs += got
                names.append(os.path.basename(q))
        if len(names) >= 2:
            blocks = [{k: x for k, x in b.items() if k != 'event_idx'}
                      for b in parsed.get('team_rankings') or [] if isinstance(b, dict) and b.get('kind') == 'xc']
            w = xc_verify_parsed({'events': evs, 'team_rankings': blocks})
            if w and rank.get(w['status'], 9) < rank.get(best['status'], 9):
                best = dict(w, sibling=' + '.join(names))
    if upgrade:
        return best if best and best.get('status') == 'verified' and best is not orig else orig
    return best
