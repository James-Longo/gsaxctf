"""Meet ledger: every meet we know exists, and whether we have it.

The ledger answers "which meets exist, and do we have each one?" across all
sources. It is derived, never edited by hand:

  have      every results file in backend/data/parsed_results (sub5 parses,
            Five K Sport, New England and MileSplit transcriptions); the
            boys' and girls' files of one meet are one meet
  listings  backend/data/meet_listings/*.json: meets some site says exist
            (a MileSplit season list, a sub5 index page, the Internet
            Archive's sub5 captures), written by agents or scripts:
            {"site": "milesplit", "year": 2015, "season": "Outdoor",
             "listed": "<list page url>", "meets": [{"id": "205897",
             "name": "...", "date": "2015-05-22", "url": "...",
             "kind": "hs|ms|youth|college|open",
             "match": "<stem of the stored file, when a reader decides they are one meet>"}]}
  not found backend/data/missing_meets_not_found.txt and
            ne_meets_not_found.txt ("<year> <season> <meet>: <where>")

A listed meet is matched to a meet we have by URL, else by date (within a
day) and name. Statuses: have, missing (listed, high school or middle
school, not matched), not_found (looked for, nowhere to be had), skipped
(listed but not a school meet).

Each file also carries a parse confidence (certain / changed / high /
unverified / suspect; see "parse confidence" below).

usage: python3 -m backend.meet_ledger build     write backend/data/meet_ledger.json
       python3 -m backend.meet_ledger report [--season 2014/Outdoor]
       python3 -m backend.meet_ledger missing <year> <season>
       python3 -m backend.meet_ledger review [N] [--season ...]   files to check, worst first
       python3 -m backend.meet_ledger signoff --auto
       python3 -m backend.meet_ledger signoff <path>... --by <who> --evidence <how checked>
"""
import argparse
import collections
import datetime as dt
import glob
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
PARSED = os.path.join(DATA, 'parsed_results')
LISTINGS = os.path.join(DATA, 'meet_listings')
LEDGER = os.path.join(DATA, 'meet_ledger.json')
NOT_FOUND = [os.path.join(DATA, 'missing_meets_not_found.txt'), os.path.join(DATA, 'ne_meets_not_found.txt')]
SEASONS = ('Indoor', 'Outdoor', 'XC')


def source_of(stem, doc):
    p = doc.get('parser') or ''
    if p == 'milesplit-manual':
        return 'milesplit'
    if p == 'ne-manual':
        return 'new-england'
    if stem.startswith('fiveks-'):
        return 'fiveksport'
    return 'sub5'


def urls_of(doc):
    u = (doc.get('source') or {}).get('url') if isinstance(doc.get('source'), dict) else None
    return [x for x in (u if isinstance(u, list) else [u]) if x]


def words(s):
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s or '')
    return {w for w in re.findall(r'[a-z]{3,}', s.lower())} - {
        'boys', 'girls', 'results', 'result', 'meet', 'track', 'field', 'outdoor', 'indoor', 'high',
        'school', 'the', 'and', 'final', 'finals', 'revised', 'updated', 'corrected', 'htm', 'html',
        'txt', 'pdf', 'json', 'varsity', 'female', 'male', 'men', 'women'}


def mile_meet_id(url):
    m = re.search(r'milesplit\.com/meets/(\d+)', url or '')
    return m.group(1) if m else None


def schools_of(doc, year, season, resolve, cache):
    """(catalog ids of the schools in a file, rows whose school doesn't resolve)."""
    out = set()
    per_row = [r.get('school') for e in doc.get('events', []) for r in e.get('results', [])]
    raws = set(per_row)
    raws |= {t.get('team') for x in doc.get('team_rankings', []) if isinstance(x, dict) for t in x.get('teams', []) if isinstance(t, dict)}
    for raw in raws:
        if not raw:
            continue
        k = (raw, year, season)
        if k not in cache:
            try:
                cache[k] = resolve(raw, year=year, season=season)
            except Exception:
                cache[k] = None
        if cache[k]:
            out.add(cache[k])
    bad = sum(1 for raw in per_row if not raw or not cache.get((raw, year, season)))
    return out, bad


