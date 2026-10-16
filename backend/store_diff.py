"""
store_diff.py - what a rebuild changed in the store, meet by meet.

Compares two copies of ui/public/data/teams (by default the committed store
in git HEAD against the working tree) and sorts every difference into a kind:

  meet_only_old / meet_only_new  a whole meet present on one side only
                                 (the double-ingest guard kept another copy,
                                 or a file stopped / started parsing)
  moved_team                     same row, another team folder
  date                           same row, another date
  event                          same row, another event (gender, name)
  name                           same mark/event/date, another athlete name
  mark                           same athlete/event/date, another mark
  added / removed                anything else

    python3 -m backend.store_diff                    # HEAD vs working tree
    python3 -m backend.store_diff --old DIR --new DIR [--json out.json]
"""

import argparse
import collections
import gzip
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEAMS = os.path.join(BASE, 'ui', 'public', 'data', 'teams')


def _rows_from_dir(root):
    out = []
    for team in sorted(os.listdir(root)):
        d = os.path.join(root, team)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith('.json.gz'):
                key = fn[:-8]
                with gzip.open(os.path.join(d, fn), 'rt', encoding='utf-8') as f:
                    out.extend((team, key, r) for r in json.load(f))
    return out


def _rows_from_git(rev='HEAD'):
    """The committed store, read straight from git (no checkout)."""
    ls = subprocess.run(['git', 'ls-tree', '-r', '--name-only', rev, '--', 'ui/public/data/teams'],
                        cwd=BASE, capture_output=True, text=True, check=True).stdout.split()
    files = [p for p in ls if p.endswith('.json.gz')]
    # one cat-file process for every blob
    proc = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=BASE,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    out = []
    for p in files:
        proc.stdin.write(f'{rev}:{p}\n'.encode())
        proc.stdin.flush()
        header = proc.stdout.readline().split()
        size = int(header[2])
        blob = proc.stdout.read(size)
        proc.stdout.read(1)
        _, _, _, _, team, fn = p.split('/', 5)
        out.extend((team, fn[:-8], r) for r in json.loads(gzip.decompress(blob)))
    proc.stdin.close()
    proc.wait()
    return out


def _meet(key, r):
    return (key, r.get('meet_name') or '')


def diff(old_rows, new_rows):
    def index(rows):
        by_meet = collections.defaultdict(list)
        for team, key, r in rows:
            by_meet[_meet(key, r)].append((team, r))
        return by_meet
    old, new = index(old_rows), index(new_rows)
    kinds = collections.Counter()
    per_meet = {}
    for m in sorted(set(old) | set(new)):
        a, b = old.get(m, []), new.get(m, [])
        if not a or not b:
            k = 'meet_only_old' if a else 'meet_only_new'
            kinds[k] += len(a or b)
            per_meet[m] = {k: len(a or b)}
            continue
        full = lambda t, r: (t, r.get('athlete_name'), r.get('event'), r.get('mark'), r.get('date'))
        ca = collections.Counter(full(t, r) for t, r in a)
        cb = collections.Counter(full(t, r) for t, r in b)
        ra, rb = ca - cb, cb - ca
        if not ra and not rb:
            continue
        mk = collections.Counter()
        # pair leftovers by progressively looser keys
        for kind, keyf in (('moved_team', lambda x: x[1:]),
                           ('date', lambda x: (x[0], x[1], x[2], x[3])),
                           ('event', lambda x: (x[0], x[1], x[3], x[4])),
                           ('name', lambda x: (x[0], x[2], x[3], x[4])),
                           ('mark', lambda x: (x[0], x[1], x[2], x[4]))):
            ia = collections.defaultdict(list)
            for x, n in ra.items():
                ia[keyf(x)].extend([x] * n)
            for y in list(rb.elements()):
                cands = ia.get(keyf(y))
                if cands:
                    x = cands.pop()
                    ra[x] -= 1
                    rb[y] -= 1
                    mk[kind] += 1
            ra, rb = +ra, +rb
        if ra:
            mk['removed'] += sum(ra.values())
        if rb:
            mk['added'] += sum(rb.values())
        kinds.update(mk)
        per_meet[m] = dict(mk)
    return kinds, per_meet


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--old', help='store dir (default: git HEAD)')
    ap.add_argument('--new', default=TEAMS, help='store dir (default: working tree)')
    ap.add_argument('--json', help='write per-meet differences here')
    ap.add_argument('--top', type=int, default=25)
    a = ap.parse_args()
    old = _rows_from_dir(a.old) if a.old else _rows_from_git()
    new = _rows_from_dir(a.new)
    kinds, per_meet = diff(old, new)
    print(f'{len(old):,} rows -> {len(new):,} rows; {len(per_meet)} meets differ')
    for k, n in kinds.most_common():
        print(f'  {k:14s} {n:,}')
    for (key, meet), d in sorted(per_meet.items(), key=lambda x: -sum(x[1].values()))[:a.top]:
        print(f'  {key:14s} {meet[:50]:50s} {d}')
    if a.json:
        with open(a.json, 'w') as f:
            json.dump([dict(key=k, meet=m, **d) for (k, m), d in per_meet.items()], f, indent=1)


if __name__ == '__main__':
    sys.exit(main())
