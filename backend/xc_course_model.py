"""
xc_course_model.py - cross-country course equivalence from shared runners.

Model: for athlete a in year y on course c,
    log(time_{a,c,y}) = ability_{a,y} + difficulty_c

Fit by robust alternating medians (median polish), using only the signal that
identifies course effects: athlete-years who raced on 2+ distinct courses in
the SAME season. Multiplicative factors absorb both course length and
difficulty, which is exactly what time conversion needs -- so courses of
different distances belong in one fit, and a 3-mile time converts to a 5K
time by the same ratio that converts between two 5Ks.

A course is therefore identified by venue AND distance: "Ellsworth (3.0 mi)"
and "Ellsworth (5K)" are two courses, because a runner's time on one does not
equal their time on the other. Distances are bucketed to 100m, which folds
the 3.1 Mile / 3.11 Mile / 5K spellings of the same race together.

Distance labels from the source files are not trusted on their own: some
files are tagged "1 Mile" while carrying 20-minute 5K times, and some carry a
per-mile pace column instead of finish times. Each (meet, event) group is
checked against a plausible XC pace band before it is admitted, and rows are
then filtered individually on the same basis.

One number is reported per course, and it absorbs everything that makes a
race take longer -- length, hills, footing, turns. That is the quantity time
conversion actually needs, and it is measured rather than assumed: no
distance enters it. A course whose stated distance is wrong still gets a
correct factor, because the factor only ever compares times that were
actually run.

Distance is used internally, as a hint and never as a measurement: to tell a
venue's 3-mile race apart from its 5K, and to flag files whose times
contradict their own label. It is deliberately absent from the output.

Output: ui/public/data/xc_courses.json.gz
    { "generated": ..., "reference": "Belfast (5K)",
      "courses": [ {course, venue, factor, pct, factorSE, pctSE, races,
                    athletes, obs, medianTime, years: [..]} ] }
factor > 1 -> a race here takes longer than one at the Festival of Champions.
"""

import gzip
import json
import math
import os
import random
import re
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.json_store import (TEAMS_DIR, DATA_DIR, _chunk_files, _load_json,
                                enrich_rows, canonical_team_name, parse_mark_value)

MIN_OBS = 30          # course must have this many multi-course observations
ITERATIONS = 12

# Distance plausibility is expressed as pace (seconds per km) so that one rule
# covers every race length. A group median outside the tight band means the
# file's distance label is wrong or its time column is not a finish time; the
# wide band then trims individuals inside an otherwise sound group.
GROUP_PACE = (150, 500)   # 4:00 .. 13:25 per mile, as a meet-wide median
ROW_PACE = (130, 800)     # allow the leader and the last finisher
MIN_RACE_T = 3 * 60       # nothing shorter than this is a finished XC race
DIST_BUCKET = 100         # metres; folds 3.1 Mile / 3.11 Mile / 5K together
REF_DIST = 5000.0         # distance the `difficulty` column is normalized to

# The Festival of Champions at Troy Howard Middle School, Belfast: a 5K, the
# largest race in the state (~1,400 runners), and the one course that most of
# Maine runs in any given season. 74% of the athlete-seasons that identify
# this model include it, which makes it the natural anchor -- factor 1.000
# then means "even with the Festival course" instead of "even with a
# statistical abstraction". It is only a choice of origin: every ratio between
# two courses is identical whichever course the scale is pinned to.
REFERENCE_COURSE = ('Belfast', 5000)
MIN_GROUP = 5             # rows needed before a group median means anything

# Riegel's endurance exponent: time scales as distance**1.06, not linearly,
# because nobody holds 5K pace for a mile or mile pace for a 5K. Normalizing
# with it is what lets a genuine 2-mile course and a 5K sit on one difficulty
# scale; normalizing linearly would make every short race look brutal.
RIEGEL = 1.06

# A fitted course whose implied difficulty lands outside this band is not a
# hard or easy course -- its distance label is wrong. The band is the model's
# own check on the source data, and it catches what pace alone cannot: a 5K
# mislabelled "1.5 Mile" still runs at a pace plausible for 1.5 miles, but it
# cannot also be as hard per mile as every real course in the state.
DIFF_RANGE = (0.80, 1.25)

# How far apart two estimates of ONE course land, measured rather than guessed:
# splitting a course's own races into two halves by meet and fitting each half
# separately, the halves disagree by a median of 0.9% and by 3.8% at the 90th
# percentile (44 courses with enough races to test). Two nodes at one venue
# closer than that cannot be distinguished from a single course disagreeing
# with itself, so they are one course. This replaces the distance label as the
# arbiter: the label proposes a split, the data disposes of it.
MERGE_TOL = 0.038

# Splitting a course by season is far more dangerous than merging: season to
# season a course varies with weather and footing, and a blanket "these
# seasons disagree, so they are different courses" would shatter every stable
# venue -- Belfast included, which would destroy the anchor the whole table is
# measured against. So seasons are never used to split a course. They are used
# only to find a season that disagrees with its OWN course so violently that
# the file behind it must be wrong: 3x the 3.8% same-course noise floor.
SEASON_OUTLIER = 0.11

# ...but a course CAN change for good: South Portland's loop rated 0.80-0.90
# every season through 2022 and 0.98 from 2023; Oxford Hills moved from 1.02
# to 1.12 around 2011. Averaging such a course over all its seasons fits
# neither layout, and the outlier check above then drops the NEW layout as
# the odd one out. An era split is accepted only when the evidence is a
# sustained level shift, not noise: at least ERA_MIN_SEASONS seasons on each
# side, medians ERA_SHIFT apart (beyond the 3.8% same-course noise floor),
# and the seasons cleanly on their own side of the midpoint: a season counts
# as misplaced when it sits past the midpoint by more than half the noise
# floor; an era of three seasons or fewer may hold none, a split at most
# ERA_MISPLACED of all seasons.
ERA_SHIFT = 0.05
ERA_MIN_SEASONS = 2
ERA_MISPLACED = 0.1
ERA_SEP = '~'      # older eras get venue + '~first-last'; the newest keeps the plain name