# ---- parse confidence -------------------------------------------------------
# Each file gets a confidence from the evidence we hold, and a file we are sure
# of is signed off (backend/data/parse_signoff.json) against fingerprints of
# its source and of our parse. A signed-off file is never revisited while both
# fingerprints hold; if either changes (a re-parse moved its rows, sub5
# replaced the file) the sign-off lapses and the file shows as `changed`.
#
#   certain     signed off and unchanged
#   changed     signed off, but the source or the parse is no longer the same
#   high        score check within rounding, a reader's transcription, a
#               hand transcription from another site, or a clean audit;
#               no warning signs
#   unverified  nothing confirms or questions it (most files with no team
#               scores to check against)
#   not-results / unrecoverable   a reader judged the file has nothing to
#               ingest (backend/data/unparsed_audit.json)
#   suspect     a warning sign: no rows, team scores that don't add up,
#               schools we can't identify, or results flagged as implausible
#
# Auto sign-off (`signoff --auto`): team scores verified exactly, every school
# identified, no flags. Everything else is signed off by a reader after
# checking the file against its source (`signoff <path> --by ... --evidence`).
SIGNOFF = os.path.join(DATA, 'parse_signoff.json')
SUB5 = os.path.join(DATA, 'sub5_archive')
TRANSCRIBED = os.path.join(DATA, 'transcribed')
_ctx = {}


def _sha(b):
    import hashlib
    return hashlib.sha256(b).hexdigest()[:16]


def parse_sha(doc):
    return _sha(json.dumps([doc.get('events'), doc.get('team_rankings')], sort_keys=True).encode())


def source_path(year, season, stem):
    hits = [p for p in glob.glob(os.path.join(SUB5, str(year), season, glob.escape(stem) + '.*'))
            if os.path.splitext(os.path.basename(p))[0] == stem]
    return hits[0] if hits else None


def source_sha(year, season, stem, path):
    src = source_path(year, season, stem)
    return _sha(open(src, 'rb').read()) if src else _sha(open(os.path.join(os.path.dirname(BASE), path), 'rb').read())


def _context():
    if not _ctx:
        _ctx['verify'] = json.load(open(os.path.join(DATA, 'meet_verification.json'))) \
            if os.path.exists(os.path.join(DATA, 'meet_verification.json')) else {}
        flags = collections.Counter()
        fp = os.path.join(DATA, 'qaqc_flags.json')
        for x in (json.load(open(fp)) if os.path.exists(fp) else []):
            flags[(str(x.get('year')), x.get('season'), x.get('meet'))] += 1
        _ctx['flags'] = flags
        audits = {}
        for d in ('track_audit', 'track_audit_r2'):
            for f in glob.glob(os.path.join(DATA, d, '*', 'findings.json')):
                try:
                    a = json.load(open(f))
                    audits[a.get('key')] = a.get('verdict')
                except Exception:
                    pass
        _ctx['audits'] = audits
        _ctx['signoff'] = json.load(open(SIGNOFF)) if os.path.exists(SIGNOFF) else {}
        ua = os.path.join(DATA, 'unparsed_audit.json')
        _ctx['unparsed'] = {os.path.splitext(k)[0]: v.get('status') for k, v in
                            (json.load(open(ua)).items() if os.path.exists(ua) else [])}
    return _ctx


