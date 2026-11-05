"""Per-season sanity counts for track (the classes of error that XC review found).

usage: python3 -m backend.track_sanity [--season Indoor] [--save] [--show CLASS YEAR]

Counts, per season year, things a coach would notice in the store
(ui/public/data/teams): one-gender meets, outdoor events in an indoor
season, marks in the wrong format, junk names, duplicate rows, one runner
in two schools or both genders in a season, dates outside the season, a
meet on two dates, plus the QAQC flags (backend/data/qaqc_flags.json) by
check. `--save` appends the run to backend/data/track_sanity.json and the
printout marks every count that rose since the last saved run: a rise
stops the older-data loop until it is explained. `--show` lists the rows
behind one count.
"""
import argparse, glob, gzip, json, os, re, sys
from collections import Counter, defaultdict
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEAMS = os.path.join(BASE, 'ui', 'public', 'data', 'teams')
FLAGS = os.path.join(BASE, 'backend', 'data', 'qaqc_flags.json')
HISTORY = os.path.join(BASE, 'backend', 'data', 'track_sanity.json')

OUTDOOR_ONLY = re.compile(r'\b(100 Meter Dash|110 Meter Hurdles|100 Meter Hurdles|300 Meter Hurdles|400 Meter Hurdles|'
                          r'4x100|Discus|Javelin|Hammer|3200 Meter Run|1600 Meter Run|Steeplechase)\b')
INDOOR_ONLY = re.compile(r'\b(55 Meter|60 Meter|Weight Throw|600 Yard|300 Meter Dash|1000 Meter Run)\b')
FIELD = re.compile(r'Jump|Vault|Put|Throw|Discus|Javelin|Hammer')
FIELD_MARK = re.compile(r'^\d{1,3}-\d{1,2}(\.\d+)?$|^\d{1,2}\.\d{2}m?$')
TIME_MARK = re.compile(r'^(\d{1,2}:)?\d{1,2}:\d{2}(\.\d+)?$|^\d{1,3}\.\d{1,3}$')
BAD_NAME = re.compile(r'\d|\bunknown\b|\bcoach\b|^\W|\(|\)|,|\b(relay|team|school|academy|high)\b', re.I)


def season_window(year, season):
    """(first, last) month-day dates a season of that year can fall in."""
    if season == 'Indoor':
        return f'{year - 1}-11-01', f'{year}-03-31'
    if season == 'Outdoor':
        return f'{year}-03-15', f'{year}-07-31'
    return f'{year}-08-01', f'{year}-11-30'


def load(season):
    """{year: [row + team]} from every team file of the season."""
    out = defaultdict(list)
    for f in glob.glob(os.path.join(TEAMS, '*', f'*_{season}.json.gz')):
        team = os.path.basename(os.path.dirname(f))
        year = int(os.path.basename(f)[:4])
        for r in json.load(gzip.open(f)):
            r['team'] = team
            out[year].append(r)
    return out


