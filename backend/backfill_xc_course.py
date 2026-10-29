"""backfill_xc_course.py - repoint stored XC `course` values at the real venue.

Result files carry no venue of their own in ~95% of cases, so the scraper used
to fall back to the filename stem ("Results-F1-3", "focboysheats"), which names
no place. The sub5 season index tables carry an explicit venue column; this
backfill applies that mapping to rows already in the store, so the course model
can be rebuilt without a full re-scrape.

Course identity, best source first:
    1. venue column from the season index page   (web_meet_mapping.json)
    2. venue recorded in the parsed result file   (parser / Hy-Tek header)
    3. meet name from the season index page       ("... at Scarborough")
    4. the filename stem                          (last resort, unchanged)

Usage:  python -m backend.backfill_xc_course [--dry-run]
"""

import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.json_store import (TEAMS_DIR, _chunk_files, _load_json,
                                _atomic_write)

HERE = os.path.dirname(os.path.abspath(__file__))
PARSED_DIR = os.path.join(HERE, 'data', 'parsed_results')


def load_index_mapping():
    path = os.path.join(HERE, 'web_meet_mapping.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_file_venues():
    """venue recorded inside each parsed result file, keyed '<year>/XC/<stem>'."""
    out = {}
    if not os.path.isdir(PARSED_DIR):
        return out
    for year in sorted(os.listdir(PARSED_DIR)):
        xc_dir = os.path.join(PARSED_DIR, year, 'XC')
        if not os.path.isdir(xc_dir):
            continue
        for fn in os.listdir(xc_dir):
            if not fn.endswith('.json'):
                continue
            try:
                with open(os.path.join(xc_dir, fn), encoding='utf-8') as f:
                    d = json.load(f)
            except Exception:
                continue
            if isinstance(d, dict) and d.get('venue'):
                out[f'{year}/XC/{fn[:-5]}'] = d['venue']
    return out


def resolve(year, stem, index_map, file_venues):
    for ext in ('.htm', '.html', '.pdf', '.txt', ''):
        entry = index_map.get(f'{year}/XC/{stem}{ext}')
        if entry and entry.get('venue'):
            return entry['venue'], 'index-venue'
    fv = file_venues.get(f'{year}/XC/{stem}')
    if fv:
        return fv, 'file-venue'
    # A meet name is only usable when it names the host ("... at Scarborough");
    # otherwise it is a label, not a place, and must not become a course.
    for ext in ('.htm', '.html', '.pdf', '.txt', ''):
        entry = index_map.get(f'{year}/XC/{stem}{ext}')
        if entry and entry.get('meet'):
            m = re.search(r'\bat\s+([A-Z][\w.\'-]*(?:\s+[A-Z][\w.\'-]*){0,3})',
                          entry['meet'])
            if m:
                return m.group(1).strip(), 'index-meet-at'
    return None, 'unresolved'


def main(dry_run=False):
    index_map = load_index_mapping()
    file_venues = load_file_venues()
    print(f'{len(index_map):,} index entries, {len(file_venues):,} file venues')

    src = Counter()
    changed_rows = changed_files = 0
    for team_dir_name in sorted(os.listdir(TEAMS_DIR)):
        d = os.path.join(TEAMS_DIR, team_dir_name)
        if not os.path.isdir(d):
            continue
        for key, chunk in _chunk_files(d):
            if not key.endswith('_XC'):
                continue
            year = key.partition('_')[0]
            path = os.path.join(d, chunk)
            rows = _load_json(path, [])
            dirty = False
            for p in rows:
                stem = p.get('meet_name') or ''
                if not stem:
                    continue
                venue, how = resolve(year, stem, index_map, file_venues)
                src[how] += 1
                if venue is None:
                    # last resort: the filename stem, same as the scraper. Set
                    # it explicitly so a stale value from an earlier pass with
                    # a looser fallback cannot survive here.
                    venue = stem
                if venue != p.get('course'):
                    p['course'] = venue
                    dirty = True
                    changed_rows += 1
            if dirty and not dry_run:
                _atomic_write(path, rows)
                changed_files += 1
            elif dirty:
                changed_files += 1

    print(f'\nrows by course source: {dict(src)}')
    total = sum(src.values())
    if total:
        named = total - src['unresolved']
        print(f'{named:,}/{total:,} XC rows ({named * 100 // total}%) now carry a real venue')
    print(f'{"would update" if dry_run else "updated"}: '
          f'{changed_rows:,} rows in {changed_files:,} chunk files')


if __name__ == '__main__':
    main(dry_run='--dry-run' in sys.argv)