def confidence(path, year, season, stem, doc, rows, unresolved):
    c = _context()
    key = f'{year}_{season}_{stem}'
    score = (c['verify'].get(key) or {}).get('status')
    flags = c['flags'][(str(year), season, stem)]
    transcribed = os.path.exists(os.path.join(TRANSCRIBED, str(year), season, stem + '.json'))
    manual = (doc.get('parser') or '').endswith('-manual')
    audit = c['audits'].get(key)
    psha, ssha = parse_sha(doc), source_sha(year, season, stem, path)
    out = dict(score=score, flags=flags, unresolved=unresolved, parse_sha=psha, source_sha=ssha)
    if transcribed:
        out['transcribed'] = True
    so = c['signoff'].get(path)
    warn = []
    unparsed = c['unparsed'].get(f'{year}/{season}/{stem}')
    if rows == 0 and unparsed in ('not-results', 'unrecoverable'):
        return dict(out, confidence=unparsed)   # judged by a reader: nothing to ingest
    if rows == 0 and not doc.get('team_rankings'):
        warn.append('no rows')
    if score == 'mismatch':
        warn.append('team scores do not add up')
    if rows and unresolved > max(2, 0.05 * rows):
        warn.append(f'{unresolved} rows with an unidentified school')
    if flags >= 3:
        warn.append(f'{flags} results flagged as implausible')
    if so and so.get('parse_sha') == psha and so.get('source_sha') == ssha:
        out['confidence'] = 'certain'
        out['signed_off'] = so.get('by')
    elif so:
        out['confidence'] = 'changed'
        out['was'] = so.get('by')
    elif warn:
        out['confidence'] = 'suspect'
    elif score == 'verified_close' or score == 'verified' or transcribed or manual or audit == 'clean':
        out['confidence'] = 'high'
    else:
        out['confidence'] = 'unverified'
    if warn:
        out['warnings'] = warn
    return out


def signoff(paths, by, evidence, auto=False):
    """Record files as certain against their current fingerprints."""
    so = json.load(open(SIGNOFF)) if os.path.exists(SIGNOFF) else {}
    led = json.load(open(LEDGER))['meets']
    n = 0
    today = dt.date.today().isoformat()
    for r in led:
        for f in r['files']:
            pick = (auto and f.get('score') == 'verified' and not f.get('warnings') and not f.get('flags')
                    and f.get('unresolved') == 0 and f.get('confidence') != 'changed') or f['path'] in paths
            if not pick or (so.get(f['path']) and f.get('confidence') == 'certain'):
                continue
            so[f['path']] = dict(parse_sha=f['parse_sha'], source_sha=f['source_sha'], date=today,
                                 by='auto: team scores verified exactly, all schools identified, no flags' if auto and f['path'] not in paths else by,
                                 evidence=evidence)
            n += 1
    json.dump(dict(sorted(so.items())), open(SIGNOFF, 'w'), indent=1)
    return n


def load_have():
    from backend import school_catalog
    cache = {}
    files = []
    for path in sorted(glob.glob(os.path.join(PARSED, '*', '*', '*.json'))):
        year, season = path.split(os.sep)[-3:-1]
        if season not in SEASONS:
            continue
        try:
            doc = json.load(open(path))
        except Exception:
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        rows = sum(len(e.get('results', [])) for e in doc.get('events', []))
        schools, unresolved = schools_of(doc, int(year), season, school_catalog.resolve, cache)
        rel = os.path.relpath(path, os.path.dirname(BASE))
        files.append(dict(year=int(year), season=season, stem=stem, date=doc.get('date') or None,
                          name=doc.get('meet_name') or '', source=source_of(stem, doc), urls=urls_of(doc),
                          rows=rows, schools=schools, path=rel,
                          check=confidence(rel, int(year), season, stem, doc, rows, unresolved)))
    # one meet = files of one season on one date whose schools overlap (boys + girls files)
    meets = []
    by_day = collections.defaultdict(list)
    for f in files:
        key = (f['year'], f['season'], f['date'] if f['date'] and f['date'] != 'Unknown' else 'nodate:' + f['stem'])
        group = None
        for m in by_day[key]:
            a, b = m['schools'], f['schools']
            if a and b and len(a & b) / min(len(a), len(b)) >= 0.6:
                group = m
                break
        if group is None:
            group = dict(year=f['year'], season=f['season'], date=f['date'], name=f['name'] or f['stem'],
                         schools=set(), files=[], urls=[])
            by_day[key].append(group)
            meets.append(group)
        group['schools'] |= f['schools']
        group['files'].append(dict(path=f['path'], source=f['source'], rows=f['rows'], **f['check']))
        group['urls'] += f['urls']
    return meets


