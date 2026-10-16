"""
athlete_catalog.py - one id per runner, across every spelling of their name.

The store keys an athlete by slug(printed name + store team), so "Addison
Pellerano", "Adison Pellarano" and "Pellerano Addison" are three athletes and
none of them has a whole career. This module groups those spellings into one
runner, with evidence, in two layers -- like the scraper and the parser:

1. Code (`build`): every individual result is grouped by (school, gender,
   printed name). Inside one school and gender, candidate pairs are found by
   how their names relate (case/order/punctuation, joined surnames, a typo,
   truncation to a column width, a dropped leading letter, nicknames,
   initials, one-token names) and checked against the results themselves:

     * two spellings in the same race are two people (hard);
     * graduation years that clearly disagree are two people (hard);
     * the misspelt token is rare, the events overlap, the marks agree,
       the seasons are adjacent (soft).

   Clean, unambiguous pairs merge automatically. Everything else -- sibling
   risk, nicknames, initials, one-token names, conflicting evidence -- goes
   to the review queue. Long careers on one team are NOT evidence of two
   people: a middle school and high school can share a team.

2. Review (an agent; docs/agents/athlete-review.md): `review-export` writes
   the queue in batches with both spellings' results side by side; a
   reviewer (a Sonnet subagent, or James) decides same / different; and
   `review-import` records the decisions in backend/data/athlete_decisions.json.
   Decisions are permanent and override the code layer.

Relay teams are not athletes but are kept as their own entities: one relay
team is one school, gender, event and SET of legs, so the same four runners
in another order are the same team.

Ids: a runner's catalog id is the store id of their main spelling (the one
with the most results), so most runners -- never split -- keep the id they
have now. The store itself is not rewritten (its row ids derive from the
store athlete id and drive the double-ingest guard); the catalog is a map
from store ids to runners that PR flags, the athlete registry, the site and
the XC simulator all resolve through.

    python3 -m backend.athlete_catalog build          # code layer -> catalog + queue
    python3 -m backend.athlete_catalog stats
    python3 -m backend.athlete_catalog review-export --batches 5 --size 20
    python3 -m backend.athlete_catalog review-import <decisions.json> ...
    python3 -m backend.athlete_catalog apply          # PR flags + registry
"""

import argparse
import collections
import gzip
import itertools
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import json_store as js  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'backend', 'data')
CATALOG_PATH = os.path.join(DATA, 'athlete_catalog.json.gz')
DECISIONS_PATH = os.path.join(DATA, 'athlete_decisions.json')
QUEUE_PATH = os.path.join(DATA, 'athlete_review_queue.json.gz')
BUILDER_VERSION = 1

GRADE_WORDS = {'FR': 9, 'FY': 9, 'SO': 10, 'JR': 11, 'SR': 12}
GRADE_TOKENS = {'fr', 'so', 'jr', 'sr', 'ms'}
SUFFIX_TOKENS = {'ii', 'iii', 'iv'}
# a runner's results can span middle school and high school on one team;
# beyond this many academic years a span is worth a reviewer's look
LONG_SPAN = 7

# English diminutives seen in Maine results (pairs are review, never auto)
NICK = [
    ('matthew', 'matt'), ('michael', 'mike'), ('christopher', 'chris'),
    ('nicholas', 'nick'), ('alexander', 'alex'), ('alexandra', 'alex'),
    ('benjamin', 'ben'), ('samuel', 'sam'), ('samantha', 'sam'),
    ('william', 'will'), ('william', 'bill'), ('william', 'liam'),
    ('robert', 'rob'), ('robert', 'bob'), ('robert', 'bobby'),
    ('richard', 'rick'), ('richard', 'ricky'), ('richard', 'rich'),
    ('james', 'jim'), ('james', 'jimmy'), ('joseph', 'joe'), ('joseph', 'joey'),
    ('daniel', 'dan'), ('daniel', 'danny'), ('jonathan', 'jon'),
    ('jonathan', 'john'), ('john', 'jack'), ('thomas', 'tom'),
    ('thomas', 'tommy'), ('anthony', 'tony'), ('andrew', 'andy'),
    ('andrew', 'drew'), ('zachary', 'zach'), ('zachary', 'zack'),
    ('zachary', 'zac'), ('jacob', 'jake'), ('joshua', 'josh'),
    ('timothy', 'tim'), ('patrick', 'pat'), ('steven', 'steve'),
    ('stephen', 'steve'), ('edward', 'ed'), ('edward', 'eddie'),
    ('elizabeth', 'liz'), ('elizabeth', 'beth'), ('elizabeth', 'lizzie'),
    ('elizabeth', 'eliza'), ('elizabeth', 'libby'), ('katherine', 'kate'),
    ('katherine', 'katie'), ('kathryn', 'kate'), ('kathryn', 'katie'),
    ('catherine', 'cate'), ('catherine', 'katie'), ('margaret', 'maggie'),
    ('margaret', 'meg'), ('rebecca', 'becca'), ('rebecca', 'becky'),
    ('jennifer', 'jen'), ('jennifer', 'jenny'), ('abigail', 'abby'),
    ('abigail', 'abbie'), ('madeline', 'maddie'), ('madeleine', 'maddie'),
    ('madison', 'maddie'), ('isabella', 'bella'), ('isabelle', 'bella'),
    ('isabel', 'izzy'), ('isabella', 'izzy'), ('olivia', 'liv'),
    ('victoria', 'tori'), ('gabriella', 'gabby'), ('gabrielle', 'gabby'),
    ('caroline', 'carrie'), ('emily', 'em'), ('emma', 'em'),
    ('allison', 'ally'), ('alexis', 'lexi'), ('nathaniel', 'nate'),
    ('nathan', 'nate'), ('gregory', 'greg'), ('jeffrey', 'jeff'),
    ('kenneth', 'ken'), ('ronald', 'ron'), ('donald', 'don'),
    ('charles', 'charlie'), ('charlotte', 'charlie'), ('frederick', 'fred'),
    ('theodore', 'theo'), ('theodore', 'ted'), ('benjamin', 'benji'),
    ('maxwell', 'max'), ('maximilian', 'max'), ('cameron', 'cam'),
    ('jackson', 'jack'), ('peter', 'pete'), ('douglas', 'doug'),
    ('susanna', 'susie'), ('susan', 'sue'), ('christina', 'tina'),
    ('christine', 'chris'), ('kristen', 'kris'), ('jessica', 'jess'),
    ('jessica', 'jessie'), ('stephanie', 'steph'), ('natalie', 'nat'),
    ('josephine', 'josie'), ('evelyn', 'evie'), ('eleanor', 'ellie'),
    ('eleanor', 'nora'), ('gabriel', 'gabe'), ('mitchell', 'mitch'),
    ('spencer', 'spence'), ('sebastian', 'seb'), ('vincent', 'vinny'),
    ('lawrence', 'larry'), ('raymond', 'ray'), ('henry', 'hank'),
]
NICKSET = {frozenset(p) for p in NICK}


# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------

def osa(a, b):
    """Optimal string alignment distance (Levenshtein + adjacent swap)."""
    la, lb = len(a), len(b)
    if abs(la - lb) > 3:
        return 9
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            c = a[i - 1] != b[j - 1]
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]


def soundex(s):
    codes = {**dict.fromkeys('bfpv', '1'), **dict.fromkeys('cgjkqsxz', '2'),
             **dict.fromkeys('dt', '3'), 'l': '4', **dict.fromkeys('mn', '5'), 'r': '6'}
    s = re.sub(r'[^a-z]', '', s.lower())
    if not s:
        return ''
    out, last = s[0].upper(), codes.get(s[0], '')
    for ch in s[1:]:
        c = codes.get(ch, '')
        if c and c != last:
            out += c
        if ch not in 'hw':
            last = c
    return (out + '000')[:4]


def clean_name(raw):
    """Printed name -> tokens: column bleed ('Drake Smith    LE'), punctuation,
    grade tags and generational suffixes dropped."""
    s = re.sub(r'&#39;', "'", raw or '')
    s = re.sub(r'\s{2,}[A-Z]{1,4}(\s+[a-z]{1,4})?\s*$', '', s).strip()
    s = s.lower().replace("'", '').replace('’', '').replace('`', '').replace('.', ' ')
    s = re.sub(r'[-_/]', ' ', s)
    toks = re.findall(r'[a-z]+', s)
    while len(toks) > 2 and toks[-1] in GRADE_TOKENS | SUFFIX_TOKENS:
        toks.pop()
    return toks


def grade_num(g):
    s = str(g or '').strip().upper()
    if not s:
        return None
    if s in GRADE_WORDS:
        return GRADE_WORDS[s]
    m = re.fullmatch(r'0?(\d{1,2})', s)
    if m:
        n = int(m.group(1))
        return n if 5 <= n <= 12 else None
    return None


def academic_year(year, season):
    """Academic year named by its spring: fall 2025 XC belongs to 2026."""
    y = int(year)
    return y + 1 if season == 'XC' else y


def gender_of(event):
    m = re.match(r'(Boys|Girls|Men|Women|Mixed)', event or '')
    g = m.group(1) if m else '?'
    return {'Men': 'Boys', 'Women': 'Girls'}.get(g, g)


def family(event, season):
    e = (event or '').lower()
    if season == 'XC' or 'cross country' in e:
        return 'xc'
    for k, f in (('hurdle', 'hurdles'), ('steeple', 'distance'), ('jump', 'jumps'),
                 ('vault', 'jumps'), ('put', 'throws'), ('throw', 'throws'),
                 ('discus', 'throws'), ('javelin', 'throws'), ('hammer', 'throws'),
                 ('pentathlon', 'multi'), ('heptathlon', 'multi'),
                 ('decathlon', 'multi'), ('walk', 'walk')):
        if k in e:
            return f
    if 'mile' in e:
        return 'distance'
    m = re.search(r'(\d+)\s*(meter|m\b|yard)', e)
    if m:
        d = int(m.group(1))
        return 'sprint' if d <= 400 else ('mid' if d <= 1000 else 'distance')
    return 'other'


def is_relay(name, event):
    return ',' in (name or '') or 'relay' in (event or '').lower()


def is_team_label(name, team):
    """'Brewer B', 'MDI  A Relay', 'a runner1' are labels, not athletes."""
    n = re.sub(r'\s+', ' ', (name or '').strip())
    if not n or re.search(r'relay|runner\s*\d|^team\b|unknown|^tbd', n, re.I):
        return True
    m = re.match(r'^(.*\S)\s+([A-Fa-f]{1,2})$', n)
    if m:
        pre = m.group(1).lower().replace('.', '').strip()
        hay = (team or '').lower().replace('.', '')
        if pre and (pre in hay or pre.split()[0] in hay):
            return True
    return False