# Courses change discretely and do not change back. Three or more eras must
# move one way: harder then easier again (A -> B -> A, or Foxcroft's 0.92 ->
# 1.05 -> 0.97) is a run of noisy seasons, not two course changes, so only
# the single strongest split is kept.
#
# Known changes override detection entirely. backend/data/xc_course_changes.json
# maps a venue (its display name) to the seasons a new course was first run,
# with a source: {"South Portland": {"changes": [2023], "source": "..."}}.
# "changes": [] records that the venue never changed. Detection only runs
# for venues not listed, and its splits are candidates to confirm there.
def _load_course_changes():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'data', 'xc_course_changes.json')
    try:
        with open(path, encoding='utf-8') as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith('_')}
    except (OSError, ValueError):
        return {}


KNOWN_CHANGES = _load_course_changes()
MIN_SEASON_OBS = 12    # below this a season cannot judge anything
MIN_SEASONS = 3        # with two seasons there is no way to say which is wrong
BOOTSTRAP = 200    # cluster-bootstrap replicates for the factor standard error
# Courses rated less precisely than this (bootstrap SE, as a factor) are not
# published: a conversion through Fort Kent's 2005 4K (+-10%) says nothing.
MAX_PUBLISH_SE = 0.04


NOISE_TOKENS = re.compile(
    r'\b(results?|list|final|meet|race|invitational|invite|inv|festival|'
    r'varsity|jv|frosh|freshman|boys?|girls?|men|women|xc|cross|country|'
    r'sept?|oct|nov|aug|day|home|dual|tri|quad|team|scores?|updated?|'
    r'revised|corrected|copy|page|[bg]v|[bg]jv|\d+(st|nd|rd|th))\b', re.I)

# Labels that name a meet, a division or a rotating championship rather than a
# place. A course factor pooled across rotating venues is not a course factor.
MEET_LABEL = re.compile(
    r'\bchampionships?\b|\bregionals?\b|\bclass\s+[abcd]\b|\bdivision\b|'
    r'\bstates?\b(?!\s*park)|\bconference\b|venue\s+varies|:\s*$|'
    r'^wmclass|^scarinvite', re.I)

# Institutional and landform suffixes that name the *kind* of place rather
# than the place. Stripping them yields a merge key, so "Thornton" and
# "Thornton Academy", or "Smiling Hill" and "Smiling Hill Farm", collapse to
# one course without needing an alias entry per spelling.
VENUE_SUFFIX = re.compile(
    r'\s*\b('
    r'academy|college|university|'
    r'(senior|junior)?\s*high\s*school|middle\s*school|grade\s*school|'
    r'high|hs|jhs|jr\s*high|ms|elementary|school|'
    r'invitational|invite|ac|acad|'
    r'recreation\s*area|rec\s*area|golf\s*course|'
    r'community\s*park|park|farm|field|fields|course|trails?'
    r')\b\s*$', re.I)

# Irregular forms that no structural rule reaches: initialisms, typos, and
# venues whose common name shares no tokens with its formal one. These map
# merge key -> merge key, so the display name is still chosen from the
# fullest spelling actually observed.
KEY_FIXUPS = {
    'gng': 'gray new gloucester',
    'gray': 'gray new gloucester',
    'new gloucester': 'gray new gloucester',
    'uma': 'um augusta',
    'augusta': 'um augusta',
    'umpi': 'um presque isle',
    'sjc': 'st josephs',
    'st joseph': 'st josephs',
    'linconville': 'lincolnville',
    'mattanawcook acadely': 'mattanawcook',
    'van cortland': 'van cortlandt',
    's portland': 'south portland',
    'spruce mtn': 'spruce mountain',
    'pvcc orono': 'orono',
    'cumberland': 'twin brook',
    'topsham': 'mt ararat',
    'bath': 'hyde',
    'dover foxcroft': 'foxcroft',
    'la liberte': 'laliberte',
    'medomak valley': 'medomak',
    'greater houlton': 'houlton',
    'mt desert island': 'mdi',
    # Mt. Blue State Park (Weld, Dirigo's home course) is not the Mt. Blue
    # High School course (Farmington): their factors differ by ~6-7%.
    # "State park" is therefore not stripped as a suffix; these fold the
    # park's own spellings together.
    'blue hill': 'gsa',
    'mt blue sp': 'mt blue state park',
    'mt blue state': 'mt blue state park',
}


# Races that are not high-school cross country: middle-school meets, alumni
# and open races. Matched against the meet FILE NAME only, never the venue --
# the Festival of Champions is itself held at a middle school, so matching
# venue strings would delete the reference course. Verified against every
# distinct meet name in the store: 28 files, no false positives (MSSM, a high
# school, has no separator around its "MS" and is not matched). Junior-high
# files (ljhsxcboys, cony-jh-xc, ResultsMadJHXCBoys, wjhs-...) and grade-band
# races (WELLS-EXTRAV-6TH) were added once the .txt archives came in: they
# file 2-mile middle-school times under the high school's name and a "5K"
# label, which rated seventh graders as the fastest runners in the state.
NON_HS_MEET = re.compile(
    r'middle|[-_ ]ms[-_ ]|^ms[-_ ]|[-_ ]ms$|alumni|masters|'
    r'jh(s|xc|[-_ .]|$)|junior|\b6th|78th|'
    # middle-level leagues: every year these files carry grades they run at
    # median grade 7-8, so the years without grades are the same races
    r'busline|pvml|pvms|'
    # USATF Junior Olympic and youth races (4K/5K age-group fields, many of
    # them out of state: Long Island, Queensbury, Saratoga, Burrillville)
    r'joxc|usatf|^youth[bg]?$|'
    # Southern Maine middle-school league festivals ("smmsaaseniorgirls")
    # and county middle-school meets with "ms" glued on ("yorkcountymsgirls")
    r'smmsaa|countyms|'
    r'fun[-_ ]?run|parent|coach|elementary|youth|open[-_ ]race', re.I)