def counts(rows, year, season):
    """{class: [example rows]} for one season year."""
    hits = defaultdict(list)
    lo, hi = season_window(year, season)
    by_meet = defaultdict(list)
    for r in rows:
        by_meet[r['meet_name']].append(r)
    for meet, rs in by_meet.items():
        sexes = {r['event'].split()[0] for r in rs}
        if len({'Boys', 'Girls'} & sexes) == 1 and not re.search(r'boy|girl|men|women', meet, re.I):
            hits['one-gender meet'].append((meet, sorted(sexes), len(rs)))
        dates = {r['date'] for r in rs if r['date']}
        if len(dates) > 1:
            hits['meet on two dates'].append((meet, sorted(dates)))
    seen = Counter()
    name_teams = defaultdict(set)
    name_sexes = defaultdict(set)
    marks = defaultdict(set)
    for r in rows:
        ev, mark, name = r['event'], str(r['mark']).strip(), (r['athlete_name'] or '').strip()
        relay = 'Relay' in ev
        if season == 'Indoor' and OUTDOOR_ONLY.search(ev):
            hits['outdoor event indoors'].append((r['meet_name'], ev))
        if season == 'Outdoor' and INDOOR_ONLY.search(ev):
            hits['indoor event outdoors'].append((r['meet_name'], ev))
        if mark and mark.upper() not in ('DNF', 'DNS', 'DQ', 'NH', 'NM', 'FOUL', 'FAIL', 'SCR', 'NT', 'ND'):
            if re.search(r'athlon', ev):
                pass   # multi-event points and component marks
            elif FIELD.search(ev) and not FIELD_MARK.match(mark):
                hits['field mark not a distance'].append((r['meet_name'], ev, name, mark))
            if not FIELD.search(ev) and not TIME_MARK.match(mark):
                hits['running mark not a time'].append((r['meet_name'], ev, name, mark))
        if not relay and re.search(r'\brelay$', name, re.I):
            hits['relay team as athlete'].append((r['meet_name'], r['team'], ev, name))
            continue
        if not relay and (BAD_NAME.search(name) or len(re.sub(r'\W', '', name)) < 3):
            hits['junk name'].append((r['meet_name'], r['team'], name))
        if not r['date'] or not re.match(r'\d{4}-\d\d-\d\d$', r['date']):
            hits['no date'].append((r['meet_name'], r['team']))
        elif not lo <= r['date'] <= hi:
            hits['date outside season'].append((r['meet_name'], r['date']))
        g = r.get('grade')
        if str(g).isdigit() and int(g) <= 8:
            hits['grade 8 or under'].append((r['meet_name'], r['team'], name, g))
        if relay:
            continue
        key = (name.lower(), ev, r['meet_name'], mark)
        seen[key] += 1
        if seen[key] == 2:
            hits['duplicate row'].append((r['meet_name'], r['team'], name, ev, mark))
        full = len(name.split()) >= 2 and not re.match(r'^[A-Z]\.?\s', name)
        if full and r['team'] != 'Unattached':
            name_teams[name.lower()].add(r['team'])
            name_sexes[(name.lower(), r['team'])].add(ev.split()[0])
            marks[(name.lower(), r['team'], ev, r['meet_name'])].add(mark)
    for n, ts in name_teams.items():
        if len(ts) > 1:
            hits['name at two schools'].append((n, sorted(ts)))
    for (n, t), sx in name_sexes.items():
        if {'Boys', 'Girls'} <= sx:
            hits['runner in both genders'].append((n, t))
    for (n, t, ev, m), ms in marks.items():
        if len(ms) > 1 and not re.search(r'55|60|Hurdles|athlon', ev):   # prelims/finals are sprint and hurdle events; multi-event components
            hits['two marks in one race'].append((m, t, n, ev, sorted(ms)))
    return hits


def run(season):
    data = load(season)
    flags = json.load(open(FLAGS)) if os.path.exists(FLAGS) else []
    table = {}
    detail = {}
    for year in sorted(data):
        rows = data[year]
        h = counts(rows, year, season)
        sex = Counter(r['event'].split()[0] for r in rows)
        c = {'rows': len(rows), 'meets': len({r['meet_name'] for r in rows}),
             'teams': len({r['team'] for r in rows}), 'boys': sex['Boys'], 'girls': sex['Girls']}
        c.update({k: len(v) for k, v in h.items()})
        for f in flags:
            if f.get('season') == season and str(f.get('year')) == str(year):
                c['qaqc ' + f['check']] = c.get('qaqc ' + f['check'], 0) + 1
        table[year] = c
        detail[year] = h
    return table, detail


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--season', default='Indoor')
    ap.add_argument('--save', action='store_true')
    ap.add_argument('--show', nargs=2, metavar=('CLASS', 'YEAR'))
    a = ap.parse_args()
    table, detail = run(a.season)
    if a.show:
        for x in detail.get(int(a.show[1]), {}).get(a.show[0], []):
            print(x)
        return
    hist = json.load(open(HISTORY)) if os.path.exists(HISTORY) else []
    prev = next((h['counts'] for h in reversed(hist) if h['season'] == a.season), {})
    cols = sorted({k for c in table.values() for k in c} - {'rows', 'meets', 'teams', 'boys', 'girls'})
    print('year  rows  meets teams  boys/girls | ' + ' | '.join(cols))
    rises = []
    for y, c in sorted(table.items(), reverse=True):
        p = prev.get(str(y), {})
        cells = []
        for k in cols:
            v = c.get(k, 0)
            up = p and v > p.get(k, 0)
            if up:
                rises.append((y, k, p.get(k, 0), v))
            cells.append(f"{v}{'^' if up else ''}")
        print(f"{y} {c['rows']:6d} {c['meets']:4d} {c['teams']:4d}  {c['boys']}/{c['girls']} | " + ' | '.join(cells))
    for r in rises:
        print('ROSE', *r, file=sys.stderr)
    if a.save:
        hist.append({'run': datetime.now().isoformat(timespec='seconds'), 'season': a.season,
                     'counts': {str(y): c for y, c in table.items()}})
        json.dump(hist, open(HISTORY, 'w'), indent=1)


if __name__ == '__main__':
    main()