BLEED = re.compile(r'\s{2,}[A-Z]{1,4}(\s+[a-z]{1,4})?\s*$')


def tidy(name):
    """A printed name without column bleed ('Drake Smith    LE') or doubled spaces."""
    return re.sub(r'\s+', ' ', BLEED.sub('', name or '')).strip()


def display_name(names_counts, first_freq=None):
    """Canonical spelling for a cluster: a clean First Last in proper case,
    then the spelling with the most results. Word order follows whichever
    word is more often a first name across the store, so a runner printed
    "Pelletier Caleb" in most files still reads "Caleb Pelletier"."""
    first_freq = first_freq or {}
    tidy_counts = collections.Counter()
    for name, n in names_counts.items():
        tidy_counts[tidy(name)] += n

    def score(item):
        name, n = item
        toks = name.split()
        lo = [t.lower() for t in toks]
        first_first = len(lo) < 2 or first_freq.get(lo[0], 0) >= first_freq.get(lo[-1], 0)
        return (len(toks) >= 2,
                first_first,
                all(t[:1].isupper() for t in toks),          # every word capitalized
                not name.isupper() and not name.islower(),   # mixed case
                n, len(name))
    return max(tidy_counts.items(), key=score)[0]


# ---------------------------------------------------------------------------
# Loading the store
# ---------------------------------------------------------------------------

def _unit_for(folder, team, cache={}):
    """School unit (catalog id) a store team folder belongs to, or a
    'store:' placeholder for folders the school catalog cannot place."""
    if folder not in cache:
        try:
            from backend import school_catalog as sc
            sid = sc.id_for_store_name(team) or sc.id_for_store_name(folder.replace('_', ' '))
        except Exception:  # noqa: BLE001 - catalog optional
            sid = None
        cache[folder] = sid or f'store:{team}'
    return cache[folder]


def load_rows():
    """Every row of the store as a compact tuple:
    (folder, team, unit, year, season, ay, name, store_id, event, mark, grade, meet, date)."""
    out = []
    for folder in sorted(os.listdir(js.TEAMS_DIR)):
        d = os.path.join(js.TEAMS_DIR, folder)
        if not os.path.isdir(d):
            continue
        team = js.canonical_team_name(folder)
        unit = _unit_for(folder, team)
        for key, fn in js._chunk_files(d):
            year, _, season = key.partition('_')
            if not year.isdigit():
                continue
            ay = academic_year(year, season)
            for p in js.enrich_rows(team, key, js._load_json(os.path.join(d, fn), [])):
                out.append((folder, team, unit, int(year), season, ay,
                            p.get('athlete_name', '') or '', p.get('athlete_id', ''),
                            p.get('event', ''), p.get('mark', ''), grade_num(p.get('grade')),
                            p.get('meet_name', '') or '', (p.get('date') or '')[:10]))
    return out


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

def entity_key(unit, gender, name):
    return f'{unit}|{gender}|{name}'


def relay_key(unit, gender, name):
    """One relay team is one school, gender and set of legs, in any order and
    any event: the store id of a relay (its printed legs + school) does not
    name the event, so the 4x100 and 4x200 of the same four are one team."""
    legs = sorted(' '.join(clean_name(x)) for x in name.split(',') if clean_name(x))
    return f'relay|{unit}|{gender}|' + ';'.join(legs)


def build_entities(rows):
    ents, relays = {}, {}
    for (folder, team, unit, year, season, ay, name, aid, event, mark, g, meet, d) in rows:
        gender = gender_of(event)
        if is_relay(name, event):
            if ',' not in name:
                continue
            k = relay_key(unit, gender, name)
            r = relays.setdefault(k, dict(unit=unit, gender=gender, events=collections.Counter(),
                                          members=collections.Counter(), names=collections.Counter(),
                                          teams=collections.Counter(), seasons=set()))
            r['events'][event] += 1
            r['members'][aid] += 1
            r['names'][name] += 1
            r['teams'][team] += 1
            r['seasons'].add(season)
            continue
        if is_team_label(name, team):
            continue
        k = entity_key(unit, gender, name)
        e = ents.get(k)
        if e is None:
            e = ents[k] = dict(key=k, unit=unit, g=gender, name=name, toks=clean_name(name),
                               num=tuple(re.findall(r'\d+', name)), n=0, ays=set(), years=set(),
                               seasons=collections.Counter(), grads=collections.Counter(),
                               races=set(), meets=set(), fams=set(), best={},
                               members=collections.Counter(), teams=collections.Counter())
        e['n'] += 1
        e['ays'].add(ay)
        e['years'].add(year)
        e['seasons'][season] += 1
        if g is not None:
            e['grads'][ay + 12 - g] += 1
        e['races'].add(f'{meet}|{year}|{season}|{event}')
        e['meets'].add(f'{meet}|{year}|{season}')
        e['fams'].add(family(event, season))
        e['members'][aid] += 1
        e['teams'][team] += 1
        try:
            v, _ = js.parse_mark_value(mark, event)
        except Exception:  # noqa: BLE001
            v = None
        if v:
            k2 = (event, ay)
            cur = e['best'].get(k2)
            if cur is None or (v > cur if js.is_distance_event(event) else v < cur):
                e['best'][k2] = v
    # a store id is one relay team (a race read as the wrong gender files
    # the same printed relay under both)
    owner = {}
    for k in list(relays):
        r = relays[k]
        into = next((owner[sid] for sid in r['members'] if sid in owner), None)
        if into is None:
            for sid in r['members']:
                owner[sid] = k
            continue
        t = relays.pop(k)
        for f in ('events', 'members', 'names', 'teams'):
            relays[into][f].update(t[f])
        relays[into]['seasons'] |= t['seasons']
        for sid in t['members']:
            owner[sid] = into
    for e in ents.values():
        e['ays'] = sorted(e['ays'])
        e['years'] = sorted(e['years'])
    return ents, relays


