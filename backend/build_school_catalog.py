"""
build_school_catalog.py - build the school identity catalog with evidence.

Inputs
  backend/school_catalog_seed.py           hand-curated institutions, codes, co-ops, MPA lists
  <parsed>/{year}/{season}/*.json          every parsed result file (raw school strings)
  <archive>/{year}/XC/*.txt.htm            raw Hy-Tek XC files (official Team Scores blocks)
  <store>/teams/*/...json.gz               current store (to map store team names -> ids)

Outputs (backend/data/)
  school_catalog.json             institutions + co-ops + MPA classification (one entry per real institution)
  school_raw_map.json             every distinct raw school string -> id, method, rows; per-file overrides;
                                  store team -> id; unresolved/ambiguous list
  school_catalog_validation.json  team-score re-scoring (before vs after), identity conflicts,
                                  same-day class conflicts, MPA coverage

Method
  1. Name resolution (school_catalog.Index): exact name/alias -> stem by level -> code -> unique
     Hy-Tek truncation -> mascot. Level context comes from the file/meet (MS meets mean MS schools)
     and from the grades in the group.
  2. Athlete continuity: every (file, raw string) group is compared with the athletes of the same
     academic year under every other string. A group whose athletes run for school X everywhere
     else is X. This resolves codes/mascots/single letters per file, confirms name matches, and
     flags name matches that the athletes contradict.
  3. Validation by official team scores (XC): finishers are grouped by resolved team unit and
     re-scored with standard XC rules; totals are compared with the file's own Team Scores block.

Usage
  python3 -m backend.build_school_catalog [--parsed DIR ...] [--archive DIR ...] [--store DIR]
"""

import argparse
import collections
import glob
import gzip
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import school_catalog as sc          # noqa: E402
from backend import school_catalog_seed as seed   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
REPO = os.path.dirname(HERE)

# ---------------------------------------------------------------------------
# Catalog from seed
# ---------------------------------------------------------------------------


def seed_entries():
    schools = {}
    groups = (('ME_HS', 'hs', 'ME'), ('ME_MS', 'ms', 'ME'), ('COLLEGES', 'college', None),
              ('OOS', 'hs', None), ('CLUBS', 'club', None), ('SPECIAL', 'x', None))
    for groupname, level, default_state in groups:
        for t in getattr(seed, groupname, []):
            sid, name, town, mpa, names, codes, nicks, extra = t
            if sid in schools:
                raise ValueError(f'duplicate id {sid}')
            e = dict(name=name, level=extra.get('level', level), state=extra.get('state', default_state),
                     town=town, names=list(names), codes=list(codes), nicknames=list(nicks),
                     curation='seed')
            if mpa:
                e['mpa'] = mpa
            for k in ('years', 'notes', 'successor', 'kind', 'bare_ok', 'members', 'middle_grades'):
                if k in extra:
                    e[k] = extra[k]
            schools[sid] = e
    coops = []
    for c in seed.COOPS:
        c = dict(c)
        for m in c['members']:
            if m not in schools:
                raise ValueError(f'co-op {c["id"]} member {m} not in catalog')
        coops.append(c)
        for m in c['members']:
            schools[m].setdefault('coop_of', []).append(c['id'])
        schools[c['id']] = dict(name=c['label'], level='coop', state='ME', names=list(c['labels']), codes=[],
                                nicknames=[], members=c['members'], seasons=c['seasons'], genders=c['genders'],
                                curation='seed')
    # MPA classification
    for key, table in (('xc_2026', seed.MPA_XC_2026), ('it_2026', seed.MPA_IT_2026), ('ot_2026', seed.MPA_OT_2026)):
        for cls, ids in table.items():
            for i, ref in enumerate(ids, 1):
                sid, _, g = ref.partition('|')
                if sid not in schools:
                    raise ValueError(f'MPA {key} {cls}: unknown id {sid}')
                rec = {'class': cls, 'rank': i}
                if g:
                    rec['gender'] = {'B': 'Boys', 'G': 'Girls'}[g]
                schools[sid].setdefault('mpa_class', {}).setdefault(key, []).append(rec)
    return schools, coops


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------

def athlete_key(name):
    """Order-insensitive athlete key: 'Smith, John' == 'John Smith' == 'JOHN SMITH'."""
    n = re.sub(r'\b(jr|sr|ii|iii|iv)\b\.?', ' ', (name or '').lower())
    toks = re.findall(r'[a-z]+', n)
    if len(toks) < 2:
        return None
    return ' '.join(sorted(toks))


def file_level(rel, meet_name):
    stem_ = os.path.splitext(os.path.basename(rel))[0]
    return sc.meet_level(f'{stem_} {meet_name or ""}')


def academic_year(year, season):
    # XC year Y is the fall of academic year Y; Indoor/Outdoor year Y are winter/spring of Y-1.
    y = int(year)
    return y if season == 'XC' else y - 1


# files whose source tags them middle school (meet_level 'ms'); 'hs' is a converter default, not evidence
FILE_MS = set()


def scan(parsed_roots):
    """Yield row dicts from every parsed results file. Later roots override earlier ones per rel path."""
    files = {}
    for root in parsed_roots:
        for f in glob.glob(os.path.join(root, '*', '*', '*.json')):
            files[os.path.relpath(f, root)] = f
    rows = []
    for rel in sorted(files):
        year, season, _fn = rel.split(os.sep)
        try:
            with open(files[rel], encoding='utf-8') as fh:
                d = json.load(fh)
        except Exception:
            continue
        if isinstance(d, list):
            d = {'events': d}
        meet = d.get('meet_name') or ''
        date = d.get('date') or ''
        if d.get('meet_level') == 'ms':
            FILE_MS.add(rel)   # the source's own level tag (MileSplit's Middle School list)
        for ei, e in enumerate(d.get('events') or []):
            if not isinstance(e, dict):
                continue
            if 'results' in e:
                for ri, r in enumerate(e.get('results') or []):
                    rows.append((year, season, rel, e.get('meet_name') or meet, e.get('date') or date,
                                 e.get('event') or '', e.get('gender') or '', bool(e.get('is_relay')),
                                 r.get('athlete') or '', r.get('school') or '', str(r.get('grade') or ''),
                                 r.get('result') or '', ei, ri))
            else:
                ev = e.get('event') or ''
                rows.append((year, season, rel, meet, e.get('date') or date, ev, e.get('gender') or '',
                             'relay' in ev.lower() or '4x' in ev.lower(), e.get('athlete_name') or '',
                             e.get('school') or '', str(e.get('grade') or ''), e.get('mark') or '', -1, ei))
    return rows


def clean_raw(s):
    return re.sub(r'\s+', ' ', s or '').strip()


# ---------------------------------------------------------------------------
# Resolution with athlete continuity
# ---------------------------------------------------------------------------

MS_GRADES = {'5', '6', '7', '8', '05', '06', '07', '08', 'MS'}
HS_GRADES = {'9', '10', '11', '12', '09', 'FR', 'SO', 'JR', 'SR'}


class Group:
    __slots__ = ('rel', 'raw', 'year', 'season', 'ay', 'rows', 'athletes', 'level', 'meet_level', 'gender', 'name',
                 'decision', 'method', 'candidates', 'weak', 'evidence', 'flags')

    def __init__(self, rel, raw, year, season):
        self.rel, self.raw, self.year, self.season = rel, raw, year, season
        self.ay = academic_year(year, season)
        self.rows = 0
        self.athletes = set()
        self.level = None
        self.meet_level = None
        self.gender = None
        self.name = None
        self.decision = None
        self.method = None
        self.candidates = []
        self.weak = True
        self.evidence = None
        self.flags = []


def coop_of(schools, a, b, season):
    """A co-op (for this season) that has both a and b as members, or has one as member and is the other."""
    for sid in (a, b):
        e = schools.get(sid, {})
        if e.get('level') == 'coop' and season in e.get('seasons', []) and ({a, b} - {sid}) <= set(e['members']):
            return sid
    global _COOP_CACHE
    if _COOP_CACHE is None or _COOP_CACHE[0] is not schools:
        _COOP_CACHE = (schools, [(cid, e) for cid, e in schools.items() if e.get('level') == 'coop'])
    for cid, e in _COOP_CACHE[1]:
        if season in e.get('seasons', []) and a in e['members'] and b in e['members']:
            return cid
    return None


_COOP_CACHE = None
KEYS = []
ROW_STORE = {}
STORE_MAP = {}


def compatible(schools, a, b):
    """Two ids denote the same competing team (same id, or co-op and member)."""
    if a == b:
        return True
    ea, eb = schools.get(a, {}), schools.get(b, {})
    return b in ea.get('members', []) or a in eb.get('members', [])


