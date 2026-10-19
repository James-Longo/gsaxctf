"""List Indoor/Outdoor rows outside predictor BOUNDS, grouped by meet."""
import collections, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from backend import json_store as js
from backend.predictor_data import BOUNDS, TRACK, FIELD
EV = {f'{g} {e}' for g in ('Boys', 'Girls') for e in TRACK + FIELD}
out = []
total = collections.Counter()
for team in js.list_teams():
    d = js.team_dir(team)
    if not os.path.isdir(d):
        continue
    for key, fn in js._chunk_files(d):
        if not key.endswith(('Indoor', 'Outdoor')):
            continue
        for p in js.enrich_rows(team, key, js._load_json(os.path.join(d, fn), [])):
            ev = p.get('event')
            if ev not in EV:
                continue
            v, _ = js.parse_mark_value(p.get('mark'), ev)
            if v is None:
                continue
            total[ev] += 1
            lo, hi = BOUNDS[ev.split(' ', 1)[1]]
            if not lo <= v <= hi:
                out.append(dict(team=team, key=key, meet=p.get('meet_name'), event=ev,
                                athlete=p.get('athlete_name'), mark=p.get('mark'), value=v,
                                side='low' if v < lo else 'high'))
json.dump(dict(rows=out, total=total), open(sys.argv[1], 'w'))
by_ev = collections.Counter((r['event'], r['side']) for r in out)
print(len(out), 'rows out of bounds of', sum(total.values()))
for (e, s), n in sorted(by_ev.items(), key=lambda x: -x[1])[:30]:
    print(f'{n:6} {s:4} {e}  ({100*n/total[e]:.2f}%)')
