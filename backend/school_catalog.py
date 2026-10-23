"""
school_catalog.py - resolve raw school strings from result files to catalog ids.

The catalog (backend/data/school_catalog.json, built by build_school_catalog.py
from the hand-curated school_catalog_seed.py plus evidence from every parsed
result file) has one entry per real institution. This module answers:

    resolve(raw_school, *, year, season, gender=None, meet_name=None, grade=None)
        -> catalog id or None

Resolution order
----------------
1. Per-file override: the builder resolved this exact string in this exact
   results file with athlete-continuity evidence (codes like 'WIN', mascots
   like 'Scots', single letters). Keyed by year/season/file stem.
2. Raw-string map: the builder's global answer for this exact raw string,
   provided it is context-free (it means the same school in every level).
3. Rules (for never-seen strings): clean the string (gender suffix 'Morse F',
   leading 'M ' on 'M NYA MS', ', ME' tails, season words, years), then
   exact name/alias -> name stem by level -> unique Hy-Tek truncation ->
   code -> mascot. Bare town names ('Falmouth') use the meet level: an MS
   meet means the middle school.

Ids: me-hs-*, me-ms-*, col-*, oos-<st>-*, club-*, coop-*, x-* (Unattached etc.)

Also:
    team_unit(id, year, season, gender)  -> co-op id the school competed in, else id
    store_team_id(store_team_name)       -> catalog id for an existing store team
    info(id)                             -> the catalog entry
"""

import json
import os
import re

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
CATALOG_PATH = os.path.join(DATA_DIR, 'school_catalog.json')
RAWMAP_PATH = os.path.join(DATA_DIR, 'school_raw_map.json')

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

TOKEN_MAP = {
    'mount': 'mt', 'mnt': 'mt', 'mtn': 'mountain', 'saint': 'st', 'ste': 'st', 'ft': 'fort',
    'acad': 'academy', 'acd': 'academy', 'jr': 'junior', 'sr': 'senior', 'comm': 'community',
    'hghs': 'hs', 'h': 'h', 'hi': 'high', 'hig': 'high', 'sch': 'school', 'schl': 'school',
    'schoo': 'school', 'scho': 'school', 'scool': 'school', 'schools': 'school', 'highschool': 'high school',
    'univ': 'university', 'u': 'university', 'coll': 'college', 'ctr': 'center', 'cntr': 'center',
    'chr': 'christian', 'chris': 'christian', 'st.': 'st', 'so': 'south', 'no': 'north',
    'elem': 'elementary', 'elementa': 'elementary', 'midd': 'middle', 'mid': 'middle', 'middl': 'middle',
    'middlle': 'middle', 'middlesch': 'middle school', 'inst': 'institute', 'ins': 'institute',
    'cent': 'central', 'reg': 'regional', 'regio': 'regional', 'regl': 'regional',
}
# words that never distinguish one school from another
GENERIC = {'high', 'school', 'hs', 'regional', 'area', 'community', 'district', 'memorial', 'comprehensive',
           'senior', 'secondary', 'the', 'of', 'academy', 'and', 'jr-sr', 'shs', 'ths', 'consolidated'}
MS_WORDS = {'ms', 'middle', 'jh', 'jhs', 'junior', 'elementary', 'intermediate', 'grammar', 'mid', 'k8', 'cs',
            'village', 'upper', 'lower'}
SEASON_WORDS = {'indoor', 'outdoor', 'out', 'xc', 'cc', 'cross', 'country', 'track', 'tf', 't&f', 't+f', 'field',
                'boys', 'girls', 'boy', 'girl', 'mens', 'womens', 'men', 'women', 'varsity', 'jv', 'team', 'relay',
                'and', '&', 'trac', 'tr', 'trk', 'spring', 'winter', 'fall', 'wt', 'it', 'ot', 'b&g', 'b/g', 't', 'f',
                'x-c', 'indoo', 'outdoo', 'cross-country', 'gi', 'gir', 'bo', 'boy', 'b', 'g', 'idt&f', 'xct', 'mix', 'mixed'}
US_STATES = {'ME', 'MA', 'NH', 'VT', 'CT', 'RI', 'NY', 'NS', 'NB', 'PEI', 'QC'}


