"""before/ vs after/: rows the sync will keep, per canonical event.
Flags any file where a canonical event loses kept rows."""
import glob, json, os, sys, collections
sys.path.insert(0, '/home/james-longo/Projects/gsaxctf')
from backend.event_canon import canonical_event
B, A = sys.argv[1], sys.argv[2]

def kept(path, season):
    try:
        d = json.load(open(path))
    except FileNotFoundError:
        return collections.Counter(), 0
    evs = d.get('events', []) if isinstance(d, dict) else d
    c = collections.Counter(); total = 0
    for e in evs:
        if not isinstance(e, dict):
            continue
        n = len(e.get('results') or []); total += n
        g = e.get('gender') or 'Boys'
        ce = canonical_event(e.get('event', ''), {'Women': 'Girls', 'Men': 'Boys'}.get(g, g), season=season)
        c[ce if ce else ('DROPPED',)] += n
    return c, total

changed, flagged = [], []
for f in sorted(glob.glob(B + '/*/*/*.json')):
    rel = os.path.relpath(f, B); season = rel.split('/')[1]
    if open(f).read() == (open(os.path.join(A, rel)).read() if os.path.exists(os.path.join(A, rel)) else ''):
        continue
    b, tb = kept(f, season); a, ta = kept(os.path.join(A, rel), season)
    losses = {str(k): (b[k], a.get(k, 0)) for k in b if k != ('DROPPED',) and a.get(k, 0) < b[k]}
    kb = sum(v for k, v in b.items() if k != ('DROPPED',)); ka = sum(v for k, v in a.items() if k != ('DROPPED',))
    changed.append(dict(rel=rel, rows=(tb, ta), kept=(kb, ka), losses=losses))
    if losses:
        flagged.append(changed[-1])
print(len(changed), 'files changed; kept rows', sum(c['kept'][0] for c in changed), '->', sum(c['kept'][1] for c in changed))
print(len(flagged), 'files where some event loses kept rows:')
for c in sorted(flagged, key=lambda c: c['kept'][1] - c['kept'][0]):
    print(f"  {c['rel']:60} kept {c['kept'][0]:5} -> {c['kept'][1]:5}  ", dict(list(c['losses'].items())[:4]))
json.dump(changed, open(os.path.join(os.path.dirname(A), 'changed2.json'), 'w'))