# ---------------------------------------------------------------------------
# Candidate pairs and evidence
# ---------------------------------------------------------------------------

def name_relation(a, b):
    """How two names relate, or None. Returns (relation, detail)."""
    ta, tb = a['toks'], b['toks']
    if not ta or not tb:
        return None
    if sorted(ta) == sorted(tb):
        return ('trivial', 'case/punctuation/order/spacing')
    if ''.join(sorted(ta)) == ''.join(sorted(tb)) or ''.join(ta) == ''.join(tb):
        return ('concat', 'space or hyphen joined')
    if len(ta) == len(tb) and len(ta) >= 2 and ta[1:] == tb[1:] and ta[0] != tb[0]:
        s1, l1 = sorted((ta[0], tb[0]), key=len)
        if len(s1) >= 2 and len(l1) - len(s1) <= 2 and l1.endswith(s1):
            return ('leaddrop', f'{l1}->{s1}')
    ja, jb = ' '.join(ta), ' '.join(tb)
    short, long_ = (ja, jb) if len(ja) <= len(jb) else (jb, ja)
    if len(short) >= 12 and long_.startswith(short) and len(ta) >= 2 and len(tb) >= 2:
        return ('truncated', f'{len(short)}-character prefix')
    if len(ta) == 1 or len(tb) == 1:
        one, other = (ta, tb) if len(ta) == 1 else (tb, ta)
        if len(other) >= 2 and one[0] in other:
            return ('single', 'one-token name')
        return None
    sa, sb = set(ta), set(tb)
    if (sa < sb or sb < sa) and len(sa & sb) >= 2:
        return ('subset', 'extra name token')
    best = None
    for (fa, la_), (fb, lb) in (((ta[0], ta[-1]), (tb[0], tb[-1])),
                                ((ta[0], ta[-1]), (tb[-1], tb[0]))):
        for rel in _pair_rel(fa, la_, fb, lb):
            if best is None or rel[2] < best[2]:
                best = rel
    return (best[0], best[1]) if best else None


def _pair_rel(fa, la_, fb, lb):
    out = []
    lim = lambda s: 1 if len(s) <= 5 else 2  # noqa: E731
    if fa == fb and la_ != lb:
        d = osa(la_, lb)
        if d <= lim(min(la_, lb, key=len)):
            out.append(('typo_last', f'{la_}~{lb} d={d}', d))
    if la_ == lb and fa != fb:
        if frozenset((fa, fb)) in NICKSET:
            out.append(('nickname', f'{fa}/{fb}', 1))
        elif len(fa) == 1 or len(fb) == 1:
            if fa[0] == fb[0]:
                out.append(('initial', f'{fa}/{fb}', 1))
        elif (fa.startswith(fb) or fb.startswith(fa)) and min(len(fa), len(fb)) >= 3:
            out.append(('prefix_first', f'{fa}/{fb}', 1))
        else:
            d = osa(fa, fb)
            if d <= lim(min(fa, fb, key=len)):
                out.append(('typo_first', f'{fa}~{fb} d={d}', d))
    if fa != fb and la_ != lb and len(fa) > 2 and len(fb) > 2:
        if osa(fa, fb) == 1 and osa(la_, lb) == 1:
            out.append(('typo_both', f'{fa}~{fb},{la_}~{lb}', 2))
    return out


def blocking_keys(e):
    keys = set()
    for t in e['toks']:
        keys.add(('sx', soundex(t)))
        if len(t) >= 3:
            keys.add(('p3', t[:3]))
        if len(t) >= 4:
            keys.add(('s3', t[-3:]))
    j = ' '.join(e['toks'])
    if len(j) >= 6:
        keys.add(('d1', j[1:4]))
        keys.add(('d1', j[:3]))
        keys.add(('d2', j[2:5]))
    return keys


def _mark_gap(a, b):
    gaps = []
    for (ev, ay), va in a['best'].items():
        for dy in (-1, 0, 1):
            vb = b['best'].get((ev, ay + dy))
            if vb:
                gaps.append(abs(va - vb) / min(va, vb))
    return min(gaps) if gaps else None


def _grad_check(a, b):
    ga, gb = a['grads'], b['grads']
    if not ga or not gb:
        return 'unknown', None, None
    ma, mb = ga.most_common(1)[0][0], gb.most_common(1)[0][0]
    if ma == mb:
        return 'agree', ma, mb
    sa, sb = ga[ma] / sum(ga.values()), gb[mb] / sum(gb.values())
    if sum(ga.values()) >= 2 and sum(gb.values()) >= 2 and sa >= .75 and sb >= .75:
        return 'conflict', ma, mb
    return ('mixed' if set(ga) & set(gb) else 'conflict_weak'), ma, mb


