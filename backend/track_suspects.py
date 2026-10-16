"""
track_suspects.py - which unscored track files most need a reader.

About a third of the indoor/outdoor files print no official team scores, so
the score check (track_verify.py) can't vouch for them. These checks need no
scores; each file gets a suspicion score from:

  order      places and marks disagree (3rd faster than 2nd), share of rows
  plausible  marks outside what the event allows (a 9.0 1600m, a 70-ft long jump)
  status     share of rows that are only a status (a parse that read the
             wrong column stores DQ/NT everywhere)
  thin       events with a single row (a page the parser lost)
  schools    groups school_consistency.py flags in this meet

    python3 -m backend.track_suspects [--top 40] [--json out.json]
"""

import argparse
import collections
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
PARSED = os.path.join(BASE, 'backend', 'data', 'parsed_results')

# rough bounds (seconds or inches) per event family, generous: a flag means
# "look", not "wrong"
BOUNDS = [
    (re.compile(r'\b(50|55|60)\b.*(dash|meter|yard)', re.I), 5.5, 12.0),
    (re.compile(r'\b100 meter dash', re.I), 9.5, 22.0),
    (re.compile(r'\b200 meter dash', re.I), 19.5, 45.0),
    (re.compile(r'\b400 meter dash', re.I), 43.0, 110.0),
    (re.compile(r'\b800 meter run', re.I), 100.0, 300.0),
    (re.compile(r'\b(1600 meter|1 mile) run', re.I), 230.0, 720.0),
    (re.compile(r'\b(3200 meter|2 mile) run', re.I), 500.0, 1500.0),
    (re.compile(r'long jump', re.I), 96.0, 300.0),
    (re.compile(r'triple jump', re.I), 200.0, 600.0),
    (re.compile(r'high jump', re.I), 36.0, 90.0),
    (re.compile(r'shot put', re.I), 120.0, 900.0),
]
STATUS = {'DQ', 'DNF', 'DNS', 'NH', 'NM', 'FOUL', 'SCR', 'FAIL', 'FS', 'ND', 'NT'}
FIELD = re.compile(r'jump|vault|put|throw|discus|javelin|hammer', re.I)


def _val(mark, event):
    from backend.json_store import parse_mark_value
    try:
        v, _ = parse_mark_value(mark, event)
        return v
    except Exception:  # noqa: BLE001
        return None


def score_file(d):
    rows = order_bad = order_n = implaus = status = thin = 0
    for e in d.get('events') or []:
        if not isinstance(e, dict) or e.get('is_relay'):
            continue
        res = [r for r in e.get('results') or [] if r.get('type') != 'Seed']
        if not res:
            continue
        ev = e.get('event') or ''
        rows += len(res)
        if len(res) == 1:
            thin += 1
        status += sum(1 for r in res if (r.get('result') or '').upper() in STATUS)
        field = bool(FIELD.search(ev))
        placed = [(r['place'], _val(r.get('result', ''), ev)) for r in res
                  if isinstance(r.get('place'), int) and r.get('type', 'Finals') == 'Finals']
        placed = [(p, v) for p, v in placed if v]
        placed.sort()
        for (p1, v1), (p2, v2) in zip(placed, placed[1:]):
            if p2 > p1:
                order_n += 1
                if (v2 > v1 + 1e-9) if field else (v2 < v1 - 1e-9):
                    order_bad += 1
        for pat, lo, hi in BOUNDS:
            if pat.search(ev):
                for r in res:
                    v = _val(r.get('result', ''), ev)
                    if v and not (lo <= v <= hi):
                        implaus += 1
                break
    if not rows:
        return None
    return dict(rows=rows, order=round(order_bad / order_n, 3) if order_n else 0.0,
                implausible=round(implaus / rows, 3), status=round(status / rows, 3), thin_events=thin)


def suspects(scores_only_unscored=True):
    ver = json.load(open(os.path.join(BASE, 'backend', 'data', 'meet_verification.json')))
    out = []
    for year in sorted(os.listdir(PARSED)):
        for season in ('Indoor', 'Outdoor'):
            dd = os.path.join(PARSED, year, season)
            if not os.path.isdir(dd):
                continue
            for fn in os.listdir(dd):
                key = f'{year}_{season}_{fn[:-5]}'
                st = (ver.get(key) or {}).get('status')
                if scores_only_unscored and st not in ('no_rankings', 'scores_only', None):
                    continue
                try:
                    d = json.load(open(os.path.join(dd, fn)))
                except (OSError, ValueError):
                    continue
                s = score_file(d if isinstance(d, dict) else {'events': d})
                if s:
                    s['key'] = key
                    s['suspicion'] = round(3 * s['order'] + 4 * s['implausible'] + 2 * s['status']
                                           + 0.2 * min(s['thin_events'], 10), 3)
                    out.append(s)
    out.sort(key=lambda s: -s['suspicion'])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--top', type=int, default=40)
    ap.add_argument('--json')
    a = ap.parse_args()
    out = suspects()
    bands = collections.Counter('high' if s['suspicion'] >= 1 else 'some' if s['suspicion'] >= 0.3 else 'low'
                                for s in out)
    print(f'{len(out)} unscored track files: {dict(bands)}')
    for s in out[:a.top]:
        print(f"  {s['suspicion']:5.2f} {s['key'][:60]:60s} rows={s['rows']:4d} order={s['order']:.2f} "
              f"implaus={s['implausible']:.2f} status={s['status']:.2f} thin={s['thin_events']}")
    if a.json:
        with open(a.json, 'w') as f:
            json.dump(out, f, indent=1)


if __name__ == '__main__':
    main()