def load_listings():
    out = []
    for path in sorted(glob.glob(os.path.join(LISTINGS, '*.json'))):
        doc = json.load(open(path))
        for m in doc.get('meets', []):
            out.append(dict(m, site=doc.get('site'), year=int(m.get('year') or doc['year']),
                             season=m.get('season') or doc['season'], listed=doc.get('listed'),
                             listing_file=os.path.basename(path)))
    return out


def load_not_found():
    out = []
    for path in NOT_FOUND:
        if not os.path.exists(path):
            continue
        for line in open(path):
            m = re.match(r'\s*(\d{4})\s+(indoor|outdoor|xc)\b\s*(.*)', line, re.I)
            if m:
                season = {'indoor': 'Indoor', 'outdoor': 'Outdoor', 'xc': 'XC'}[m.group(2).lower()]
                out.append(dict(year=int(m.group(1)), season=season, text=m.group(3).strip()))
    return out


def near(d1, d2, days=1):
    try:
        a, b = dt.date.fromisoformat(d1[:10]), dt.date.fromisoformat(d2[:10])
    except (TypeError, ValueError):
        return False
    return abs((a - b).days) <= days


def match(listing, meets, by_url, by_stem):
    mid = mile_meet_id(listing.get('url'))
    if mid and mid in by_url:
        return by_url[mid]
    if listing.get('match'):   # a reader's verdict: this listing is the meet stored as <stem>
        return by_stem.get(listing['match'])
    cands = [m for m in meets if m['year'] == listing['year'] and m['season'] == listing['season']
             and near(m['date'], listing.get('date'))]
    if not cands:
        return None
    lw = words(listing.get('name'))
    def score(m):
        mw = words(m['name']) | {w for f in m['files'] for w in words(os.path.basename(f['path']))}
        glued = ' '.join(os.path.basename(f['path']).lower() for f in m['files'])
        return len(lw & mw) + sum(1 for w in lw - mw if len(w) >= 4 and w in glued)
    best = max(cands, key=score)
    same_day = [m for m in cands if near(m['date'], listing.get('date'), 0)]
    if score(best) > 0:
        return best
    if len(same_day) == 1 and len(cands) == 1:
        return best   # the only meet that day: likely the same one under another name
    return None


def build():
    meets = load_have()
    by_url = {}
    by_stem = {os.path.splitext(os.path.basename(f['path']))[0]: m for m in meets for f in m['files']}
    for m in meets:
        for u in m['urls']:
            mid = mile_meet_id(u)
            if mid:
                by_url[mid] = m
    rows = []
    for m in meets:
        rows.append(dict(year=m['year'], season=m['season'], date=m['date'], name=m['name'], status='have',
                         schools=sorted(m['schools']), files=m['files'], listed=[]))
    index = {id(m): r for m, r in zip(meets, rows)}
    for l in load_listings():
        hit = match(l, meets, by_url, by_stem)
        ref = dict(site=l['site'], id=l.get('id'), url=l.get('url'), name=l.get('name'))
        if hit is not None:
            index[id(hit)]['listed'].append(ref)
            continue
        kind = l.get('kind', 'hs')
        if l.get('site') == 'milesplit' and l.get('url') and not re.match(r'https?://me\.milesplit', l['url']) and kind == 'hs':
            kind = 'out-of-state'   # a meet on another state's MileSplit: Maine rows only, low priority
        rows.append(dict(year=l['year'], season=l['season'], date=l.get('date'), name=l.get('name'),
                         status='missing' if kind in ('hs', 'ms') else 'skipped', kind=kind,
                         schools=[], files=[], listed=[ref]))
    for nf in load_not_found():
        rows.append(dict(year=nf['year'], season=nf['season'], date=None, name=nf['text'], status='not_found',
                         schools=[], files=[], listed=[]))
    # a missing listing that a not-found line names (by MileSplit id) is not_found
    nf_ids = {i for nf in load_not_found() for i in re.findall(r'\b(\d{6})\b', nf['text'])}
    for r in rows:
        if r['status'] == 'missing' and any(x.get('id') in nf_ids for x in r['listed']):
            r['status'] = 'not_found'
    rows.sort(key=lambda r: (r['year'], SEASONS.index(r['season']), r['date'] or '', r['name'] or ''))
    out = dict(_meta=dict(built=dt.datetime.now().isoformat(timespec='seconds'),
                          note='derived by backend/meet_ledger.py; do not edit'), meets=rows)
    json.dump(out, open(LEDGER, 'w'), indent=1)
    return rows


