"""Rows lost per (year, season, meet) between HEAD's store and the working store."""
import gzip, json, os, subprocess, sys, collections, glob
os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
scope = json.load(open('backend/data/meet_scope.json'))
moved = set(scope['summer']) | set(scope['excluded'])
def rows(blob):
    return json.loads(gzip.decompress(blob)) if blob else []
head = subprocess.run(['git', 'ls-tree', '-r', '--name-only', 'HEAD', 'ui/public/data/teams'], capture_output=True, text=True).stdout.split()
work = set(glob.glob('ui/public/data/teams/*/*.json.gz'))
LOSTROWS = []; lost = collections.Counter(); gained = collections.Counter(); ex = {}
for path in sorted(set(head) | work):
    key = os.path.basename(path).split('.')[0]          # 2018_Indoor
    if '_' not in key:
        continue                                        # a team's index file
    y, s = key.split('_', 1)
    old = subprocess.run(['git', 'show', f'HEAD:{path}'], capture_output=True).stdout if path in head else b''
    new = open(path, 'rb').read() if os.path.exists(path) else b''
    if old == new:
        continue
    a = collections.Counter((r.get('meet_name'), r.get('event'), r.get('athlete_name'), r.get('mark')) for r in rows(old))
    b = collections.Counter((r.get('meet_name'), r.get('event'), r.get('athlete_name'), r.get('mark')) for r in rows(new))
    for k, n in (a - b).items():
        lost[(y, s, k[0])] += n; ex.setdefault((y, s, k[0]), (path, k)); LOSTROWS.append((y, s, k, n))
    for k, n in (b - a).items():
        gained[(y, s, k[0])] += n
tot_l = sum(lost.values()); print('rows lost', tot_l, 'gained', sum(gained.values()))
cat = collections.Counter()
for (y, s, m), n in lost.items():
    k = f'{y}_{s}_{m}'
    cat['meet_scope (summer/excluded)' if k in moved else ('XC' if s == 'XC' else 'track other')] += n
print(dict(cat))
print('track meets losing rows (not in meet_scope), net = gained - lost:')
net = {k: n - gained.get(k, 0) for k, n in lost.items()}
print('net track loss outside meet_scope:', sum(v for k, v in net.items() if k[1] != 'XC' and f'{k[0]}_{k[1]}_{k[2]}' not in moved and v > 0))
for (y, s, m), n in sorted(lost.items(), key=lambda x: -(x[1] - gained.get(x[0], 0))):
    if s == 'XC' or f'{y}_{s}_{m}' in moved or n - gained.get((y, s, m), 0) <= 5: continue
    print(f'  {n:5} lost {gained.get((y,s,m),0):5} gained  {y} {s} {m}   e.g. {ex[(y,s,m)][1][1:]} [{ex[(y,s,m)][0].split("/")[-2]}]')

import re
net_keys = {k for k, n in lost.items() if k[1] != 'XC' and f'{k[0]}_{k[1]}_{k[2]}' not in moved and n - gained.get(k, 0) > 0}
kinds = collections.Counter()
other = []
for y, s_, k, n in LOSTROWS:
    if (y, s_, k[0]) not in net_keys: continue
    if re.fullmatch(r'\d{1,2}:\d{2}:\d{2}(\.\d+)?', str(k[3]).strip()): kinds['clock time in a race'] += n
    else: kinds['other'] += n; other.append((y, s_, k, n))
print(dict(kinds))
for o in other[:25]: print('  ', o)