def norm(s: str) -> str:
    """Lowercase, punctuation-free, token-mapped form used as a lookup key."""
    s = s.lower().replace('&', ' and ').replace("'", '').replace('’', '')
    s = re.sub(r'(?<=[a-z])\.(?=[a-z])', '. ', s)          # 'mt.desert' -> 'mt. desert'
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    toks = []
    for t in s.split():
        t = TOKEN_MAP.get(t, t)
        toks.extend(t.split())
    # 'h s' -> hs, 'm s' -> ms, 'j h' -> jh
    out = []
    for t in toks:
        if out and len(t) == 1 and len(out[-1]) == 1 and (out[-1] + t) in ('hs', 'ms', 'jh'):
            out[-1] = out[-1] + t
        else:
            out.append(t)
    return ' '.join(out)


def flat(s: str) -> str:
    """Lowercase + punctuation-to-space WITHOUT token mapping (for truncation prefixes)."""
    s = s.lower().replace("'", '').replace('’', '')
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return ' '.join(s.split())


def level_of(n: str):
    """Level implied by tokens of a normalised string, or None."""
    toks = set(n.split())
    if toks & {'ms', 'middle', 'jh', 'jhs', 'elementary', 'intermediate', 'grammar', 'k8'} or \
            'junior high' in n:
        return 'ms'
    if toks & {'college', 'university'} or re.search(r'\bstate$', n):
        return 'college'
    return None


def stem(n: str) -> str:
    toks = [t for t in n.split() if t not in GENERIC and t not in MS_WORDS]
    return ' '.join(toks)


_TIME_RE = re.compile(r'\d+:\d\d|\d+\.\d\d\b|\d+-\d\d(\.\d+)?\b|\d+\.\d+m\b')


# Strings that are never a school ('PACE' column header, 'Average:' footer, timer banners). Filled from
# the catalog ('not_schools') at load time, or from the seed by the builder.
NOT_SCHOOL_PATTERNS = []


def academic_year(year, season):
    """XC season-year Y is academic year Y; Indoor/Outdoor season-year Y is academic year Y-1."""
    y = int(year)
    return y if season == 'XC' else y - 1


def in_years(entry, ay):
    """Did this catalog entry exist (under this identity) in academic year `ay`?"""
    if ay is None:
        return True
    lo, hi = (entry.get('years') or [None, None])
    return (lo is None or ay >= lo) and (hi is None or ay <= hi)


def looks_like_debris(raw: str) -> bool:
    """Strings that are not a school column at all (leaked marks, names, scores, headers)."""
    if not raw:
        return True
    if any(re.search(p, raw) for p in NOT_SCHOOL_PATTERNS):
        return True
    if _TIME_RE.search(raw):
        return True
    if re.match(r'^[A-Z][A-Za-z\'\-]+,\s+[A-Za-z]', raw):     # 'Hall, Danny SO Lawrence'
        return True
    if re.fullmatch(r'[\d\s\-:.()|*]+', raw):
        return True
    return False


def salvage(raw: str):
    """Recover the school from a parse-debris string: 'Lincoln Academy 5:33.1' (pace column glued on),
    'Hall, Danny SO Lawrence' (name and class glued on), 'Lucy SR George Stevens Ac (45) 26:13.15 8:25.8'.
    Returns the cleaned string, or None when nothing school-like is left."""
    s = re.sub(r'\s+', ' ', raw or '').strip()
    s = re.sub(r'^\d+[\s.)\-]+', '', s)
    s = re.sub(r"^[A-Z][A-Za-z'\-]+,\s*[A-Z][A-Za-z'\-.]*\s+", '', s)
    s = re.sub(r'^[A-Z][a-z]+\s+(FR|SO|JR|SR)\s+', '', s)
    s = re.sub(r'^(FR|SO|JR|SR|\d{1,2})\s+', '', s)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'\s*(\(\d+\)|\d[\d:.]*[a-z]?|-|NWI|DNF|DNS|NT)\s*$', '', s).strip()
    if not s or s == (raw or '').strip() or len(s) < 2 or re.search(r'\d', s):
        return None
    return s