# No Maine high-school cross-country race is longer than 5K. A 6K, 8K or
# 4.97-mile field is a college race sharing the store (Bowdoin, Colby, UNE).
# This reads the distance label only to answer "is this even high school",
# which the 8K/6K spellings settle unambiguously -- not to size a course.
MAX_HS_DIST = 5600

# Ablation switches for testing one cleaning rule at a time:
# XC_ABLATE=eras,teamlevel,mindist,offnorm,relay turns those rules off.
ABLATE = set(filter(None, os.environ.get('XC_ABLATE', '').split(',')))
# ...and none much shorter than 4K. Every field at 2.3 miles or less is a
# junior-varsity, freshman or middle-school race (1.37 to 2.3 miles, 2K, 3K);
# the 4K-ish fields are real varsity races (Orono's Red Riot, LaLiberte's
# 2.42-mile 2015 varsity), graded 9-12.
MIN_HS_DIST = 3800

# A meet whose runners ran this much faster or slower (log) than they ran
# everywhere else that season -- compared with the course's other meets on
# the same measure -- is a different race filed under the course's label:
# relay legs (Mt. Blue Relays legs run 11-17 minutes under a "5K" label), a
# JV loop, a wrong distance. Comparing runners with themselves keeps the
# field out of it: an elite field (the New Englands at Belfast) runs fast
# everywhere and is not flagged, which a raw median comparison got wrong.
# Weather and footing move a meet a few percent; a relay leg moves it ~40%.
OFF_NORM = 0.15
MIN_NORM_MEETS = 3
MIN_LINKED = 5     # runners with other races that season needed to judge a meet
# relay meets: each runner's time is one leg (Mt. Blue Relays legs run 11-17
# minutes under a "5K" label), not an individual race
RELAY_MEET = re.compile(r'relay', re.I)
MIN_GRADED = 10       # graded rows needed before a meet's grade mix is judged

EVENT_DIST = re.compile(r'([\d.]+)\s*(Miles?|K|Meters?)\b', re.I)
_DIST_UNIT = {'mile': 1609.344, 'miles': 1609.344,
              'k': 1000.0, 'meter': 1.0, 'meters': 1.0}


def event_distance(event):
    """Nominal race distance in metres from an event label, bucketed.

    Bucketing to DIST_BUCKET folds the several spellings of one race
    ('3.1 Mile' 4989m, '3.11 Mile' 5005m, '5K' 5000m) onto a single course.
    """
    m = EVENT_DIST.search(event or '')
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    metres = v * _DIST_UNIT[m.group(2).lower()]
    if not (800 <= metres <= 12000):
        return None
    return int(round(metres / DIST_BUCKET) * DIST_BUCKET)


def distance_label(metres):
    """How Maine XC names the distance: whole kilometres as '5K', the rest in
    miles, which is how every other race here is advertised."""
    if metres % 1000 == 0:
        return f'{metres // 1000}K'
    mi = metres / 1609.344
    return f'{mi:.2f}'.rstrip('0').rstrip('.') + ' mi'


def course_label(venue, metres):
    return f'{venue} ({distance_label(metres)})'


def _load_aliases():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'data', 'xc_course_aliases.json')
    try:
        with open(path, encoding='utf-8') as f:
            return {k.lower(): v for k, v in json.load(f).items()}
    except Exception:
        return {}


COURSE_ALIASES = _load_aliases()


def _venue_key(name):
    """Merge key for a venue: lowercase, punctuation-free, and stripped of
    institutional suffixes, so every spelling of one place maps together."""
    k = name.lower()
    # "Saxl Park, Bangor", "Fort Foster, Kittery", "Twin Brook, Cumberland":
    # the town after a comma names where the place is, not a different place.
    # A two-letter state ("Burrillville, RI") is kept: it marks out of state.
    m = re.match(r'^(.+?),\s*([a-z .]+)$', k)
    if m and not re.fullmatch(r'[a-z]{2}', m.group(2).strip()):
        k = m.group(1)
    k = re.sub(r'\bmount\b', 'mt', k)
    k = re.sub(r'\bmt\.?\b', 'mt', k)
    k = re.sub(r'\bft\.?\b', 'fort', k)
    k = re.sub(r'\bst\.?\b', 'st', k)
    k = re.sub(r'\buniv(ersity)?\s+of\s+maine\b', 'um', k)
    k = re.sub(r'\bumaine\b', 'um', k)
    k = re.sub(r'\([^)]*\)', ' ', k)
    k = re.sub(r"[.'\u2019]", '', k)
    k = re.sub(r'[-/,]+', ' ', k)
    k = re.sub(r'\s+', ' ', k).strip()
    prev = None
    while prev != k:            # "Mt. Blue State Park" -> "mt blue"
        prev = k
        k = VENUE_SUFFIX.sub('', k).strip()
    return k


def _clean_venue(raw):
    """Tidy an index-supplied venue string: drop wrapped whitespace, trailing
    state, and the gender/division debris that bleeds in from the meet cell."""
    s = re.sub(r'\s+', ' ', str(raw)).strip()
    # 2003-04 index cells carry the division list after the venue:
    # "Ellsworth Invitational - Girls Varsity - Boys JV", "Scarborough
    # Invitational - Girls Middle School"
    s = re.sub(r'\s+[-\u2013]\s+(girls?|boys?|jv|varsity|middle|junior|senior|men|women)\b.*$',
               '', s, flags=re.I)
    s = re.sub(r'\s*[-\u2013]\s*$', '', s)
    s = re.sub(r'\b(boys?|girls?|men|women|varsity|jv|frosh)\b', ' ', s, flags=re.I)
    s = re.sub(r'\s+', ' ', s).strip(' ,.-')
    s = re.sub(r',?\s*\b(ME|Maine)\b\.?$', '', s).strip(' ,.-')
    return s


