"""
track_audit.py - a sampled, agent-read audit of indoor/outdoor meets.

Code checks (team-score verification, school consistency) cover what they
can; a reader comparing the source file with what the site stores catches
the rest. This module picks the sample and hands each reader a bundle;
docs/agents/track-audit.md is the reader's procedure.

    python3 -m backend.track_audit sample --per-year 3 --seed 2026 --out DIR
        stratified by year and verification status: per year one meet that
        still mismatches its official scores, one with no scores to check,
        one verified (a control); seasons alternate
    python3 -m backend.track_audit collect DIR     # findings -> summary JSON

Each bundle DIR/<key>/ holds meta.json (source file, season, date,
verification) and stored.json (every stored row of the meet, by event).
The reader writes DIR/<key>/findings.json.
"""

import argparse
import collections
import glob
import gzip
import json
import os
import random
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
DATA = os.path.join(BASE, 'backend', 'data')
TEAMS = os.path.join(BASE, 'ui', 'public', 'data', 'teams')


def _verification():
    with open(os.path.join(DATA, 'meet_verification.json'), encoding='utf-8') as f:
        return json.load(f)


def _stored_rows():
    """(year_season, meet_name) -> stored rows."""
    out = collections.defaultdict(list)
    for team in os.listdir(TEAMS):
        d = os.path.join(TEAMS, team)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith('.json.gz') or fn.endswith('_XC.json.gz'):
                continue
            key = fn[:-8]
            with gzip.open(os.path.join(d, fn), 'rt', encoding='utf-8') as f:
                for r in json.load(f):
                    out[(key, r.get('meet_name'))].append(dict(
                        team_folder=team, athlete=r.get('athlete_name'), event=r.get('event'),
                        mark=r.get('mark'), grade=r.get('grade'), date=(r.get('date') or '')[:10]))
    return out


def sample(per_year, seed, out_dir):
    ver = _verification()
    rng = random.Random(seed)
    pools = collections.defaultdict(lambda: collections.defaultdict(list))
    for k, v in ver.items():
        m = re.match(r'(\d{4})_(Indoor|Outdoor)_(.+)$', k)
        if not m:
            continue
        st = v.get('status')
        cls = 'mismatch' if st == 'mismatch' else 'unscored' if st in ('no_rankings', 'scores_only') else \
            'verified' if st in ('verified', 'verified_close') else None
        if cls:
            pools[m.group(1)][(cls, m.group(2))].append(k)
    stored = _stored_rows()
    picks = []
    for i, year in enumerate(sorted(pools)):
        order = ['mismatch', 'unscored', 'verified'][:per_year]
        while len(order) < per_year:
            order.append(order[len(order) % 3])
        for j, cls in enumerate(order):
            season = ('Outdoor', 'Indoor')[(i + j) % 2]
            cands = pools[year][(cls, season)] or pools[year][(cls, ('Indoor', 'Outdoor')[(i + j + 1) % 2])]
            cands = [c for c in sorted(cands) if c not in picks and
                     stored.get((f"{c.split('_')[0]}_{c.split('_')[1]}", c.split('_', 2)[2]))]
            if cands:
                picks.append(rng.choice(cands))
    os.makedirs(out_dir, exist_ok=True)
    for k in picks:
        year, season, stem = k.split('_', 2)
        src = sorted(glob.glob(os.path.join(DATA, 'sub5_archive', year, season, glob.escape(stem) + '.*')))
        rows = stored.get((f'{year}_{season}', stem), [])
        by_event = collections.defaultdict(list)
        for r in rows:
            by_event[r['event']].append({x: r[x] for x in ('athlete', 'team_folder', 'mark', 'grade', 'date')})
        d = os.path.join(out_dir, k)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'meta.json'), 'w') as f:
            json.dump(dict(key=k, year=year, season=season, source_files=src, stored_rows=len(rows),
                           verification=ver.get(k)), f, indent=1)
        with open(os.path.join(d, 'stored.json'), 'w') as f:
            json.dump(by_event, f, indent=0)
    print(json.dumps(dict(sampled=len(picks), keys=picks), indent=1))
    return picks


def collect(out_dir):
    kinds = collections.Counter()
    meets = []
    for d in sorted(glob.glob(os.path.join(out_dir, '*', 'findings.json'))):
        try:
            with open(d) as f:
                fd = json.load(f)
        except (OSError, ValueError):
            continue
        for x in fd.get('findings', []):
            kinds[x.get('kind')] += x.get('rows', 1) or 1
        meets.append(dict(key=fd.get('key'), verdict=fd.get('verdict'), n=len(fd.get('findings', []))))
    summary = dict(meets=len(meets), by_verdict=dict(collections.Counter(m['verdict'] for m in meets)),
                   rows_by_kind=dict(kinds.most_common()), detail=meets)
    with open(os.path.join(out_dir, 'summary.json'), 'w') as f:
        json.dump(summary, f, indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != 'detail'}, indent=1))
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('sample')
    s.add_argument('--per-year', type=int, default=3)
    s.add_argument('--seed', type=int, default=2026)
    s.add_argument('--out', required=True)
    c = sub.add_parser('collect')
    c.add_argument('dir')
    a = ap.parse_args()
    if a.cmd == 'sample':
        sample(a.per_year, a.seed, a.out)
    else:
        collect(a.dir)


if __name__ == '__main__':
    main()