def variants(raw: str, gender=None):
    """Yield (candidate_string, note, gender_hint, state) from most to least literal."""
    s = re.sub(r'\s+', ' ', raw or '').strip().strip('"').strip()
    if not s:
        return
    seen = set()
    state = None

    def emit(v, note):
        v = v.strip(' -–—*,.:;/')
        if v and (v, note) not in seen and v not in {x for x, _ in seen}:
            seen.add((v, note))
            return [(v, note)]
        return []

    out = []
    out += emit(s, 'literal')
    t = s
    # glued words: 'JonesportBeals', 'Medomak ValleyHigh School', 'Gray New Gloucester HighSchoo'
    t2 = re.sub(r'(?<=[a-z])(?=(High|Middle|Hig|School|Academy|Acad|Christian)\b)', ' ', t)
    t2 = re.sub(r'(?<=[a-z]{3})(?=[A-Z][a-z]{2})', ' ', t2)
    if t2 != t:
        t = t2
        out += emit(t, 'deglue')
    # parenthetical tails that are not states: 'Loranger MS (Old Orchard Beach'
    m = re.search(r'\s*\((?!\s*(?:Mass|Me|Conn|N\.H|Vt|R\.I|MA|NH|VT|CT|RI|NY)\b)[^)]*\)?\s*$', t)
    if m and m.start() > 2:
        t = t[:m.start()]
        out += emit(t, 'paren-tail')
    # leading place / grade numbers and dashes: '6 Camden Rockp', '- Winthrop', '01-Unattache', 'M18 Lisb'
    t2 = re.sub(r'^[MF]\d{2}\s+', '', t)
    t2 = re.sub(r'^[\-–—*#\s]*(\d+[\s\-.]+)?', '', t2)
    if t2 != t:
        t = t2
        out += emit(t, 'lead-num')
    # leading class year: 'JR WTVL', 'SR MESS'
    t2 = re.sub(r'^(JR|SR|SO|FR)\s+', '', t)
    if t2 != t:
        t = t2
        out += emit(t, 'lead-class')
    # comma tails: 'Scarborough,ME, ME', 'Ams11,Auburn, ME', 'Cumberland, RI'
    if ',' in t:
        head, tail = t.split(',', 1)
        m = re.search(r'\b(' + '|'.join(US_STATES) + r')\b\s*,?\s*$', tail.strip())
        if m and m.group(1) != 'ME':
            state = m.group(1)
        t = head
        out += emit(t, 'comma-tail')
    # ' NS' / '-NS' / " 'NS'" after a school is 'non-scoring' (relay-meet files: 'Cony NS', 'Brunswick Mix-NS',
    # Mt. Blue Relays "Winslow 'NS'"), not Nova Scotia (Nova Scotia schools print ' - NS' with spaces, handled below)
    t2 = re.sub(r"(?:\s+'?|(?<=[a-z])-)NS'?$", '', t)
    if t2 != t and not re.search(r'\s-\s*NS$', t):
        t = t2
        out += emit(t, 'non-scoring')
    # dashed state in any case: 'Windsor-Ct', 'E. Greenwich -ri', 'Barrington Hs-Ri'
    m = re.search(r'\s*-\s*(ct|ri|nh|vt|ma|ny|me|ns|nb|pei)\.?\s*(\'[A-D]\')?\s*$', t, re.I)
    if m and m.start() > 2:
        st = m.group(1).upper()
        if st != 'ME':
            state = st
        t = t[:m.start()]
        out += emit(t, 'state-tail')
    # parenthetical / dashed state: 'Regis (Mass.)', 'Lincoln - RI', 'Colonel Gray-PEI', 'GreenfieldMA'
    m = re.search(r'[\s\-(]+\(?(' + '|'.join(sorted(US_STATES, key=len, reverse=True)) +
                  r'|Mass\.?|Me\.?|Conn\.?|N\.H\.|Vt\.?)\)?\.?\s*$', t)
    if m:
        st = m.group(1).upper().rstrip('.')
        st = {'MASS': 'MA', 'CONN': 'CT', 'N.H': 'NH'}.get(st, st)
        if st != 'ME':
            state = st
        t = t[:m.start()]
        out += emit(t, 'state-tail')
    m = re.search(r'(?<=[a-z])(MA|NH|VT|CT|RI|NY|ME)$', t)
    if m:
        if m.group(1) != 'ME':
            state = m.group(1)
        t = t[:m.start()]
        out += emit(t, 'state-glued')
    # gender suffix: 'Morse M', 'Edward F' (LaLiberte PDFs) - only when it agrees with the event
    m = re.search(r'\s([MFWBG])$', t)
    if m and gender:
        g = m.group(1)
        if (g in 'MB' and gender.lower().startswith('b')) or (g in 'FWG' and gender.lower().startswith('g')):
            t = t[:m.start()]
            out += emit(t, 'gender-suffix')
    # season / program words and years at the end: 'Mtb Track'12', 'Bru 06-07', 'Elhs Boys Out', "'A'"
    for _ in range(4):
        t2 = re.sub(r"\s*'?[A-D]'$", '', t)
        if t2 != t:   # the squad letter alone first: "Union 122 'A'" is Union 122 before it is a "Union" + year
            out += emit(t2, 'season-words')
        t2 = re.sub(r"[\s\-]*'?\d{2,4}(\s*-\s*\d{2,4})?$", '', t2)
        t2 = re.sub(r'(?<=[A-Za-z])\d$', '', t2)                # 'BRU7', 'WIN1'
        t2 = re.sub(r'(?i)(?<=[a-z])(boys|girls)$', '', t2)
        # truncated program names: 'Camden Hills Cross Countr', 'Sanford High School X Cou', "XC '"
        t2 = re.sub(r"(?i)\s+(cross|x)[\s\-]*(c|co|cou|coun|count|countr|country)?\s*'?$", '', t2)
        t2 = re.sub(r"(?i)\s+(xc|cc)\s*'?$", '', t2)
        t2 = re.sub(r"(?i)\s+(track|t)\s*(&|and)?\s*(f|fi|fie|fiel|field)?$", '', t2) if len(t2) > 8 else t2
        words = t2.split()
        while len(words) > 1 and words[-1].lower().strip('.') in SEASON_WORDS:
            words.pop()
        t2 = ' '.join(words)
        t2 = re.sub(r'\s+[A-D]$', '', t2)                    # relay squad letter
        if t2 == t:
            break
        t = t2
        out += emit(t, 'season-words')
    # gender glued onto a short code: 'ELB', 'Elhsg', 'WHSG', 'EL-B', 'Elgi'
    m = re.fullmatch(r'([A-Za-z]{2,5}?)[\-\s]?(B|G|b|g|Gi|gi|Bo|bo)', t)
    if m and len(t) <= 7:
        out += emit(m.group(1), 'glued-gender')
    # leading gender column glued on: 'M NYA MS', 'M BRUNSWICK JR H.S.'
    m = re.match(r'^([MFWBG])\s+(?=\S{2,})', t)
    if m:
        out += emit(t[m.end():], 'lead-gender')
    for v, note in out:
        yield v, note, state