def norm_course(raw):
    """Normalize a course identity to a canonical venue name.

    Venue strings from the sub5 season index ("Thornton Academy", "Mt. Blue
    State Park") are the normal input and need only cleaning plus suffix
    folding. Filename-derived names ("laliberte-varsity-2024-list") are the
    legacy fallback for rows scraped before the index venue column was
    captured, and get de-noised before the same folding applies.
    """
    s = _clean_venue(raw)
    if not s:
        return ''

    # Only filename slugs go through de-noising; a clean venue name must not
    # be camelCase-split ("McAuley" -> "Mc Auley") or stripped of real tokens.
    slug_like = bool(
        re.search(r'[\d_%]', s)
        or s.islower()
        or re.search(r'result|heat|section|\bpdf\b|^meet\b|^with\b', s, re.I)
        or (' ' not in s and len(s) > 18))
    if slug_like:
        # filename form: split camelCase and separators, drop noise + dates
        s = re.sub(r'%20', ' ', s)
        s = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', s)
        s = re.sub(r'[-_/.]+', ' ', s)
        # years glue straight onto the venue in the oldest slugs
        # ("ellsworth2003bv"), so no word boundary can be required here
        s = re.sub(r'(19|20)\d{2}', ' ', s)
        s = re.sub(r'\b\d{1,2}\b', ' ', s)
        s = NOISE_TOKENS.sub(' ', s)
        toks = []
        for t in s.split():
            # drop glued month+day tokens: sept3, august31, oct12
            if re.fullmatch(r'(jan|feb|mar|apr|may|jun|jul|aug|sept?|oct|nov|dec)[a-z]*\d*',
                            t, re.I):
                continue
            # strip glued qualifiers, glued dates and trailing digits:
            # maranacookgirls, foxcroft9, scarborough17sept, wmclassag
            prev = None
            while prev != t:
                prev = t
                t = re.sub(r'(?i)(?<=\w\w)(girls?|boys?|jv|varsity|varisty|'
                           r'sections?|heats?|results?|[bg]v|[bg]jv)$', '', t)
                t = re.sub(r'(?i)(?<=\w\w)\d*(jan|feb|mar|apr|may|jun|jul|aug|'
                           r'sept?|oct|nov|dec)[a-z]*\d*$', '', t)
                t = re.sub(r'\d+$', '', t)
            if t:
                toks.append(t)
        s = ' '.join(toks).strip(' ,.-')
        if len(s) < 3:
            return ''
        # debris that is a file description, not a place
        if re.search(r'result|by\s?heat|section|heats?$|\bpdf\b|^meet\b|^with\b',
                     s, re.I):
            s2 = COURSE_ALIASES.get(s.title().lower())
            return s2 if s2 is not None else ''
        s = re.sub(r'^la\s*liberte$', 'LaLiberte', s, flags=re.I)
        s = s.title()

    # explicit alias table wins (an empty value means "exclude")
    aliased = COURSE_ALIASES.get(s.lower())
    if aliased is not None:
        if not aliased:
            return ''
        s = aliased

    # A meet or division label is not a course, and a championship whose venue
    # rotates year to year would pool several real courses into one factor.
    if MEET_LABEL.search(s):
        return ''

    key = KEY_FIXUPS.get(_venue_key(s), _venue_key(s))
    if not key or len(key) < 3:
        return ''
    return CANONICAL_NAME.get(key, s)


# Filled by build_canonical_names(): merge key -> the fullest spelling seen.
CANONICAL_NAME = {}


def build_canonical_names(raw_names):
    """Choose one display name per merge key, preferring the most complete
    spelling ('Thornton Academy' over 'Thornton') so the published course
    list reads like a list of places."""
    groups = defaultdict(set)
    for r in raw_names:
        c = _clean_venue(r)
        if not c:
            continue
        a = COURSE_ALIASES.get(c.lower())
        if a:
            c = a
        if MEET_LABEL.search(c):
            continue
        k = KEY_FIXUPS.get(_venue_key(c), _venue_key(c))
        if k and len(k) >= 3:
            groups[k].add(c)
    CANONICAL_NAME.clear()
    for k, variants in groups.items():
        # the fullest spelling, but not one carrying a town after a comma, a
        # meet word or a middle-school tag when a plain one exists
        # ("Kennebunk" over "Kennebunk Middle School", "Saxl Park" over
        # "Saxl Park, Bangor", "Ellsworth" over "Ellsworth Invitational")
        def debris(v):
            return bool(re.search(r',|\binvit|\bmiddle\s*school\b|\bms\b', v, re.I))
        # ties go to the properly capitalized spelling ("Saxl Park")
        CANONICAL_NAME[k] = max(variants, key=lambda v: (not debris(v), len(v),
                                                         sum(ch.isupper() for ch in v), v))
    return CANONICAL_NAME


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def _team_level(team):
    try:
        from backend import school_catalog as sc
    except ImportError:
        return None
    sid = sc.id_for_store_name(team)
    inf = sc.info(sid) if sid else None
    return (inf or {}).get('level') or ('coop' if inf else None)


