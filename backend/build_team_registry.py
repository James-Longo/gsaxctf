"""
build_team_registry.py - Generate backend/data/team_registry.json.

The registry solves the team-identity problem: one school gets entered under
many names (truncations, abbreviations, glued suffixes, misspellings), and
bare town names mean different schools at different meet levels ("Falmouth"
in an MS meet is Falmouth Middle School, in an HS meet Falmouth High School).

Structure:
{
  "teams":   { canonical_name: {"level": "hs"|"ms"|"college"|"club"} },
  "aliases": { alias_lower: {"hs": canonical, "ms": canonical, ...} }
}

Generation is data-driven: it clusters every team currently in the store by a
normalized key, classifies level from name tokens + observed grades, picks
the biggest explicitly-named member as each cluster's canonical, and maps all
members as aliases. MANUAL_ALIASES handles irregulars (acronyms, nicknames,
misspellings) and always wins. Re-running preserves MANUAL_ALIASES; the
registry file itself may also be hand-edited (regeneration merges aliases,
never removes manually added ones).
"""

import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.json_store import TEAMS_DIR

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), 'data', 'team_registry.json')

# Irregular names that clustering can't derive. alias (lower) -> canonical.
# The canonical's level comes from its own classification.
MANUAL_ALIASES = {
    'mta': 'Mt. Ararat High School',
    'mess indoor': 'Messalonskee High School',
    'mess': 'Messalonskee High School',
    'greeley': 'Greely High School',
    'gng': 'Gray New Gloucester High School',
    'gnghs': 'Gray New Gloucester High School',
    'prhs': 'Poland Regional High School',
    'wtvl': 'Waterville High School',
    'oths': 'Old Town High School',
    'traiptrack': 'Traip Academy',
    'traipkittry': 'Traip Academy',
    'sumnernarragaugus': 'Sumner/Narragaugus',
    'narraguagus': 'Sumner/Narragaugus',
    'sumner memorial': 'Sumner/Narragaugus',
    'boothbaywiscasset': 'Boothbay/Wiscasset',
    'medomak': 'Medomak Valley High School',
    'lake region': 'Lake Region High School',
    'holham': 'Hall-Dale High School',
    'halldale': 'Hall-Dale High School',
    'mount desert island highschool': 'Mt. Desert Island High School',
    'southern maine c': 'University of Southern Maine',
    'maine track': 'University of Maine',
    'mainefarmington': 'University of Maine at Farmington',
    'colbysawyer': 'Colby-Sawyer College',
    'tripp': 'Tripp Middle School',
    'york it': 'York High School',
    'khs track': 'Kennebunk High School',
    'khstf': 'Kennebunk High School',
    'biddtf': 'Biddeford High School',
    'ws cohen': 'William S Cohen School',
    'cohen school': 'William S Cohen School',
    'wagner school': 'Wagner Middle School',
    'wagner ms': 'Wagner Middle School',
    'leonard school': 'Leonard Middle School',
    'leonard ms': 'Leonard Middle School',
    'doughty': 'James Doughty School',
    'james doughty school': 'James Doughty School',
    'warsaw jh': 'Warsaw Middle School',
    'hawkshermon': 'Hermon High School',
    'sedomochadf': 'Sedomocha Middle School',
    'sedomocha ms': 'Sedomocha Middle School',
}

MS_TOKENS = re.compile(
    r'\b(ms|middle|jh|junior high|jr high|elementary|elem|intermediate|grammar|'
    r'primary|consolidated|community school|village school|central school)\b', re.I)
COLLEGE_TOKENS = re.compile(
    r'\b(college|university|univ|bowdoin|bates|colby|husson|umaine|maine maritime|'
    r'usm|umf|una|unh|merrimack|st joseph\'?s?|thomas college|cc)\b', re.I)
HS_TOKENS = re.compile(r'\b(high school|hs|high|academy|acad|institute|christian school)\b', re.I)
# Maine K-8 schools are commonly "<Name> School" (no "High")
K8_SCHOOL = re.compile(r'\bschool\b', re.I)

STRIP_WORDS = {'high', 'school', 'schools', 'hs', 'academy', 'acad', 'regional',
               'area', 'community', 'memorial', 'district', 'institute',
               'comprehensive', 'consolidated', 'boys', 'girls', 'indoor',
               'outdoor', 'track', 'field', 'tf', 'team', 'varsity', 'club',
               'ms', 'middle', 'junior', 'jh', 'elementary', 'elem', 'grammar',
               'intermediate', 'college', 'university'}


