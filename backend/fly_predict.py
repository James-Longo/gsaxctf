"""
fly_predict.py - predict GSA sprint times from 20m fly times (internal tool).

Fly times come from the practice sheet (the same Google Sheet main.py's
/practice-results reads). Each session gives the athlete's fastest trial;
grass sessions are converted to track (the grass penalty is fitted from the
sheet each run, ~3%); an athlete's fly for a season is the average of those
sessions on a log scale. Hand (2025) and electronic (2026) times are pooled:
hand sessions scatter ~2.5x more but showed no bias against race times.

Model, per event: race = k x fly, where k is the median race/fly ratio over
every GSA athlete-season with both a fly and a season best in that event.
Held-out checks (leave one athlete-season out) beat a fitted slope, a
girls/boys term and a hand-timing term, so the ratio is all there is. The
+/- printed is the held-out error (about 68% of athletes land inside).

Sheet names are first names only: a name maps to the one GSA athlete of
that first name with a track season that spring; NAMES settles the rest.

Usage
  python3 -m backend.fly_predict                 # everyone, latest season
  python3 -m backend.fly_predict Wyatt Ripley    # these athletes
  python3 -m backend.fly_predict 2.40            # a raw fly time (track)
  python3 -m backend.fly_predict 2.48 --grass    # a raw fly time on grass
  python3 -m backend.fly_predict --season 2025   # a past season
  python3 -m backend.fly_predict --event 200     # one event only
  python3 -m backend.fly_predict --fit           # the ratios, errors, pairs
"""

import argparse
import collections
import csv
import io
import math
import os
import re
import statistics
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import json_store as js  # noqa: E402

SHEET = ('https://docs.google.com/spreadsheets/d/'
         '1fql3yYQs_9OZZmS8-KHDliEPTKl__ZFZ592E8dkZD7Q/export?format=csv')
TEAM = 'George Stevens Academy'
# sheet first name -> store name, where the first name alone is ambiguous
NAMES = {'Owen': 'Owen Hughes'}
EVENTS = ['55 Meter Dash', '100 Meter Dash', '200 Meter Dash', '400 Meter Dash',
          '55 Meter Hurdles', '100 Meter Hurdles', '110 Meter Hurdles',
          '300 Meter Hurdles', '800 Meter Run']
MIN_PAIRS = 6


def read_sheet():
    """Practice sessions: one row per athlete, date and surface."""
    with urllib.request.urlopen(SHEET, timeout=30) as r:
        text = r.read().decode('utf-8')
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        raw = (row.get('20m Fly') or '').strip()
        name = (row.get('Name') or '').strip()
        if not raw or not name:
            continue
        m, d, y = row['Date'].strip().split('/')
        y = int(y) + (2000 if int(y) < 100 else 0)
        trials = []
        for t in raw.split(','):
            t = t.strip().lower()
            try:
                trials.append(float(t.replace('h', '')))
            except ValueError:
                pass          # 'x', '?', blank
        if trials:
            out.append({'name': name, 'year': y, 'date': f'{y}-{int(m):02d}-{int(d):02d}',
                        'grass': (row.get('20m Fly Surface') or '').strip() == 'Grass',
                        'hand': 'h' in raw.lower(), 'best': min(trials)})
    return out


def grass_penalty(sessions):
    """Log-scale grass effect, within athlete-season (demeaned least squares)."""
    by = collections.defaultdict(list)
    for s in sessions:
        by[(s['name'], s['year'])].append(s)
    num = den = 0.0
    for ss in by.values():
        if len({s['grass'] for s in ss}) < 2:
            continue
        gm = statistics.mean(s['grass'] for s in ss)
        lm = statistics.mean(math.log(s['best']) for s in ss)
        for s in ss:
            num += (s['grass'] - gm) * (math.log(s['best']) - lm)
            den += (s['grass'] - gm) ** 2
    return num / den if den else 0.0


def fly_levels(sessions, grass):
    """(name, year) -> track-equivalent season fly (seconds) and session count."""
    by = collections.defaultdict(list)
    for s in sessions:
        by[(s['name'], s['year'])].append(math.log(s['best']) - grass * s['grass'])
    return {k: (math.exp(statistics.mean(v)), len(v)) for k, v in by.items()}


def season_bests():
    """(store name, year) -> {event: best seconds}, plus gender by name."""
    sb = collections.defaultdict(dict)
    gender = {}
    for r in js.load_team(TEAM):
        n = r.get('athlete_name') or ''
        if ',' in n or r.get('season') not in ('Indoor', 'Outdoor'):
            continue
        g, _, ev = r['event'].partition(' ')
        if ev not in EVENTS:
            continue
        try:
            v = js.parse_mark_value(r['mark'], r['event'])[0]
        except Exception:  # noqa: BLE001 - unparseable mark
            continue
        if not v:
            continue
        key = (n, int(r['year']))
        sb[key][ev] = min(sb[key].get(ev, 1e9), v)
        gender[n] = g
    return sb, gender