def load_observations(team_filter=True):
    """Three passes: collect every raw row first so canonical display names can
    be chosen from the fullest spelling observed, then validate each source
    file's distance label against the times it carries, then normalize.

    The middle pass is what makes mixed distances safe. A file tagged
    "1 Mile" whose finishers all took 20 minutes is not a mile race, and a
    file whose "time" column is really a per-mile pace is not a set of finish
    times; both show up as a group median pace far outside GROUP_PACE.
    """
    raw_rows = []   # (athlete_id, year, raw_course, value, dist, meet, date)
    grades = defaultdict(list)
    skipped_dist = 0
    skipped_nonhs = 0
    for fn in sorted(os.listdir(TEAMS_DIR)):
        full = os.path.join(TEAMS_DIR, fn)
        if not os.path.isdir(full):
            continue
        team = canonical_team_name(fn)
        # Only high-school runners identify high-school courses: the school
        # catalog knows each team's level, and middle-school, college and
        # club teams share the store (an 8th grader's 2-mile time filed under
        # a "5K" label, a college 5K at Bowdoin). Co-ops of high schools and
        # the few team names the catalog can't resolve are kept.
        hs_team = (not team_filter or 'teamlevel' in ABLATE
                   or _team_level(team) not in ('ms', 'college', 'club', 'x'))
        for key, chunk in _chunk_files(full):
            if not key.endswith('_XC'):
                continue
            rows = enrich_rows(team, key, _load_json(os.path.join(full, chunk), []))
            for p in rows:
                event = p.get('event', '')
                if 'Cross Country' not in event:
                    continue
                raw = p.get('course') or p.get('meet_name') or ''
                if not raw:
                    continue
                if NON_HS_MEET.search(p.get('meet_name') or '') or \
                        ('relay' not in ABLATE and RELAY_MEET.search(p.get('meet_name') or '')):
                    skipped_nonhs += 1
                    continue
                dist = event_distance(event)
                if dist is None:
                    skipped_dist += 1
                    continue
                if dist > MAX_HS_DIST or (dist < MIN_HS_DIST and 'mindist' not in ABLATE):
                    skipped_nonhs += 1
                    continue
                if not hs_team:
                    skipped_nonhs += 1
                    continue
                val, _ = parse_mark_value(p.get('mark', ''), event)
                if val is None or val < MIN_RACE_T:
                    continue
                raw_rows.append((p['athlete_id'], p['year'], raw, val, dist,
                                 p.get('meet_name'), p.get('date', ''), event))
                gr = str(p.get('grade') or '').strip()
                if gr.isdigit():
                    grades[(p.get('meet_name'), p['year'])].append(int(gr))

    # A meet whose runners are mostly 8th graders or younger is a middle-school
    # race whatever its file is called: league files like busline-boys.txt or
    # gsb-girls.txt carry no tell in the name. Ungraded meets fall back on
    # NON_HS_MEET above.
    ms_meet = {k for k, gs in grades.items()
               if len(gs) >= MIN_GRADED and sum(g <= 8 for g in gs) > len(gs) / 2}
    if ms_meet:
        before = len(raw_rows)
        raw_rows = [r for r in raw_rows if (r[5], r[1]) not in ms_meet]
        skipped_nonhs += before - len(raw_rows)

    build_canonical_names(r[2] for r in raw_rows)

    # Pass 2: trust a file's distance label only if its own times agree with it.
    groups = defaultdict(list)
    for r in raw_rows:
        groups[(r[5] or r[2], r[1], r[7])].append(r[3] / r[4] * 1000)
    ok_group = {}
    for g, paces in groups.items():
        med = median(paces)
        ok_group[g] = (len(paces) >= MIN_GROUP
                       and GROUP_PACE[0] <= med <= GROUP_PACE[1])
    bad = sum(len(v) for g, v in groups.items() if not ok_group[g])
    print(f'{len(raw_rows):,} dated XC rows; {bad:,} dropped in '
          f'{sum(1 for g in ok_group if not ok_group[g]):,} groups whose times '
          f'contradict their distance label')
    if skipped_dist:
        print(f'{skipped_dist:,} rows had no parsable race distance')
    if skipped_nonhs:
        print(f'{skipped_nonhs:,} rows dropped as not high-school racing '
              '(middle school, alumni, open, college)')

    obs = []  # (athlete_id, year, (venue, dist), log_time, meet, date)
    for aid, year, raw, val, dist, meet, d, event in raw_rows:
        if not ok_group[(meet or raw, year, event)]:
            continue
        pace = val / dist * 1000
        if not (ROW_PACE[0] <= pace <= ROW_PACE[1]):
            continue
        venue = norm_course(raw)
        if not venue:
            continue
        obs.append((aid, year, (venue, dist), math.log(val), meet, d))
    return obs if 'offnorm' in ABLATE else drop_off_norm_meets(obs)


def drop_off_norm_meets(obs):
    """Remove meets whose runners' times are out of line with those runners'
    own other races that season, by more than OFF_NORM beyond what the
    course's meets usually show."""
    by_as = defaultdict(list)
    for o in obs:
        by_as[(o[0], o[1])].append((o[4], o[3]))
    resid = defaultdict(list)          # (course, meet, year) -> residuals
    for o in obs:
        others = [lt for m, lt in by_as[(o[0], o[1])] if m != o[4]]
        if len(others) >= 2:
            resid[(o[2], o[4], o[1])].append(o[3] - median(others))
    meet_r = {k: median(v) for k, v in resid.items() if len(v) >= MIN_LINKED}
    per_course = defaultdict(list)
    for (course, _, _), r in meet_r.items():
        per_course[course].append(r)
    norm = {c: median(v) for c, v in per_course.items() if len(v) >= MIN_NORM_MEETS}
    bad = {k for k, r in meet_r.items() if k[0] in norm and abs(r - norm[k[0]]) > OFF_NORM}
    if bad:
        n = sum(1 for o in obs if (o[2], o[4], o[1]) in bad)
        print(f'{n:,} rows dropped in {len(bad)} meets whose runners ran '
              f'out of line with their own other races (relay legs, JV loops, wrong label)')
    return [o for o in obs if (o[2], o[4], o[1]) not in bad]


