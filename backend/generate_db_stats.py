"""
Generate db_stats.json — a human-readable snapshot of the database contents.

Commit this file alongside track_app.db so that `git diff db_stats.json`
shows exactly what changed between database versions.

Run this script any time the DB is updated:
    python3 backend/generate_db_stats.py
"""

import sqlite3
import json
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'track_app.db')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'db_stats.json')


def generate_stats():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    stats = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "totals": {},
        "by_year": {},
        "by_year_meet": {},
        "teams": {},
    }

    # Overall totals
    cursor.execute("SELECT COUNT(*) FROM performances")
    stats["totals"]["performances"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM athletes")
    stats["totals"]["athletes"] = cursor.fetchone()[0]

    # Counts per year
    cursor.execute("""
        SELECT year, season, COUNT(*) as cnt
        FROM performances
        GROUP BY year, season
        ORDER BY year, season
    """)
    for row in cursor.fetchall():
        key = f"{row['year']} {row['season']}"
        stats["by_year"][key] = row["cnt"]

    # Counts per year+meet (sorted by year then meet name)
    cursor.execute("""
        SELECT year, meet_name, COUNT(*) as cnt
        FROM performances
        GROUP BY year, meet_name
        ORDER BY year, MIN(date), meet_name
    """)
    for row in cursor.fetchall():
        key = f"{row['year']}|{row['meet_name']}"
        stats["by_year_meet"][key] = row["cnt"]

    # GSA-specific counts
    cursor.execute("""
        SELECT year, COUNT(*) as cnt
        FROM performances
        WHERE team LIKE 'George Stevens%'
        GROUP BY year
        ORDER BY year
    """)
    gsa = {}
    for row in cursor.fetchall():
        gsa[row["year"]] = row["cnt"]
    stats["teams"]["George Stevens Academy"] = gsa

    conn.close()

    with open(OUTPUT_PATH, 'w') as f:
        json.dump(stats, f, indent=2)

    print(f"db_stats.json written — {stats['totals']['performances']:,} performances, "
          f"{stats['totals']['athletes']:,} athletes.")


if __name__ == "__main__":
    generate_stats()