EVENT_MS = re.compile(r'\bms\b|middle|junior high|\bjh\b|grade [5-8]|elementary|\b[5-8]th\b', re.I)
EVENT_HS = re.compile(r'\bhigh school\b|\bhs\b|class [abcd]\b', re.I)


def explicit_level(raw):
    """Level a school string states about itself: 'Cohen Middle School' -> ms, 'Orono High School' -> hs."""
    n = sc.norm(raw or '')
    lv = sc.level_of(n)
    if lv:
        return lv
    toks = set(n.split())
    if toks & {'high', 'hs'}:
        return 'hs'
    return None


_INDEX_MEETS = None


def index_meet(rel):
    """The meet name sub5's season index gives a file ('<year>/<season>/<stem>.json'), or ''."""
    global _INDEX_MEETS
    if _INDEX_MEETS is None:
        _INDEX_MEETS = {}
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web_meet_mapping.json'), encoding='utf-8') as fh:
                for k, v in json.load(fh).items():
                    if isinstance(v, dict) and v.get('meet'):
                        _INDEX_MEETS[os.path.splitext(k)[0]] = v['meet']
        except (OSError, ValueError):
            pass
    return _INDEX_MEETS.get(os.path.splitext(rel)[0].replace(os.sep, '/'), '')


def row_levels(rows):
    """Meet level for every row, decided per race (file + event), strongest signal first:
      1. the event name ('Girls 2 Mile Middle School', 'Class A', 'Varsity')
      2. the school strings in the race that state a level ('Cape Elizabeth M. S.', 'Orono High School')
      3. numeric grades (5-8 vs 9-12)
      4. the file stem ('conymsboys_oct6', 'scarboroughmsinvite')
    A file whose source tags it middle school (meet_level 'ms') is middle school before all of these.
      5. the meet name - weakest: it is often the venue ('Troy Howard Middle School' hosted a
         New England qualifier; 'Bowdoin College' hosts high-school indoor meets)."""
    race = collections.defaultdict(lambda: {'ex': collections.Counter(), 'gr': collections.Counter(), 'raws': set()})
    for r in rows:
        k = (r[2], r[5])
        d = race[k]
        raw = clean_raw(r[9])
        if raw not in d['raws']:
            d['raws'].add(raw)
            d['ex'][explicit_level(raw)] += 1
        gu = r[10].strip()
        if gu in ('5', '6', '7', '8', '05', '06', '07', '08'):
            d['gr']['ms'] += 1
        elif gu in ('9', '09', '10', '11', '12'):
            d['gr']['hs'] += 1
    lv_of = {}
    for (rel, ev), d in race.items():
        lv = None
        if rel in FILE_MS and (os.path.basename(rel).startswith('ms-') or d['ex']['ms'] or d['ex']['hs'] < 3):
            # (a sub5 parse's tag can come from the venue line - 'Troy Howard Middle School, Belfast'
            # hosted the 2004 state meet - so school strings that say high school outrank it)
            lv = 'ms'
        elif EVENT_MS.search(ev):
            lv = 'ms'
        elif EVENT_HS.search(ev):
            lv = 'hs'
        if lv is None:
            ms, hs = d['ex']['ms'], d['ex']['hs']
            if ms + hs >= 2 and max(ms, hs) / (ms + hs) >= 0.75:
                lv = 'ms' if ms > hs else 'hs'
        if lv is None:
            ms, hs = d['gr']['ms'], d['gr']['hs']
            if ms + hs >= 8 and max(ms, hs) / (ms + hs) >= 0.7:
                lv = 'ms' if ms > hs else 'hs'
        if lv is None:
            stem_ = os.path.splitext(os.path.basename(rel))[0]
            lv = sc.meet_level(stem_)
        if lv is None:
            # the sub5 index's meet title, before its venue and race list, when it says junior high or
            # middle school and nothing else ('Junior High Meet at Waterville: Girls - Boys'; never
            # 'XC Meet at Troy Howard Middle School' or 'Scarborough Invitational - Girls Middle School - ... Varsity')
            title = re.split(r'\s+at\s+|:', index_meet(rel), 1)[0]
            if re.search(r'(?i)\b(junior high|jr\.? high|middle school)\b', title) and \
                    not re.search(r'(?i)high school|varsity|\bjv\b|\bhs\b|class [a-d]\b', title):
                lv = 'ms'
        lv_of[(rel, ev)] = lv
    # meet-name fallback (needs a row to read the meet name)
    out = []
    for r in rows:
        lv = lv_of[(r[2], r[5])]
        # (the meet name is NOT used: it is often the venue - 'Troy Howard Middle School' hosted the
        # New England qualifier, 'Bowdoin College' hosts high-school indoor meets; relevel() covers
        # middle-school meets whose strings carry no level)
        if lv == 'college':
            d = race[(r[2], r[5])]
            if d['ex']['hs'] or d['gr']['hs']:
                lv = 'hs'
        out.append(lv)
    return out


def file_rule_for(g):
    """Seed FILE_RULES: per-file meanings read from the result files themselves."""
    stem_ = os.path.splitext(os.path.basename(g.rel))[0]
    for raws, season, (lo, hi), pattern, sid in seed.FILE_RULES:
        if g.raw in raws and (season is None or season == g.season) and lo <= int(g.year) <= hi \
                and re.search(pattern, stem_, re.I):
            return sid
    return None


def build_groups(rows, idx, levels):
    """Group rows by (file, meet level, raw string). Returns (groups, row_keys)."""
    groups = {}
    keys = []
    by_name = {e['name']: k for k, e in idx.schools.items()}
    MG_TWIN = {by_name[e['name'][:-16]]: k for k, e in idx.schools.items()   # 'X' -> 'X (middle grades)'
               if e.get('level') == 'ms' and e['name'].endswith(' (middle grades)') and e['name'][:-16] in by_name}
    # a high school whose middle grades are a school of another name ('Valley' -> Upper Kennebec Valley MS)
    MG_TWIN.update({k: e['middle_grades'] for k, e in idx.schools.items() if e.get('middle_grades') in idx.schools})
    for r, lvl in zip(rows, levels):
        year, season, rel, meet, date, ev, gender, relay, ath, school, grade = r[:11]
        raw = clean_raw(school)
        key = (rel, lvl, raw)
        keys.append(key)
        g = groups.get(key)
        if g is None:
            g = groups[key] = Group(rel, raw, year, season)
            g.level = lvl
            g.gender = collections.Counter()
            g.name = collections.Counter()   # temporarily: grade counter
        g.rows += 1
        g.gender[gender] += 1
        gu = grade.strip().upper()
        g.name['ms' if gu in MS_GRADES else 'hs' if gu in HS_GRADES else ''] += 1
        if not relay:
            k = athlete_key(ath)
            if k:
                g.athletes.add(k)
    for g in groups.values():
        grades = g.name
        tot = grades['ms'] + grades['hs']
        g.meet_level = g.level   # the race's own level, before the group's grades fill it in
        if g.level is None and tot >= 3 and grades['ms'] / tot >= 0.8:
            g.level = 'ms'
        gender = g.gender.most_common(1)[0][0] if g.gender else None
        g.gender = gender
        rule = file_rule_for(g)
        if rule:
            g.name = (rule, 'manual (file rule)', [rule], False)
        elif not g.raw or sc.looks_like_debris(g.raw):
            g.name = (None, 'debris' if g.raw else 'blank', [], True)
            fixed = sc.salvage(g.raw) if g.raw else None
            if fixed:
                sid, method, cands, weak = idx.match(fixed, level=g.level, gender=gender, ay=g.ay)
                if sid and not method.startswith(('fuzzy', 'nickname')):
                    g.name = (sid, 'salvaged:' + method, cands, weak)
        else:
            g.name = idx.match(g.raw, level=g.level, gender=gender, ay=g.ay)
            sid, method, cands, weak = g.name
            # bare town / default-level truncation in an MS-context group resolving to an HS
            if sid and g.level == 'ms' and idx.schools[sid].get('level') == 'hs' and \
                    method.split('+')[0] in ('bare-name', 'truncation', 'stem', 'code', 'nickname'):
                g.name = (sid, method, cands, True)
            # a K-12 school's own name in a middle-school race is its middle grades' entry
            # ('Islesboro Central School' in a grades 4-8 meet -> 'Islesboro Central School (middle grades)')
            if sid and g.meet_level == 'ms' and idx.schools[sid].get('level') == 'hs' and explicit_level(g.raw) != 'hs':
                twin = MG_TWIN.get(sid)
                if twin:
                    g.name = sid, method, cands, weak = (twin, method + '+middle-grades', [twin], False)
            # truncations/bare names with same-stem entries at other levels need confirmation
            if sid and not weak and method.split('+')[0] in ('truncation', 'bare-name') and len(cands) == 1:
                lv = idx.schools[sid].get('level')
                st = sc.stem(sc.norm(idx.schools[sid]['name']))
                if any((o, st) in idx.stems for o in ('hs', 'ms') if o != lv):
                    g.name = (sid, method, cands, True)
        g.decision, g.method, g.candidates, g.weak = g.name
    return groups, keys