# ---------------------------------------------------------------------------
# Index over catalog entries
# ---------------------------------------------------------------------------

class Index:
    def __init__(self, schools: dict):
        self.schools = schools
        self.exact = {}      # norm(name) -> set(ids)
        self.stems = {}      # (level, stem) -> set(ids)
        self.prefixes = []   # (flat(name), id)
        self.codes = {}      # CODE -> set(ids)
        self.nicks = {}      # norm(nickname) -> set(ids)
        for sid, e in schools.items():
            lvl = e.get('level', 'hs')
            names = [e['name']] + list(e.get('names', [])) + list(e.get('aliases', []))
            for nm in names:
                n = norm(nm)
                if not n:
                    continue
                self.exact.setdefault(n, set()).add(sid)
                st = stem(n)
                if st:
                    self.stems.setdefault((lvl, st), set()).add(sid)
                self.prefixes.append((flat(nm), sid))
                if n != flat(nm):
                    self.prefixes.append((n, sid))   # token-mapped form: "mt desert island high school"
            for c in e.get('codes', []):
                self.codes.setdefault(c.upper(), set()).add(sid)
            for k in e.get('nicknames', []):
                self.nicks.setdefault(norm(k), set()).add(sid)
        self.prefixes.sort()

    def _state_ok(self, sid, state):
        e = self.schools[sid]
        st = e.get('state', 'ME')
        if state is None:
            return st in ('ME', None) or e.get('level') in ('college', 'club', 'x') or bool(e.get('bare_ok'))
        return st == state

    def _pick(self, ids, level, state):
        ids = {i for i in ids if self._state_ok(i, state)} or (set() if state else ids)
        ay = getattr(self, '_cur_ay', None)
        if ay is not None:   # a school that did not exist that year cannot be meant ('SMHS' in 2006)
            ids = {i for i in ids if in_years(self.schools[i], ay)}
        if len(ids) <= 1:
            return ids
        if level:
            lv = {i for i in ids if self.schools[i].get('level') == level}
            if lv:
                return lv
        return ids

    def match(self, raw: str, level=None, gender=None, ay=None):
        """Name-only resolution. Returns (id|None, method, candidates:list, weak:bool).
        `ay` (academic year) rejects schools that did not exist that year."""
        key = (raw, level, gender, ay)
        hit = self._memo.get(key) if hasattr(self, '_memo') else None
        if hit is None:
            if not hasattr(self, '_memo'):
                self._memo = {}
            self._cur_ay = ay
            try:
                hit = self._memo[key] = self._match(raw, level, gender)
            finally:
                self._cur_ay = None
        return hit

    def _variants_plus(self, raw, gender):
        """variants() plus versions with a trailing mascot removed ('Lincoln Academy Eagles')."""
        for v, note, state in variants(raw, gender):
            yield v, note, state
            words = v.split()
            for k in (2, 1):
                if len(words) > k and norm(' '.join(words[-k:])) in self.nicks:
                    yield ' '.join(words[:-k]), note + '+mascot-tail', state
                    break

    def _match(self, raw, level, gender):
        best_amb = None
        last = None
        fallback = None
        for v, note, state in self._variants_plus(raw, gender):
            n = norm(v)
            if not n:
                continue
            last = (v, state)
            vlevel = level_of(n)
            want = vlevel or level
            tag = '' if note == 'literal' else f'+{note}'
            # 1. exact name / alias
            ids = self._pick(self.exact.get(n, set()), want, state)
            if len(ids) == 1:
                sid = next(iter(ids))
                # a level-free name in a meet of another level means that level's school
                # ('Ellsworth' / 'Bangor Christian' in an MS meet)
                if vlevel is None and level and self.schools[sid].get('level') not in (level, 'coop', 'x') \
                        and not set(n.split()) & {'high', 'hs'}:
                    alt = self._pick(self.stems.get((level, stem(n)), set()), level, state)
                    if len(alt) == 1:
                        return next(iter(alt)), 'exact+level-context' + tag, sorted(alt | ids), False
                # an out-of-state school named without its state ('Cumberland') needs athlete confirmation
                weak = bool(state is None and self.schools[sid].get('bare_ok'))
                return sid, 'exact' + tag, sorted(ids), weak
            if len(ids) > 1 and not best_amb:
                best_amb = (None, 'ambiguous-name' + tag, sorted(ids), True)
            # 2. stem at the string's own level, else the meet level, else hs
            st = stem(n)
            if st and not vlevel and fallback is None:
                # remember a same-stem school at a level the context does not suggest (used last, weak)
                for lv in ('ms', 'hs', 'college'):
                    if lv not in (level, 'hs' if level is None else None):
                        ids = self._pick(self.stems.get((lv, st), set()), lv, state)
                        if len(ids) == 1:
                            fallback = (next(iter(ids)), 'bare-name+other-level' + tag, sorted(ids), True)
                            break
            if st:
                order = [vlevel] if vlevel else ([level, 'hs'] if level and level != 'hs' else ['hs', 'college', 'club'])
                for lv in order:
                    ids = self._pick(self.stems.get((lv, st), set()), lv, state)
                    if len(ids) == 1:
                        sid = next(iter(ids))
                        bare = vlevel is None and not (set(n.split()) - set(st.split()))
                        weak = bare and level is None and any(
                            (o, st) in self.stems for o in ('ms', 'hs') if o != lv)
                        return sid, ('stem' if not bare else 'bare-name') + tag, [sid], weak
                    if len(ids) > 1 and not best_amb:
                        best_amb = (None, 'ambiguous-stem' + tag, sorted(ids), True)
                        break
            # 3. code (as printed, case-insensitive): 'MTA', 'GNG', 'Gnghs'
            compact = re.sub(r'[^A-Za-z0-9&+]', '', v).upper()
            ids = self._pick(self.codes.get(compact, set()) | self.codes.get(v.upper(), set()), want, state)
            if ids:
                return (next(iter(ids)) if len(ids) == 1 else None), 'code' + tag, sorted(ids), len(ids) != 1
            # 4. Hy-Tek truncation: a unique prefix of a full name ('Mt. Desert I',
            # 'Camden Hills Regional Hig'). Short all-caps prefixes ('GREE') are weak.
            f = flat(v)
            if len(f.replace(' ', '')) >= 4:
                ids = self._pick(self._prefix_ids(f) | self._prefix_ids(n), want, state)
                if len(ids) > 1:     # a co-op label is never printed truncated to its host's name
                    ids = {i for i in ids if self.schools[i].get('level') != 'coop'} or ids
                if len(ids) > 1 and want is None:
                    hs = {i for i in ids if self.schools[i].get('level') == 'hs'}
                    if len(hs) == 1:   # default to the high school, but ask for confirmation
                        return next(iter(hs)), 'truncation' + tag, sorted(ids), True
                if len(ids) == 1:
                    weak = v.isupper() and len(f) <= 5 or len(f) <= 4
                    return next(iter(ids)), 'truncation' + tag, sorted(ids), weak
                if len(ids) > 1 and not best_amb:
                    best_amb = (None, 'ambiguous-truncation' + tag, sorted(ids), True)
            # 5. mascot
            ids = self._pick(self.nicks.get(n, set()), want, state)
            if ids:
                return (next(iter(ids)) if len(ids) == 1 else None), 'nickname' + tag, sorted(ids), True
        if best_amb:
            return best_amb
        if fallback:
            return fallback
        # 6. spelling slip ('Maine Central Insitute', 'Lweiston High Sc', 'Carrebec'): a unique close
        # match on letters only, never for short strings. Weak: athletes must confirm.
        if last:
            v, state = last
            c = re.sub(r'[^a-z]', '', v.lower())
            if len(c) >= 7 and not looks_like_debris(v) and not re.match(r'^\s*\d', raw):
                sid = self._fuzzy(c, level, state)
                if sid:
                    return sid, 'fuzzy', [sid], True
        return None, 'unresolved', [], True

    def _fuzzy(self, c, level, state):
        import difflib
        if not hasattr(self, '_compact'):
            self._compact = {}
            for f, sid in self.prefixes:
                if self.schools[sid].get('curation') == 'auto':
                    continue          # never spell-correct into an uncurated entry
                self._compact.setdefault(f.replace(' ', ''), set()).add(sid)
            self._compact_keys = list(self._compact)
        # compare against names of the same length band, and their same-length prefixes (truncations)
        best = []
        sm = difflib.SequenceMatcher()
        sm.set_seq2(c)
        for k in self._compact_keys:
            if k[:1] != c[:1]:
                continue
            if abs(len(k) - len(c)) > 3 and not (len(k) > len(c) and k[:2] == c[:2]):
                continue
            truncated = len(k) > len(c) + 2
            kk = k[:len(c)] if truncated else k
            cut = 0.93 if truncated else 0.88
            sm.set_seq1(kk)
            if sm.real_quick_ratio() < cut or sm.quick_ratio() < cut:
                continue
            r = sm.ratio()
            if r >= cut:
                best.append((r, k))
        if not best:
            return None
        best.sort(reverse=True)
        top = best[0][0]
        ids = set()
        for r, k in best:
            if r >= top - 0.02:
                ids |= self._compact[k]
        ids = self._pick(ids, level, state)
        return next(iter(ids)) if len(ids) == 1 else None

    def _prefix_ids(self, f):
        import bisect
        i = bisect.bisect_left(self.prefixes, (f, ''))
        ids = set()
        while i < len(self.prefixes) and self.prefixes[i][0].startswith(f):
            ids.add(self.prefixes[i][1])
            i += 1
        return ids


