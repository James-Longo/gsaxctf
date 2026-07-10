"""
event_canon.py - single source of truth for event names.

canonical_event(raw_event, gender) -> (gender, canonical_name) or None.

Fixes, in order:
  1. Inner-gender correction: "Girls #15 Men's 400m Hurdles" is a Boys event
     whose section header bled the wrong gender prefix.
  2. Out-of-scope rejection: USATF youth/masters age-division events
     (Bantam, 8&U, "11-12 Division", "40-44", ...) return None.
  3. Core-event extraction: distance + unit + type, relays, field events —
     tolerant of "100M Dash", "4X800 relay", "1600 M Run", all-caps, etc.
  4. Division/meet suffixes are dropped ("Meet A", "JR. DIV", "5th/6th
     grade", "Open Division", "Varsity", heat/page/bleed junk).
  5. Unrecognizable labels return None (they're parse debris).
"""

import re

FIELD_EVENTS = [
    (re.compile(r'high\s*jump|\bhj\b', re.I), 'High Jump'),
    (re.compile(r'long\s*jump|\blj\b', re.I), 'Long Jump'),
    (re.compile(r'triple\s*jump|\btj\b', re.I), 'Triple Jump'),
    (re.compile(r'pole\s*vault|\bpv\b|ole\s*va', re.I), 'Pole Vault'),
    (re.compile(r'shot\s*put|\bshot\b|\bsp\b', re.I), 'Shot Put'),
    (re.compile(r'discus|\bdisc\b|discu\b', re.I), 'Discus'),
    (re.compile(r'javelin|\bjav\b|javel\b', re.I), 'Javelin'),
    (re.compile(r'weight\s*throw', re.I), 'Weight Throw'),
    (re.compile(r'hammer', re.I), 'Hammer Throw'),
]

OUT_OF_SCOPE = re.compile(
    r'bantam|midget|8\s*&\s*u|8 & under|9-10|11-12|13-14|15-16|17-18|19-29|'
    r'\b[3-9]\d-\d\d\b|youth (?:girls|boys)|young (?:men|women)|masters|'
    r'\bkg\b|\blb\b\.?', re.I)

INNER_GENDER = re.compile(r"\b(men|boys|male)'?s?\b|\b(women|girls|female)'?s?\b", re.I)

DIST_RE = re.compile(
    r'\b(10000|5000|3200|3000|1600|1500|1000|800|600|400|300|200|150|110|100|'
    r'80|60|55|50|45|40)\s*(m\b|meters?\b|metre|yard|yd\b|y\b)?', re.I)
RELAY_RE = re.compile(r'(?:4|3)\s*[xX]\s*(\d{2,4}|880|1?\s*mile|8)\b')

TYPE_HURDLES = re.compile(r'hurd|\bhh\b|\bih\b|\blh\b|\bh\b$', re.I)
TYPE_WALK = re.compile(r'race\s*walk|racewalk|\brw\b', re.I)
TYPE_STEEPLE = re.compile(r'steeple', re.I)
WHEELCHAIR = re.compile(r'wheelchair', re.I)
MILE_RE = re.compile(r'\b(1|2|one|two)?\s*miles?\b', re.I)
MEDLEY = re.compile(r'medley', re.I)
PENTA = re.compile(r'pentathlon|heptathlon|decathlon', re.I)

JUNK = re.compile(
    r'page \d|maine\s*today|team\s+mark|team\s+best|per/sc|bowdoin college|'
    r'\bcont|\d/\d{1,2}/\d{2,4}|,', re.I)


XC_TOKEN = re.compile(r'\bcc\b|cross\s*country|\bxc\b', re.I)
K_DIST = re.compile(r'\b([2-9](?:\.\d)?)\s*k\b', re.I)


