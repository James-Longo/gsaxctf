"""
xc_course_model.py - cross-country course equivalence from shared runners.

Model: for athlete a in year y on course c,
    log(time_{a,c,y}) = ability_{a,y} + difficulty_c

Fit by robust alternating medians (median polish), using only the signal that
identifies course effects: athlete-years who raced on 2+ distinct courses in
the SAME season. Multiplicative factors absorb both course length and
difficulty, which is exactly what time conversion needs.

Output: ui/public/data/xc_courses.json.gz
    { "generated": ..., "reference": "median course",
      "courses": [ {course, factor, pct, races, athletes, obs, medianTime,
                    years: [..]} ] }
factor > 1 -> slower course (longer and/or harder).
"""

import gzip
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.json_store import (TEAMS_DIR, DATA_DIR, _chunk_files, _load_json,
                                enrich_rows, canonical_team_name, parse_mark_value)

MIN_OBS = 30          # course must have this many multi-course observations
MIN_T, MAX_T = 9 * 60, 50 * 60   # plausible 5K XC times (elite MS .. back of pack)
ITERATIONS = 12


NOISE_TOKENS = re.compile(
    r'\b(results?|list|final|meet|race|invitational|invite|inv|festival|'
    r'varsity|jv|frosh|freshman|boys?|girls?|men|women|xc|cross|country|'
    r'sept?|oct|nov|aug|day|home|dual|tri|quad|team|scores?|updated?|'
    r'revised|corrected|copy|page|\d+(st|nd|rd|th))\b', re.I)


import os as _os
_ALIAS_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'data', 'xc_course_aliases.json')
try:
    import json as _json
    COURSE_ALIASES = {k.lower(): v for k, v in _json.load(open(_ALIAS_PATH)).items()}
except Exception:
    COURSE_ALIASES = {}


def norm_course(raw):
    """Normalize a course identity. Venue strings ('Twin Brook, Cumberland,
    ME') pass through cleanly; filename-derived names get de-noised so
    'laliberte-varsity-2024-list' and 'LaLiberte-JV-Race-Results' merge."""
    s = str(raw).strip()
    s = re.sub(r'%20', ' ', s)
    s = re.sub(r'\b(ME|Maine)\b\.?$', '', s).strip(' ,.-')
    if ',' in s:  # venue form: "Twin Brook, Cumberland"
        s = re.sub(r'\s+', ' ', s).strip(' ,.-')
        s = s.title() if s.isupper() else s
        return COURSE_ALIASES.get(s.lower(), s)  # '' alias = exclude
    # filename form: split camelCase and separators, drop noise + dates
    s = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', s)
    s = re.sub(r'[-_/.]+', ' ', s)
    s = re.sub(r'\b(19|20)\d{2}\b', ' ', s)
    s = re.sub(r'\b\d{1,2}\b', ' ', s)
    s = NOISE_TOKENS.sub(' ', s)
    toks = []
    for t in s.split():
        # drop glued month+day tokens: sept3, august31, oct12
        if re.fullmatch(r'(jan|feb|mar|apr|may|jun|jul|aug|sept?|oct|nov|dec)[a-z]*\d*',
                        t, re.I):
            continue
        # strip glued qualifiers and trailing digits: maranacookgirls, foxcroft9
        prev = None
        while prev != t:
            prev = t
            t = re.sub(r'(?i)(?<=\w\w)(girls?|boys?|jv|varsity|varisty|sections?)$', '', t)
            t = re.sub(r'\d+$', '', t)
        if t:
            toks.append(t)
    s = ' '.join(toks).strip(' ,.-')
    if len(s) < 3:
        return ''
    # debris that is a file description, not a place
    if re.search(r'result|by\s?heat|section|heats?$|\bpdf\b|^meet\b|^with\b', s, re.I):
        s2 = COURSE_ALIASES.get(s.title().lower())
        return s2 if s2 is not None else ''
    s = re.sub(r'^la\s*liberte$', 'LaLiberte', s, flags=re.I)
    s = s.title()
    return COURSE_ALIASES.get(s.lower(), s)  # '' alias = exclude


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def load_observations():
    obs = []  # (athlete_id, year, course, log_time, meet, date)
    for fn in sorted(os.listdir(TEAMS_DIR)):
        full = os.path.join(TEAMS_DIR, fn)
        if not os.path.isdir(full):
            continue
        team = canonical_team_name(fn)
        for key, chunk in _chunk_files(full):
            if not key.endswith('_XC'):
                continue
            rows = enrich_rows(team, key, _load_json(os.path.join(full, chunk), []))
            for p in rows:
                if '5K Cross Country' not in p.get('event', ''):
                    continue
                course = norm_course(p.get('course') or p.get('meet_name') or '')
                if not course:
                    continue
                val, _ = parse_mark_value(p.get('mark', ''), p['event'])
                if val is None or not (MIN_T <= val <= MAX_T):
                    continue
                obs.append((p['athlete_id'], p['year'], course,
                            math.log(val), p.get('meet_name'), p.get('date', '')))
    return obs


