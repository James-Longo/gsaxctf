"""
json_store.py - JSON-based data store replacing SQLite.

Data lives in ui/public/data/teams/{TeamSlug}.json.
Each team file is a flat list of performance records.
PR flags (was_pr, is_pr, is_sb) are pre-computed and stored with each record.
"""

import json
import os
import re
import hashlib
import tempfile
import shutil

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'ui', 'public', 'data')
TEAMS_DIR = os.path.join(DATA_DIR, 'teams')
ATHLETES_PATH = os.path.join(DATA_DIR, 'athletes.json')
MANIFEST_PATH = os.path.join(DATA_DIR, 'manifest.json')
SCRAPE_STATE_PATH = os.path.join(BASE_DIR, 'backend', 'data', 'scrape_state.json')

# ---------------------------------------------------------------------------
# Slugify helpers
# ---------------------------------------------------------------------------

def slugify_team(name: str) -> str:
    """'George Stevens Academy' -> 'George_Stevens_Academy'"""
    name = re.sub(r'[^\w\s]', '', name)
    return re.sub(r'\s+', '_', name.strip())


def slugify_athlete(name: str, team: str) -> str:
    """Stable athlete ID: 'James Longo' + 'GSA' -> 'james-longo--george-stevens-academy'"""
    raw = f"{name.lower()}--{team.lower()}"
    raw = re.sub(r'[^\w]', '-', raw)
    return re.sub(r'-+', '-', raw).strip('-')


def make_perf_id(athlete_id: str, event: str, mark: str, date: str, meet: str) -> str:
    key = f"{athlete_id}|{event}|{mark}|{date}|{meet}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Mark parsing (mirrors utils.js parseMark)
# ---------------------------------------------------------------------------

BAD_MARKS = {'DQ', 'DNS', 'DNF', 'NH', 'NM', 'FOUL', 'SCR', 'ND', 'NT', 'X', 'NWI'}

DISTANCE_KEYWORDS = ['jump', 'put', 'throw', 'vault', 'discus', 'javelin']


def is_distance_event(event_name: str) -> bool:
    if not event_name:
        return False
    return any(k in event_name.lower() for k in DISTANCE_KEYWORDS)


def parse_mark_value(mark: str, event_name: str = "") -> tuple:
    """
    Returns (numeric_value, is_distance) or (None, None) if unparseable/invalid.
    Times -> total seconds (lower is better).
    Distances -> total inches (higher is better).
    """
    if not mark:
        return None, None
    m = str(mark).strip().upper()
    if m in BAD_MARKS or any(m.startswith(b) for b in BAD_MARKS):
        return None, None

    force_distance = is_distance_event(event_name)
    has_dist_chars = ("'" in m or '"' in m or
                      (bool(re.search(r'\d-\d', m)) and ':' not in m))

    if force_distance or has_dist_chars:
        # Feet-inches: "19-09.50"  or  "19'9.5\""
        feet = re.match(r"^(\d+)['\-]", m)
        inches = re.search(r"['\-\s](\d+(?:\.\d+)?)", m)
        total = 0.0
        if feet:
            total += int(feet.group(1)) * 12
        if inches:
            total += float(inches.group(1))
        return (total if total > 0 else None), True

    # Time
    cleaned = re.sub(r'[A-Z]+$', '', m)  # strip trailing 'H' for hand-timed
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


def is_better(new_mark: str, old_mark: str, event_name: str = "") -> bool:
    """True if new_mark is a better result than old_mark for this event."""
    nv, nd = parse_mark_value(new_mark, event_name)
    ov, _ = parse_mark_value(old_mark, event_name)
    if nv is None or ov is None:
        return False
    return nv > ov if nd else nv < ov


# ---------------------------------------------------------------------------
# PR / SB Calculation
# ---------------------------------------------------------------------------

