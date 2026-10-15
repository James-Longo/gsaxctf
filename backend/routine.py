"""
routine.py - the site update routine's code steps.

This replaces the weekly GitHub Action. A Claude routine (a scheduled task in
the desktop app, with a browser) runs the agent procedure in
docs/agents/update-routine.md, which calls these steps and adds what code
can't do: fetching Five K Sport files in the browser, reading results by hand
when verification fails, and the athlete-identity review.

    python3 -m backend.routine plan       # what's in season and what to run (JSON)
    python3 -m backend.routine scrape     # sub5: download, parse, sync (+ manifest, meet links, athlete catalog)
    python3 -m backend.routine qaqc       # score verification of the meets added since the last run (JSON)
    python3 -m backend.routine sims       # postseason forecasts for sports in their championship window
    python3 -m backend.routine check      # production build + tests
    python3 -m backend.routine publish --yes   # commit and push (GitHub Pages deploys on push)

State between runs (the meets already reported) lives in
backend/data/routine_state.json, which is local to this computer.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'backend', 'data')
STATE_PATH = os.path.join(DATA, 'routine_state.json')
UI = os.path.join(BASE, 'ui')

SPORT_OF = {'XC': 'xc', 'Indoor': 'indoor', 'Outdoor': 'outdoor'}

# What a publish commits: the site's data and the pipeline's tracked state.
# Athlete decisions, the athlete catalog and its review queue are internal
# artifacts that stay on this computer (.gitignore).
PUBLISH_PATHS = [
    'ui/public/data',
    'backend/data/scrape_state.json',
    'backend/data/parsed_results',
    'backend/data/sub5_archive',
    'backend/data/fiveks_archive',
    'backend/data/meet_verification.json',
    'backend/data/qaqc_flags.json',
    'backend/web_date_mapping.json',
    'backend/web_meet_mapping.json',
    'backend/web_url_mapping.json',
]


def _load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save_state(state):
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=1, sort_keys=True)


def _offset(md):
    from backend.json_store import _season_offset
    return _season_offset(int(md[:2]), int(md[3:5]))


def in_season(today=None):
    """Season types whose window (from the manifest) contains today."""
    today = today or date.today()
    windows = _load_json(os.path.join(UI, 'public', 'data', 'manifest.json'), {}).get('season_windows', {})
    t = _offset(today.strftime('%m-%d'))
    return sorted(s for s, w in windows.items() if _offset(w['start']) <= t <= _offset(w['end']))


def xc_sim_due(today=None):
    """The XC forecast is published while this season's championship groups
    exist and their last meet hasn't passed."""
    today = today or date.today()
    groups = _load_json(os.path.join(DATA, 'xc_groups.json'), {}).get(str(today.year))
    if not groups:
        return False, 'no championship groups for this season (backend/data/xc_groups.json)'
    last = max(m['date'] for m in groups.get('meets', []))
    if today.isoformat() > last:
        return False, f'season over (last championship meet {last})'
    return True, f'championship meets through {last}'


def plan():
    today = date.today()
    seasons = in_season(today)
    due, why = xc_sim_due(today)
    out = dict(date=today.isoformat(), in_season=seasons,
               fiveksport=('XC' in seasons), xc_postseason=dict(due=due, why=why))
    try:
        from backend import fiveksport
        out['fiveksport_pending'] = len(fiveksport.pending(today.year)) if 'XC' in seasons else 0
    except Exception as e:  # noqa: BLE001 - network
        out['fiveksport_pending'] = f'unavailable: {e}'
    try:
        from backend import athlete_catalog as ac
        out['athlete_review_queue'] = ac.load_catalog().get('stats', {}).get('review_queue')
    except Exception:  # noqa: BLE001
        pass
    print(json.dumps(out, indent=1))
    return out


def scrape():
    """sub5 for every season (index pages are re-read; files already synced
    are skipped), then the store, manifest, meet links and athlete catalog."""
    from backend.scraper_v2 import Sub5ScraperV2
    n = Sub5ScraperV2(progress_callback=lambda *a, **k: None).run_full_scrape()
    print(json.dumps(dict(new_performances=n)))
    return n