def relevel(groups, idx):
    """'The company a string keeps': in a file with no level signal, if the schools that resolve
    unambiguously are mostly middle schools ('Dedham School', 'Bay School', 'Cohen Middle School'), the
    bare names in that file ('Ellsworth', 'Bucksport') are middle schools too (and vice versa)."""
    company = collections.defaultdict(collections.Counter)
    for g in groups.values():
        if not g.decision or g.weak or g.method.split('+')[0] not in ('exact', 'stem', 'truncation', 'code'):
            continue
        e = idx.schools[g.decision]
        lv = e.get('level')
        if lv not in ('hs', 'ms'):
            continue
        st = sc.stem(sc.norm(e['name']))
        if any((o, st) in idx.stems for o in ('hs', 'ms') if o != lv):
            continue      # level-ambiguous name: not evidence
        company[g.rel][lv] += 1
    changed = 0
    for g in groups.values():
        if g.level is not None or not g.raw or g.method in ('debris', 'blank') or \
                (g.method or '').startswith('manual'):
            continue
        c = company.get(g.rel)
        if not c or c['ms'] + c['hs'] < 3:
            continue
        lv = 'ms' if c['ms'] > c['hs'] else 'hs'
        if max(c['ms'], c['hs']) / (c['ms'] + c['hs']) < 0.75 or lv == 'hs':
            continue
        g.level = 'ms'
        sid, method, cands, weak = idx.match(g.raw, level='ms', gender=g.gender, ay=g.ay)
        if sid != g.decision:
            g.decision, g.method, g.candidates, g.weak = sid, (method + '+file-company') if sid else method, cands,                 weak if sid else True
            changed += 1
    print(f'relevel: {changed} groups re-resolved as middle-school by file company')


CLUB_RE = re.compile(r'\b(tc|track club|striders|running|runners|harriers|aac|ac|youth|pal)\b', re.I)


def auto_entries(groups, schools):
    """Strings printed WITH an out-of-state tag ('Cumberland - RI', 'GreenfieldMA', 'Regis (Mass.)') that
    match no curated entry become automatic entries, one per (state, name stem). They are uncurated
    (curation='auto') and merge nothing beyond identical stems; bare spellings join them only through
    athlete continuity."""
    found = {}
    for g in groups.values():
        if g.decision or g.method in ('debris', 'blank'):
            continue
        last = None
        for v, note, state in sc.variants(g.raw, g.gender):
            if state and state != 'ME':
                last = (v, state)
        if not last:
            continue
        v, st = last
        n = sc.norm(v)
        key = (st, sc.stem(n) or n)
        if not key[1] or len(key[1]) < 3:
            continue
        found.setdefault(key, collections.Counter())[v] += g.rows
    out = {}
    for (st, k), names in found.items():
        name = names.most_common(1)[0][0]
        lvl = 'college' if sc.level_of(sc.norm(name)) == 'college' or re.search(r'\b(college|univ|state)\b', name, re.I) \
            else 'club' if CLUB_RE.search(name) else 'hs'
        sid = f'oos-auto-{st.lower()}-{re.sub(r"[^a-z0-9]+", "-", k).strip("-")}'
        if sid in schools:
            continue
        out[sid] = dict(name=name, level=lvl, state=st, town=None, names=sorted(names), codes=[], nicknames=[],
                        curation='auto', notes='Created from state-tagged result strings; not hand-checked.')
    return out


def evidence_index(groups, schools, strong_only=True):
    idx = collections.defaultdict(collections.Counter)
    for g in groups.values():
        if not g.decision or (strong_only and g.weak) or g.decision.startswith('x-'):
            continue       # 'Unattached' says nothing about which school an athlete belongs to
        for a in g.athletes:
            idx[(g.ay, a)][g.decision] += 1
    return idx


def group_evidence(g, eidx, schools):
    votes = collections.Counter()
    seen = 0
    for a in g.athletes:
        c = eidx.get((g.ay, a))
        if not c:
            continue
        c = collections.Counter(c)
        if g.decision and not g.weak:
            c[g.decision] -= 1           # remove own contribution
            if c[g.decision] <= 0:
                del c[g.decision]
        if not c:
            continue
        seen += 1
        top, n = c.most_common(1)[0]
        if n / sum(c.values()) >= 0.7:
            votes[top] += 1
    # merge co-op votes into the member/host when comparing
    return votes, seen


def decide(groups, schools, passes=3):
    stats = collections.Counter()
    for p in range(passes):
        eidx = evidence_index(groups, schools)
        changed = 0
        for g in groups.values():
            if not g.athletes:
                continue
            votes, seen = group_evidence(g, eidx, schools)
            if not votes:
                continue
            top, n = votes.most_common(1)[0]
            second = votes.most_common(2)[1][1] if len(votes) > 1 else 0
            # athletes split between two members of a co-op that exists for this sport: the co-op
            if len(votes) > 1:
                (a, na), (b, nb) = votes.most_common(2)
                c = coop_of(schools, a, b, g.season)
                if c and (na + nb) / sum(votes.values()) >= 0.8 and min(na, nb) >= 2:
                    votes[c] = na + nb
                    top, n = c, na + nb
                    second = votes.most_common(4)[2][1] if len(votes) > 3 else 0
            share = n / max(1, sum(v for k, v in votes.items() if k == top or not compatible(schools, k, top)))
            g.evidence = {'votes': dict(votes.most_common(4)), 'athletes': len(g.athletes), 'with_evidence': seen}
            strong_ev = (n >= 3 and share >= 0.6 and n >= 2 * second) or \
                        (n >= 2 and share >= 0.8 and second == 0) or \
                        (n >= 1 and share == 1.0 and len(g.athletes) <= 2 and top in g.candidates)
            if g.decision and not g.weak:
                # confirmed or contradicted?
                if compatible(schools, g.decision, top) or not strong_ev:
                    continue
                if g.method.startswith('manual'):
                    g.flags.append(f'athletes disagree with file rule ({g.decision} -> {top}, {n}/{seen})')
                    continue
                own = sum(v for k, v in votes.items() if compatible(schools, k, g.decision))
                if own > 0.25 * sum(votes.values()):
                    continue
                base = g.method.split('+')[0]
                flag = f'athletes contradict name match ({g.decision} -> {top}, {n}/{seen})'
                if flag not in g.flags:
                    g.flags.append(flag)
                same_level = schools[g.decision]['level'] == schools.get(top, {}).get('level')
                if base in ('exact', 'stem') and same_level and 'level-context' not in g.method \
                        and not (g.decision.startswith('oos-auto') and
                                 not re.search(r'\S\s*[-,(]?\s*\b(VT|NH|MA|RI|CT|NY)\)?$', g.raw or '')):
                    # an exact full-name match is kept, but the conflict is reported (not a match to an
                    # automatic out-of-state entry named by a bare string: 'Lincoln' (RI) for Lincoln Academy;
                    # a printed state, 'Lake Region VT', stays)
                    continue
                to_meet_level = schools[g.decision].get('level') in ('ms', 'hs') and \
                    schools.get(top, {}).get('level') == g.level
                if not same_level and (g.level or sc.level_of(sc.norm(g.raw))) and not to_meet_level:
                    # the level came from the meet or the string itself; athletes seen at another
                    # level the same year are more likely a mis-levelled file elsewhere: report only
                    # (athletes at the meet's own level correct a name matched at the other level)
                    continue
                g.decision, g.method, g.weak = top, f'athlete-continuity (overrode {g.method})', False
                changed += 1
            elif strong_ev:
                lv_top = schools.get(top, {}).get('level')
                if g.meet_level in ('ms', 'hs') and lv_top in ('ms', 'hs') and lv_top != g.meet_level:
                    # the race's level is known: middle schoolers seen later at the high school
                    # ('Deer Isle St' in a middle-school league race) stay at their level (a group
                    # graded 'MS' in a varsity race is the high school's middle schoolers: not this)
                    continue
                prev = g.decision
                how = 'athlete-continuity'
                if g.candidates and top in g.candidates:
                    how = f'{g.method.split("+")[0]}+athletes'
                elif g.candidates:
                    how = f'athlete-continuity (name suggested {",".join(g.candidates[:3])})'
                g.decision, g.method, g.weak = top, how, False
                if prev != top:
                    changed += 1
        stats[f'pass{p + 1}_changed'] = changed
        if not changed:
            break
    return stats


