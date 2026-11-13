"""Bulk MileSplit recovery: every meet the ledger lists as missing, staged, matched, checked.

For each missing listing (backend/meet_ledger.py, status "missing", a Maine
MileSplit meet) of the chosen seasons:

  1. stage   the meet's results through the converter (backend/milesplit.py,
             CANON=1) into backend/data/milesplit_bulk/staged/<year>/<season>/
             -- one request at a time, 3 s apart, pages cached;
  2. match   it to the meets we hold by date (within 2 days) and the set of
             schools, or by its runners at their times (every race 80%+ inside
             one held file, whatever the dates say): a meet we already have
             under another name is recorded as a "match" on its listing (never
             fetched again) and dropped;
     A meet whose rows are mostly colleges, clubs or out-of-state schools is
     skipped and its listing marked (MileSplit's own level tag, read by
     `milesplit list`, keeps most of them from being fetched at all);
  3. check   every row complete, schools identified (resolved with the file's name, as the store
             does), team scores verified where the results print them (or every team's
             places are its runners' printed team points: a tie rule the recount misses),
             times in place order and under 90 minutes, every race's sex known, date in the
             season and the sheet's own date agreeing with the listing; races already held
             (the same runners at their times) are left out of a meet that adds new ones;
  4. accept  a meet that passes into backend/data/parsed_results/, or leave it
             staged with its reasons for a reader (status "review").

Progress lives in backend/data/milesplit_bulk/report.json, keyed by MileSplit
meet id, so a run can stop at any point and resume. Files under
staged/ are the reader's queue (docs/agents/missing-meets.md).

usage: python3 -m backend.milesplit_bulk stage --season XC --years 2025 2024 [--limit N] [--retry review]
       python3 -m backend.milesplit_bulk report [--season XC]
"""
import argparse
import collections
import datetime as dt
import glob
import json
import os
import re
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
DATA = os.path.join(BASE, 'data')
BULK = os.path.join(DATA, 'milesplit_bulk')
STAGED = os.path.join(BULK, 'staged')
REPORT = os.path.join(BULK, 'report.json')
LISTINGS = os.path.join(DATA, 'meet_listings')

MAX_INCOMPLETE = 0.01      # share of rows missing athlete/school/result a meet may carry
MAX_UNRESOLVED = 0.05      # share of rows whose school the catalog cannot identify
MATCH_OVERLAP = 0.6        # school overlap (of the smaller meet) that makes two meets one
MIN_MAINE_SCHOOL = 0.5     # below this share of Maine school rows a meet is college/club/out-of-state: skipped


def load_report():
    return json.load(open(REPORT)) if os.path.exists(REPORT) else {}


def save_report(rep):
    os.makedirs(BULK, exist_ok=True)
    tmp = REPORT + '.tmp'
    json.dump(rep, open(tmp, 'w'), indent=1, sort_keys=True)
    os.replace(tmp, REPORT)