def _dist_adj(dist):
    """Log-scale time a course's length alone accounts for, vs a 5K."""
    return RIEGEL * math.log(dist / REF_DIST)


def difficulty_of(log_factor, dist):
    """Course factor with length divided out: what it would be at 5K."""
    return math.exp(log_factor - _dist_adj(dist))


def _center(course_f):
    """Centering constant that pins the scale to the Festival of Champions.

    Falls back to the median difficulty for the four seasons that have no
    Festival in the store (2003, 2013, 2016 and the cancelled 2020), so those
    years still produce a usable scale. Centering on the median raw factor
    would be meaningless once distances are mixed -- it would track whichever
    race length happened to be commonest, not how hard anything is.
    """
    if REFERENCE_COURSE in course_f:
        return course_f[REFERENCE_COURSE]
    return median([f - _dist_adj(dist) for (_, dist), f in course_f.items()])


def _solve(multi):
    """Alternating medians over a fixed set of athlete-years. Returns
    (course -> log factor, course -> observation count), centered so that the
    median-difficulty course sits at 1.0."""
    course_f = defaultdict(float)
    ability = {}
    residuals = defaultdict(list)
    for _ in range(ITERATIONS):
        for ay, rows in multi.items():
            ability[ay] = median([lt - course_f[c] for c, lt in rows])
        residuals = defaultdict(list)
        for ay, rows in multi.items():
            for c, lt in rows:
                residuals[c].append(lt - ability[ay])
        for c, rs in residuals.items():
            course_f[c] = median(rs)
    center = _center(course_f)
    for c in course_f:
        course_f[c] -= center
    return course_f, {c: len(rs) for c, rs in residuals.items()}


def multi_course_athlete_years(obs):
    by_ay = defaultdict(list)
    for aid, year, course, lt, meet, d in obs:
        by_ay[(aid, year)].append((course, lt))
    return {ay: rows for ay, rows in by_ay.items()
            if len({c for c, _ in rows}) >= 2}


def fit(obs, bootstrap=BOOTSTRAP):
    """Fit course factors, plus a cluster-bootstrap standard error.

    The resampling unit is the MEET, not the athlete-season. That choice is
    the whole uncertainty estimate. Resampling athlete-seasons holds every
    race fixed and only asks "what if different runners had shown up", so it
    never sees the mud, the weather, the timing, or the year the finish chute
    moved -- and it reports intervals of a few tenths of a percent. Splitting
    each course's own races in half by meet and fitting the halves separately
    shows the true disagreement is a median of 0.9% and 3.8% at the 90th
    percentile, roughly an order of magnitude wider. Resampling meets captures
    that, because conditions are shared within a meet and independent between
    them.

    Athlete ids are kept across the resample rather than relabelled per draw,
    so a runner still links the courses they raced; a meet drawn twice simply
    carries double weight.
    """
    multi = multi_course_athlete_years(obs)
    print(f'{len(obs):,} XC observations; {len(multi):,} multi-course athlete-years')
    course_f, counts = _solve(multi)

    stderr = {}
    if bootstrap:
        rng = random.Random(0)
        by_meet = defaultdict(list)
        for o in obs:
            by_meet[(o[4], o[1])].append(o)     # (meet file, season)
        meets = list(by_meet)
        print(f'bootstrapping over {len(meets):,} meet-seasons '
              f'({bootstrap} replicates)')
        draws = defaultdict(list)
        for _ in range(bootstrap):
            sample = []
            for _ in range(len(meets)):
                sample.extend(by_meet[meets[rng.randrange(len(meets))]])
            bmulti = multi_course_athlete_years(sample)
            bf, bcounts = _solve(bmulti)
            for c, f in bf.items():
                # a course barely present in this replicate would contribute
                # noise about a course, not noise about the estimate
                if bcounts.get(c, 0) >= MIN_OBS:
                    draws[c].append(f)
        for c, vals in draws.items():
            if len(vals) < 2:
                continue
            mu = sum(vals) / len(vals)
            var = sum((v - mu) ** 2 for v in vals) / (len(vals) - 1)
            stderr[c] = math.sqrt(var)
    return course_f, counts, stderr


def drop_mislabelled(obs):
    """Fit once cheaply, discard courses whose distance label the fit
    contradicts, and hand back the surviving observations.

    This has to happen before the real fit rather than at print time: a
    mislabelled course still pulls on the athlete-year abilities it shares
    with everything else, so leaving its rows in would bias the courses that
    are labelled correctly.
    """
    course_f, counts, _ = fit(obs, bootstrap=0)
    bad = set()
    for (venue, dist), f in course_f.items():
        if counts.get((venue, dist), 0) < MIN_OBS:
            continue
        d = difficulty_of(f, dist)
        if not (DIFF_RANGE[0] <= d <= DIFF_RANGE[1]):
            bad.add((venue, dist))
    if bad:
        print(f'\ndropping {len(bad)} course(s) whose fitted factor contradicts '
              f'their distance label:')
        for venue, dist in sorted(bad, key=lambda c: -difficulty_of(course_f[c], c[1])):
            print(f"  implied difficulty {difficulty_of(course_f[(venue, dist)], dist):5.2f}  "
                  f"{course_label(venue, dist)}")
    kept = [o for o in obs if o[2] not in bad]
    print(f'\n{len(obs) - len(kept):,} observations dropped with them; refitting\n')
    return kept