# ---------------------------------------------------------------------------
# Team-score validation (XC)
# ---------------------------------------------------------------------------

TS_ROW = re.compile(r'^\s*\*?(\d+)\s+(.+?)[\s*]{2,}(\d+)\s+((?:\d+\s*)+)$')
TS_ROW_TIE = re.compile(r'^\s*(\d+)\s+(.+?)\s+(\d+)\s+((?:\(?\d+\)?\s*)+)$')


def parse_team_scores(text):
    """Return [{'event_idx': i, 'gender': g, 'teams': [(rank, name, total, [places...])]}] for Hy-Tek blocks."""
    text = re.sub(r'<[^>]+>', '', text)
    lines = text.splitlines()
    blocks = []
    event_idx = -1
    gender = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        if re.match(r'^\s*Event\s+\d+\s', ln):
            event_idx += 1
            gender = 'Girls' if re.search(r'girls|women', ln, re.I) else 'Boys' if re.search(r'boys|men', ln, re.I) else None
        if re.match(r'^\s*Team Scores\s*$', ln):
            teams = []
            section = ''
            j = i + 1
            while j < len(lines) and j < i + 600:
                l2 = lines[j]
                if re.match(r'^\s*Event\s+\d+\s', l2) or re.match(r'^\s*Team Scores\s*$', l2):
                    break
                m = re.match(r'^\s*Results\s*-\s*(Men|Women|Boys|Girls)\s*(.*)$', l2)
                if m:
                    # one Team Scores block can hold several races ('Results - Men Class A School')
                    if teams:
                        blocks.append({'event_idx': max(event_idx, 0), 'gender': gender, 'section': section,
                                       'teams': teams})
                        teams = []
                    gender = 'Girls' if m.group(1) in ('Women', 'Girls') else 'Boys'
                    section = m.group(2).strip()
                m = TS_ROW.match(l2.rstrip())
                if m and 'Total Time' not in l2 and 'Average' not in l2:
                    places = [int(x) for x in m.group(4).split()]
                    teams.append((int(m.group(1)), m.group(2).strip().rstrip('*').strip(), int(m.group(3)), places))
                j += 1
            if teams:
                blocks.append({'event_idx': max(event_idx, 0), 'gender': gender, 'section': section, 'teams': teams})
            i = j
            continue
        i += 1
    return blocks


def xc_score(finishers):
    """finishers: list of team keys in finish order (None = unattached/unknown).
    Standard XC: teams with >=5 finishers score; runners 8+ on a team and individuals are removed;
    top 5 count, 6-7 displace. Returns {team: (total, [places])}."""
    counts = collections.Counter(t for t in finishers if t)
    scoring = {t for t, n in counts.items() if n >= 5}
    seen = collections.Counter()
    place = 0
    pts = collections.defaultdict(list)
    for t in finishers:
        if t not in scoring:
            continue
        seen[t] += 1
        if seen[t] > 7:
            continue
        place += 1
        pts[t].append(place)
    return {t: (sum(p[:5]), p) for t, p in pts.items()}


def compare_scores(official, ours, resolve_official):
    """Match each official team to a computed team by its finishing places (the grouping test), then
    check that the official team name resolves to that same unit (the naming test).
    Returns (verified, teams_ok, details, names_agree, names_checked). A race is verified when every
    official team has a computed team with identical places and no computed team is left over."""
    by_places = {}
    for k, (tot, pl) in ours.items():
        by_places.setdefault(tuple(pl), k)
    ok = 0
    details = []
    used = set()
    agree = checked = 0
    for rank, name, total, places in official:
        key = resolve_official(name)
        hit = by_places.get(tuple(places))
        if hit is None:
            # Hy-Tek lists only scorers + displacers; tolerate a different count of non-displacing extras
            hit = next((k for k, (tot, pl) in ours.items() if pl[:len(places)] == places and tot == total
                        and k not in used), None)
        if hit is not None and hit not in used:
            ok += 1
            used.add(hit)
            if not str(key).startswith('raw:'):
                checked += 1
                agree += key == hit
            details.append((name, hit, total, ours[hit][0], 'ok' if key == hit or str(key).startswith('raw:')
                            else 'ok-name-differs:' + str(key)))
        else:
            got = ours.get(key)
            details.append((name, key, total, got[0] if got else None, 'mismatch' if got else 'no-team'))
            if got:
                used.add(key)
    for k, (tot, pl) in ours.items():
        if k not in used:
            details.append((None, k, None, tot, 'extra-team'))
    verified = ok == len(official) and len(used) == len(ours)
    return verified, ok, details, agree, checked


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def file_expansion(groups, schools):
    """A truncated name is the school a full name in the same file starts
    with: "Mountain Val" beside "Mountain Valley" is Mountain Valley, whatever
    the string means elsewhere (the Dirigo/Mountain Valley XC co-op made it
    Dirigo). Only a truncation or a weak decision gives way, and only to one
    exact full name."""
    by_file = collections.defaultdict(list)
    for g in groups.values():
        by_file[g.rel].append(g)
    changed = 0
    for rel, gs in by_file.items():
        full = [(sc.norm(x.raw), x) for x in gs if x.decision and not x.weak and
                (x.method or '').split('+')[0] in ('exact', 'stem') and x.raw]
        for g in gs:
            m = (g.method or '').split('+')[0]
            cont = (g.method or '').startswith('athlete-continuity')
            if not g.raw or not (g.weak or m in ('truncation', 'code') or cont) or (g.method or '').startswith('manual'):
                continue
            n = sc.norm(g.raw)
            hits = {x.decision for fn, x in full if fn != n and fn.startswith(n)} if len(n) >= 6 else set()
            # a code made of a full name's initials: "WE" beside "Warsaw
            # Elementary", "MBJH" beside "Mt. Blue Junior High"
            if not hits and re.fullmatch(r'[A-Z]{2,5}', (g.raw or '').strip()):
                code = g.raw.strip()
                hits = {x.decision for fn, x in full
                        if ''.join(w[0] for w in re.findall(r'[A-Za-z]+', x.raw)).upper() == code}
            if len(hits) == 1:
                sid = hits.pop()
                cur = schools.get(g.decision) if g.decision else None
                # (the level is the meet's call; a curated school is not
                # swapped for an automatic out-of-state entry)
                if cur and (cur.get('level') != schools.get(sid, {}).get('level') or sid.startswith('oos-auto')):
                    continue
                # continuity gives way only to a school its own name suggested
                if cont and sid not in (g.candidates or []):
                    continue
                if sid != g.decision:
                    g.flags.append(f'file expansion: {g.decision} -> {sid}')
                    g.decision, g.method, g.weak = sid, f'file-expansion (was {g.method})', False
                    changed += 1
    print(f'file expansion: {changed} truncated names read as a full name in the same file')
    return changed