def cluster_key(name: str) -> str:
    """Level-blind identity key: 'Falmouth High School', 'Falmouth MS' and
    'FalmouthME' all reduce to 'falmouth'."""
    n = re.sub(r'(?<=[a-z])(ME|MA|NH|VT|CT|RI)\b', '', name)
    n = re.sub(r'[,\s]+(ME|MA|NH|VT|CT|RI)\s*$', '', n)
    # de-glue CamelCase compounds (but not Mc/Mac names)
    n = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', n)
    n = n.lower().replace('.', ' ').replace('-', ' ').replace("'", '').replace('/', ' ')
    n = re.sub(r'\bmount\b', 'mt', n)
    n = re.sub(r'\bsaint\b', 'st', n)
    n = re.sub(r'\b(19|20)\d{2}\b', '', n)
    toks = [t for t in n.split() if t not in STRIP_WORDS]
    # drop trailing relay-squad letters and truncated strip words
    while toks and (toks[-1] in ('a', 'b', 'c', 'd')
                    or any(w.startswith(toks[-1]) for w in STRIP_WORDS)):
        toks.pop()
    return ' '.join(toks)


def classify_level(name: str, ms_grade_fraction: float) -> str:
    if COLLEGE_TOKENS.search(name):
        return 'college'
    if MS_TOKENS.search(name):
        return 'ms'
    if HS_TOKENS.search(name):
        return 'hs'
    # "<Name> School" with no 'High' anywhere = K-8 in Maine
    if K8_SCHOOL.search(name):
        return 'ms'
    # No explicit token: use observed grades
    if ms_grade_fraction > 0.5:
        return 'ms'
    return 'hs'


def load_team_stats():
    """Return ({team: (perf_count, ms_grade_fraction)},
               {team: {(year, season): set(athlete_names)}}) from the store."""
    stats = {}
    rosters = {}
    for fn in sorted(os.listdir(TEAMS_DIR)):
        full = os.path.join(TEAMS_DIR, fn)
        if not os.path.isdir(full):
            continue
        name = fn.replace('_', ' ')
        count = 0
        ms = 0
        roster = defaultdict(set)
        for chunk in os.listdir(full):
            if not chunk.endswith('.json'):
                continue
            try:
                perfs = json.load(open(os.path.join(full, chunk), encoding='utf-8'))
            except Exception:
                continue
            year, _, season = chunk[:-5].partition('_')
            count += len(perfs)
            ms += sum(1 for p in perfs if p.get('grade') == 'MS')
            for p in perfs:
                a = p.get('athlete_name', '')
                # skip relay pseudo-athletes and comma-joined relay rosters
                if not a or ',' in a or a.endswith(' Relay'):
                    continue
                roster[(year, season)].add(a.lower())
        stats[name] = (count, ms / count if count else 0.0)
        rosters[name] = dict(roster)
    return stats, rosters


# Athlete-overlap evidence: two "teams" sharing a large fraction of athletes
# in the SAME year+season are the same team under different names.  The
# same-season constraint keeps MS and HS programs apart (an athlete competes
# for one level at a time).
MIN_SHARED = 5
MIN_OVERLAP = 0.5