def merge_same_venue(obs):
    """Collapse venue nodes that the data cannot tell apart.

    Complete linkage, not single linkage: a cluster forms only when EVERY pair
    inside it agrees. Caribou's races span 16% end to end in steps of 2-4%, so
    chaining neighbours would sweep genuinely different courses into one.
    """
    course_f, counts, _ = fit(obs, bootstrap=0)
    by_venue = defaultdict(list)
    for key, f in course_f.items():
        if counts.get(key, 0) >= MIN_OBS:
            by_venue[key[0]].append((key[1], f))

    remap = {}
    for venue, nodes in by_venue.items():
        if len(nodes) < 2:
            continue
        clusters = [[n] for n in nodes]
        while len(clusters) > 1:
            best = None
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    union = clusters[i] + clusters[j]
                    spread = max(abs(a[1] - b[1]) for a in union for b in union)
                    if spread <= MERGE_TOL and (best is None or spread < best[0]):
                        best = (spread, i, j)
            if best is None:
                break
            _, i, j = best
            clusters[i] += clusters[j]
            del clusters[j]
        for cl in clusters:
            if len(cl) < 2:
                continue
            # keep the best-evidenced node's key so the survivor is the one
            # most of the racing actually happened on
            keep = max(cl, key=lambda n: counts[(venue, n[0])])[0]
            for dist, _ in cl:
                if dist != keep:
                    remap[(venue, dist)] = (venue, keep)

    if remap:
        merged = defaultdict(list)
        for src, dst in remap.items():
            merged[dst].append(src[1])
        print(f'\nmerging {len(remap)} venue node(s) the data cannot separate:')
        for dst, srcs in sorted(merged.items()):
            names = ', '.join(distance_label(d) for d in sorted(srcs))
            print(f'  {dst[0]}: {names} -> {distance_label(dst[1])}')
    else:
        print('\nno venue nodes close enough to merge')
    out = [(a, y, remap.get(c, c), lt, m, d) for a, y, c, lt, m, d in obs]
    print()
    return out


def _season_ratings(obs):
    """(venue, dist) -> [(year, log factor, n)], each season fitted as its
    own course node."""
    per = [(a, y, (f'{c[0]}|{c[1]}@{y}', c[1]), lt, m, d) for a, y, c, lt, m, d in obs]
    cf, counts, _ = fit(per, bootstrap=0)
    seasons = defaultdict(list)
    for key, f in cf.items():
        if counts.get(key, 0) < MIN_SEASON_OBS:
            continue
        name, yr = key[0].rsplit('@', 1)
        venue, dist = name.rsplit('|', 1)
        seasons[(venue, int(dist))].append((yr, f, counts[key]))
    return seasons


def _eras(ys):
    """Split a course's (year, factor, n) seasons into eras by binary
    segmentation; returns a list of season lists, oldest first."""
    ys = sorted(ys, key=lambda t: int(t[0]))
    best = None
    for k in range(ERA_MIN_SEASONS, len(ys) - ERA_MIN_SEASONS + 1):
        left, right = ys[:k], ys[k:]
        ml, mr = median([f for _, f, _ in left]), median([f for _, f, _ in right])
        gap = abs(ml - mr)
        if gap <= ERA_SHIFT:
            continue
        mid = (ml + mr) / 2
        side = 1 if mr > ml else -1
        slack = MERGE_TOL / 2
        wl = sum(1 for _, f, _ in left if (f - mid) * side > slack)
        wr = sum(1 for _, f, _ in right if (mid - f) * side > slack)
        if (len(left) <= 3 and wl) or (len(right) <= 3 and wr) or wl + wr > ERA_MISPLACED * len(ys):
            continue
        if best is None or gap > best[0]:
            best = (gap, k)
    if best is None:
        return [ys]
    eras = _eras(ys[:best[1]]) + _eras(ys[best[1]:])
    levels = [median([f for _, f, _ in e]) for e in eras]
    steps = [b - a for a, b in zip(levels, levels[1:])]
    returns = any(x * y < 0 for x, y in zip(steps, steps[1:]))
    if returns:
        # no return to an earlier course: keep only the single best split,
        # which by construction cannot return
        return [ys[:best[1]], ys[best[1]:]]
    return eras


def era_rules(obs, quiet=False):
    """course -> start years of each era after the first (oldest first),
    for every course that changed for good. The reference course is never
    split."""
    seasons = _season_ratings(obs)
    rules, report = {}, []
    for course, ys in seasons.items():
        known = KNOWN_CHANGES.get(base_venue(course[0]))
        if known is not None:
            starts = sorted(int(y) for y in known.get('changes', []))
            if starts and course != REFERENCE_COURSE:
                rules[course] = starts
            continue
        if course == REFERENCE_COURSE or len(ys) < 2 * ERA_MIN_SEASONS:
            continue
        eras = _eras(ys)
        if len(eras) < 2:
            continue
        rules[course] = [int(e[0][0]) for e in eras[1:]]
        report.append((course, eras))
    if report and not quiet:
        print(f'\n{len(report)} course(s) changed between eras; each era is rated on its own:')
        for course, eras in sorted(report, key=lambda r: r[0][0].lower()):
            parts = ', '.join(f"{e[0][0]}-{e[-1][0]} {math.exp(median([f for _, f, _ in e])):.3f}"
                              for e in eras)
            print(f'  {course_label(*course)}: {parts}')
    return rules


def apply_eras(obs, rules):
    """Rename every observation on a split course to its era by year. The
    newest era keeps the course's plain name, so current courses (and the
    Festival anchor) keep their identity; an older era becomes
    'Venue~first-last', where first-last are its rated seasons' span."""
    names = {}
    for course, starts in rules.items():
        bounds = [0] + starts
        for i in range(len(starts)):
            names[(course, i)] = (bounds[i], starts[i])
    seen = defaultdict(lambda: defaultdict(list))
    for a, y, c, lt, m, d in obs:
        if c in rules:
            era = sum(1 for st in rules[c] if int(y) >= st)
            seen[c][era].append(int(y))
    out = []
    for a, y, c, lt, m, d in obs:
        if c in rules:
            era = sum(1 for st in rules[c] if int(y) >= st)
            if era < len(rules[c]):
                ys = seen[c][era]
                c = (f'{c[0]}{ERA_SEP}{min(ys)}-{max(ys)}', c[1])
        out.append((a, y, c, lt, m, d))
    return out