def matcher(sb):
    first = collections.defaultdict(set)
    for (n, y) in sb:
        first[(n.split()[0], y)].add(n)

    def match(name, year):
        if name in NAMES:
            return NAMES[name]
        c = first.get((name, year), set())
        return next(iter(c)) if len(c) == 1 else None
    return match


def fit(levels, sb, match):
    """event -> {'k': ratio, 'err': held-out log error, 'pairs': [...]}"""
    model = {}
    for ev in EVENTS:
        pairs = []
        for (name, y), (fly, _n) in sorted(levels.items()):
            full = match(name, y)
            if full and ev in sb.get((full, y), {}):
                pairs.append((full, y, fly, sb[(full, y)][ev]))
        if len(pairs) < MIN_PAIRS:
            continue
        logs = [math.log(t / f) for _, _, f, t in pairs]
        held = [logs[i] - statistics.median(logs[:i] + logs[i + 1:]) for i in range(len(logs))]
        model[ev] = {'k': math.exp(statistics.median(logs)),
                     'err': math.sqrt(statistics.mean(h * h for h in held)),
                     'pairs': pairs}
    return model


def fmt(sec):
    if sec >= 60:
        return f'{int(sec // 60)}:{sec % 60:05.2f}'
    return f'{sec:.2f}'


def short(ev):
    return re.sub(r' Meter (Dash|Run)', '', ev).replace(' Meter Hurdles', 'H')


def predict_line(fly, model, events, gender=None, actual=None):
    cells = []
    for ev in events:
        if ev not in model:
            continue
        if gender and (gender, ev) in (('Girls', '110 Meter Hurdles'), ('Boys', '100 Meter Hurdles')):
            continue
        m = model[ev]
        p = m['k'] * fly
        lo, hi = p * math.exp(-m['err']), p * math.exp(m['err'])
        a = f' (SB {fmt(actual[ev])})' if actual and ev in actual else ''
        cells.append(f'{short(ev)} {fmt(p)} [{fmt(lo)}-{fmt(hi)}]{a}')
    return '  '.join(cells)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('who', nargs='*', help='sheet first names, or raw fly times')
    ap.add_argument('--season', type=int, help='spring year (default: latest on the sheet)')
    ap.add_argument('--event', action='append', help='e.g. 100, 400, 300H (repeatable)')
    ap.add_argument('--grass', action='store_true', help='raw fly times were on grass')
    ap.add_argument('--fit', action='store_true', help='print the model and its pairs')
    a = ap.parse_intermixed_args()

    sessions = read_sheet()
    grass = grass_penalty(sessions)
    levels = fly_levels(sessions, grass)
    sb, gender = season_bests()
    match = matcher(sb)
    model = fit(levels, sb, match)

    events = EVENTS
    if a.event:
        want = {e.upper().replace('M', '') for e in a.event}
        events = [ev for ev in EVENTS if short(ev).upper() in want]

    if a.fit:
        print(f'grass penalty {100 * (math.exp(grass) - 1):+.1f}% (grass fly times are converted to track)')
        for ev in events:
            if ev not in model:
                continue
            m = model[ev]
            print(f'\n{short(ev):5s} = {m["k"]:.2f} x fly   held-out error +/-{100 * m["err"]:.1f}%   n={len(m["pairs"])}')
            for full, y, f, t in sorted(m['pairs'], key=lambda p: p[2]):
                print(f'   {y} {full:22s} fly {f:.2f}  SB {fmt(t):>7s}  predicted {fmt(m["k"] * f):>7s}')
        return

    season = a.season or max(s['year'] for s in sessions)
    raw = [w for w in a.who if re.fullmatch(r'\d+(\.\d+)?', w)]
    names = [w for w in a.who if w not in raw]
    for w in raw:
        fly = float(w) / (math.exp(grass) if a.grass else 1.0)
        surf = f' on grass = {fly:.2f} on track' if a.grass else ''
        print(f'fly {w}{surf}:  {predict_line(fly, model, events)}')
    if raw and not names:
        return
    sheet_names = sorted({n for (n, y) in levels if y == season})
    if names:
        lower = {n.lower(): n for (n, _y) in levels}
        for n in names:
            if n.lower() not in lower:
                print(f'{n}: not on the fly sheet')
        sheet_names = [lower[n.lower()] for n in names if n.lower() in lower]
    print(f'{season} fly times (season average, track-equivalent); [range] = held-out error')
    for n in sheet_names:
        if (n, season) not in levels:
            seasons = sorted(y for (m, y) in levels if m == n)
            print(f'{n}: no {season} fly times (has {", ".join(map(str, seasons))}; use --season)')
            continue
        fly, k = levels[(n, season)]
        full = match(n, season)
        label = full or f'{n} (no GSA match)'
        g = gender.get(full)
        print(f'\n{label}  fly {fly:.2f} ({k} session{"s" * (k > 1)})')
        print('   ' + predict_line(fly, model, events, g, sb.get((full, season))))


if __name__ == '__main__':
    main()
