"""Middle-school XC meets whose names don't say so ('coastal-boys', 'Small School girls',
'parker-pruitt-girls', 'Airline Inv girls'), read from the runners themselves.

A file's level comes first from what it says: a 'meet_level' tag, its file name ('scarboroughmsinvite'),
schools printed with their level ('Ellsworth Middle School'), grade columns. A file that says nothing
is a middle-school meet when its runners race in middle-school meets that season and not in
high-school ones: children don't run both. Each pass adds the meets it settles to the known ones,
until nothing changes. Only 'ms' is written; everything else keeps the high-school default.

    python3 -m backend.meet_levels        # writes backend/data/meet_levels.json
"""
import collections
import glob
import json
import os
import re

from backend import school_catalog as sc

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
OUT = os.path.join(DATA, 'meet_levels.json')
EXPL_MS = re.compile(r'(?i)middle|\bm\.?s\.?$|\bms\b|\bjh\b|junior high|jr\.? high|elementary')
EXPL_HS = re.compile(r'(?i)high school|\bh\.?s\.?$|\bhs\b|academy|varsity|\bjv\b')
MS_GRADES = {'5', '6', '7', '8', '05', '06', '07', '08', 'MS'}
HS_GRADES = {'9', '10', '11', '12', '09', 'FR', 'SO', 'JR', 'SR'}


def _key(a):
    a = (a or '').lower()
    if ',' in a:
        last, first = a.split(',', 1)
        a = f'{first.strip()} {last.strip()}'
    t = re.findall(r'[a-z]+', a)
    return ' '.join(t) if len(t) >= 2 and min(map(len, t)) >= 2 else None


def _read(season='XC'):
    files = {}
    for f in sorted(glob.glob(os.path.join(DATA, 'parsed_results', '*', season, '*.json'))):
        y = int(f.split(os.sep)[-3])
        stem = os.path.splitext(os.path.basename(f))[0]
        try:
            d = json.load(open(f))
        except (OSError, ValueError):
            continue
        # (not the meet name: it is often the venue, 'KVAC XC Meet at Auburn Middle School')
        lvl = 'ms' if d.get('meet_level') == 'ms' else sc.meet_level(stem)
        names, exm, exh, gr = set(), 0, 0, collections.Counter()
        for e in d.get('events') or []:
            if e.get('is_relay'):
                continue
            for r in e.get('results') or []:
                k = _key(r.get('athlete'))
                if k:
                    names.add((e.get('gender'), k))
                s = r.get('school') or ''
                exm += bool(EXPL_MS.search(s))
                exh += bool(EXPL_HS.search(s))
                g = str(r.get('grade') or '').strip().upper()
                gr['ms' if g in MS_GRADES else 'hs' if g in HS_GRADES else ''] += 1
        why = None
        hs_strong = (gr['hs'] >= 8 and gr['hs'] >= gr['ms']) or exh >= max(5, 3 * exm)
        if lvl == 'ms' and sc.meet_level(stem) != 'ms':
            if hs_strong:
                # a tag or meet name that says middle school over high-school grades and schools: the
                # venue ('Troy Howard Middle School' hosted the 2004 state meet), not the runners
                lvl = 'hs'
            else:
                why = 'tagged or named middle school in the file'
        if not lvl:
            if not hs_strong and (exm >= max(5, 3 * exh) or (gr['ms'] >= 8 and gr['ms'] >= 4 * gr['hs'])):
                lvl, why = 'ms', f'{exm} rows print a middle school, {gr["ms"]} middle-school grades'
            elif exh >= max(5, 3 * exm) or (gr['hs'] >= 8 and gr['hs'] >= 4 * gr['ms']):
                lvl = 'hs'
        files[f'{y}/{season}/{stem}'] = [y, lvl, names, why]
    return files


def build(season='XC'):
    files = _read(season)
    # (a file whose name doesn't say middle school but whose contents do: the resolver sees only the name)
    found = {rel: v[3] for rel, v in files.items() if v[1] == 'ms' and v[3]}
    while True:
        seen = collections.defaultdict(collections.Counter)
        for y, lvl, names, _ in files.values():
            if lvl in ('ms', 'hs'):
                for n in names:
                    seen[(y,) + n][lvl] += 1
        new = 0
        for rel, v in files.items():
            y, lvl, names, _ = v
            if lvl:
                continue
            m = h = 0
            for n in names:
                c = seen.get((y,) + n)
                if c and c['ms'] > c['hs']:
                    m += 1
                elif c and c['hs'] > c['ms']:
                    h += 1
            if m >= max(3, 2 * h, 0.3 * len(names)):
                v[1] = 'ms'
                found[rel] = f'{m} of {len(names)} runners race middle-school meets that season, {h} high-school'
                new += 1
        if not new:
            break
    return found


def main():
    found = build('XC')
    doc = {'_doc': __doc__.split('\n\n')[0], 'ms': dict(sorted(found.items()))}
    json.dump(doc, open(OUT, 'w'), indent=1)
    print(f'{len(found)} XC files read as middle-school meets -> {os.path.relpath(OUT)}')


if __name__ == '__main__':
    main()
