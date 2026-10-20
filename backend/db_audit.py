"""Database audit: every result file not yet certain, newest season first, read by an agent against its source.

The parsers do the first read; this is the second. A file is `certain` when it is signed off
(backend/meet_ledger.py): team scores verified exactly, every school identified, nothing flagged,
or a reader confirmed the parse against its source. Everything else is audited here, most recent
year first, so 2026 is made perfect before 2025, and so on back (docs/agents/database-audit.md).

    python3 -m backend.db_audit progress              certain / audited / left, per year
    python3 -m backend.db_audit fixes                 'fixed' verdicts whose fix hasn't reached the parse yet
    python3 -m backend.db_audit queue [--n 20] [--year 2026]
                                                       next files to audit, newest first
    python3 -m backend.db_audit show <path>            the source text beside the parse
    python3 -m backend.db_audit record <path> --verdict confirmed|fixed|source-error|james \\
           --by "<who>" --notes "<evidence>"

Verdicts (backend/data/audit_log.json, keyed by file, with the parse and source fingerprints):
  confirmed     the parse matches its source row for row: signed off as certain
  source-error  the parse matches its source, and the source itself is wrong (the notes say
                where): signed off as certain, the error recorded
  fixed         the parse was wrong and a fix was made (a transcription override or a parser
                fix): the file comes back to the queue once its parse has changed, to confirm
  james         needs James's call (named in the notes): left out of the queue
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
DATA = os.path.join(BASE, 'data')
LEDGER = os.path.join(DATA, 'meet_ledger.json')
LOG = os.path.join(DATA, 'audit_log.json')
SUB5 = os.path.join(DATA, 'sub5_archive')
MSCACHE = os.path.join(DATA, 'milesplit_cache')
TRANSCRIBED = os.path.join(DATA, 'transcribed')

ORDER = {'changed': 0, 'suspect': 1, 'unverified': 2, 'high': 3}   # within a year: worst first


def load_log():
    return json.load(open(LOG)) if os.path.exists(LOG) else {}


def files():
    for r in json.load(open(LEDGER))['meets']:
        for f in r['files']:
            yield r, f


def pending(log, year=None):
    out = []
    for r, f in files():
        c = f.get('confidence')
        if c not in ORDER or (year and r['year'] != year):
            continue
        e = log.get(f['path'])
        if e and (e['verdict'] == 'james' or (e['verdict'] == 'fixed' and e['parse_sha'] == f['parse_sha'])):
            continue   # waiting on James, or on the fix to reach the parse
        out.append((-r['year'], ORDER[c], r['season'], f['path'], r, f))
    return [(r, f) for *_, r, f in sorted(out, key=lambda t: t[:4])]


def source_text(path, doc):
    """The text a reader checks the parse against."""
    year, season, stem = path.split('/')[-3], path.split('/')[-2], os.path.splitext(os.path.basename(path))[0]
    t = os.path.join(TRANSCRIBED, year, season, stem + '.json')
    note = f'(a transcription override exists: {os.path.relpath(t, ROOT)})\n' if os.path.exists(t) else ''
    if stem.startswith('ms-'):
        urls = (doc.get('source') or {}).get('url') or []
        out = []
        for u in urls if isinstance(urls, list) else [urls]:
            m = re.search(r'/meets/([^/]+)/results/(\d+)', u or '')
            p = m and os.path.join(MSCACHE, f'{m.group(1)}-{m.group(2)}.html')
            if not p or not os.path.exists(p):
                out.append(f'[not cached: {u}]')
                continue
            raw = open(p, errors='replace').read()
            pre = re.findall(r'<pre[^>]*>(.*?)</pre>', raw, re.S)
            if pre:
                out.append(html.unescape(re.sub(r'<[^>]+>', '', pre[0])))
            else:
                rows = re.findall(r'<tr[^>]*>(.*?)</tr>', raw, re.S)
                out.append('\n'.join('\t'.join(html.unescape(re.sub(r'<[^>]+>', '', c)).strip()
                                               for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r_, re.S)) for r_ in rows))
            out[-1] = f'== {u}\n' + out[-1]
        return note + '\n'.join(out)
    hits = [p for p in os.listdir(os.path.join(SUB5, year, season)) if os.path.splitext(p)[0] == stem] \
        if os.path.isdir(os.path.join(SUB5, year, season)) else []
    if not hits:
        return note + '[no archived source file found]'
    src = os.path.join(SUB5, year, season, hits[0])
    ext = os.path.splitext(src)[1].lower()
    if ext == '.pdf':
        r = subprocess.run(['pdftotext', '-layout', src, '-'], capture_output=True, text=True, errors='replace')
        return note + f'== {os.path.relpath(src, ROOT)}\n' + r.stdout
    raw = open(src, 'rb').read().decode('utf-8', errors='replace')
    if ext in ('.htm', '.html'):
        raw = re.sub(r'(?is)<(script|style).*?</\1>', '', raw)
        raw = re.sub(r'(?i)<br\s*/?>|</(p|tr|div|h\d|li)>', '\n', raw)
        raw = re.sub(r'(?i)</t[dh]>', '\t', raw)
        raw = html.unescape(re.sub(r'<[^>]+>', '', raw))
    return note + f'== {os.path.relpath(src, ROOT)}\n' + raw


def show(path):
    from backend import school_catalog as sc
    path = os.path.relpath(os.path.abspath(path), ROOT)
    doc = json.load(open(os.path.join(ROOT, path)))
    year, season = path.split('/')[-3], path.split('/')[-2]
    led = next(((r, f) for r, f in files() if f['path'] == path), (None, {}))[1]
    print(f'# {path}  confidence={led.get("confidence")} score={led.get("score")} '
          f'warnings={led.get("warnings")} unresolved={led.get("unresolved")} flags={led.get("flags")}')
    print(f'# meet: {doc.get("meet_name")}  date: {doc.get("date")}  parser: {doc.get("parser")}')
    print('\n######## SOURCE ########')
    print(source_text(path, doc).rstrip())
    print('\n######## PARSE ########')
    for i, e in enumerate(doc.get('events', [])):
        print(f'-- [{i}] {e.get("gender")} {e.get("event")} ({len(e.get("results", []))} rows)')
        for r in e.get('results', []):
            raw = r.get('school') or ''
            sid = sc.resolve(raw, year=year, season=season, gender=e.get('gender'), meet_name=os.path.basename(path), grade=r.get('grade')) if raw else None
            who = r.get('athlete') or ', '.join(r.get('athletes') or [])
            tp = f' tp={r["team_place"]}' if r.get('team_place') is not None else ''
            print(f'  {r.get("place")!s:>4} | {who} | {raw} -> {sid or "?"} | gr {r.get("grade") or "-"} | {r.get("result")}{tp}')
    for b in doc.get('team_rankings', []):
        print(f'-- team scores {b.get("gender")} {b.get("event_header")}: ' +
              '; '.join(f'{t.get("rank")}. {t.get("team")} {t.get("score")}' for t in b.get('teams', [])))


def record(path, verdict, by, notes):
    from backend import meet_ledger as ml
    path = os.path.relpath(os.path.abspath(path), ROOT)
    f = next((f for r, f in files() if f['path'] == path), None)
    if f is None:
        sys.exit(f'{path}: not in the ledger (run python3 -m backend.meet_ledger build)')
    log = load_log()
    log[path] = dict(verdict=verdict, by=by, notes=notes, date=dt.date.today().isoformat(),
                     parse_sha=f['parse_sha'], source_sha=f['source_sha'])
    json.dump(dict(sorted(log.items())), open(LOG, 'w'), indent=1)
    if verdict in ('confirmed', 'source-error'):
        ml.signoff([path], by=f'{by} (audit: {verdict})', evidence=notes)
    print(path, verdict)


def progress():
    import collections
    log = load_log()
    by = collections.defaultdict(collections.Counter)
    for r, f in files():
        c = f.get('confidence')
        if c in ('not-results', 'unrecoverable'):
            continue
        k = 'certain' if c == 'certain' else ('james' if log.get(f['path'], {}).get('verdict') == 'james' else 'left')
        by[r['year']][k] += 1
    print('year  certain  left  james')
    for y in sorted(by, reverse=True):
        print(f'{y}  {by[y]["certain"]:7}  {by[y]["left"]:4}  {by[y]["james"]:5}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['progress', 'queue', 'show', 'record', 'fixes'])
    ap.add_argument('path', nargs='?')
    ap.add_argument('--n', type=int, default=20)
    ap.add_argument('--year', type=int)
    ap.add_argument('--verdict', choices=['confirmed', 'fixed', 'source-error', 'james'])
    ap.add_argument('--by', default='agent audit')
    ap.add_argument('--notes', default='')
    a = ap.parse_args()
    if a.cmd == 'progress':
        progress()
    elif a.cmd == 'queue':
        for r, f in pending(load_log(), a.year)[:a.n]:
            print(f"{r['year']} {r['season']:7} {f.get('confidence'):10} {f['path']}  {'; '.join(f.get('warnings', [])) or f.get('score') or ''}")
    elif a.cmd == 'fixes':   # the reviewers' findings still to apply (parser patterns, school codes, overrides)
        cur = {f['path']: f['parse_sha'] for r, f in files()}
        for p_, e in sorted(load_log().items()):
            if e['verdict'] == 'fixed' and cur.get(p_) == e['parse_sha']:
                print(f"{p_}  [{e['date']} {e['by']}]\n    {e['notes']}")
    elif a.cmd == 'show':
        show(a.path)
    else:
        if not (a.path and a.verdict and a.notes):
            sys.exit('record needs a path, --verdict and --notes (the evidence)')
        record(a.path, a.verdict, a.by, a.notes)


if __name__ == '__main__':
    main()