def canonical_event(raw, gender, season=None):
    """Return (gender, canonical_event_name) or None to drop the row."""
    if not raw:
        return None
    s = str(raw).strip()

    if OUT_OF_SCOPE.search(s):
        return None

    # Cross country: one race per gender; distance from "5k"/"5000m"/miles.
    if season == 'XC' or XC_TOKEN.search(s):
        m = INNER_GENDER.search(s)
        if m:
            gender = 'Boys' if m.group(1) else 'Girls'
        k = K_DIST.search(s)
        if k:
            return gender, f'{k.group(1).upper()}K Cross Country'
        d = DIST_RE.search(s)
        if d and int(d.group(1)) >= 1500:
            meters = int(d.group(1))
            if meters % 1000 == 0:
                return gender, f'{meters // 1000}K Cross Country'
            return gender, f'{meters} Meter Cross Country'
        mi = re.search(r'(\d(?:\.\d+)?)\s*miles?', s, re.I)
        if mi:
            return gender, f'{mi.group(1)} Mile Cross Country'
        return gender, '5K Cross Country'  # the default HS race

    # inner gender overrides the section prefix
    m = INNER_GENDER.search(s)
    if m:
        inner = 'Boys' if m.group(1) else 'Girls'
        if inner != gender:
            gender = inner
        s = INNER_GENDER.sub(' ', s)

    # obvious debris: commas (athlete bleed), dates, header words
    if JUNK.search(s):
        return None

    wheelchair = bool(WHEELCHAIR.search(s))
    penta = PENTA.search(s)
    if penta:
        kind = penta.group(0).title()
        return gender, f'Indoor {kind}' if 'indoor' in s.lower() else kind

    # relays first (so "4x800" isn't read as an 800)
    m = RELAY_RE.search(s.replace(' ', ' '))
    if m or MEDLEY.search(s) or re.search(r'\brelay\b', s, re.I):
        if MEDLEY.search(s):
            name = 'Sprint Medley Relay' if re.search(r'sprint', s, re.I) else \
                   'Distance Medley Relay' if re.search(r'distance', s, re.I) else 'Medley Relay'
            return gender, name
        if re.search(r'shut+le|shut\s*hurd', s, re.I):
            return gender, 'Shuttle Hurdle Relay'
        if m:
            leg = m.group(1).replace(' ', '').lower()
            unit = 'Yard' if re.search(r'y(ar)?d', s, re.I) or leg == '880' else 'Meter'
            if 'mile' in leg or leg == '1':
                return gender, '3x1 Mile Relay' if s.replace(' ', '').lower().startswith('3x') else '4x1 Mile Relay'
            if leg == '8':
                leg = '800'
            return gender, f'4x{leg} {unit} Relay'
        # bare "... Relay" with a distance elsewhere: "1600 Relay" = 4x400
        d = DIST_RE.search(s)
        if d:
            total = int(d.group(1))
            if total in (400, 800, 1600, 3200):
                unit = 'Yard' if re.search(r'y(ar)?d', s, re.I) else 'Meter'
                return gender, f'4x{total // 4} {unit} Relay'
        if re.search(r'one\s*mile', s, re.I):
            return gender, '4x400 Meter Relay'
        return None  # relay without a resolvable distance

    # field events
    for pat, name in FIELD_EVENTS:
        if pat.search(s):
            return gender, name + (' (Wheelchair)' if wheelchair else '')

    # miles
    m = MILE_RE.search(s)
    if m and not DIST_RE.search(s):
        n = (m.group(1) or '1').lower()
        n = {'one': '1', 'two': '2'}.get(n, n)
        return gender, f'{n} Mile Run'

    # distance + type
    m = DIST_RE.search(s)
    if not m:
        return None
    dist = int(m.group(1))
    unit = 'Yard' if (m.group(2) and re.match(r'y', m.group(2), re.I)) or \
                     re.search(r'\byard|\byd\b', s, re.I) else 'Meter'

    if TYPE_WALK.search(s):
        return gender, f'{dist} {unit} Race Walk'
    if TYPE_STEEPLE.search(s):
        return gender, f'{dist} {unit} Steeplechase'
    if TYPE_HURDLES.search(s):
        return gender, f'{dist} {unit} Hurdles'

    suffix = ' (Wheelchair)' if wheelchair else ''
    # dash for sprints, run for 600+ (metric convention used site-wide)
    if unit == 'Meter':
        kind = 'Dash' if dist <= 400 else 'Run'
    else:
        kind = 'Dash' if dist <= 600 else 'Run'
    return gender, f'{dist} {unit} {kind}{suffix}'