def evaluate(a, b, rel, tf):
    """Evidence for one candidate pair and the code layer's label:
    'auto' (merge), 'review' (queue) or 'reject' (two people)."""
    major, minor = (a, b) if a['n'] >= b['n'] else (b, a)
    co_race = len(a['races'] & b['races'])
    co_meet = len(a['meets'] & b['meets'])
    ays = sorted(set(a['ays']) | set(b['ays']))
    span = ays[-1] - ays[0] + 1
    gap = min(abs(x - y) for x in a['ays'] for y in b['ays'])
    gstat, gma, gmb = _grad_check(a, b)
    fam_j = len(a['fams'] & b['fams']) / max(1, len(a['fams'] | b['fams']))
    mgap = _mark_gap(a, b)
    diff_tokens = set(minor['toks']) - set(major['toks'])
    rare = all(tf.get(t, 0) <= 2 for t in diff_tokens) if diff_tokens else True
    sib = False
    if rel in ('typo_first', 'prefix_first', 'initial', 'nickname') and a['toks'][-1] == b['toks'][-1]:
        fa, fb = a['toks'][0], b['toks'][0]
        sib = tf.get(fa, 0) >= 3 and tf.get(fb, 0) >= 3 and rel != 'nickname'
    neg, soft = [], []
    if co_race:
        neg.append(f'same race x{co_race}')
    if gstat == 'conflict':
        neg.append(f'graduation year {gma} vs {gmb}')
    if a['num'] and b['num'] and a['num'] != b['num']:
        neg.append(f"different number tags {a['num']} vs {b['num']}")
    if co_meet and not co_race and rel not in ('trivial', 'concat'):
        soft.append(f'same meet x{co_meet}')
    if gstat == 'conflict_weak':
        soft.append(f'graduation year (weak) {gma} vs {gmb}')
    if span > LONG_SPAN:
        soft.append(f'combined span {span} academic years')
    if gap > 1:
        soft.append(f'gap {gap} years')
    if fam_j == 0:
        soft.append('no shared event family')
    tol = .25 if 'xc' in (a['fams'] & b['fams']) else .15
    if mgap is not None and mgap > tol:
        soft.append(f'marks differ {mgap:.0%}')
    if sib:
        soft.append('sibling risk (both first names common)')
    if neg:
        label = 'reject'
    elif rel in ('trivial', 'concat'):
        label = 'auto' if all(s == 'no shared event family' for s in soft) else 'review'
    elif rel in ('typo_last', 'typo_first', 'typo_both', 'truncated', 'leaddrop'):
        label = 'auto' if (not soft and rare and (rel != 'typo_both' or minor['n'] <= 3)) else 'review'
    else:
        label = 'review'
    return dict(a=major['key'], b=minor['key'], relation=rel, label=label,
                negatives=neg, soft=soft, co_race=co_race, co_meet=co_meet, span=span, gap=gap,
                grad=gstat, mark_gap=None if mgap is None else round(mgap, 3),
                minor_tokens_rare=rare, sibling_risk=sib, n_a=major['n'], n_b=minor['n'],
                last_year=max(a['years'][-1], b['years'][-1]))


def candidate_pairs(ents):
    tf = collections.Counter()
    for e in ents.values():
        for t in set(e['toks']):
            tf[t] += 1
    by_unit = collections.defaultdict(list)
    for e in ents.values():
        if e['g'] in ('Boys', 'Girls'):
            by_unit[(e['unit'], e['g'])].append(e)
    pairs = []
    for lst in by_unit.values():
        if len(lst) < 2:
            continue
        idx = collections.defaultdict(list)
        for i, e in enumerate(lst):
            for k in blocking_keys(e):
                idx[k].append(i)
        seen = set()
        for bucket in idx.values():
            for i, j in itertools.combinations(bucket, 2):
                if (i, j) in seen:
                    continue
                seen.add((i, j))
                a, b = lst[i], lst[j]
                if min(abs(x - y) for x in a['ays'] for y in b['ays']) > 3:
                    continue
                r = name_relation(a, b)
                if not r:
                    continue
                ev = evaluate(a, b, r[0], tf)
                ev['detail'] = r[1]
                pairs.append(ev)
    return pairs


# ---------------------------------------------------------------------------
# Decisions and clustering
# ---------------------------------------------------------------------------

def pair_key(a, b):
    return '||'.join(sorted((a, b)))


def load_decisions():
    try:
        with open(DECISIONS_PATH, encoding='utf-8') as f:
            return json.load(f).get('pairs', {})
    except (OSError, ValueError):
        return {}