def company_check(groups, schools):
    """'The company a school keeps', for the decisions that rest on weak names.

    A code, a mascot or an athlete-continuity decision can settle on the wrong
    school when two schools share it ("Hawks": Marshwood and Hermon; "MJHS":
    Messalonskee and Mattanawcook) -- and continuity can then confirm the
    mistake, because the same runners carry the same string in other files.
    The schools a file names in full are independent evidence: Marshwood's
    home meet also has Sanford, Noble and Massabesic, schools Marshwood meets
    every season and Hermon never does. Among the ids the string resolves to
    anywhere, the one that races with this file's other schools far more often
    than the current decision wins."""
    named = collections.defaultdict(set)
    for g in groups.values():
        if g.decision and not g.weak and not g.decision.startswith('x-') and \
                (g.method or '').split('+')[0] in ('exact', 'stem', 'truncation'):
            named[g.rel].add(g.decision)
    cooc = collections.Counter()
    nfiles = collections.Counter()
    for ids in named.values():
        for a in ids:
            nfiles[a] += 1
            for b in ids:
                if a != b:
                    cooc[(a, b)] += 1
    by_raw = collections.defaultdict(collections.Counter)
    for g in groups.values():
        if g.decision:
            by_raw[g.raw][g.decision] += g.rows
    # where a middle schooler runs in high school: (athlete) -> {ay: hs town}
    later = collections.defaultdict(dict)
    for g in groups.values():
        e = schools.get(g.decision) if g.decision else None
        if e and e.get('level') == 'hs' and e.get('town') and not g.weak:
            for a in g.athletes:
                later[a][g.ay] = e['town']

    hs_towns = {e.get('town') for e in schools.values() if e.get('level') == 'hs' and e.get('town')}

    def later_town(g):
        towns = collections.Counter()
        for a in g.athletes:
            t = [tw for ay, tw in later.get(a, {}).items() if g.ay < ay <= g.ay + 5]
            if t:
                towns[collections.Counter(t).most_common(1)[0][0]] += 1
        if not towns:
            return None
        t, n = towns.most_common(1)[0]
        return t if n >= 4 and n >= 0.7 * sum(towns.values()) else None
    changed = 0
    for g in groups.values():
        m = g.method or ''
        if not g.decision or m.startswith(('manual', 'later-hs')) or \
                not (g.weak or m.split('+')[0] in ('code', 'mascot', 'nickname')
                     or m.startswith(('athlete-continuity', 'company'))):
            continue
        others = named.get(g.rel, set()) - {g.decision}
        # a full name ("Phillips Exeter", "Plymouth South") is not up for
        # grabs: only a short code, a mascot or nickname may become a school
        # its name doesn't suggest
        open_name = len(g.raw or '') <= 6 or m.split('+')[0] in ('mascot', 'nickname') or \
            (' ' not in (g.raw or '') and (g.raw or '').isupper())
        cands = set(g.candidates or [])
        if open_name:
            cands |= set(by_raw[g.raw]) | set((g.evidence or {}).get('votes', {}))
        # same level only: middle vs high school is the meet's and the
        # string's call (relevel, level context), not the company's
        lv = schools.get(g.decision, {}).get('level')
        cands = {c for c in cands if c in schools and not c.startswith('x-')
                 and schools[c].get('level') == lv and nfiles[c] >= 5}

        # middle school: the high school its runners go on to names the town
        if lv == 'ms':
            t = later_town(g)
            # (a town with no high school sends its runners elsewhere:
            # Durham's go on to Freeport, which says nothing against Durham)
            if t and schools.get(g.decision, {}).get('town') != t and \
                    schools.get(g.decision, {}).get('town') in hs_towns:
                fit = [c for c in cands if schools[c].get('town') == t]
                if len(fit) == 1:
                    g.flags.append(f'later high school: {g.decision} -> {fit[0]} (runners go on to {t})')
                    g.decision, g.method, g.weak = fit[0], f'later-hs (was {m.split(" (was ")[0]})', False
                    changed += 1
                    continue
            if t and schools.get(g.decision, {}).get('town') == t:
                continue      # the future high school agrees: leave it
        if len(others) < 2:
            continue

        def score(sid):
            # share of sid's meets that have each of this file's schools: a
            # big school that races everyone does not win by size
            if not nfiles[sid]:
                return 0.0
            return sum(cooc[(sid, o)] for o in others if not compatible(schools, sid, o)) / nfiles[sid]
        cur = score(g.decision)
        best = max(cands, key=score, default=None)
        if best and best != g.decision and not compatible(schools, best, g.decision):
            b = score(best)
            if b >= 0.5 and b >= 5 * max(cur, 0.05):
                g.flags.append(f'company: {g.decision} ({cur:.2f}) -> {best} ({b:.2f})')
                g.decision, g.method, g.weak = best, f'company (was {m.split(" (was ")[0]})', False
                changed += 1
    print(f'company check: {changed} groups re-resolved by the schools they race with')
    return changed


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--parsed', nargs='*', default=[os.path.join(DATA, 'parsed_results')])
    ap.add_argument('--archive', nargs='*', default=[os.path.join(DATA, 'sub5_archive')])
    ap.add_argument('--store', default=os.path.join(REPO, 'ui', 'public', 'data', 'teams'))
    ap.add_argument('--no-before', action='store_true', help='skip the scraper_v2 baseline in validation')
    ap.add_argument('--out', default=DATA)
    ap.add_argument('--rows-cache', default=None, help='pickle of scanned rows (dev speed-up)')
    ap.add_argument('--skip-validation', action='store_true')
    ap.add_argument('--dump-groups', default=None, help='pickle group decisions (debugging)')
    args = ap.parse_args(argv)
    t0 = time.time()

    schools, coops = seed_entries()
    sc.NOT_SCHOOL_PATTERNS[:] = seed.NOT_SCHOOLS
    idx = sc.Index(schools)
    print(f'seed: {len(schools)} entries ({len(coops)} co-ops)')

    if args.rows_cache and os.path.exists(args.rows_cache):
        import pickle
        with open(args.rows_cache, 'rb') as f:
            rows = pickle.load(f)
    else:
        rows = scan(args.parsed)
        if args.rows_cache:
            import pickle
            with open(args.rows_cache, 'wb') as f:
                pickle.dump(rows, f)
    print(f'scanned {len(rows)} rows in {time.time() - t0:.0f}s')
    levels = row_levels(rows)
    groups, keys = build_groups(rows, idx, levels)
    auto = auto_entries(groups, schools)
    if auto:
        schools.update(auto)
        idx = sc.Index(schools)
        groups, keys = build_groups(rows, idx, levels)
    relevel(groups, idx)
    global KEYS
    KEYS = keys
    print(f'{len(groups)} (file, raw string) groups; {len(auto)} automatic out-of-state entries')
    stats = decide(groups, schools)
    print('evidence passes:', dict(stats))
    file_expansion(groups, schools)
    # the company check corrects codes and mascots that continuity then
    # leaned on elsewhere ("MJH" -> Mattanawcook made Messalonskee's own
    # runners look like Mattanawcook's): re-run the evidence after it
    for _ in range(2):
        if not company_check(groups, schools):
            break
        print('evidence passes:', dict(decide(groups, schools)))
    coop_activity(groups, schools, coops, idx, args)
    n_host = coop_labels_to_host(groups, schools)
    print(f'co-op labels read where the co-op was not competing -> host school: {n_host} groups')
    if args.dump_groups:
        import pickle
        with open(args.dump_groups, 'wb') as f:
            pickle.dump({k: (g.decision, g.method, g.weak, g.candidates, g.evidence, g.flags, g.rows,
                             len(g.athletes)) for k, g in groups.items()}, f)

    out = assemble(groups, rows, schools, coops, idx, args)
    print(f'done in {time.time() - t0:.0f}s')
    return out


def category(method, decision, candidates, schools):
    """Coarse resolution method for reporting."""
    method = method or 'unresolved'
    if not decision:
        if method in ('debris', 'blank'):
            return method
        return 'ambiguous' if candidates else 'unresolved'
    if method.startswith('salvaged:'):
        return 'debris-salvage'
    if method.startswith('manual'):
        return 'manual (file rule)'
    if 'co-op-not-active->host' in method:
        return 'co-op label -> host (co-op not active)'
    if schools.get(decision, {}).get('level') == 'coop':
        return 'co-op label'
    base = method.split(' (')[0].split('+')[0]
    if 'overrode' in method or base in ('athlete-continuity', 'ambiguous-name', 'ambiguous-stem',
                                        'ambiguous-truncation'):
        return 'athlete-continuity'
    if base == 'exact' and schools.get(decision, {}).get('curation') == 'auto':
        return 'state-tagged (auto entry)'
    return {'exact': 'exact/alias', 'stem': 'exact/alias', 'bare-name': 'bare name + level context',
            'truncation': 'truncation', 'code': 'code', 'nickname': 'mascot', 'fuzzy': 'spelling (fuzzy)'}.get(base, base)


def name_based(method):
    """A decision read from the string itself (name, alias, truncation, unique code), not from per-file evidence."""
    base = (method or '').split(' (')[0].split('+')[0]
    base = base[len('salvaged:'):] if base.startswith('salvaged:') else base
    return base in ('exact', 'stem', 'bare-name', 'truncation', 'code', 'file-expansion')


