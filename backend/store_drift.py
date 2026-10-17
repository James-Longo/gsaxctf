"""Store drift: team-seasons that lost results since the last commit.

A rebuild that moves rows between teams (a school-name rule, a catalog
change) shows up here before it is published: every team-season whose row
count fell, biggest drop first. Each big drop needs a reason (rows moved to
the right school, a duplicate removed) before the data is pushed.

usage: python3 -m backend.store_drift [min_loss]   (default 10)
"""
import gzip, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEAMS = 'ui/public/data/teams'


def head_files():
    out = subprocess.run(['git', '-C', ROOT, 'ls-tree', '-r', '--name-only', 'HEAD', TEAMS],
                         capture_output=True, text=True).stdout.split()
    return [p for p in out if p.endswith('.json.gz')]


def count_head(path):
    raw = subprocess.run(['git', '-C', ROOT, 'show', f'HEAD:{path}'], capture_output=True).stdout
    return len(json.loads(gzip.decompress(raw)))


def count_now(path):
    p = os.path.join(ROOT, path)
    return len(json.load(gzip.open(p))) if os.path.exists(p) else 0


rows = []
for p in head_files():
    a = count_head(p)
    b = count_now(p)
    if b < a:
        rows.append((a - b, a, b, p))
rows.sort(reverse=True)
min_loss = int(sys.argv[1]) if len(sys.argv) > 1 else 10
for loss, a, b, p in rows:
    if loss >= min_loss:
        print(f'{loss:6} {a:6} -> {b:6}  {p[len(TEAMS) + 1:]}')
print(len(rows), 'team-seasons lost rows;', sum(r[0] for r in rows), 'rows in all')