def cluster(ents, pairs, decisions):
    """Union-find over auto pairs and reviewed 'same' decisions. A union is
    refused when it would put two entities that ran the same race, or that a
    reviewer decided are different, into one runner."""
    parent = {k: k for k in ents}
    members = {k: {k} for k in ents}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    different = collections.defaultdict(set)
    for pk, d in decisions.items():
        a, b = pk.split('||')
        if d.get('decision') == 'different':
            different[a].add(b)
            different[b].add(a)

    refused = []

    def union(a, b, why):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        ma, mb = members[ra], members[rb]
        for x in ma:
            if different[x] & mb:
                refused.append((a, b, why, 'reviewed as different'))
                return
        ra_races = set().union(*(ents[x]['races'] for x in ma))
        if any(ra_races & ents[y]['races'] for y in mb):
            refused.append((a, b, why, 'same race'))
            return
        if len(ma) < len(mb):
            ra, rb = rb, ra
        parent[rb] = ra
        members[ra] |= members.pop(rb)

    for pk, d in decisions.items():
        a, b = pk.split('||')
        if d.get('decision') == 'same' and a in ents and b in ents:
            union(a, b, 'reviewed')
    for p in pairs:
        if p['label'] == 'auto' and pair_key(p['a'], p['b']) not in decisions:
            union(p['a'], p['b'], 'auto')
    # One store id is one runner: the site resolves a profile by it, so a
    # name filed under both genders (a race the parser read as the wrong
    # sex, a Mixed list) must not become two runners with one id. The
    # conflict is reported by build() for QAQC.
    by_sid = collections.defaultdict(list)
    for k, e in ents.items():
        for sid in e['members']:
            by_sid[sid].append(k)
    for ks in by_sid.values():
        for k in ks[1:]:
            union(ks[0], k, 'store id')
    groups = collections.defaultdict(list)
    for k in ents:
        groups[find(k)].append(k)
    return list(groups.values()), refused


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(rows=None, quiet=False):
    say = (lambda *a: None) if quiet else (lambda *a: print(*a, file=sys.stderr))
    rows = rows if rows is not None else load_rows()
    say(f'{len(rows):,} rows')
    ents, relays = build_entities(rows)
    say(f'{len(ents):,} name entities, {len(relays):,} relay teams')
    pairs = candidate_pairs(ents)
    labels = collections.Counter(p['label'] for p in pairs)
    say(f'{len(pairs):,} candidate pairs: {dict(labels)}')
    decisions = load_decisions()
    groups, refused = cluster(ents, pairs, decisions)
    first_freq = collections.Counter(e['toks'][0] for e in ents.values() if len(e['toks']) >= 2)

    athletes = []
    member_of = {}
    gender_conflicts = []
    for keys in groups:
        es = [ents[k] for k in keys]
        store_ids = collections.Counter()
        names = collections.Counter()
        teams = collections.Counter()
        grads = collections.Counter()
        seasons = collections.Counter()
        for e in es:
            store_ids.update(e['members'])
            names[e['name']] += e['n']
            teams.update(e['teams'])
            grads.update(e['grads'])
            seasons.update(e['seasons'])
        cid = store_ids.most_common(1)[0][0]
        by_g = collections.Counter()
        for e in es:
            by_g[e['g']] += e['n']
        gender = max(by_g, key=lambda g: (g in ('Boys', 'Girls'), by_g[g]))
        if len([g for g in by_g if g in ('Boys', 'Girls')]) > 1:
            gender_conflicts.append(dict(
                id=cid, gender=gender, rows=dict(by_g),
                other=sorted(r for e in es if e['g'] != gender for r in e['races'])[:20]))
        a = dict(id=cid, name=display_name(names, first_freq), gender=gender, unit=es[0]['unit'],
                 class_of=grads.most_common(1)[0][0] if grads else None,
                 primary_team=teams.most_common(1)[0][0], teams=sorted(teams),
                 sports=sorted(seasons), rows=sum(e['n'] for e in es),
                 years=[min(min(e['years']) for e in es), max(max(e['years']) for e in es)])
        if len(store_ids) > 1:
            a['members'] = sorted(store_ids)
        if len(names) > 1:
            aka = sorted({tidy(n) for n in names} - {a['name']})
            if aka:
                a['aka'] = aka
            a['entities'] = sorted(keys)
        athletes.append(a)
        for sid in store_ids:
            member_of[sid] = cid
    relay_out = []
    for k, r in relays.items():
        cid = r['members'].most_common(1)[0][0]
        relay_out.append(dict(id=f'relay--{cid}', key=k, name=tidy(r['names'].most_common(1)[0][0]),
                              gender=r['gender'], event=r['events'].most_common(1)[0][0],
                              events=sorted(r['events']), kind='relay',
                              primary_team=r['teams'].most_common(1)[0][0],
                              sports=sorted(r['seasons']), members=sorted(r['members'])))
        for sid in r['members']:
            member_of[sid] = f'relay--{cid}'

    queue = [p for p in pairs if p['label'] == 'review'
             and decisions.get(pair_key(p['a'], p['b']), {}).get('decision') in (None, 'unsure')]
    # most useful first: recent runners, then the most results at stake
    queue.sort(key=lambda p: (-p['last_year'], -(p['n_a'] + p['n_b'])))
    stats = dict(
        built=date.today().isoformat(), builder_version=BUILDER_VERSION, rows=len(rows),
        entities=len(ents), athletes=len(athletes),
        merged_athletes=sum(1 for a in athletes if 'entities' in a),
        entities_merged=sum(len(a.get('entities', [])) for a in athletes),
        relay_teams=len(relay_out), pairs=dict(labels), decisions=len(decisions),
        review_queue=sum(1 for p in queue if pair_key(p['a'], p['b']) not in decisions),
        unsure=sum(1 for p in queue if pair_key(p['a'], p['b']) in decisions), refused=len(refused),
        gender_conflicts=len(gender_conflicts))
    say(json.dumps(stats))
    catalog = dict(stats=stats, athletes=athletes, relays=relay_out, member_of=member_of,
                   refused=[dict(a=a, b=b, why=w, reason=r) for a, b, w, r in refused],
                   gender_conflicts=sorted(gender_conflicts, key=lambda c: -sum(c['rows'].values())))
    _write_gz(CATALOG_PATH, catalog)
    _write_gz(QUEUE_PATH, dict(built=stats['built'], pairs=queue))
    return catalog, ents, pairs