def qaqc():
    """Score verification for every meet, then a report of the meets added
    since the last routine run: verified / mismatch / no rankings."""
    import io
    import contextlib
    from backend import qaqc as q
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        q.check_meet_scoring()
        q.check_result_order()
    synced = set(_load_json(os.path.join(DATA, 'scrape_state.json'), {}).get('synced_meets', {}))
    state = _load_json(STATE_PATH, {})
    seen = set(state.get('reported_meets', []))
    if not seen:
        # first run: everything already in the store counts as reported
        seen = set(synced)
        state['reported_meets'] = sorted(seen)
        _save_state(state)
        print(json.dumps(dict(first_run=True, meets=len(seen))))
        return {}
    ver = _load_json(os.path.join(DATA, 'meet_verification.json'), {})
    new = sorted(synced - seen)
    report = {k: ver.get(k, {}).get('status', 'not checked') for k in new}
    # Five K Sport files carry their own verification (fiveksport.verify)
    counts = {}
    for v in report.values():
        counts[v] = counts.get(v, 0) + 1
    out = dict(new_meets=len(new), by_status=counts,
               mismatches=[k for k, v in report.items() if v == 'mismatch'],
               report=report)
    print(json.dumps(out, indent=1))
    return out


def mark_reported():
    """After the agent has dealt with this run's QAQC report."""
    synced = set(_load_json(os.path.join(DATA, 'scrape_state.json'), {}).get('synced_meets', {}))
    state = _load_json(STATE_PATH, {})
    state['reported_meets'] = sorted(synced)
    state['last_run'] = date.today().isoformat()
    _save_state(state)


def sims():
    """Publish the postseason forecasts that are due. Track forecasts are
    computed in the browser, so only XC has a published file."""
    due, why = xc_sim_due()
    if not due:
        print(json.dumps(dict(xc_postseason='skipped', why=why)))
        return False
    env = dict(os.environ, PYTHONHASHSEED='0', OMP_NUM_THREADS='1')
    r = subprocess.run([sys.executable, '-m', 'backend.xc_postseason_publish',
                        '--asof', date.today().isoformat(), '--sims', '5000'],
                       cwd=BASE, env=env, capture_output=True, text=True)
    print(r.stderr[-600:])
    if r.returncode:
        raise SystemExit('xc_postseason_publish failed')
    return True


def check():
    """Production build and the test suites; nonzero exit on any failure."""
    ok = True
    for cmd, cwd in ((['npx', 'vite', 'build'], UI),
                     ([sys.executable, 'backend/tests/test_parsers.py'], BASE),
                     ([sys.executable, 'backend/tests/test_fiveksport.py'], BASE)):
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
        print(' '.join(cmd[-1:]), 'OK' if r.returncode == 0 else 'FAILED', '|', ' / '.join(tail))
        ok = ok and r.returncode == 0
    if not ok:
        raise SystemExit(1)
    return ok


def publish(message, yes=False):
    """Commit the data and push. The push deploys the site: GitHub Pages
    rebuilds ui/ on every push to main (.github/workflows/deploy-pages.yml).
    Code changes the agent committed earlier in the run go out with it."""
    if not yes:
        raise SystemExit('publish needs --yes')
    subprocess.run(['git', 'add', '--'] + [p for p in PUBLISH_PATHS if os.path.exists(os.path.join(BASE, p))],
                   cwd=BASE, check=True)
    staged = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=BASE)
    if staged.returncode:
        subprocess.run(['git', 'commit', '-m', message], cwd=BASE, check=True)
    subprocess.run(['git', 'push'], cwd=BASE, check=True)
    mark_reported()
    print('pushed; GitHub Pages is deploying (gh run list --workflow deploy-pages.yml)')


def main():
    ap = argparse.ArgumentParser(description='Site update routine (code steps)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    for c in ('plan', 'scrape', 'qaqc', 'sims', 'check', 'mark-reported'):
        sub.add_parser(c)
    p = sub.add_parser('publish')
    p.add_argument('--yes', action='store_true')
    p.add_argument('-m', '--message', default=f'data: routine update {date.today().isoformat()}')
    a = ap.parse_args()
    {'plan': plan, 'scrape': scrape, 'qaqc': qaqc, 'sims': sims, 'check': check,
     'mark-reported': mark_reported}.get(a.cmd, lambda: publish(a.message, a.yes))()


if __name__ == '__main__':
    main()