# ---------------------------------------------------------------------------
# Runtime API
# ---------------------------------------------------------------------------

_CAT = None
_RAW = None
_IDX = None


def _load():
    global _CAT, _RAW, _IDX
    if _CAT is None:
        with open(CATALOG_PATH, encoding='utf-8') as f:
            _CAT = json.load(f)
        try:
            with open(RAWMAP_PATH, encoding='utf-8') as f:
                _RAW = json.load(f)
        except FileNotFoundError:
            _RAW = {'raw': {}, 'overrides': {}, 'store_teams': {}}
        _IDX = Index(_CAT['schools'])
        NOT_SCHOOL_PATTERNS[:] = _CAT.get('not_schools', [])
    return _CAT, _RAW, _IDX


def meet_level(meet_name: str = None, grade=None):
    """'ms' / 'college' / 'hs' / None from a file stem or meet name (same rule as scraper_v2)."""
    if meet_name:
        # "ms-<slug>": a MileSplit transcription's file prefix, not "middle school"
        low = re.sub(r'[-_.]+', ' ', re.sub(r'^ms-(?=[a-z0-9])', '', meet_name).lower())
        low = re.sub(r'\bst\.? doms?\b', 'st dominic', low)   # "St. Doms" is a school, not an MS code
        if re.search(r'\bms\b|\bjh\b|middle school|junior high|elementary|middle(?!ton|bury|sex|boro)|^jh|xcjh|jh(?:xc|cc|boys|girls|champ|meet)|[a-z]ms(\b|\d)|'
                     r'ms(boys|girls|invite|inv|xc|cc|champ|meet|results)|(boys|girls)ms\b', low):
            return 'ms'
        if re.search(r'\bcollege\b|university|collegiate|gnac|nescac|nescac|\bnaia\b|\bncaa\b', low):
            return 'college'
    g = str(grade or '').strip().upper()
    if g in ('5', '6', '7', '8', 'MS', '05', '06', '07', '08'):
        return 'ms'
    if g in ('FR', 'SO', 'JR', 'SR') and meet_name and re.search(r'college|univ', meet_name.lower()):
        return 'college'
    return None