def assemble(groups, rows, schools, coops, idx, args):
    # ---- raw string map -------------------------------------------------
    by_raw = collections.defaultdict(list)
    for g in groups.values():
        by_raw[g.raw].append(g)
    raw_map = {}
    overrides = collections.defaultdict(dict)
    method_rows = collections.Counter()
    method_strings = collections.Counter()
    unresolved = []
    for raw, gs in by_raw.items():
        rows_n = sum(g.rows for g in gs)
        ids = collections.Counter()
        lv = collections.defaultdict(collections.Counter)
        methods = collections.Counter()
        seasons = collections.Counter()
        years = set()
        by_season = collections.defaultdict(collections.Counter)
        for g in gs:
            ids[g.decision] += g.rows
            if not g.decision or name_based(g.method):
                lv[g.level or 'hs'][g.decision] += g.rows
            by_season[g.season][g.decision] += g.rows
            if g.decision:
                methods[g.method or 'unresolved'] += g.rows
            seasons[g.season] += g.rows
            years.add(int(g.year))
        top, top_n = ids.most_common(1)[0]
        entry = {'rows': rows_n, 'seasons': dict(seasons), 'years': [min(years), max(years)]}
        resolved_rows = sum(n for i, n in ids.items() if i)
        if top is None and resolved_rows == 0:
            entry['id'] = None
            m = gs[0].method or 'unresolved'
            entry['method'] = m
            cands = sorted({c for g in gs for c in (g.candidates or [])})
            if cands:
                entry['candidates'] = cands[:8]
            unresolved.append((raw, entry))
        else:
            best = max((i for i in ids if i), key=lambda i: ids[i])
            entry['id'] = best
            entry['method'] = methods.most_common(1)[0][0]
            # a meaning read from one file (seed FILE_RULES / FILE_CODES: 'K' is Kennebunk in this dual meet) is never
            # the string's global meaning: such strings are context dependent, answered per file only
            manual = any((g.method or '').startswith('manual') for g in gs)
            if len([i for i in ids if i]) > 1 or ids.get(None) or manual:
                entry['by_id'] = {str(k): v for k, v in ids.most_common()}
                # level-split strings are context dependent. The per-level answer (by_level, used for files the
                # builder has not seen) comes from name matches only ('York' -> York HS / York MS); a level's answer
                # made of per-file evidence (file rules, athlete continuity: 'M', 'D', 'T') is no rule for other files
                levels = {l: c.most_common(1)[0][0] for l, c in lv.items() if c}
                if len(set(levels.values()) - {None}) > 1:
                    entry['context_dependent'] = True
                    entry['by_level'] = {l: i for l, i in levels.items() if i}
                # several schools, or a large unresolved share: the string has no context-free meaning
                # ('Warriors', 'Win', 'M'); runtime resolution then needs the per-file overrides
                distinct = {i for i in ids if i}
                if len(distinct) > 1 and not entry.get('by_level') or ids.get(None, 0) >= 0.2 * rows_n or manual:
                    entry['context_dependent'] = True
                for g in gs:
                    if g.decision != best or entry.get('context_dependent'):
                        y, s, fn = g.rel.split(os.sep)
                        overrides[f'{y}/{s}/{os.path.splitext(fn)[0]}'][raw] = g.decision
            if ids.get(None):
                entry['unresolved_rows'] = ids[None]
            # a string can mean a co-op in one sport and the school in another ('North Yarmou')
            bs = {se: c.most_common(1)[0][0] for se, c in by_season.items()}
            if any(v != best and v for v in bs.values()):
                entry['by_season'] = {se: v for se, v in bs.items() if v}
        flags = sorted({f for g in gs for f in g.flags})
        if flags:
            entry['flags'] = flags[:5]
        raw_map[raw] = entry
        for g in gs:
            method_rows[category(g.method, g.decision, g.candidates, schools)] += g.rows
        entry['how'] = category(entry.get('method'), entry.get('id'), entry.get('candidates'), schools)
        method_strings[entry['how']] += 1

    # ---- co-op evidence: labels seen, member strings scored inside a co-op ----

    # ---- usage stats per school ----------------------------------------
    usage = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for g in groups.values():
        if g.decision:
            usage[g.decision][g.season][int(g.year)] += g.rows
    for sid, e in schools.items():
        u = usage.get(sid)
        e['rows'] = sum(sum(v.values()) for v in u.values()) if u else 0
        if u:
            e['seen'] = {s: [min(y), max(y)] for s, y in u.items()}
        e['raw_strings'] = 0
    for raw, entry in raw_map.items():
        if entry.get('id') in schools:
            schools[entry['id']]['raw_strings'] += 1

    # ---- store team map --------------------------------------------------
    if args.skip_validation:
        store_map, validation = {}, {}
    else:
        store_map, store_splits = map_store_teams(rows, groups, args.store, schools)
        STORE_MAP.clear()
        STORE_MAP.update(store_map)
        # ---- validation --------------------------------------------------
        validation = validate(rows, groups, schools, coops, idx, args, raw_map)
        validation['store_team_splits'] = store_splits

    # ---- write -----------------------------------------------------------
    os.makedirs(args.out, exist_ok=True)
    catalog = {
        '_meta': {
            'generated_by': 'backend/build_school_catalog.py',
            'seed': 'backend/school_catalog_seed.py',
            'mpa_sources': seed.MPA_SOURCES,
            'counts': collections.Counter(e['level'] for e in schools.values()),
            'id_scheme': 'me-hs-* Maine high schools, me-ms-* Maine middle/K-8, col-* colleges, oos-* out-of-state '
                         'schools, club-* clubs, coop-* co-operative teams (sport/gender/year specific), x-* special',
        },
        'schools': dict(sorted(schools.items())),
        'coops': coops,
        'not_schools': seed.NOT_SCHOOLS,
        'file_rules': [{'raw': r, 'season': se, 'years': list(y), 'file': f, 'id': i}
                       for r, se, y, f, i in seed.FILE_RULES],
    }
    with open(os.path.join(args.out, 'school_catalog.json'), 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=1, ensure_ascii=False, default=dict)
    rawdoc = {
        '_meta': {
            'methods_by_rows': dict(method_rows.most_common()),
            'methods_by_strings': dict(method_strings.most_common()),
            'distinct_strings': len(raw_map),
            'note': "'raw' keys are whitespace-collapsed school strings exactly as printed. 'overrides' are "
                    "per-file answers (year/season/file-stem) that differ from the string's global id.",
        },
        'raw': dict(sorted(raw_map.items(), key=lambda kv: -kv[1]['rows'])),
        'overrides': {k: dict(sorted(v.items())) for k, v in sorted(overrides.items())},
        'store_teams': store_map,
        'unresolved': [{'raw': r, **e} for r, e in sorted(unresolved, key=lambda x: -x[1]['rows'])],
    }
    with open(os.path.join(args.out, 'school_raw_map.json'), 'w', encoding='utf-8') as f:
        json.dump(rawdoc, f, indent=0, ensure_ascii=False)
    with open(os.path.join(args.out, 'school_catalog_validation.json'), 'w', encoding='utf-8') as f:
        json.dump(validation, f, indent=1, ensure_ascii=False, default=list)
    print('methods by rows:', dict(method_rows.most_common()))
    print('methods by strings:', dict(method_strings.most_common()))
    return catalog, rawdoc, validation


# ---------------------------------------------------------------------------
# Store team mapping
# ---------------------------------------------------------------------------

def _nkey(name):
    return ' '.join(sorted(re.findall(r'[a-z]+', (name or '').lower())))


