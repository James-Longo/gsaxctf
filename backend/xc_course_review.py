"""xc_course_review.py - the review list for the XC course registry pass.

The course table (xc_course_model.py) folds venue spellings together by rule,
but a rule cannot tell when two different names are one place ("Gull Crest
Field" is Cape Elizabeth's course) or when one name covers two places. This
gathers the evidence a reviewer needs for each published course and the
candidate pairs worth deciding, and packs them into batches.

Candidate pairs, each with its evidence:
    header  - one meet whose sub5 index venue and file-header venue name
              different courses
    factor  - two venues whose fitted factors agree within the same-course
              noise floor and whose meets share a host school name
Every course with only one or two races is listed too: a fragment is usually
a spelling or a distance label that should belong to another course.

Output: backend/data/xc_course_review.json
Usage:  python3 -m backend.xc_course_review
"""

import gzip
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import xc_course_model as cm
from backend.json_store import (TEAMS_DIR, _chunk_files, _load_json,
                                enrich_rows, canonical_team_name)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PARSED_DIR = os.path.join(HERE, 'data', 'parsed_results')
COURSES = os.path.join(ROOT, 'ui', 'public', 'data', 'xc_courses.json.gz')
OUT = os.path.join(HERE, 'data', 'xc_course_review.json')

BATCH_SIZE = 35       # venues per reviewer batch
FRAGMENT_RACES = 2    # a course this small is listed as a possible fragment


def key(name):
    k = cm._venue_key(cm._clean_venue(name or ''))
    return cm.KEY_FIXUPS.get(k, k)


def index_venue(index_map, year, stem):
    for ext in ('', '.htm', '.html', '.pdf', '.txt'):
        e = index_map.get(f'{year}/XC/{stem}{ext}')
        if e and e.get('venue'):
            return re.sub(r'\s+', ' ', e['venue']).strip()
    return None


def file_venue(year, stem):
    try:
        with open(os.path.join(PARSED_DIR, year, 'XC', stem + '.json'),
                  encoding='utf-8') as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    v = d.get('venue') if isinstance(d, dict) else None
    return re.sub(r'\s+', ' ', v).strip() if v else None


def load_meets():
    """(year, meet) -> raw course, row count, date, teams."""
    meets = {}
    for fn in sorted(os.listdir(TEAMS_DIR)):
        full = os.path.join(TEAMS_DIR, fn)
        if not os.path.isdir(full):
            continue
        team = canonical_team_name(fn)
        for k, chunk in _chunk_files(full):
            if not k.endswith('_XC'):
                continue
            for p in enrich_rows(team, k, _load_json(os.path.join(full, chunk), [])):
                if 'Cross Country' not in p.get('event', ''):
                    continue
                mk = (p['year'], p.get('meet_name') or '')
                m = meets.setdefault(mk, {'raw': Counter(), 'rows': 0,
                                          'date': p.get('date', '')[:10],
                                          'teams': Counter()})
                m['raw'][p.get('course') or p.get('meet_name') or ''] += 1
                m['rows'] += 1
                m['teams'][team] += 1
    return meets