def file_rule(raw_school, year, season, meet_name, rules):
    """Per-file meaning of a context-dependent string (catalog 'file_rules', from reading the files)."""
    if not meet_name:
        return None
    stem_ = os.path.splitext(os.path.basename(meet_name))[0]
    for r in rules:
        if raw_school not in r['raw'] or (r.get('season') and r['season'] != season):
            continue
        lo, hi = r['years']
        if not lo <= int(year) <= hi:
            continue
        if re.search(r['file'], stem_, re.I):
            return r['id']
    return None


def coop_or_host(sid, year, season, gender=None):
    """A co-op label read in a sport/year/gender where that co-op was not competing means its host
    school ('Lisbon/Oak Hill' in 2026 XC is Lisbon: the co-op is outdoor-track only)."""
    cat, _, _ = _load()
    if not sid or not sid.startswith('coop-'):
        return sid
    c = next((c for c in cat.get('coops', []) if c['id'] == sid), None)
    if not c:
        return sid
    active = season in c['seasons'] and int(year) in c.get('active', {}).get(season, []) and \
        not (gender and c.get('genders') and gender not in c['genders'])
    return sid if active else c.get('host', sid)


def resolve(raw_school, *, year, season, gender=None, meet_name=None, grade=None):
    """Catalog id for a raw school string in context, or None when unresolved/ambiguous."""
    sid = _resolve(raw_school, year=year, season=season, gender=gender, meet_name=meet_name, grade=grade)
    return coop_or_host(sid, year, season, gender)