def recalculate_prs(performances: list) -> list:
    """
    Compute was_pr, is_pr, and is_sb for a list of performance dicts.

    was_pr : True if this result was a PR at the time it was run
             (better than everything before it for that athlete+event).
             This flag NEVER changes once set — it's a historical record.
    is_pr  : True for the single current best mark per athlete+event.
             Only one record per athlete+event can have is_pr=True.
    is_sb  : True for the best mark per athlete+event+year+season.

    The performances list may contain data from multiple athletes.
    Sorts chronologically, mutates in-place, and returns the list.
    """
    sorted_p = sorted(performances, key=lambda p: p.get('date', ''))

    # --- Pass 1: was_pr and is_sb ---
    running_best: dict = {}   # (athlete_id, event) -> best numeric value
    running_sb: dict = {}     # (athlete_id, event, year, season) -> best value

    for p in sorted_p:
        event = p.get('event', '')
        aid = p.get('athlete_id', '')
        mark = p.get('mark', '')
        year = p.get('year', '')
        season = p.get('season', '')

        val, _ = parse_mark_value(mark, event)

        if val is None:
            p['was_pr'] = False
            p['is_sb'] = False
            p['is_pr'] = False
            continue

        pr_key = (aid, event)
        sb_key = (aid, event, year, season)

        # was_pr
        if pr_key not in running_best:
            p['was_pr'] = True
            running_best[pr_key] = (val, mark)
        else:
            old_val, old_mark = running_best[pr_key]
            if is_better(mark, old_mark, event):
                p['was_pr'] = True
                running_best[pr_key] = (val, mark)
            else:
                p['was_pr'] = False

        # is_sb
        if sb_key not in running_sb:
            p['is_sb'] = True
            running_sb[sb_key] = (val, mark)
        else:
            old_val, old_mark = running_sb[sb_key]
            if is_better(mark, old_mark, event):
                p['is_sb'] = True
                running_sb[sb_key] = (val, mark)
            else:
                p['is_sb'] = False

    # --- Pass 2: is_pr (last was_pr chronologically = current best) ---
    current_pr_id: dict = {}  # (athlete_id, event) -> perf id
    for p in sorted_p:
        if p.get('was_pr'):
            current_pr_id[(p.get('athlete_id'), p.get('event'))] = p['id']

    for p in sorted_p:
        key = (p.get('athlete_id'), p.get('event'))
        p['is_pr'] = (p.get('id') == current_pr_id.get(key))

    return performances


# ---------------------------------------------------------------------------
# Atomic file I/O
# ---------------------------------------------------------------------------