def fit(obs):
    # keep only athlete-years with 2+ distinct courses (they identify factors)
    by_ay = defaultdict(list)
    for aid, year, course, lt, meet, d in obs:
        by_ay[(aid, year)].append((course, lt))
    multi = {ay: rows for ay, rows in by_ay.items()
             if len({c for c, _ in rows}) >= 2}
    print(f'{len(obs):,} XC observations; {len(multi):,} multi-course athlete-years')

    course_f = defaultdict(float)
    ability = {}
    for _ in range(ITERATIONS):
        for ay, rows in multi.items():
            ability[ay] = median([lt - course_f[c] for c, lt in rows])
        residuals = defaultdict(list)
        for ay, rows in multi.items():
            for c, lt in rows:
                residuals[c].append(lt - ability[ay])
        for c, rs in residuals.items():
            course_f[c] = median(rs)
    # center on the median course
    center = median(list(course_f.values()))
    for c in course_f:
        course_f[c] -= center
    counts = {c: len(rs) for c, rs in residuals.items()}
    return course_f, counts


def main():
    obs = load_observations()
    course_f, counts = fit(obs)

    # per-course stats over ALL observations (not just multi-course)
    stats = defaultdict(lambda: {'times': [], 'athletes': set(),
                                 'meets': set(), 'years': set()})
    for aid, year, course, lt, meet, d in obs:
        s = stats[course]
        s['times'].append(math.exp(lt))
        s['athletes'].add(aid)
        s['meets'].add((meet, year))
        s['years'].add(year)

    out = []
    for c, f in course_f.items():
        if counts.get(c, 0) < MIN_OBS:
            continue
        s = stats[c]
        med = median(s['times'])
        mm, ss = divmod(int(round(med)), 60)
        out.append({
            'course': c,
            'factor': round(math.exp(f), 4),
            'pct': round((math.exp(f) - 1) * 100, 1),
            'obs': counts[c],
            'athletes': len(s['athletes']),
            'races': len(s['meets']),
            'years': sorted(s['years']),
            'medianTime': f'{mm}:{ss:02d}',
        })
    out.sort(key=lambda x: x['factor'])

    payload = {'generated': date.today().isoformat(),
               'event': '5K Cross Country',
               'note': 'factor is multiplicative vs the median Maine course; '
                       'includes both course length and difficulty',
               'courses': out}
    path = os.path.join(DATA_DIR, 'xc_courses.json.gz')
    with gzip.GzipFile(filename='', mode='wb', fileobj=open(path, 'wb'), mtime=0) as f:
        f.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    print(f'{len(out)} courses written to {path}')
    for c in out[:5] + out[-5:]:
        print(f"  {c['factor']:.3f}  {c['course'][:44]:46s} med {c['medianTime']} ({c['athletes']} athletes)")


if __name__ == '__main__':
    main()