def _write_gz(path, obj):
    tmp = path + '.tmp'
    with gzip.open(tmp, 'wt', encoding='utf-8', compresslevel=6) as f:
        json.dump(obj, f, separators=(',', ':'))
    os.replace(tmp, path)


def _read_gz(path, default=None):
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def load_catalog():
    return _read_gz(CATALOG_PATH, {})


def resolver():
    """store athlete id -> catalog id (identity for ids the catalog doesn't know)."""
    m = load_catalog().get('member_of', {})
    return lambda aid: m.get(aid, aid)


# ---------------------------------------------------------------------------
# Review layer: export a batch for a reviewer, import decisions
# ---------------------------------------------------------------------------

def _entity_rows(rows, keys):
    want = {}
    for k in keys:
        unit, g, name = k.split('|', 2)
        want[(unit, g, name)] = k
    out = collections.defaultdict(list)
    for (folder, team, unit, year, season, ay, name, aid, event, mark, g, meet, d) in rows:
        k = want.get((unit, gender_of(event), name))
        if k and not is_relay(name, event):
            out[k].append(dict(season=f'{year} {season}', date=d, meet=meet, event=event,
                               mark=mark, grade=g, team=team))
    for k in out:
        out[k].sort(key=lambda r: (r['season'], r['date'], r['meet']))
    return out


def _nearest(rows, other, cap=40):
    """Up to `cap` of a side's results, the ones closest in time to the
    other side's (that is where a reviewer compares them), in date order."""
    if len(rows) <= cap:
        return rows
    oy = {int(r['season'][:4]) for r in other} or {0}
    near = sorted(rows, key=lambda r: (min(abs(int(r['season'][:4]) - y) for y in oy), r['date']))[:cap]
    return sorted(near, key=lambda r: (r['season'], r['date'], r['meet']))


