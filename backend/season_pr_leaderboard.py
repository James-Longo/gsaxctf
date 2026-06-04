"""
season_pr_leaderboard.py — Rank athletes by number of PRs in a given season.

Reads the JSON flat-file store (ui/public/data/teams/*.json).

PRs are tracked SEASON-TYPE-SPECIFIC (Indoor and Outdoor separately), the way
coaches track them: a mark counts as a PR if it beats the athlete's best PRIOR
mark in that same event AND same season type (across all years). A debut (no
prior mark in that event for that season type) is excluded — nothing to beat.
Relays are excluded.

This deliberately does NOT use the stored `was_pr` flag, which is career-wide:
that flag mixes Indoor and Outdoor into one best, so a strong indoor mark would
mask a genuine outdoor PR (e.g. a triple jumper who jumps farther indoors but
sets a new outdoor best would wrongly show zero outdoor PRs).

Usage:
    python season_pr_leaderboard.py 2026 Outdoor
    python season_pr_leaderboard.py 2026 Indoor --team "George Stevens%"
    python season_pr_leaderboard.py 2026 Outdoor --csv season_prs_2026.csv
"""

import argparse
import csv
import fnmatch
import glob
import json
import os
from collections import defaultdict

from json_store import is_better

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'ui', 'public', 'data', 'teams')


def is_relay(event: str) -> bool:
    e = (event or '').lower()
    return 'relay' in e or '4x' in e


def load_all_performances(team_pattern: str | None):
    """Yield every performance record, optionally filtered by a team glob pattern."""
    for path in glob.glob(os.path.join(DATA_DIR, '*.json')):
        with open(path, encoding='utf-8') as f:
            perfs = json.load(f)
        for p in perfs:
            if team_pattern and not fnmatch.fnmatch(p.get('team', ''), team_pattern):
                continue
            yield p


def season_pr_leaderboard(year: str, season: str, team_pattern: str | None = None):
    """
    Return a list of (athlete_name, team, pr_count, detail_list) sorted by pr_count desc.

    detail_list is [(event, mark, meet_name, date), ...] for each PR counted.
    """
    # Each athlete's history WITHIN this season type (all years), so we can find
    # the prior best for the same event and judge season-type-specific PRs.
    # Keyed by (athlete_id, event) -> [(date, mark), ...].
    history = defaultdict(list)
    target = []  # performances within the requested year + season

    for p in load_all_performances(team_pattern):
        if is_relay(p.get('event', '')):
            continue
        if p.get('season') != season:
            continue  # only compare within the same season type (Indoor/Outdoor)
        key = (p.get('athlete_id', ''), p.get('event', ''))
        history[key].append((p.get('date', ''), p.get('mark', '')))
        if p.get('year') == str(year):
            target.append(p)

    leaderboard = defaultdict(list)  # (name, team) -> [detail, ...]

    for p in target:
        event = p.get('event', '')
        date = p.get('date', '')
        mark = p.get('mark', '')

        # Best prior mark for this athlete in this event + season type (any year).
        prior_best = None
        for d, m in history[(p.get('athlete_id', ''), event)]:
            if d < date and (prior_best is None or is_better(m, prior_best, event)):
                prior_best = m

        if prior_best is None:
            continue  # debut for this season type — nothing to beat
        if not is_better(mark, prior_best, event):
            continue  # not an improvement

        key = (p.get('athlete_name', ''), p.get('team', ''))
        leaderboard[key].append((event, mark, p.get('meet_name', ''), date))

    rows = [
        (name, team, len(details), sorted(details, key=lambda d: d[3]))
        for (name, team), details in leaderboard.items()
    ]
    rows.sort(key=lambda r: (-r[2], r[0]))
    return rows


def main():
    ap = argparse.ArgumentParser(description='Rank athletes by PRs in a season.')
    ap.add_argument('year', help='e.g. 2026')
    ap.add_argument('season', help='Indoor | Outdoor')
    ap.add_argument('--team', help='glob pattern, e.g. "George Stevens*"', default=None)
    ap.add_argument('--top', type=int, default=25, help='how many to print (default 25)')
    ap.add_argument('--csv', help='also write full results to this CSV path', default=None)
    args = ap.parse_args()

    rows = season_pr_leaderboard(args.year, args.season, args.team)

    scope = f' for teams matching "{args.team}"' if args.team else ''
    print(f"\nPR leaderboard — {args.year} {args.season}{scope}")
    print(f"{'#':>3}  {'PRs':>3}  {'Athlete':<28} {'Team'}")
    print('-' * 70)
    for i, (name, team, count, _details) in enumerate(rows[:args.top], 1):
        print(f"{i:>3}  {count:>3}  {name:<28} {team}")

    if not rows:
        print("(no PRs found — check the year/season spelling and team pattern)")

    if args.csv:
        with open(args.csv, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['Rank', 'Athlete', 'Team', 'PRs', 'PR Details'])
            for i, (name, team, count, details) in enumerate(rows, 1):
                detail_str = '; '.join(f"{ev} {mk} @ {mt}" for ev, mk, mt, _ in details)
                w.writerow([i, name, team, count, detail_str])
        print(f"\nWrote {len(rows)} athletes to {args.csv}")


if __name__ == '__main__':
    main()