def split_eras(obs):
    """Give each era of a course that changed for good its own course node."""
    return apply_eras(obs, era_rules(obs))


def base_venue(venue):
    """Display name of a course node (era tag removed)."""
    return venue.split(ERA_SEP, 1)[0]


def clean_observations(team_filter=True):
    """The full cleaning chain, shared by the course table and the
    postseason simulator. The course table rates courses on high-school
    racing only (team_filter=True). The simulator rates runners, and a
    middle-school or college result still says how fast someone is: with the
    filter on, its leave-one-season-out podium accuracy dropped (inclusion
    -0.9 points, order -0.8), so it passes team_filter=False."""
    merged = merge_same_venue(drop_mislabelled(load_observations(team_filter)))
    return drop_outlier_seasons(merged if 'eras' in ABLATE else split_eras(merged))


def drop_outlier_seasons(obs):
    """Remove seasons whose own course contradicts them, and flag the rest.

    The merge step only ever tested splits the distance label proposed; two
    seasons that happened to share a label were pooled without any check. This
    points the same agreement test inward, at the seasons inside one course.

    A lone season far from its course's other seasons is not a course change,
    it is a bad results file -- a mistimed meet, a shortened loop, a results
    page that is really a different race. Those are dropped. Courses with only
    two seasons are reported rather than touched, because nothing in the data
    says which of the two is the liar.
    """
    seasons = _season_ratings(obs)

    bad, flagged = set(), []
    for course, ys in seasons.items():
        fs = [f for _, f, _ in ys]
        med = median(fs)
        if len(ys) < MIN_SEASONS:
            if len(ys) == 2 and abs(fs[0] - fs[1]) > MERGE_TOL:
                flagged.append((abs(fs[0] - fs[1]), course, ys))
            continue
        mad = median([abs(f - med) for f in fs])
        thresh = max(SEASON_OUTLIER, 3 * 1.4826 * mad)
        for yr, f, n in ys:
            if abs(f - med) > thresh:
                bad.add((course, yr))

    if bad:
        print(f'\ndropping {len(bad)} season(s) that contradict their own course:')
        for (course, yr) in sorted(bad):
            ys = {y: (f, n) for y, f, n in seasons[course]}
            med = median([f for _, f, _ in seasons[course]])
            f, n = ys[yr]
            print(f'  {course[0]} {yr}: rating {math.exp(f):.3f} vs {math.exp(med):.3f} '
                  f'for the course ({(math.exp(f - med) - 1) * 100:+.0f}%, n={n})')
    if flagged:
        print(f'\n{len(flagged)} course(s) rest on two seasons that disagree '
              'beyond the noise floor -- kept, but the rating is a blend:')
        for gap, course, ys in sorted(flagged, reverse=True):
            detail = ', '.join(f'{y} {math.exp(f):.3f} (n={n})' for y, f, n in sorted(ys))
            print(f'  {course[0]}: {detail}  [{gap * 100:.1f}% apart]')

    kept = [o for o in obs if (o[2], str(o[1])) not in bad]
    print(f'\n{len(obs) - len(kept):,} observations dropped with them\n')
    return kept


def main():
    obs = clean_observations()
    course_f, counts, stderr = fit(obs)

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
    for (venue, dist), f in course_f.items():
        if counts.get((venue, dist), 0) < MIN_OBS:
            continue
        s = stats[(venue, dist)]
        med = median(s['times'])
        mm, ss = divmod(int(round(med)), 60)
        factor = math.exp(f)
        base = base_venue(venue)
        yrs = sorted(s['years'])
        out.append({
            # `course` stays distance-qualified: it is the unique key the UI
            # selects on, since one venue can host two different races. An
            # older era of a changed course also carries its years.
            'course': course_label(venue, dist) if base == venue
                      else f'{base} ({distance_label(dist)}, {yrs[0]}-{yrs[-1]})',
            'venue': base,
            # the distance the results files call it: a name that tells a
            # venue's courses apart, never an input to the factor
            'distance': distance_label(dist),
            'factor': round(factor, 4),
            'pct': round((factor - 1) * 100, 1),
            'obs': counts[(venue, dist)],
            'athletes': len(s['athletes']),
            'races': len(s['meets']),
            'years': sorted(s['years']),
            'medianTime': f'{mm}:{ss:02d}',
        })
        se = stderr.get((venue, dist))
        if (venue, dist) != REFERENCE_COURSE and (se is None or factor * se > MAX_PUBLISH_SE):
            out.pop()
            continue
        if se is not None:
            # log-scale SE -> the same multiplicative units as the columns
            out[-1]['factorSE'] = round(factor * se, 4)
            out[-1]['pctSE'] = round(factor * se * 100, 1)
    out.sort(key=lambda x: x['factor'])

    ref = course_label(*REFERENCE_COURSE)
    payload = {'generated': date.today().isoformat(),
               'event': 'Cross Country (all distances)',
               'reference': ref,
               'note': 'factor converts a time from one course to another: '
                       'time_B = time_A * factor_B / factor_A. It absorbs '
                       'length and terrain together and is measured from '
                       'runners who raced both, so no course distance enters '
                       f'it. Pinned to {ref}, the Festival of Champions, '
                       'at 1.000',
               'courses': out}
    path = os.path.join(DATA_DIR, 'xc_courses.json.gz')
    with gzip.GzipFile(filename='', mode='wb', fileobj=open(path, 'wb'), mtime=0) as f:
        f.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    print(f'{len(out)} courses written to {path} (anchored on {ref})')
    for c in out[:5] + out[-5:]:
        print(f"  {c['factor']:.3f}  {c['course'][:40]:42s} "
              f"med {c['medianTime']} ({c['athletes']} athletes)")


if __name__ == '__main__':
    main()