def main():
    with open(COURSES, 'rb') as f:
        table = json.loads(gzip.decompress(f.read()))
    by_key = defaultdict(list)
    for c in table['courses']:
        by_key[key(c['venue'])].append(c)

    index_map = json.load(open(os.path.join(HERE, 'web_meet_mapping.json'),
                               encoding='utf-8'))
    meets = load_meets()
    cm.build_canonical_names(r for m in meets.values() for r in m['raw'])

    venues = defaultdict(lambda: {'raw': Counter(), 'meets': [], 'teams': Counter()})
    pairs = defaultdict(list)
    for (year, meet), m in sorted(meets.items()):
        raw = m['raw'].most_common(1)[0][0]
        name = cm.norm_course(raw)
        iv, fv = index_venue(index_map, year, meet), file_venue(year, meet)
        if not name:
            continue
        k = key(name)
        v = venues[k]
        v['raw'][raw] += m['rows']
        v['teams'].update(m['teams'])
        v['meets'].append({'year': year, 'meet': meet, 'date': m['date'],
                           'rows': m['rows'], 'index_venue': iv,
                           'file_venue': fv})
        if iv and fv and cm.norm_course(fv) and key(iv) != key(fv):
            a, b = sorted((key(iv), key(fv)))
            pairs[(a, b)].append({'kind': 'header', 'year': year, 'meet': meet,
                                  'index_venue': iv, 'file_venue': fv})

    # factor agreement between venues that host the same school's meets
    def factors(k):
        return [(c['course'], c['factor']) for c in by_key.get(k, [])]
    pub = [k for k in venues if k in by_key]
    hosts = {k: {t for t, _ in venues[k]['teams'].most_common(3)} for k in pub}
    for i, a in enumerate(pub):
        for b in pub[i + 1:]:
            if not hosts[a] & hosts[b]:
                continue
            close = [(ca, cb) for ca in by_key[a] for cb in by_key[b]
                     if abs(ca['factor'] / cb['factor'] - 1) <= cm.MERGE_TOL
                     and min(ca['races'], cb['races']) <= FRAGMENT_RACES]
            if close:
                pairs[tuple(sorted((a, b)))].append({
                    'kind': 'factor', 'shared_teams': sorted(hosts[a] & hosts[b]),
                    'courses': [[ca['course'], cb['course']] for ca, cb in close]})

    def card(k, full=True):
        v = venues[k]
        c = {'key': k,
             'name': by_key[k][0]['venue'] if k in by_key else cm.norm_course(
                 v['raw'].most_common(1)[0][0]),
             'courses': [{'course': c['course'], 'factor': c['factor'],
                          'factorSE': c.get('factorSE'), 'races': c['races'],
                          'years': c['years']} for c in by_key.get(k, [])]}
        if not full:
            return c
        # the meets that carry evidence: every one whose index or header
        # venue names something else, and one per season besides
        seen, meets = set(), []
        for m in v['meets']:
            odd = any(x and key(x) != k for x in (m['index_venue'], m['file_venue']))
            if odd or m['year'] not in seen:
                seen.add(m['year'])
                meets.append(m)
        c.update(raw_names=dict(v['raw'].most_common()),
                 top_teams=[t for t, _ in v['teams'].most_common(5)],
                 meets_total=len(v['meets']), meets=meets)
        return c

    # published venues, and the unpublished ones a header pair ties to them
    review = set(pub) | {x for a, b in pairs for x in (a, b)
                         if (a in by_key or b in by_key) and x in venues}
    pairs = {ab: ev for ab, ev in pairs.items() if set(ab) <= review}
    order = sorted(review)
    batches = [order[i:i + BATCH_SIZE] for i in range(0, len(order), BATCH_SIZE)]
    flagged = {x for ab in pairs for x in ab} | {
        k for k in pub if min(c['races'] for c in by_key[k]) <= FRAGMENT_RACES}

    def batch(b):
        mine = set(b)
        # a pair is decided in the batch that holds its first venue
        ps = [{'a': a, 'b': bb, 'evidence': ev}
              for (a, bb), ev in sorted(pairs.items()) if a in mine]
        partners = sorted({p['b'] for p in ps} - mine)
        return {'venues': [card(k) for k in b],
                'partners': [card(k, full=False) for k in partners],
                'pairs': ps,
                'flagged': sorted(mine & flagged)}

    out = {
        'generated': table.get('generated'),
        'doc': 'Review input for docs/agents/xc-course-review.md',
        'batches': [batch(b) for b in batches],
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f'{len(venues)} venues, {len(pairs)} candidate pairs, '
          f'{len(flagged)} flagged venues in {len(batches)} batches -> {OUT}')


if __name__ == '__main__':
    main()