def _atomic_write(path: str, data):
    """Write JSON atomically (write to tmp, then rename) to avoid corruption."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        shutil.move(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_SLUG_TO_CANONICAL = None

def canonical_team_name(dir_name: str) -> str:
    """Map a team directory name back to the canonical team name (with
    punctuation) using the team registry; falls back to underscore->space."""
    global _SLUG_TO_CANONICAL
    if _SLUG_TO_CANONICAL is None:
        _SLUG_TO_CANONICAL = {}
        reg_path = os.path.join(BASE_DIR, 'backend', 'data', 'team_registry.json')
        try:
            reg = _load_json(reg_path, {})
            for canon in reg.get('teams', {}):
                _SLUG_TO_CANONICAL[slugify_team(canon)] = canon
        except Exception:
            pass
    return _SLUG_TO_CANONICAL.get(dir_name, dir_name.replace('_', ' '))


def team_path(team_name: str) -> str:
    """Legacy flat-file path (pre-chunking). Kept for migration reads."""
    return os.path.join(TEAMS_DIR, slugify_team(team_name) + '.json')


def team_dir(team_name: str) -> str:
    return os.path.join(TEAMS_DIR, slugify_team(team_name))


def _chunk_key(p: dict) -> str:
    return f"{p.get('year') or 'Unknown'}_{p.get('season') or 'Unknown'}"


# Fields stripped from stored rows because they're derivable from the chunk
# path (team, year, season) or from other fields (athlete_id, id). Stripping
# them halves the deployed JSON size; enrich_rows() restores them on read.
def slim_row(p: dict) -> dict:
    out = {k: v for k, v in p.items()
           if k not in ('team', 'season', 'year', 'athlete_id', 'id')}
    if not out.get('splits'):
        out.pop('splits', None)
    d = out.get('date', '')
    if isinstance(d, str) and d.endswith('T12:00:00'):
        out['date'] = d[:10]
    return out


def enrich_rows(team_name: str, chunk_key: str, rows: list) -> list:
    """Rebuild the full performance dicts from a slim chunk."""
    year, _, season = chunk_key.partition('_')
    for p in rows:
        p.setdefault('team', team_name)
        p.setdefault('year', year)
        p.setdefault('season', season)
        p.setdefault('splits', [])
        d = p.get('date', '')
        if d and d != 'Unknown' and 'T' not in d:
            p['date'] = d + 'T12:00:00'
        if 'athlete_id' not in p:
            p['athlete_id'] = slugify_athlete(p.get('athlete_name', ''), team_name)
        if 'id' not in p:
            p['id'] = make_perf_id(p['athlete_id'], p.get('event', ''),
                                   p.get('mark', ''), p.get('date', ''),
                                   p.get('meet_name', ''))
    return rows


def load_team(team_name: str) -> list:
    """Load all performances for a team (all season chunks concatenated,
    enriched back to full rows). Falls back to the legacy flat layout."""
    d = team_dir(team_name)
    if os.path.isdir(d):
        perfs = []
        for fn in sorted(os.listdir(d)):
            if fn.endswith('.json'):
                rows = _load_json(os.path.join(d, fn), [])
                perfs.extend(enrich_rows(team_name, fn[:-5], rows))
        return perfs
    return _load_json(team_path(team_name), [])


def save_team(team_name: str, performances: list):
    """Save a team's performances as slimmed per-season chunk files:
    teams/{TeamSlug}/{year}_{season}.json — small enough for the UI to
    lazy-load only the seasons it needs. Stale chunks and the legacy flat
    file are removed."""
    d = team_dir(team_name)
    os.makedirs(d, exist_ok=True)
    by_chunk = {}
    for p in performances:
        by_chunk.setdefault(_chunk_key(p), []).append(slim_row(p))
    for key, perfs in by_chunk.items():
        _atomic_write(os.path.join(d, key + '.json'), perfs)
    wanted = {key + '.json' for key in by_chunk}
    for fn in os.listdir(d):
        if fn.endswith('.json') and fn not in wanted:
            os.remove(os.path.join(d, fn))
    legacy = team_path(team_name)
    if os.path.exists(legacy):
        os.remove(legacy)


def load_athletes() -> dict:
    """Returns { athlete_name: {id, name, primary_team} }"""
    data = _load_json(ATHLETES_PATH, [])
    if isinstance(data, list):
        return {a['name']: a for a in data}
    return data


def save_athletes(athletes: dict):
    """Save athletes as a sorted list (frontend expects array)."""
    arr = sorted(athletes.values(), key=lambda a: a['name'])
    _atomic_write(ATHLETES_PATH, arr)


def load_scrape_state() -> dict:
    """Returns { 'synced_meets': { meet_key: date_str } }"""
    return _load_json(SCRAPE_STATE_PATH, {'synced_meets': {}})


def save_scrape_state(state: dict):
    _atomic_write(SCRAPE_STATE_PATH, state)


def load_manifest() -> dict:
    return _load_json(MANIFEST_PATH, {'teams': [], 'seasons': []})


def save_manifest(manifest: dict):
    _atomic_write(MANIFEST_PATH, manifest)


def list_teams() -> list:
    """Return list of canonical team names from the teams directory
    (chunk dirs, plus any legacy flat files)."""
    if not os.path.exists(TEAMS_DIR):
        return []
    names = []
    for fn in sorted(os.listdir(TEAMS_DIR)):
        full = os.path.join(TEAMS_DIR, fn)
        if os.path.isdir(full):
            names.append(canonical_team_name(fn))
        elif fn.endswith('.json'):
            names.append(canonical_team_name(fn[:-5]))
    return names


# ---------------------------------------------------------------------------
# Performance insertion with dedup + PR recalc
# ---------------------------------------------------------------------------

def add_performances_for_team(team_name: str, new_perfs: list,
                               athletes: dict) -> tuple:
    """
    Merge new_perfs into the existing team file.
    Handles deduplication and recalculates all PR flags after the merge.

    Returns (updated_athletes, inserted_count).
    new_perfs items must have keys:
      athlete_name, athlete_id, event, mark, grade, team,
      date, season, year, meet_name, splits
    (id will be generated here if missing)
    """
    existing = load_team(team_name)
    existing_ids = {p['id'] for p in existing}

    inserted = 0
    for p in new_perfs:
        pid = p.get('id') or make_perf_id(
            p['athlete_id'], p['event'], p['mark'], p['date'], p['meet_name']
        )
        p['id'] = pid
        if pid in existing_ids:
            continue
        existing.append(p)
        existing_ids.add(pid)
        inserted += 1

        # Register athlete
        aname = p['athlete_name']
        if aname and aname not in athletes:
            athletes[aname] = {
                'id': p['athlete_id'],
                'name': aname,
                'primary_team': team_name,
            }

    if inserted > 0:
        recalculate_prs(existing)
        save_team(team_name, existing)

    return athletes, inserted


def rebuild_manifest() -> dict:
    """
    Regenerate manifest.json by scanning all team chunk directories.
    Gathers available seasons (= chunk files), per-team performance counts,
    and each team's level (hs/ms/college) from the team registry.
    """
    registry_teams = {}
    reg_path = os.path.join(BASE_DIR, 'backend', 'data', 'team_registry.json')
    try:
        registry_teams = _load_json(reg_path, {}).get('teams', {})
    except Exception:
        pass

    teams_meta = []
    all_seasons = set()

    for fn in sorted(os.listdir(TEAMS_DIR)):
        full = os.path.join(TEAMS_DIR, fn)
        if not os.path.isdir(full):
            continue
        slug = fn
        team_name = canonical_team_name(fn)
        seasons = []
        count = 0
        has_splits = False
        for chunk_fn in sorted(os.listdir(full)):
            if not chunk_fn.endswith('.json'):
                continue
            key = chunk_fn[:-5]
            perfs = _load_json(os.path.join(full, chunk_fn), [])
            if not perfs:
                continue
            seasons.append(key)
            if 'Unknown' not in key:
                all_seasons.add(key)
            count += len(perfs)
            if not has_splits and any(bool(p.get('splits')) for p in perfs):
                has_splits = True
        teams_meta.append({
            'slug': slug,
            'name': team_name,
            'count': count,
            'seasons': sorted(seasons),
            'has_splits': has_splits,
            'level': registry_teams.get(team_name, {}).get('level', 'hs'),
        })

    manifest = {
        'teams': teams_meta,
        'seasons': sorted(all_seasons),
    }
    save_manifest(manifest)
    return manifest