def map_store_teams(rows, groups, store_dir, schools):
    """Join store rows to parsed rows (year, season, file stem, mark, athlete) to learn which catalog
    ids each store team actually holds."""
    if not os.path.isdir(store_dir):
        return {}, []
    sys.path.insert(0, REPO)
    from backend.json_store import _chunk_files, _load_json, canonical_team_name
    store = {}
    for fn in os.listdir(store_dir):
        full = os.path.join(store_dir, fn)
        if not os.path.isdir(full):
            continue
        team = canonical_team_name(fn)
        for key, chunk in _chunk_files(full):
            year, _, season = key.partition('_')
            try:
                prs = _load_json(os.path.join(full, chunk), [])
            except Exception:
                continue
            for p in prs:
                store[(year, season, p.get('meet_name', ''), str(p.get('mark', '')).strip(),
                       _nkey(p.get('athlete_name', '')))] = team
    held = collections.defaultdict(collections.Counter)
    ROW_STORE.clear()
    for i, r in enumerate(rows):
        year, season, rel = r[0], r[1], r[2]
        stem_ = os.path.splitext(os.path.basename(rel))[0]
        t = store.get((year, season, stem_, str(r[11]).strip(), _nkey(r[8])))
        if not t:
            continue
        g = groups.get(KEYS[i])
        held[t][g.decision if g else None] += 1
        ROW_STORE[i] = t
    store_map = {}
    splits = []
    for team, c in sorted(held.items()):
        tot = sum(c.values())
        resolved = {k: v for k, v in c.items() if k}
        if not resolved:
            store_map[team] = None
            continue
        top, n = max(resolved.items(), key=lambda kv: kv[1])
        if n / tot >= 0.9:
            store_map[team] = top
        else:
            store_map[team] = {'id': top, 'held': {str(k): v for k, v in c.most_common(6)}}
        # a store team holding a second institution (>=5% of its rows, or >=100 rows) is a wrong merge
        real = [(k, v) for k, v in c.most_common() if k and (v >= max(5, 0.05 * tot) or v >= 100)]
        if len(real) > 1:
            splits.append({'store_team': team, 'rows': tot,
                           'holds': [{'id': k, 'name': schools[k]['name'], 'rows': v} for k, v in real]})
    splits.sort(key=lambda s: -s['rows'])
    # store teams with no joinable rows (rows dropped at sync, or written by an older scrape):
    # name-only resolution, marked as such
    idx = sc.Index(schools)
    for fn in os.listdir(store_dir):
        if not os.path.isdir(os.path.join(store_dir, fn)):
            continue
        team = canonical_team_name(fn)
        if team in store_map:
            continue
        sid, method, cands, weak = idx.match(team)
        store_map[team] = {'id': sid if sid and not weak else None, 'basis': 'name only (no joined rows)'}
    return dict(sorted(store_map.items())), splits


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(rows, groups, schools, coops, idx, args, raw_map):
    val = {}
    # identity conflicts (name says X, athletes say Y)
    conflicts = []
    for g in groups.values():
        for f in g.flags:
            conflicts.append({'raw': g.raw, 'file': g.rel, 'rows': g.rows, 'flag': f,
                              'decision': g.decision, 'evidence': g.evidence})
    conflicts.sort(key=lambda c: -c['rows'])
    val['identity_conflicts'] = conflicts

    # MPA coverage
    cov = []
    for sid, e in schools.items():
        for key, recs in e.get('mpa_class', {}).items():
            for rec in recs:
                cov.append({'list': key, 'class': rec['class'], 'id': sid, 'name': e['name'],
                            'gender': rec.get('gender'), 'rows': e.get('rows', 0), 'seen': e.get('seen', {})})
    no_data = [c for c in cov if c['rows'] == 0]
    no_xc = [c for c in cov if c['list'] == 'xc_2026' and 'XC' not in c['seen'] and schools[c['id']]['level'] != 'coop']
    val['mpa_coverage'] = {'entries': len(cov), 'no_data': no_data, 'xc_list_without_xc_rows': no_xc}

    # same-day class conflicts: an id whose athletes ran two different MPA class races on one date
    val['class_conflicts'] = class_conflicts(rows, groups, schools)
    # MPA class membership: in 2025/2026 class races every team should be in that class on the 2026-27 list
    val['mpa_class_membership'] = class_membership(rows, groups, schools, args)

    # team scores
    val['team_scores'] = team_score_check(rows, groups, schools, coops, idx, args, raw_map)
    return val


CLASS_RE = re.compile(r'class[\s_-]*([abcd])\b|\b([abcd])[\s_-]*(north|south)\b|(north|south)[\s_-]*([abcd])\b|'
                      r'class([abcd])(boys|girls)', re.I)


def race_class(rel, event, meet):
    s = f'{os.path.basename(rel)} {event} {meet}'.lower().replace('.txt', '')
    if 'combined' in s or 'all classes' in s:
        return None
    m = CLASS_RE.search(s)
    if not m:
        return None
    letter = next(x for x in (m.group(1), m.group(2), m.group(5), m.group(6)) if x)
    region = (m.group(3) or m.group(4) or '')
    return f'{letter.upper()}{(" " + region.title()) if region else ""}'


def class_conflicts(rows, groups, schools):
    """For XC championship races (regionals/states, identified by class in file/event names): each
    team must appear in one class race per date. Report ids and raw strings that span two classes."""
    seen = collections.defaultdict(lambda: collections.defaultdict(set))  # (date, gender, id) -> class -> files
    raw_seen = collections.defaultdict(lambda: collections.defaultdict(set))
    for i, r in enumerate(rows):
        year, season, rel, meet, date, ev, gender = r[:7]
        if season != 'XC' or not date or not re.match(r'^\d{4}-\d\d-\d\d', date):
            continue
        cl = race_class(rel, ev, meet)
        if not cl:
            continue
        g = groups.get(KEYS[i])
        if not g or not g.decision:
            continue
        seen[(date, gender, g.decision)][cl[0]].add(rel)
        raw_seen[(date, gender, g.raw)][cl[0]].add(rel)
    out = []
    for (date, gender, sid), cls in seen.items():
        if len(cls) > 1 and schools.get(sid, {}).get('level') != 'x':
            out.append({'date': date, 'gender': gender, 'id': sid, 'classes': {k: sorted(v) for k, v in cls.items()}})
    return sorted(out, key=lambda x: x['date'])


MPA_LIST_SEASONS = {'xc_2026': [('XC', 2026)], 'it_2026': [('Indoor', 2026), ('Indoor', 2027)],
                    'ot_2026': [('Outdoor', 2026)]}
_BLOCK_CACHE = {}


def team_score_blocks(rel, archive_roots):
    if rel in _BLOCK_CACHE:
        return _BLOCK_CACHE[rel]
    out = None
    for root in archive_roots:
        cand = os.path.join(root, os.path.splitext(rel)[0] + '.htm')
        if os.path.exists(cand):
            try:
                text = open(cand, encoding='utf-8', errors='replace').read()
            except Exception:
                break
            out = parse_team_scores(text) if 'Team Scores' in text else []
            break
    _BLOCK_CACHE[rel] = out
    return out


def coop_labels_to_host(groups, schools):
    """A co-op label in a sport/year/gender where that co-op was not competing names its host school
    ('Lisbon/Oak Hill' in 2026 XC = Lisbon's XC team; Lisbon/Oak Hill is an outdoor-track co-op).
    Same rule as school_catalog.coop_or_host() at runtime."""
    n = 0
    for g in groups.values():
        e = schools.get(g.decision or '', {})
        if e.get('level') != 'coop':
            continue
        active = g.season in e.get('seasons', []) and int(g.year) in e.get('active', {}).get(g.season, []) and \
            not (g.gender and e.get('genders') and g.gender not in e['genders'])
        if not active:
            host = next(c['host'] for c in seed.COOPS if c['id'] == g.decision)
            g.decision, g.method = host, f'{g.method}+co-op-not-active->host'
            n += 1
    return n


def coop_activity(groups, schools, coops, idx, args):
    """When was each co-op actually competing? Evidence: (1) its label printed in results, (2) its label as
    an official team in a Team Scores block, (3) an MPA classification list. 'active' fills gaps of up to
    two years between evidence years; team_unit() uses 'active'."""
    ev = collections.defaultdict(lambda: collections.defaultdict(set))
    src = collections.defaultdict(lambda: collections.defaultdict(set))
    for g in groups.values():
        if g.decision and schools.get(g.decision, {}).get('level') == 'coop':
            ev[g.decision][g.season].add(int(g.year))
            src[g.decision]['result labels'].add(f'{g.season} {g.year}')
    xc_files = {g.rel for g in groups.values() if g.season == 'XC'}
    for rel in xc_files:
        blocks = team_score_blocks(rel, args.archive)
        if not blocks:
            continue
        year = int(rel.split(os.sep)[0])
        for b in blocks:
            for _rank, name, _tot, _pl in b['teams']:
                sid = idx.match(name)[0]
                if sid and schools.get(sid, {}).get('level') == 'coop':
                    ev[sid]['XC'].add(year)
                    src[sid]['team-score blocks'].add(f'XC {year}')
    for sid, e in schools.items():
        for key, recs in e.get('mpa_class', {}).items():
            if e.get('level') == 'coop':
                for season, y in MPA_LIST_SEASONS[key]:
                    ev[sid][season].add(y)
                    src[sid]['MPA lists'].add(f'{season} {y}')
    for c in coops:
        seen_all = ev.get(c['id'], {})
        # the seed says which sports the co-op exists in; a label seen in another sport is recorded only
        seen = {s: y for s, y in seen_all.items() if s in c['seasons']}
        outside = {s: sorted(y) for s, y in seen_all.items() if s not in c['seasons']}
        if outside:
            c['observed_outside_seasons'] = outside
        c['observed'] = {s: sorted(y) for s, y in seen.items()}
        c['observed_sources'] = {k: sorted(v) for k, v in src.get(c['id'], {}).items()}
        active = {}
        for s, ys in seen.items():
            ys = sorted(ys)
            fill = set(ys)
            for a, b in zip(ys, ys[1:]):
                if b - a <= 3:
                    fill.update(range(a, b + 1))
            active[s] = sorted(fill)
        c['active'] = active
        schools[c['id']]['active'] = active


