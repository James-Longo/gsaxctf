"""Bulk MileSplit recovery: every meet the ledger lists as missing, staged, matched, checked.

For each missing listing (backend/meet_ledger.py, status "missing", a Maine
MileSplit meet) of the chosen seasons:

  1. stage   the meet's results through the converter (backend/milesplit.py,
             CANON=1) into backend/data/milesplit_bulk/staged/<year>/<season>/
             -- one request at a time, 3 s apart, pages cached;
  2. match   it to the meets we hold by date (within 2 days) and the set of
             schools: a meet we already have under another name is recorded
             as a "match" on its listing (never fetched again) and dropped;
     A meet whose rows are mostly colleges, clubs or out-of-state schools is
     skipped and its listing marked (MileSplit's own level tag, read by
     `milesplit list`, keeps most of them from being fetched at all);
  3. check   every row complete, schools identified, team scores verified
             where the results print them, date in the season;
  4. accept  a meet that passes into backend/data/parsed_results/, or leave it
             staged with its reasons for a reader (status "review").

Progress lives in backend/data/milesplit_bulk/report.json, keyed by MileSplit
meet id, so a run can stop at any point and resume. Files under
staged/ are the reader's queue (docs/agents/missing-meets.md).

usage: python3 -m backend.milesplit_bulk stage --season XC --years 2025 2024 [--limit N]
       python3 -m backend.milesplit_bulk report [--season XC]
"""
import argparse
import collections
import datetime as dt
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


def school_ids(doc, year, season, cache):
    from backend import school_catalog as sc
    rows = [r for e in doc.get('events', []) for r in e.get('results', [])]
    ids, bad = set(), 0
    for r in rows:
        raw = r.get('school') or ''
        k = (raw, year, season)
        if k not in cache:
            try:
                cache[k] = sc.resolve(raw, year=year, season=season) if raw else None
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
    if season == 'XC':
        from backend.qaqc import xc_verify_parsed
        v = xc_verify_parsed(doc)
        if v and v.get('status') not in ('verified', 'verified_close'):
            why.append(f"team scores {v.get('status')}")
    return why


def held_meets(year, season):
    """[(stem, school ids, day)] for the meets we hold, from the ledger."""
    led = json.load(open(os.path.join(DATA, 'meet_ledger.json')))['meets']
    out = []
    for r in led:
        if r['year'] == year and r['season'] == season and r['status'] == 'have':
            stem = os.path.splitext(os.path.basename(r['files'][0]['path']))[0]
            out.append((stem, set(r['schools']), day(r['date'] or '')))
    return out


def missing_listings(year, season):
    led = json.load(open(os.path.join(DATA, 'meet_ledger.json')))['meets']
    out = []
    for r in led:
        if r['year'] == year and r['season'] == season and r['status'] == 'missing':
            for x in r['listed']:
                if x.get('site') == 'milesplit' and re.match(r'https?://me\.milesplit\.com/meets/\d+', x.get('url') or ''):
                    out.append(dict(id=str(x['id']), url=x['url'], name=x.get('name'), date=r.get('date'), kind=r.get('kind')))
    return out


def maine_share(doc, year, season, cache):
    """Share of rows whose school is a Maine high school, middle school or co-op."""
    rows = [r for e in doc.get('events', []) for r in e.get('results', [])]
    if not rows:
        return 1.0
    ok = sum(1 for r in rows if (cache.get((r.get('school') or '', year, season)) or '').startswith(('me-hs-', 'me-ms-', 'coop-')))
    return ok / len(rows)


def set_listing_kind(year, season, mid, kind, note):
    p = os.path.join(LISTINGS, f'milesplit-{year}-{season}.json')
    doc = json.load(open(p))
    for m in doc['meets']:
        if str(m['id']) == mid:
            m['kind'] = kind
            m['kind_checked'] = True
            m['note'] = note
    json.dump(doc, open(p, 'w'), indent=1)


def set_listing_match(year, season, mid, stem, note):
    p = os.path.join(LISTINGS, f'milesplit-{year}-{season}.json')
    doc = json.load(open(p))
    for m in doc['meets']:
        if str(m['id']) == mid:
            m['match'] = stem
            m['note'] = note
    json.dump(doc, open(p, 'w'), indent=1)


def stage_one(year, season, lst, held, cache):
    slug = re.search(r'/meets/([^/?#]+)', lst['url']).group(1)
    env = dict(os.environ, CANON='1', MS_STAGE=STAGED, PYTHONPATH=ROOT)
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
    ids, unresolved, nrows = school_ids(doc, year, season, cache)
    maine = maine_share(doc, year, season, cache)
    if nrows and maine < MIN_MAINE_SCHOOL:
        os.remove(path)
        set_listing_kind(year, season, lst['id'], 'open',
                         f'auto (milesplit_bulk): {maine:.0%} of rows are Maine high or middle schools (college, club or out-of-state meet)')
        return dict(status='skipped', why=[f'not a Maine school meet ({maine:.0%} Maine school rows)'])
    d = day(doc.get('date')) or day(lst.get('date') or '')
    for stem, hids, hday in held:
        if same_meet(ids, d, hids, hday):
            os.remove(path)
            set_listing_match(year, season, lst['id'], stem, 'auto (milesplit_bulk): same date and schools as the meet we hold')
            return dict(status='duplicate', match=stem)
    why = check(doc, season, year)
    if nrows and unresolved > MAX_UNRESOLVED * nrows:
        why.append(f'{unresolved} rows with an unidentified school')
    rel = os.path.relpath(path, ROOT)
    if why:
        return dict(status='review', why=why, file=rel, rows=nrows)
    dest = os.path.join(DATA, 'parsed_results', str(year), season, os.path.basename(path))
    if os.path.exists(dest):
        return dict(status='review', why=['a file of this name is already in parsed_results'], file=rel, rows=nrows)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(path, dest)
    held.append((os.path.splitext(os.path.basename(dest))[0], ids, d))
    return dict(status='accepted', file=os.path.relpath(dest, ROOT), rows=nrows)


def stage(season, years, limit=None):
    rep = load_report()
    cache = {}
    done = 0
    for year in years:
        held = held_meets(year, season)
        todo = [l for l in missing_listings(year, season) if l['id'] not in rep]
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
    a = ap.parse_args()
    if a.cmd == 'stage':
        summary(stage(a.season, a.years, a.limit), a.season)
    else:
        summary(load_report(), a.season)


if __name__ == '__main__':
    main()
