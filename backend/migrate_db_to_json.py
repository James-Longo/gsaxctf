"""
migrate_db_to_json.py - ONE-TIME migration from track_app.db to team-based JSON files.

Run this locally ONCE:
    python backend/migrate_db_to_json.py

This reads every row from track_app.db, groups by team, computes PR flags,
and writes ui/public/data/teams/{TeamSlug}.json + athletes.json + manifest.json.
Also creates backend/data/scrape_state.json so the weekly scraper knows which
meets are already processed.

It does NOT delete the database. Do that manually after verifying the output.
"""

import sqlite3
import json
import os
import sys
import re
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.json_store import (
    slugify_team, slugify_athlete, make_perf_id,
    recalculate_prs, save_team, save_athletes,
    save_scrape_state, rebuild_manifest,
    TEAMS_DIR, SCRAPE_STATE_PATH
)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'track_app.db')


def migrate():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    os.makedirs(TEAMS_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(SCRAPE_STATE_PATH), exist_ok=True)

    print(f"Opening database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ------------------------------------------------------------------
    # 1. Load all athletes
    # ------------------------------------------------------------------
    print("Loading athletes...")
    db_athletes = {}
    for row in cursor.execute("SELECT id, name FROM athletes").fetchall():
        db_athletes[row['id']] = row['name']

    print(f"  {len(db_athletes):,} athletes loaded.")

    # ------------------------------------------------------------------
    # 2. Load all performances
    # ------------------------------------------------------------------
    print("Loading performances...")
    rows = cursor.execute("""
        SELECT p.id, p.athlete_id, p.event, p.mark, p.place,
               p.team, p.date, p.season, p.year, p.meet_name,
               p.meet_url, p.splits, p.grade
        FROM performances p
        ORDER BY p.date ASC
    """).fetchall()
    print(f"  {len(rows):,} performances loaded.")
    conn.close()

    # ------------------------------------------------------------------
    # 3. Group performances by team, build athlete registry
    # ------------------------------------------------------------------
    print("Grouping by team and building athlete registry...")
    by_team = defaultdict(list)   # team_name -> [perf_dict]
    athletes_out = {}             # athlete_name -> {id, name, primary_team}
    scrape_state_meets = {}       # meet_key -> date

    for row in rows:
        db_athlete_name = db_athletes.get(row['athlete_id'], '')
        if not db_athlete_name:
            continue

        team = row['team'] or 'Unknown'
        if team == 'Unknown':
            continue  # Skip truly unknown teams

        # Season stored as "2026 Outdoor" in DB — split it
        full_season = row['season'] or ''
        year = str(row['year'] or '')
        # Derive season type (Indoor / Outdoor) from the full_season string
        season_type = full_season.replace(year, '').strip() if year in full_season else full_season

        # Athlete ID slug
        athlete_id = slugify_athlete(db_athlete_name, team)

        # Performance ID (stable hash)
        date = row['date'] or ''
        meet_name = row['meet_name'] or ''
        mark = row['mark'] or ''
        event = row['event'] or ''

        perf_id = make_perf_id(athlete_id, event, mark, date, meet_name)

        # Parse splits
        splits = []
        if row['splits']:
            try:
                splits = json.loads(row['splits'])
            except Exception:
                splits = []

        perf = {
            'id': perf_id,
            'athlete_name': db_athlete_name,
            'athlete_id': athlete_id,
            'event': event,
            'mark': mark,
            'grade': row['grade'] or '',
            'team': team,
            'date': date,
            'season': season_type,
            'year': year,
            'meet_name': meet_name,
            'splits': splits,
            # PR flags — will be computed below
            'was_pr': False,
            'is_pr': False,
            'is_sb': False,
        }

        by_team[team].append(perf)

        # Register athlete (primary team = most recent team for this name)
        if db_athlete_name not in athletes_out:
            athletes_out[db_athlete_name] = {
                'id': athlete_id,
                'name': db_athlete_name,
                'primary_team': team,
            }

        # Track which meets are already synced
        meet_key = f"{year}_{season_type}_{meet_name}"
        if meet_key not in scrape_state_meets and date:
            scrape_state_meets[meet_key] = date

    print(f"  {len(by_team):,} teams found.")
    print(f"  {len(athletes_out):,} unique athlete names found.")
    print(f"  {len(scrape_state_meets):,} unique meets tracked.")

    # ------------------------------------------------------------------
    # 4. Write team JSON files with PR flags
    # ------------------------------------------------------------------
    print("Writing team JSON files...")
    total_written = 0
    for i, (team_name, perfs) in enumerate(sorted(by_team.items())):
        recalculate_prs(perfs)
        save_team(team_name, perfs)
        total_written += len(perfs)
        if (i + 1) % 10 == 0 or (i + 1) == len(by_team):
            print(f"  [{i+1}/{len(by_team)}] Written {total_written:,} performances so far...")

    print(f"Done. {total_written:,} performances written across {len(by_team)} team files.")

    # ------------------------------------------------------------------
    # 5. Write athletes.json
    # ------------------------------------------------------------------
    print("Writing athletes.json...")
    save_athletes(athletes_out)
    print(f"  {len(athletes_out):,} athletes written.")

    # ------------------------------------------------------------------
    # 6. Write scrape_state.json
    # ------------------------------------------------------------------
    print("Writing scrape_state.json...")
    save_scrape_state({'synced_meets': scrape_state_meets})
    print(f"  {len(scrape_state_meets):,} meets recorded in scrape state.")

    # ------------------------------------------------------------------
    # 7. Rebuild manifest.json
    # ------------------------------------------------------------------
    print("Rebuilding manifest.json...")
    manifest = rebuild_manifest()
    print(f"  {len(manifest['teams'])} teams, {len(manifest['seasons'])} seasons in manifest.")

    # ------------------------------------------------------------------
    # 8. Sanity check
    # ------------------------------------------------------------------
    print("\n--- Sanity Check ---")
    print(f"Total performances in DB:   {len(rows):,}")
    print(f"Total performances written: {total_written:,}")
    skipped = len(rows) - total_written
    if skipped > 0:
        print(f"Skipped (Unknown team):     {skipped:,}")

    # Check GSA specifically
    gsa_perfs = by_team.get('George Stevens Academy', [])
    gsa_prs = [p for p in gsa_perfs if p['is_pr']]
    gsa_was_prs = [p for p in gsa_perfs if p['was_pr']]
    print(f"\nGSA performances:  {len(gsa_perfs):,}")
    print(f"GSA current PRs:   {len(gsa_prs):,}")
    print(f"GSA historical PRs (was_pr): {len(gsa_was_prs):,}")

    print("\nMigration complete!")
    print("Next steps:")
    print("  1. Verify ui/public/data/teams/ looks correct.")
    print("  2. Test the frontend with the new data format.")
    print("  3. Add track_app.db to .gitignore and run: git rm --cached track_app.db")


if __name__ == "__main__":
    migrate()