def report(rows, season=None):
    agg = collections.defaultdict(collections.Counter)
    for r in rows:
        key = f"{r['year']}/{r['season']}"
        if season and key != season:
            continue
        agg[key][r['status']] += 1
        agg[key]['files'] += len(r['files'])
        if r['status'] == 'have':
            agg[key]['listed_have'] += bool(r['listed'])
            for f in r['files']:
                agg[key]['src:' + f['source']] += 1
                agg[key]['c:' + f.get('confidence', '?')] += 1
    print(f"{'season':13} {'meets':>6} {'files':>6} {'missing':>8} {'notfound':>8} {'certain':>8} {'high':>5} {'unver':>6} {'suspect':>8} {'changed':>8}  sources")
    for key in sorted(agg, key=lambda k: (k.split('/')[0], SEASONS.index(k.split('/')[1]))):
        c = agg[key]
        src = ' '.join(f"{k[4:]}={v}" for k, v in sorted(c.items()) if k.startswith('src:'))
        print(f"{key:13} {c['have']:6} {c['files']:6} {c['missing']:8} {c['not_found']:8} {c['c:certain']:8} {c['c:high']:5} {c['c:unverified']:6} {c['c:suspect']:8} {c['c:changed']:8}  {src}")
    tot = collections.Counter()
    for c in agg.values():
        tot.update({k: v for k, v in c.items() if k.startswith('c:')})
    print('all files:', ', '.join(f"{k[2:]} {v}" for k, v in tot.most_common()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['build', 'report', 'missing', 'review', 'signoff'])
    ap.add_argument('args', nargs='*')
    ap.add_argument('--season')
    ap.add_argument('--auto', action='store_true')
    ap.add_argument('--by', default='')
    ap.add_argument('--evidence', default='')
    a = ap.parse_args()
    if a.cmd == 'build':
        rows = build()
        report(rows, a.season)
        return
    if a.cmd == 'signoff':
        if not a.auto and not (a.args and a.by and a.evidence):
            sys.exit('signoff <path>... --by <who> --evidence <how it was checked>, or signoff --auto')
        n = signoff(set(a.args), a.by, a.evidence, auto=a.auto)
        print(f'signed off {n} files; rebuilding')
        _ctx.clear()
        report(build(), a.season)
        return
    rows = json.load(open(LEDGER))['meets']
    if a.cmd == 'review':
        # files to look at, worst first: changed sign-offs, suspect, unverified
        order = {'changed': 0, 'suspect': 1, 'unverified': 2}
        todo = [(order[f['confidence']], r['year'], r['season'], f) for r in rows for f in r['files']
                if f.get('confidence') in order and (not a.season or f"{r['year']}/{r['season']}" == a.season)]
        for _, y, s_, f in sorted(todo, key=lambda t: (t[0], t[1], t[2], t[3]['path']))[:int(a.args[0]) if a.args else 50]:
            print(f['confidence'], f['path'], f.get('score') or '-', '; '.join(f.get('warnings', [])) or f.get('was', ''))
        return
    if a.cmd == 'report':
        report(rows, a.season)
    else:
        year, season = int(a.args[0]), a.args[1]
        for r in rows:
            if r['year'] == year and r['season'] == season and r['status'] in ('missing', 'not_found'):
                print(r['status'], r['date'], r['name'], ' '.join(x.get('url') or '' for x in r['listed']))


if __name__ == '__main__':
    main()