def _resolve(raw_school, *, year, season, gender=None, meet_name=None, grade=None):
    cat, raw, idx = _load()
    s = re.sub(r'\s+', ' ', raw_school or '').strip()
    if not s:
        return None
    ay = academic_year(year, season)
    if meet_name:
        stem_ = os.path.splitext(os.path.basename(meet_name))[0]
        ov = raw['overrides'].get(f'{year}/{season}/{stem_}', {})
        if s in ov:
            return ov[s]
        hit = file_rule(s, year, season, meet_name, cat.get('file_rules', []))
        if hit:
            return hit
    if looks_like_debris(s) and not salvage(s):
        return None
    entry = raw['raw'].get(s)
    level = meet_level(meet_name, grade)

    def ok(sid):
        return sid and in_years(cat['schools'].get(sid, {}), ay)
    if entry and ok(entry.get('by_season', {}).get(season)) and not entry.get('context_dependent'):
        return entry['by_season'][season]
    if entry and ok(entry.get('id')) and not entry.get('context_dependent'):
        return entry['id']
    if entry and entry.get('by_level') and ok(entry['by_level'].get(level or 'hs')):
        return entry['by_level'][level or 'hs']
    sid, method, cands, weak = idx.match(salvage(s) if looks_like_debris(s) else s, level=level, gender=gender, ay=ay)
    if sid and weak and (method.startswith(('code', 'nickname', 'fuzzy')) or 'other-level' in method):
        return None   # codes, mascots and spelling guesses need file evidence; the builder supplies it
    return sid