def review_export(batches, size, outdir, rows=None, unsure=False):
    """Write review batches. Normally the undecided queue; with unsure=True,
    the pairs an agent marked unsure, for a person to settle."""
    queue = (_read_gz(QUEUE_PATH, {}) or {}).get('pairs', [])
    decisions = load_decisions()
    if unsure:
        queue = [p for p in queue if decisions.get(pair_key(p['a'], p['b']), {}).get('decision') == 'unsure']
    else:
        queue = [p for p in queue if pair_key(p['a'], p['b']) not in decisions]
    take = queue[:batches * size]
    if not take:
        print('review queue is empty')
        return []
    rows = rows if rows is not None else load_rows()
    er = _entity_rows(rows, {p['a'] for p in take} | {p['b'] for p in take})
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for i in range(0, len(take), size):
        batch = []
        for p in take[i:i + size]:
            batch.append(dict(pair=pair_key(p['a'], p['b']), relation=p['relation'], detail=p.get('detail'),
                              evidence=dict(soft=p['soft'], co_meet=p['co_meet'], grad=p['grad'],
                                            mark_gap=p['mark_gap'], sibling_risk=p['sibling_risk']),
                              a=dict(entity=p['a'], results=_nearest(er.get(p['a'], []), er.get(p['b'], []))),
                              b=dict(entity=p['b'], results=_nearest(er.get(p['b'], []), er.get(p['a'], [])))))
        path = os.path.join(outdir, f'batch_{i // size + 1:03d}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(dict(instructions='docs/agents/athlete-review.md', pairs=batch), f, indent=1)
        paths.append(path)
    print(f'{len(take)} pairs in {len(paths)} batches -> {outdir}')
    return paths


def review_import(paths, reviewer):
    """Record reviewer decisions: each file holds
    {"decisions": [{"pair": "...", "decision": "same|different|unsure", "reason": "..."}]}."""
    try:
        with open(DECISIONS_PATH, encoding='utf-8') as f:
            store = json.load(f)
    except (OSError, ValueError):
        store = {'_doc': 'Athlete identity decisions (review layer). pair "A||B" -> same/different, '
                         'who decided, why. Permanent: they override the code layer. '
                         'See docs/agents/athlete-review.md.', 'pairs': {}}
    n = collections.Counter()
    for path in paths:
        with open(path, encoding='utf-8') as f:
            got = json.load(f)
        for d in got.get('decisions', []):
            dec = d.get('decision')
            if dec not in ('same', 'different', 'unsure'):
                n['invalid'] += 1
                continue
            a, b = d['pair'].split('||')
            store['pairs'][pair_key(a, b)] = dict(decision=dec, reason=d.get('reason', ''),
                                                  by=reviewer, date=date.today().isoformat())
            n[dec] += 1
    with open(DECISIONS_PATH, 'w', encoding='utf-8') as f:
        json.dump(store, f, indent=1, sort_keys=True)
    print(dict(n))
    return n


# ---------------------------------------------------------------------------
# Apply: PR flags over whole careers, and the athlete registry
# ---------------------------------------------------------------------------

def apply(catalog=None, quiet=False):
    """Recompute PR / season-best flags with catalog ids (a runner's career
    can span spellings and team folders), rewrite only the chunks whose flags
    change, and rebuild the athlete registry from the catalog."""
    say = (lambda *a: None) if quiet else (lambda *a: print(*a, file=sys.stderr))
    catalog = catalog or load_catalog()
    member_of = catalog.get('member_of', {})
    # pass 1: every row's (catalog id, event, season) key and value, in date order
    refs = collections.defaultdict(list)     # key -> [(date, value, mark, event, chunk, i)]
    chunks = {}
    for folder in sorted(os.listdir(js.TEAMS_DIR)):
        d = os.path.join(js.TEAMS_DIR, folder)
        if not os.path.isdir(d):
            continue
        team = js.canonical_team_name(folder)
        for key, fn in js._chunk_files(d):
            path = os.path.join(d, fn)
            rows = js._load_json(path, [])
            chunks[path] = (team, key, rows)
            year, _, season = key.partition('_')
            for i, p in enumerate(rows):
                aid = p.get('athlete_id') or js.slugify_athlete(p.get('athlete_name', ''), team)
                cid = member_of.get(aid, aid)
                ev = p.get('event', '')
                val, _ = js.parse_mark_value(p.get('mark', ''), ev)
                refs[(cid, ev, season)].append(((p.get('date') or ''), val, p.get('mark', ''),
                                                year, path, i))
    # pass 2: flags per key, the same rules as json_store.recalculate_prs
    flags = {}
    for k, lst in refs.items():
        lst.sort(key=lambda r: r[0])
        best, sb = None, {}
        last_pr = None
        for (dt, val, mark, year, path, i) in lst:
            f = dict(was_pr=False, is_sb=False, is_pr=False)
            if val is not None:
                if best is None or js.is_better(mark, best, k[1]):
                    f['was_pr'] = True
                    best = mark
                    last_pr = (path, i)
                if year not in sb or js.is_better(mark, sb[year], k[1]):
                    f['is_sb'] = True
                    sb[year] = mark
            flags[(path, i)] = f
        if last_pr:
            flags[last_pr]['is_pr'] = True
    changed = 0
    for path, (team, key, rows) in chunks.items():
        dirty = False
        for i, p in enumerate(rows):
            f = flags.get((path, i))
            if f and any(bool(p.get(x)) != f[x] for x in f):
                p.update(f)
                dirty = True
        if dirty:
            js._atomic_write(path, rows)
            changed += 1
    say(f'PR flags: {changed} chunk files rewritten')
    _write_registry(catalog)
    return changed


def _write_registry(catalog):
    """athletes.json.gz for the site: one entry per runner (with the store ids
    it covers and its other spellings) plus relay teams, marked kind='relay'."""
    out = []
    seen = {}
    for a in sorted(catalog.get('athletes', []), key=lambda a: -a['rows']):
        if a['id'] in seen:
            # two runners on one store id that the catalog could not join
            # (they share a race: "HERMAN" and "Herman" on one list); the
            # site has one profile per id, so they share its entry
            e = seen[a['id']]
            e['sports'] = sorted(set(e['sports']) | set(a['sports']))
            continue
        e = seen[a['id']] = dict(id=a['id'], name=a['name'], primary_team=a['primary_team'],
                                 sports=a['sports'])
        if a.get('members'):
            e['members'] = a['members']
        if a.get('aka'):
            e['aka'] = a['aka']
        if len(a.get('teams', [])) > 1:
            e['teams'] = a['teams']
        out.append(e)
    for r in catalog.get('relays', []):
        out.append(dict(id=r['id'], name=r['name'], primary_team=r['primary_team'],
                        sports=r['sports'], kind='relay', members=r['members']))
    out.sort(key=lambda e: (e.get('kind') == 'relay', e['name']))
    js._atomic_write(js.ATHLETES_PATH, out)


# ---------------------------------------------------------------------------
# QAQC
# ---------------------------------------------------------------------------

def qaqc(catalog=None):
    """Identity checks for the QAQC report."""
    catalog = catalog or load_catalog()
    s = catalog.get('stats', {})
    return dict(athletes=s.get('athletes'), merged=s.get('merged_athletes'),
                review_queue=s.get('review_queue'), decisions=s.get('decisions'),
                refused_merges=s.get('refused'), gender_conflicts=s.get('gender_conflicts'))


def main():
    ap = argparse.ArgumentParser(description='Athlete identity catalog')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('build')
    sub.add_parser('stats')
    sub.add_parser('apply')
    ex = sub.add_parser('review-export')
    ex.add_argument('--batches', type=int, default=5)
    ex.add_argument('--size', type=int, default=20)
    ex.add_argument('--out', required=True)
    ex.add_argument('--unsure', action='store_true', help='export the pairs agents marked unsure, for a person')
    im = sub.add_parser('review-import')
    im.add_argument('paths', nargs='+')
    im.add_argument('--by', required=True, help='who decided, e.g. "sonnet-5.5 review" or "James Longo"')
    a = ap.parse_args()
    if a.cmd == 'build':
        build()
    elif a.cmd == 'stats':
        print(json.dumps(load_catalog().get('stats', {}), indent=1))
    elif a.cmd == 'apply':
        apply()
    elif a.cmd == 'review-export':
        review_export(a.batches, a.size, a.out, unsure=a.unsure)
    elif a.cmd == 'review-import':
        review_import(a.paths, a.by)


if __name__ == '__main__':
    main()