def class_membership(rows, groups, schools, args):
    """XC class races (class A/B/C, north/south) in 2025-2026: is each team's resolved school in that class
    on the MPA 2026-27 list?  'after' uses the catalog; 'before' uses the store team the row landed in
    (mapped to the catalog id that team mostly holds).  Reclassification between 2025 and 2026 causes a
    few legitimate disagreements; a wrong merge (a Class C school filed under a Class A team) shows up here."""
    store_map = STORE_MAP
    def mpa_class(sid):
        e = schools.get(sid or '', {})
        recs = e.get('mpa_class', {}).get('xc_2026', [])
        if not recs:
            for c in e.get('coop_of', []):
                recs = schools.get(c, {}).get('mpa_class', {}).get('xc_2026', [])
                if recs:
                    break
        return recs[0]['class'] if recs else None
    out = {'after': collections.Counter(), 'before': collections.Counter(), 'after_disagree': collections.Counter(),
           'before_disagree': collections.Counter()}
    for i, r in enumerate(rows):
        year, season, rel, meet, date, ev, gender = r[:7]
        if season != 'XC' or year not in ('2022', '2023', '2024', '2025', '2026'):
            continue
        cl = race_class(rel, ev, meet)
        if not cl or not str(r[11]).strip()[:1].isdigit():
            continue
        g = groups.get(KEYS[i])
        for side, sid in (('after', g.decision if g else None),
                          ('before', (lambda t: (store_map.get(t) or {}).get('id') if isinstance(store_map.get(t), dict)
                                     else store_map.get(t))(ROW_STORE.get(i)) if ROW_STORE.get(i) else None)):
            mc = mpa_class(sid)
            if not mc:
                out[side]['no class'] += 1
                continue
            ok = mc[0] == cl[0] and (len(cl) == 1 or cl.split()[-1] == mc.split()[-1])
            out[side]['agree' if ok else 'disagree'] += 1
            if not ok:
                label = ROW_STORE.get(i) if side == 'before' else sid
                out[side + '_disagree'][f'{year}: {label} [{mc}] in {cl} race ({clean_raw(r[9])})'] += 1
    return {k: (dict(v.most_common(40)) if 'disagree' in k else dict(v)) for k, v in out.items()}


def team_score_check(rows, groups, schools, coops, idx, args, raw_map):
    """Re-score every XC race that has an official Team Scores block; compare before (scraper_v2 team
    names) and after (catalog team units)."""
    coop_by_member = collections.defaultdict(list)
    for c in coops:
        for m in c['members']:
            coop_by_member[m].append(c)

    def unit(sid, year, season, gender):
        for c in coop_by_member.get(sid, []):
            if c.get('genders') and gender not in c['genders']:
                continue
            if int(year) in c.get('active', {}).get(season, []):
                return c['id']
        return sid

    before = None
    if not args.no_before:
        try:
            from backend.scraper_v2 import Sub5ScraperV2, TEAM_MAPPING
            from backend.json_store import list_teams
            scr = Sub5ScraperV2()
            known = set(TEAM_MAPPING.values()) | set(list_teams())

            def before(raw, level):
                return scr.normalize_team_name(raw, all_teams=known, level=level or 'hs')
        except Exception as ex:   # pragma: no cover
            print('baseline unavailable:', ex)
            before = None

    # events per file, in parsed order
    events = collections.defaultdict(lambda: collections.defaultdict(list))
    for i, r in enumerate(rows):
        if r[1] != 'XC':
            continue
        events[r[2]][r[12] if r[12] >= 0 else 0].append((i, r))

    races = []
    for rel, evs in events.items():
        blocks = team_score_blocks(rel, args.archive)
        if not blocks:
            continue
        ev_keys = sorted(evs)
        for bi, b in enumerate(blocks):
            # pick the parsed event: named section ('Class A School'), same index, else same gender
            sec = re.sub(r'\s+', ' ', b.get('section') or '').strip().lower()
            cand = [k for k in ev_keys if sec and sec in re.sub(r'\s+', ' ', evs[k][0][1][5]).lower()] or \
                   [k for k in ev_keys if k == b['event_idx']] or \
                   [k for k in ev_keys if b['gender'] and evs[k][0][1][6] == b['gender']] or \
                   (ev_keys if len(ev_keys) == 1 else [])
            if not cand:
                continue
            ev_idx = [i for i, _ in evs[cand[0]]]
            ev_rows = [r for _, r in evs[cand[0]]]
            year, season = ev_rows[0][0], ev_rows[0][1]
            gender = ev_rows[0][6] or b['gender']
            level = KEYS[ev_idx[0]][1]
            finishers_after, finishers_before = [], []
            for i, r in zip(ev_idx, ev_rows):
                mark = str(r[11]).strip().upper()
                if not re.match(r'^\d', mark):
                    continue
                g = groups.get(KEYS[i])
                sid = g.decision if g else None
                raw_s = clean_raw(r[9])
                if sid:
                    u = None if sid.startswith('x-') else unit(sid, year, season, gender)
                else:   # unresolved: still one (unknown) team, never pooled with others
                    u = f'raw:{raw_s}' if raw_s and not sc.looks_like_debris(raw_s) else None
                finishers_after.append(u)
                if before:
                    bt = before(raw_s, level) if raw_s else None
                    finishers_before.append(None if bt in ('Unattached', 'Unknown') else bt)
            ours_after = xc_score(finishers_after)

            def res_after(name):
                sid, m, c, w = idx.match(name, level=level, gender=gender)
                if not sid:
                    # official names are full names; fall back to the raw map
                    sid = (raw_map.get(clean_raw(name)) or {}).get('id')
                return unit(sid, year, season, gender) if sid else f'raw:{clean_raw(name)}'

            ok_a, n_a, det_a, agree_a, chk_a = compare_scores(b['teams'], ours_after, res_after)
            off_max = max((p for t in b['teams'] for p in t[3]), default=0)
            our_max = max((p for t in ours_after.values() for p in t[1]), default=0)
            kinds = {d[4] for d in det_a if d[4] != 'ok'}
            if ok_a:
                why = 'verified'
            elif our_max < 0.85 * off_max or our_max > 1.15 * off_max + 2:
                why = 'finisher count differs'      # parsed race is missing (or has extra) scorers
            elif kinds & {'no-team', 'extra-team'}:
                why = 'team set differs'
            elif abs(our_max - off_max) >= 2:
                why = 'finisher count differs'
            else:
                why = 'points differ'
            rec = {'file': rel, 'block': bi, 'section': b.get('section') or None, 'gender': gender,
                   'teams': len(b['teams']), 'official_last_place': off_max, 'our_last_place': our_max,
                   'after': {'verified': ok_a, 'teams_ok': n_a, 'class': why, 'names_agree': agree_a,
                             'names_checked': chk_a, 'bad': [d for d in det_a if d[4] != 'ok'][:20]}}
            if before:
                ours_b = xc_score(finishers_before)
                ok_b, n_b, det_b, agree_b, chk_b = compare_scores(b['teams'], ours_b, lambda nm: before(nm, level))
                rec['before'] = {'verified': ok_b, 'teams_ok': n_b, 'names_agree': agree_b, 'names_checked': chk_b,
                                 'bad': [d for d in det_b if d[4] != 'ok'][:20]}
            races.append(rec)
    summ = {'races': len(races),
            'after_verified': sum(1 for r in races if r['after']['verified']),
            'after_teams_ok': sum(r['after']['teams_ok'] for r in races),
            'teams': sum(r['teams'] for r in races),
            'after_failure_classes': dict(collections.Counter(r['after']['class'] for r in races)),
            'after_official_names_agree': sum(r['after']['names_agree'] for r in races),
            'after_official_names_checked': sum(r['after']['names_checked'] for r in races)}
    if before:
        summ['before_verified'] = sum(1 for r in races if r.get('before', {}).get('verified'))
        summ['before_teams_ok'] = sum(r.get('before', {}).get('teams_ok', 0) for r in races)
        summ['before_official_names_agree'] = sum(r['before']['names_agree'] for r in races)
        summ['before_official_names_checked'] = sum(r['before']['names_checked'] for r in races)
        summ['fixed_by_catalog'] = sum(1 for r in races if r['after']['verified'] and not r['before']['verified'])
        summ['broken_by_catalog'] = sum(1 for r in races if not r['after']['verified'] and r['before']['verified'])
    print('team scores:', summ)
    return {'summary': summ, 'races': races}


if __name__ == '__main__':
    main()