_SHARED = None


def shared_codes():
    """Lower-cased codes two or more Maine schools print ('brhs' Boothbay Region / Brewer, 'ohs'
    Oceanside / Orono, 'whs' six schools). Only a meet's own evidence can place one; nothing may
    expand or guess them globally."""
    global _SHARED
    if _SHARED is None:
        cat, _, _ = _load()
        claims = {}
        for sid, s in cat['schools'].items():
            if sid.startswith(('me-hs', 'me-ms')):
                for c in s.get('codes', []):
                    claims.setdefault(c.lower(), set()).add(sid)
        _SHARED = {c for c, v in claims.items() if len(v) > 1}
    return _SHARED


def team_unit(sid, year, season, gender=None):
    """The scoring unit a school competed as: its co-op id when that co-op was active for this
    sport/season, gender and year (catalog 'active': years with evidence - the co-op label printed in
    results, the co-op as an official team in a Team Scores block, or an MPA classification list -
    with gaps of up to three years filled), else the school id."""
    cat, _, _ = _load()
    if not sid:
        return sid
    y = int(year)
    for c in cat.get('coops', []):
        if sid not in c['members'] or season not in c['seasons']:
            continue
        if gender and c.get('genders') and gender not in c['genders']:
            continue
        if y in c.get('active', {}).get(season, []):
            return c['id']
    return sid


def store_team_id(store_team_name):
    """Catalog id for an existing store team name (ui/public/data/teams/<slug>)."""
    _, raw, _ = _load()
    v = raw.get('store_teams', {}).get(store_team_name)
    if isinstance(v, dict):
        return v.get('id')
    return v


def info(sid):
    cat, _, _ = _load()
    return cat['schools'].get(sid) or next((c for c in cat.get('coops', []) if c['id'] == sid), None)


# ---------------------------------------------------------------------------
# Store team names
# ---------------------------------------------------------------------------

STORE_NAMES_PATH = os.path.join(DATA_DIR, 'catalog_store_names.json')
_STORE_NAMES = None
_STORE_IDS = None


def _store_names():
    global _STORE_NAMES, _STORE_IDS
    if _STORE_NAMES is None:
        with open(STORE_NAMES_PATH, encoding='utf-8') as f:
            _STORE_NAMES = json.load(f)['names']
        _STORE_IDS = {v: k for k, v in _STORE_NAMES.items()}
    return _STORE_NAMES, _STORE_IDS


def store_name(sid):
    """The store team name results for catalog id `sid` are filed under."""
    names, _ = _store_names()
    return names.get(sid) or (info(sid) or {}).get('name') or sid


def id_for_store_name(name):
    """Inverse of store_name(), falling back to the legacy store-team map."""
    _, ids = _store_names()
    return ids.get(name) or store_team_id(name)


def store_unit(raw_school, *, year, season, gender=None, meet_name=None, grade=None):
    """Catalog id a result row is filed under: the school, or the co-op it
    raced as that season. None when the string doesn't resolve."""
    sid = resolve(raw_school, year=year, season=season, gender=gender,
                  meet_name=meet_name, grade=grade)
    if sid is None:
        return None
    return team_unit(sid, year, season, gender) or sid