def day(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def school_ids(doc, year, season, cache, fname=None):
    """Catalog ids of the meet's schools and the count of rows the catalog cannot place; `fname`
    (the file's name, as the store resolves it) brings in its per-file rules and middle-school level."""
    from backend import school_catalog as sc
    rows = [r for e in doc.get('events', []) for r in e.get('results', [])]
    ids, bad = set(), 0
    for r in rows:
        raw = r.get('school') or ''
        k = (raw, year, season, fname)
        if k not in cache:
            try:
                cache[k] = sc.resolve(raw, year=year, season=season, meet_name=fname) if raw else None
            except Exception:  # noqa: BLE001
                cache[k] = None
        if cache[k]:
            ids.add(cache[k])
        else:
            bad += 1
    return ids, bad, len(rows)


def same_meet(a_ids, a_day, b_ids, b_day):
    if not a_ids or not b_ids or not a_day or not b_day or abs((a_day - b_day).days) > 2:
        return False
    return len(a_ids & b_ids) / min(len(a_ids), len(b_ids)) >= MATCH_OVERLAP and len(a_ids & b_ids) >= min(2, len(a_ids), len(b_ids))


def _runner_key(r):
    n = re.sub(r'^([^,]+),\s*(.+)$', r'\2 \1', (r.get('athlete') or '').lower())
    t = re.match(r'(?:(\d+):)?(\d+):(\d+)', str(r.get('result') or ''))
    return (' '.join(sorted(re.findall(r'[a-z]+', n))), int(t.group(1) or 0) * 3600 + int(t.group(2)) * 60 + int(t.group(3))) if n and t else None


_HELD_RUNNERS = {}


def _race_keys(e):
    return {k for r in e.get('results', []) for k in [_runner_key(r)] if k}


def _near(doc):
    """[(runners at their seconds +-1, runner count)] per race of a file: MileSplit copies of a sub5 meet
    are often hand-rounded ("16:50.00" for 16:49.98)."""
    out = []
    for e in doc.get('events', []):
        ks = _race_keys(e)
        if ks:
            near = {(n, t + dd) for n, t in ks for dd in (-1, 0, 1)}
            near |= _place_keys(e)
            out.append((near, len(ks)))
    return out


def _place_keys(e):
    """('place', runner, place): the same race printed with wrong times in one copy (a re-keyed MileSplit
    sheet whose times slip a row, or run 5:00 slow) still has its runners at the same places."""
    return {('place', k[0], r.get('place')) for r in e.get('results', []) if r.get('place')
            for k in [_runner_key(r)] if k}


def held_runners(year, season):
    """{stem: [(near set, count)] per race} of every file we hold for the season (cached per run). A file
    holding two or more of the season's other files is a combined re-ranking (the New England qualifier
    list pools the class races; the store drops it): it is never taken for the copy of a race."""
    if (year, season) not in _HELD_RUNNERS:
        out = {}
        for p in glob.glob(os.path.join(DATA, 'parsed_results', str(year), season, '*.json')):
            try:
                d = json.load(open(p))
            except Exception:  # noqa: BLE001
                continue
            rs = _near(d)
            if rs:
                out[os.path.splitext(os.path.basename(p))[0]] = rs
        allk = {k: set().union(*[x for x, _ in v]) for k, v in out.items()}
        size = {k: sum(n for _, n in v) for k, v in out.items()}
        for k in list(out):
            inside = sum(1 for k2 in out if k2 != k and size[k2] >= 20 and size[k2] < size[k]
                         and sum(1 for x in allk[k2] if x in allk[k]) >= 0.6 * len(allk[k2]))
            if inside >= 2:
                del out[k]
        _HELD_RUNNERS[(year, season)] = out
    return _HELD_RUNNERS[(year, season)]


def race_homes(doc, year, season):
    """Per race of the staged meet: the held file holding that race already (80%+ of its runners at their
    times, or 70%+ at their places, in a held race at least 95% its size), else None. Races of fewer than 5 runners: 'small'
    (kept: three middle schoolers within a second of their festival times are not that race, 2026 SMMSAC SR girls 440)."""
    held = held_runners(year, season)
    out = []
    for e in doc.get('events', []):
        rc = _race_keys(e)
        if len(rc) < 5:
            out.append('small')
            continue
        home = None
        for stem, races in held.items():
            for ns, n in races:
                pk = _place_keys(e)
                if n >= 0.95 * len(rc) and (sum(1 for x in rc if x in ns) >= 0.8 * len(rc)
                                            or (len(pk) >= 0.8 * len(rc) and sum(1 for x in pk if x in ns) >= 0.7 * len(pk))):
                    home = stem
                    break
            if home:
                break
        out.append(home)
    return out


def check(doc, season, year):
    """Reasons a staged meet needs a reader (empty = accept)."""
    why = []
    rows = [(e, r) for e in doc.get('events', []) for r in e.get('results', [])]
    if not rows:
        return ['no rows']
    bad = sum(1 for e, r in rows if not r.get('school') or not r.get('result')
              or (not e.get('is_relay') and not r.get('athlete')))
    if bad > MAX_INCOMPLETE * len(rows):
        why.append(f'{bad} incomplete rows')
    d = day(doc.get('date'))
    if not d or not (dt.date(year - (1 if season == 'Indoor' else 0), 8 if season == 'XC' else 1, 1) <= d <= dt.date(year, 12, 31)):
        why.append(f"date {doc.get('date')} outside the season")
    for e in doc.get('events', []):   # times that cannot be a race's: out of place order, or hours long (a spreadsheet's clock cells)
        secs = [_runner_key(dict(r, athlete='x'))[1] for r in e.get('results', []) if r.get('place') and _runner_key(dict(r, athlete='x'))]
        back = sum(1 for a, b in zip(secs, secs[1:]) if b < a - 1)
        if secs and (back > max(2, 0.05 * len(secs)) or max(secs) > 5400):
            why.append(f"{e.get('gender')} {e.get('event')}: times out of place order ({back}) or over 90 minutes")
    if doc.get('date_conflict'):
        ok = date_confirmed_by_runners(doc, year, season)
        if ok:
            note = f" The sheet's title date ({doc['date_conflict']}) is not the meet's: {ok}."
            if note not in (doc.get('notes') or ''):
                doc['notes'] = (doc.get('notes') or '') + note
            doc.pop('date_conflict')
        else:
            why.append(doc['date_conflict'])
    mixed = [e for e in doc.get('events', []) if e.get('gender') not in ('Boys', 'Girls') and e.get('combined_race') is None and e.get('mixed_race') is None
             and not (e.get('is_relay') and e.get('gender') == 'Mixed' and str(e.get('event', '')).startswith('Mixed '))]   # (a co-ed relay the sheet names 'Mixed 4x400', stored as sub5's are)
    if mixed:   # a race the sheet names no sex for, whose first names do not settle it (surnames, initials)
        why.append(f"{sum(len(e.get('results', [])) for e in mixed)} rows in a race of unknown sex")
    if season == 'XC':
        from backend.qaqc import xc_verify_parsed
        v = xc_verify_parsed(doc)
        if v and v.get('status') == 'mismatch' and printed_points_agree(doc):
            note = (' Team scores: every team\'s places in the team block are its runners\' printed team points and add up'
                    ' to its score; a recount from the finish order differs (tied finishers scored by the sheet\'s own rule).')
            if note not in (doc.get('notes') or ''):
                doc['notes'] = (doc.get('notes') or '') + note
        elif v and v.get('status') not in ('verified', 'verified_close'):
            why.append(f"team scores {v.get('status')}")
    return why



_RUNNER_YEARS = {}


def runner_years(season, year):
    """Lowercased athlete name -> the seasons' years they appear in the store (year-4 .. year+1)."""
    key = (season, year)
    if key not in _RUNNER_YEARS:
        import gzip
        idx = collections.defaultdict(set)
        for f in glob.glob(os.path.join(ROOT, 'ui', 'public', 'data', 'teams', '*', f'*_{season}.json.gz')):
            m = re.search(r'/(\d{4})_', f)
            if not m or not year - 4 <= int(m.group(1)) <= year + 1:
                continue
            d = json.load(gzip.open(f))
            for r in (d if isinstance(d, list) else d.get('performances', [])):
                idx[(r.get('athlete_name') or '').lower()].add(int(m.group(1)))
        _RUNNER_YEARS[key] = idx
    return _RUNNER_YEARS[key]


def date_confirmed_by_runners(doc, year, season):
    """A sheet whose title carries another year than MileSplit's listing (a reused meet file's title,
    'GRAY - 5/10/2024' on a 2026 meet) is the listing's year when its runners say so: 10+ of them first
    appear in our data that year (freshmen, sixth graders) and almost none had already left."""
    idx = runner_years(season, year)
    names = {(r.get('athlete') or '').lower() for e in doc.get('events', []) if not e.get('is_relay')
             for r in e.get('results', []) if r.get('athlete')}
    known = [n for n in names if idx.get(n)]
    first = sum(1 for n in known if min(idx[n]) == year)
    gone = sum(1 for n in known if max(idx[n]) < year)
    if known and first >= 10 and gone <= 0.1 * len(known):
        return f'{first} of its {len(known)} runners first appear in our data in {year}, {gone} had left before'
    return None

def printed_points_agree(doc):
    """Every team block that a recount does not reproduce is the sheet's own arithmetic: each official team's
    places are exactly one school's printed team points (the rows' Pts column), its first five add up to its
    score, and the race's printed points run from 1 with no gap (no scoring runner missing)."""
    from backend.qaqc import _xc_verify_block
    blocks = [b for b in doc.get('team_rankings', []) if b.get('kind') == 'xc']
    if not blocks:
        return False
    for b in blocks:
        i = b.get('event_idx')
        if not isinstance(i, int) or not 0 <= i < len(doc.get('events', [])):
            return False
        rows = doc['events'][i]['results']
        v = _xc_verify_block(b, rows)
        if not v or v['status'] != 'mismatch':
            continue
        tp = collections.defaultdict(list)
        for r in rows:
            if r.get('team_place'):
                tp[(r.get('school') or '').strip()].append(r['team_place'])
        cnt = collections.Counter(p for x in tp.values() for p in x)
        if not cnt:
            return False
        gaps = len(set(range(1, max(cnt) + 1)) - set(cnt))
        if gaps > sum(c - 1 for c in cnt.values()):   # a tie shares one place and leaves one unused; any other gap is a lost scorer
            return False
        sets = [sorted(x) for x in tp.values()]
        for t in b.get('teams', []):
            pl = sorted(t.get('places') or [])
            if not pl or pl not in sets or sum(pl[:5]) != t.get('score'):
                return False
    return True


def held_meets(year, season):
    """[(stem, school ids, day, [every file stem])] for the meets we hold, from the ledger."""
    led = json.load(open(os.path.join(DATA, 'meet_ledger.json')))['meets']
    out = []
    for r in led:
        if r['year'] == year and r['season'] == season and r['status'] == 'have':
            stems = [os.path.splitext(os.path.basename(f['path']))[0] for f in r['files']]
            out.append((stems[0], set(r['schools']), day(r['date'] or ''), stems))
    return out


def _names(doc):
    rows = [r for e in doc.get('events', []) for r in e.get('results', [])]
    # (a flat file lists its rows themselves as events)
    rows += [dict(athlete=e['athlete_name'], result=e.get('mark')) for e in doc.get('events', []) if 'results' not in e and e.get('athlete_name')]
    return {k[0] for r in rows for k in [_runner_key(r)] if k}


def _mark_keys(doc):
    """(runner, event, mark) of every row: a track meet is the same meet only with the same marks (weekly
    meets two days apart share schools and runners; a throwers-only meet has no m:ss times to compare)."""
    from backend.event_canon import canonical_event
    from backend.json_store import parse_mark_value
    out = set()
    for e in doc.get('events', []):
        c = canonical_event(e.get('event') or '', e.get('gender'))
        ev = c[1] if c else re.sub(r'[^a-z0-9]+', ' ', (e.get('event') or '').lower()).strip()
        for r in e.get('results', []):
            relay = 'relay' in ev.lower() or e.get('is_relay')
            n = (r.get('school') or '') if relay else (r.get('athlete') or '')
            n = re.sub(r'\b(high school|academy|hs|school)\b', ' ', n.lower()) if relay else \
                re.sub(r'^([^,]+),\s*(.+)$', r'\2 \1', n.lower())
            v, _ = parse_mark_value(str(r.get('result') or ''), ev)
            if n and v:
                out.add((' '.join(sorted(re.findall(r'[a-z]+', n))), ev, round(v, 1)))
    return out


_HELD_MARKS = {}


def held_marks(year, season, stems):
    out = set()
    for st in stems:
        k = (year, season, st)
        if k not in _HELD_MARKS:
            try:
                _HELD_MARKS[k] = _mark_keys(json.load(open(os.path.join(DATA, 'parsed_results', str(year), season, st + '.json'))))
            except Exception:  # noqa: BLE001
                _HELD_MARKS[k] = set()
        out |= _HELD_MARKS[k]
    return out


_SEASON_MARKS = {}


def season_marks(year, season):
    """{(runner, event, mark): stem} over every file held for the season (Indoor: the neighbouring
    winters too -- a December meet sits under either year depending on the source)."""
    if (year, season) not in _SEASON_MARKS:
        out = {}
        years = (year - 1, year, year + 1) if season == 'Indoor' else (year,)
        for y in years:
            for p in glob.glob(os.path.join(DATA, 'parsed_results', str(y), season, '*.json')):
                try:
                    keys = _mark_keys(json.load(open(p)))
                except Exception:  # noqa: BLE001
                    continue
                st = os.path.splitext(os.path.basename(p))[0]
                for k in keys:
                    out.setdefault(k, st)
        _SEASON_MARKS[(year, season)] = out
    return _SEASON_MARKS[(year, season)]


def track_event_homes(doc, year, season):
    """Per event of a staged track meet: the held file with half or more of its marks (the same
    runners -- relays: teams -- at the same marks), else None; events of fewer than 3 marks: the
    file holding any of them, else 'small'."""
    held = season_marks(year, season)
    out = []
    for e in doc.get('events', []):
        ks = _mark_keys(dict(events=[e]))
        if len(ks) < 3:   # (a two-team relay: held if any of its marks is)
            hit = next((held[k] for k in ks if k in held), None)
            out.append(hit or 'small')
            continue
        hits = collections.Counter(held[k] for k in ks if k in held)
        out.append(hits.most_common(1)[0][0] if hits and sum(hits.values()) >= 0.5 * len(ks) else None)
    return out


def held_names(year, season, stems):
    """First and last names of the runners in the held files `stems` (read from disk, cached)."""
    out = set()
    for st in stems:
        k = (year, season, st)
        if k not in _HELD_NAMES:
            p = os.path.join(DATA, 'parsed_results', str(year), season, st + '.json')
            try:
                _HELD_NAMES[k] = _names(json.load(open(p)))
            except Exception:  # noqa: BLE001
                _HELD_NAMES[k] = set()
        out |= _HELD_NAMES[k]
    return out


_HELD_NAMES = {}


def missing_listings(year, season):
    led = json.load(open(os.path.join(DATA, 'meet_ledger.json')))['meets']
    out = []
    for r in led:
        if r['year'] == year and r['season'] == season and r['status'] == 'missing':
            for x in r['listed']:
                if x.get('site') == 'milesplit' and re.match(r'https?://me\.milesplit\.com/meets/\d+', x.get('url') or ''):
                    out.append(dict(id=str(x['id']), url=x['url'], name=x.get('name'), date=r.get('date'), kind=x.get('kind') or r.get('kind')))
    return out


def maine_share(doc, year, season, cache, fname=None):
    """Share of rows whose school is a Maine high school, middle school or co-op."""
    rows = [r for e in doc.get('events', []) for r in e.get('results', [])]
    if not rows:
        return 1.0
    ok = sum(1 for r in rows if (cache.get((r.get('school') or '', year, season, fname)) or '').startswith(('me-hs-', 'me-ms-', 'coop-')))
    return ok / len(rows)


def _update_listing(year, season, mid, **fields):
    # a December Indoor meet is listed in the previous calendar year's file
    for y in (year, year - 1) if season == 'Indoor' else (year,):
        p = os.path.join(LISTINGS, f'milesplit-{y}-{season}.json')
        if not os.path.exists(p):
            continue
        doc = json.load(open(p))
        hits = [m for m in doc['meets'] if str(m['id']) == mid]
        if hits:
            for m in hits:
                m.update(fields)
            json.dump(doc, open(p, 'w'), indent=1)
            return


def set_listing_kind(year, season, mid, kind, note):
    _update_listing(year, season, mid, kind=kind, kind_checked=True, note=note)


def set_listing_match(year, season, mid, stem, note):
    _update_listing(year, season, mid, match=stem, note=note)


def stage_one(year, season, lst, held, cache):
    slug = re.search(r'/meets/([^/?#]+)', lst['url']).group(1)
    env = dict(os.environ, CANON='1', MS_STAGE=STAGED, PYTHONPATH=ROOT)
    if lst.get('kind') == 'ms':
        env['MSMODE'] = '1'   # middle-school meet: never expand a school to its high school's name
    try:
        r = subprocess.run([sys.executable, '-m', 'backend.milesplit', 'write', slug, str(year), season],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return dict(status='error', why=['timeout'])
    m = re.search(r'WROTE (\S+)', r.stdout)
    if not m:
        msg = (r.stdout.strip().splitlines() or [''])[-1] + ' ' + (r.stderr.strip().splitlines() or [''])[-1]
        # NO EVENTS with Pro/no-text files listed: nothing to read; with none, the converter
        # met a layout it does not read yet -- a reader's job
        nt = re.search(r"NO EVENTS (\[.*?\])", r.stdout)
        unread = nt and nt.group(1) not in ('[]',)
        status = 'empty' if unread else 'review' if 'NO EVENTS' in r.stdout else 'error'
        return dict(status=status, why=[('no readable results: ' if unread else 'converter read no events: ') + msg.strip()[:300]])
    path = m.group(1)
    doc = json.load(open(path))
    if lst.get('kind') == 'ms':   # MileSplit's own level tag: the store and catalog file it as middle school
        doc['meet_level'] = 'ms'
        json.dump(doc, open(path, 'w'), indent=1)
    ids, unresolved, nrows = school_ids(doc, year, season, cache, os.path.basename(path))
    maine = maine_share(doc, year, season, cache, os.path.basename(path))
    d = day(doc.get('date')) or day(lst.get('date') or '')
    mine = _names(doc)
    marks = _mark_keys(doc) if season != 'XC' else set()
    for stem, hids, hday, stems in held:
        # (same day, same schools -- and the same runners: a middle-school festival and the
        # conference championship two days later share every school, no runner)
        hn = held_names(year, season, stems) if mine else set()
        # (a held meet with no runners is a team-scores sheet: its results are still missing)
        if season != 'XC':
            same = same_meet(ids, d, hids, hday) and bool(marks) and \
                len(marks & held_marks(year, season, stems)) >= 0.5 * len(marks)
        else:
            same = same_meet(ids, d, hids, hday) and (not mine or (hn and len(mine & hn) >= 0.5 * min(len(mine), len(hn))))
        if same:
            os.remove(path)
            set_listing_match(year, season, lst['id'], stem, 'auto (milesplit_bulk): same date and schools as the meet we hold')
            return dict(status='duplicate', match=stem)
    homes = race_homes(doc, year, season) if season == 'XC' else track_event_homes(doc, year, season)
    real = [h for h in homes if h != 'small']
    if real and all(real):   # every race already held (the same runners at their times), whatever the dates say
        os.remove(path)
        set_listing_match(year, season, lst['id'], real[0], 'auto (milesplit_bulk): the same runners at the same times as the meet we hold')
        return dict(status='duplicate', match=real[0])
    # after the duplicate checks: a meet we already hold is a duplicate even when its sheet's school
    # codes do not resolve (2021 Morse vs Brunswick printed Brunswick as 'Bhs' and was relabelled open)
    if nrows and maine < MIN_MAINE_SCHOOL:
        os.remove(path)
        set_listing_kind(year, season, lst['id'], 'open',
                         f'auto (milesplit_bulk): {maine:.0%} of rows are Maine high or middle schools (college, club or out-of-state meet)')
        return dict(status='skipped', why=[f'not a Maine school meet ({maine:.0%} Maine school rows)'])
    if any(h and h != 'small' for h in homes):   # some races held, some new: store the new ones only
        gone = [(e['gender'], e['event'], h) for e, h in zip(doc['events'], homes) if h and h != 'small']
        doc['events'] = [e for e, h in zip(doc['events'], homes) if not h or h == 'small']
        keep = {(e['gender'], e['event']) for e in doc['events']}
        doc['team_rankings'] = [b for b in doc.get('team_rankings', []) if (b.get('gender'), b.get('event_header')) in keep]
        for b in doc['team_rankings']:
            ix = [i for i, e in enumerate(doc['events']) if (e['gender'], e['event']) == (b.get('gender'), b.get('event_header'))]
            if len(ix) == 1:
                b['event_idx'] = ix[0]
            else:
                b.pop('event_idx', None)
        doc['notes'] = (doc.get('notes') or '') + ' Races already held from another source left out (not stored twice): %s.' % '; '.join('%s %s (%s)' % x for x in gone)
        json.dump(doc, open(path, 'w'), indent=1)
        ids, unresolved, nrows = school_ids(doc, year, season, cache, os.path.basename(path))
    why = check(doc, season, year)
    json.dump(doc, open(path, 'w'), indent=1)   # (check may add a note on the team scores)
    if nrows and unresolved > MAX_UNRESOLVED * nrows:
        why.append(f'{unresolved} rows with an unidentified school')
    rel = os.path.relpath(path, ROOT)
    if why:
        return dict(status='review', why=why, file=rel, rows=nrows)
    dest = os.path.join(DATA, 'parsed_results', str(year), season, os.path.basename(path))
    if os.path.exists(dest):   # another meet of the same name (a school's second home meet): the date tells them apart
        try:
            other = json.load(open(dest)).get('source', {}).get('url')
        except Exception:  # noqa: BLE001
            other = None
        if other != doc.get('source', {}).get('url') and doc.get('date'):
            dest = dest[:-5] + '-%s.json' % doc['date']
        if os.path.exists(dest):
            return dict(status='review', why=['a file of this name is already in parsed_results'], file=rel, rows=nrows)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(path, dest)
    held.append((os.path.splitext(os.path.basename(dest))[0], ids, d, [os.path.splitext(os.path.basename(dest))[0]]))
    held_runners(year, season)[os.path.splitext(os.path.basename(dest))[0]] = _near(doc)
    if (year, season) in _SEASON_MARKS:
        for k in _mark_keys(doc):
            _SEASON_MARKS[(year, season)].setdefault(k, os.path.splitext(os.path.basename(dest))[0])
    return dict(status='accepted', file=os.path.relpath(dest, ROOT), rows=nrows)


def stage(season, years, limit=None, retry=()):
    """Stage the missing listings of `years`; `retry` statuses (e.g. 'review') are staged again,
    from the cached pages, after a converter fix."""
    rep = load_report()
    cache = {}
    done = 0
    for year in years:
        held = held_meets(year, season)
        todo = [l for l in missing_listings(year, season) if l['id'] not in rep or rep[l['id']].get('status') in retry]
        print(f'{year} {season}: {len(todo)} listings to stage', flush=True)
        for lst in todo:
            if limit is not None and done >= limit:
                return rep
            res = stage_one(year, season, lst, held, cache)
            res.update(year=year, season=season, name=lst['name'], url=lst['url'],
                       at=dt.datetime.now().isoformat(timespec='seconds'))
            rep[lst['id']] = res
            save_report(rep)
            done += 1
            print(f"  {res['status']:9} {lst['name'][:60]} {res.get('match') or '; '.join(res.get('why', []))[:80]}", flush=True)
    return rep


def summary(rep, season=None):
    c = collections.defaultdict(collections.Counter)
    for r in rep.values():
        if season and r['season'] != season:
            continue
        c[(r['year'], r['season'])][r['status']] += 1
    for k in sorted(c):
        print(k[0], k[1], dict(c[k]))
    print('all:', dict(sum(c.values(), collections.Counter())))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['stage', 'report'])
    ap.add_argument('--season', default='XC')
    ap.add_argument('--years', nargs='*', type=int, default=[])
    ap.add_argument('--limit', type=int)
    ap.add_argument('--retry', nargs='*', default=[], help="statuses to stage again, e.g. review")
    a = ap.parse_args()
    if a.cmd == 'stage':
        summary(stage(a.season, a.years or list(range(2026, 2002, -1)), a.limit, tuple(a.retry)), a.season)
    else:
        summary(load_report(), a.season)


if __name__ == '__main__':
    main()
