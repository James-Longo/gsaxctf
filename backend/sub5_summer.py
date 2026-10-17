"""sub5 youth and USATF meets for the summer track data.

USATF championships, the 14-and-under and kids' meets, and the old summer
Junior Olympic meets are age-group meets for clubs, not MPA school seasons.
backend/data/meet_scope.json lists them (with why) under "summer"; the sync
writes each to backend/data/summer/<year>/sub5-<meet>.json in the shape
backend/summer_track.py parses athletic.net captures into, and keeps them
out of the school store. An event keeps its standard name ("Long Jump") and
the division goes on it as its age group, the way a grade goes on a row.
"""
import json
import os
import re

from backend import json_store as js
from backend.event_canon import canonical_event
from backend.parser import age_group_of, strip_age_group

BASE = os.path.dirname(os.path.abspath(__file__))
SUMMER = os.path.join(BASE, 'data', 'summer')
SCOPE_PATH = os.path.join(BASE, 'data', 'meet_scope.json')


def load_scope():
    try:
        with open(SCOPE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _value(mark, event, metric=False):
    """Seconds for a time, metres for a field mark (summer_track's units)."""
    m = str(mark or '').strip()
    unit = re.fullmatch(r'(\d+(?:\.\d+)?)\s*m', m, re.I)
    if unit:
        return float(unit.group(1))
    # Junior Olympic meets print field marks in metres with no unit ("3.45")
    if metric and js.is_distance_event(event) and re.fullmatch(r'\d{1,2}\.\d{1,2}', m):
        return float(m)
    v, is_dist = js.parse_mark_value(m, event)
    if v is None:
        return None
    return round(v * 0.0254, 3) if is_dist else v


def _age_from_row(r):
    """USATF files print the athlete's age in the column the parser reads as grade."""
    g = str(r.get('grade') or '').strip()
    return int(g) if g.isdigit() and 5 <= int(g) <= 99 else None


def _group_for_age(age):
    if age is None:
        return None
    if age <= 8:
        return '8 & Under'
    if age <= 18:
        lo = age - (age % 2 == 0)   # 9-10, 11-12, 13-14, 15-16, 17-18
        return f'{lo}-{lo + 1}'
    return None


def _header(year, season, meet_name):
    """(title, venue) from a Hy-Tek file's heading: the line ending in its
    dates ("Kids Meet #1 - 12/2/2018"), then the venue line under it."""
    import glob
    from backend.parser import Sub5ColumnParser
    for src in glob.glob(os.path.join(BASE, 'data', 'sub5_archive', str(year), season, glob.escape(meet_name) + '.*')):
        if src.lower().endswith('.pdf'):
            text = Sub5ColumnParser.pdf_to_text(src) or ''
        else:
            text = re.sub(r'<[^>]*>', ' ', open(src, encoding='utf-8', errors='ignore').read())
        lines = [l.strip() for l in text.replace('&nbsp;', ' ').splitlines() if l.strip()][:12]
        junk = re.compile(r'(?i)^(licensed|hy-?tek|results\b|www\.|event\s+\d|\d{1,2}/\d{1,2}/|[ap]m$)')
        tidy = lambda x: re.sub(r'\s{2,}', ' ', x).strip()
        for i, l in enumerate(lines):
            m = re.match(r'^(.*?\S)\s+-\s+\d{1,2}/\d{1,2}/\d{2,4}', l)
            if m and not junk.match(l):
                above = [x for x in lines[:i] if not junk.match(x)]
                if above:     # "2007 USA Track & Field Junior Olympics" / "SCARBOROUGH - 6/16/2007"
                    return tidy(' '.join(above)), tidy(m.group(1))
                nxt = next((x for x in lines[i + 1:i + 3] if not junk.match(x)), None)
                return tidy(m.group(1)), (tidy(nxt) if nxt else None)
    return None, None


def write_meet(year, season, meet_name, data, date, venue, url, normalize_name):
    """Write one parsed sub5 meet as a summer track doc; returns rows written."""
    events = []
    for ev in data.get('events', []):
        if not isinstance(ev, dict) or 'results' not in ev:
            continue
        gender = {'Women': 'Girls', 'Men': 'Boys'}.get(ev.get('gender'), ev.get('gender') or '')
        label = re.sub(r'^Event\s+\d+\s+', '', strip_age_group(ev.get('event', '')))
        label = re.sub(r'\s+Division\b', '', label)
        canon = canonical_event(label, gender or 'Boys', season=season)
        name = canon[1] if canon else label
        relay = bool(ev.get('is_relay'))
        # metric when no row in the event is written in feet-inches
        metric = not any(re.search(r"\d-\d|'", str(r.get('result') or '')) for r in ev['results'])
        rows = []
        for r in ev['results']:
            mark = str(r.get('result') or '').strip()
            row = dict(place=r.get('place'), club=(r.get('school') or '').strip(), mark=mark,
                       value=_value(mark, name, metric), age=None if relay else _age_from_row(r),
                       aid=None, club_id=None)
            if relay:
                legs = [normalize_name(x) for x in re.split(r'\s*,\s*', r.get('athlete') or '') if x.strip()]
                row.update(name=None, legs=legs if len(legs) > 1 else [])
            else:
                row['name'] = normalize_name(r.get('athlete') or '')
            if r.get('type'):
                row['round'] = r['type']
            rows.append(row)
        # (parsers that keep the division in the label: "Long Jump 8 & Under
        # Division Girls", "Event 6  100 Meter Dash Youth Boys")
        group = ev.get('age_group') or age_group_of(ev.get('event', ''))
        if group:
            events.append(dict(gender=gender, age_group=group, event=name, relay=relay, url=url, results=rows))
            continue
        # a kids' meet that prints no divisions: group the rows by their own age
        by = {}
        for row in rows:
            by.setdefault(_group_for_age(row.get('age')) or 'Open', []).append(row)
        for g, rs in by.items():
            events.append(dict(gender=gender, age_group=g, event=name, relay=relay, url=url, results=rs))
    title, head_venue = _header(year, season, meet_name)
    doc = dict(meet_name=title or meet_name, date=date if date != 'Unknown' else None,
               venue=head_venue or data.get('venue') or venue, series_group=None,
               source=dict(site='sub5', url=url, meet_id=f'{year}_{season}_{meet_name}'),
               events=events)
    if season == 'Indoor':
        doc['season'] = 'Indoor'
    dest = os.path.join(SUMMER, str(year), f'sub5-{meet_name}.json')
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    return sum(len(e['results']) for e in events)