def athlete_overlap_edges(rosters):
    index = defaultdict(list)  # (athlete, year, season) -> [team]
    for team, seasons in rosters.items():
        for (year, season), athletes in seasons.items():
            for a in athletes:
                index[(a, year, season)].append(team)

    shared = defaultdict(lambda: defaultdict(int))  # (t1,t2) -> (yr,ssn) -> n
    for (a, year, season), team_list in index.items():
        if len(team_list) < 2:
            continue
        for i in range(len(team_list)):
            for j in range(i + 1, len(team_list)):
                t1, t2 = sorted((team_list[i], team_list[j]))
                shared[(t1, t2)][(year, season)] += 1

    edges = []
    for (t1, t2), seasons in shared.items():
        for (year, season), n in seasons.items():
            if n < MIN_SHARED:
                continue
            r1 = rosters[t1].get((year, season), set())
            r2 = rosters[t2].get((year, season), set())
            smaller = min(len(r1), len(r2))
            if smaller and n / smaller >= MIN_OVERLAP:
                edges.append((t1, t2, year, season, n, n / smaller))
                break
    return edges


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def build():
    stats, rosters = load_team_stats()
    print(f'Loaded {len(stats)} teams from store.')

    # Also seed with the scraper's canonical mapping values
    from backend.scraper_v2 import TEAM_MAPPING
    for canon in set(TEAM_MAPPING.values()):
        stats.setdefault(canon, (0, 0.0))

    # Anchors: explicit school names. Two different same-level anchors must
    # never land in one cluster — that vetoes bad transitive merges (e.g.
    # "YHS" overlapping both York's and Yarmouth's rosters in different
    # years, or shared nicknames like "Rams" bridging schools).
    def anchor_key(name, ms_frac):
        if HS_TOKENS.search(name) or MS_TOKENS.search(name) or COLLEGE_TOKENS.search(name):
            return f'{classify_level(name, ms_frac)}:{cluster_key(name)}'
        return None

    anchors = {}  # name -> anchor key
    for name, (count, ms_frac) in stats.items():
        ak = anchor_key(name, ms_frac)
        if ak:
            anchors[name] = ak

    uf = UnionFind()
    root_anchors = defaultdict(set)  # root -> set of anchor keys
    for name in stats:
        root_anchors[uf.find(name)].update([anchors[name]] if name in anchors else [])

    vetoed_nodes = defaultdict(set)  # name -> set of anchor keys it conflicted with

    def try_union(a, b):
        ra, rb = uf.find(a), uf.find(b)
        if ra == rb:
            return True
        merged = root_anchors[ra] | root_anchors[rb]
        # veto when two distinct anchors of the SAME level would merge
        by_level = defaultdict(set)
        for ak in merged:
            by_level[ak.split(':', 1)[0]].add(ak)
        if any(len(keys) > 1 for keys in by_level.values()):
            vetoed_nodes[a].update(root_anchors[rb])
            vetoed_nodes[b].update(root_anchors[ra])
            return False
        uf.union(ra, rb)
        root_anchors[uf.find(ra)] = merged
        return True

    # Evidence 1: name-based identity key (conservative — same key)
    key_first = {}
    for name in sorted(stats, key=lambda n: -stats[n][0]):
        key = cluster_key(name)
        if not key:
            continue
        if key in key_first:
            try_union(key_first[key], name)
        else:
            key_first[key] = name

    # Evidence 2: shared athletes in the same year+season, strongest first
    edges = athlete_overlap_edges(rosters)
    merged_n = vetoed_n = 0
    for t1, t2, year, season, n, frac in sorted(edges, key=lambda e: -e[4]):
        if try_union(t1, t2):
            merged_n += 1
        else:
            vetoed_n += 1
    print(f'Athlete-overlap: {merged_n} merges, {vetoed_n} vetoed (anchor conflicts)')

    # Names that conflicted with multiple anchors are ambiguous (shared
    # nicknames, reused acronyms): exclude them from aliasing so they never
    # steal another school's results.
    ambiguous = {name for name, aks in vetoed_nodes.items()
                 if name not in anchors and len(aks) >= 1}
    print(f'Ambiguous names excluded from aliasing: {len(ambiguous)}')
    for name in sorted(ambiguous)[:12]:
        print(f'   {name!r}')

    # Group into final clusters; ambiguous names are ejected to singletons so
    # they keep their own (junky but honest) team identity.
    clusters = defaultdict(list)  # root -> [(name, count, ms_frac)]
    for name, (count, ms_frac) in stats.items():
        root = name if name in ambiguous else uf.find(name)
        clusters[root].append((name, count, ms_frac))

    teams = {}
    aliases = defaultdict(dict)
    keys_table = defaultdict(dict)

    for _root, members in clusters.items():
        # classify each member, group by level
        by_level = defaultdict(list)
        for name, count, ms_frac in members:
            by_level[classify_level(name, ms_frac)].append((name, count))

        canon_by_level = {}
        for level, names in by_level.items():
            # canonical: the member with an explicit level token and the most
            # performances; fall back to most performances outright
            explicit = [(n, c) for n, c in names
                        if MS_TOKENS.search(n) or HS_TOKENS.search(n) or COLLEGE_TOKENS.search(n)]
            pool = explicit or names
            canonical = max(pool, key=lambda x: x[1])[0]
            # prefer an untruncated extension ("Brewer Middle School" over
            # "Brewer Middle Sc") even if the truncated form has more rows
            for n, _c in pool:
                if n.lower().startswith(canonical.lower()) and len(n) > len(canonical):
                    canonical = n
            canon_by_level[level] = canonical
            teams[canonical] = {'level': level}

        for level, names in by_level.items():
            for name, _ in names:
                aliases[name.lower()][level] = canon_by_level[level]
        # bare/ambiguous aliases get entries for every level in the cluster,
        # and every member's identity key resolves too (so a never-seen
        # variant like bare "South Portland" still lands on the canonical)
        for name, _c, _m in members:
            for level, canonical in canon_by_level.items():
                aliases[name.lower()].setdefault(level, canonical)
                keys_table[cluster_key(name)].setdefault(level, canonical)

    # Manual aliases override everything
    for alias, canonical in MANUAL_ALIASES.items():
        level = classify_level(canonical, 0.0)
        teams.setdefault(canonical, {'level': level})
        aliases[alias] = {lv: canonical for lv in ('hs', 'ms', 'college')} \
            if level == 'hs' else {level: canonical, 'hs': canonical}

    # Merge with existing registry (preserve hand edits: existing alias entries win)
    existing = {}
    if os.path.exists(REGISTRY_PATH):
        try:
            existing = json.load(open(REGISTRY_PATH, encoding='utf-8'))
        except Exception:
            existing = {}
    for alias, levels in existing.get('aliases', {}).items():
        if existing.get('manual_aliases', {}).get(alias):
            aliases[alias] = levels
    registry = {
        'teams': dict(sorted(teams.items())),
        'aliases': dict(sorted(aliases.items())),
        'keys': dict(sorted(keys_table.items())),
    }
    with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=1, ensure_ascii=False, sort_keys=True)

    levels = defaultdict(int)
    for t in teams.values():
        levels[t['level']] += 1
    print(f'Registry written: {len(teams)} canonical teams '
          f'({dict(levels)}), {len(aliases)} aliases -> {REGISTRY_PATH}')


if __name__ == '__main__':
    build()
