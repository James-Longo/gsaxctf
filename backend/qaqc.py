import sqlite3
import os
import json
import re
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'track_app.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def run_qaqc():
    print("=== Track & Field Scrape QAQC Report ===")
    
    if not os.path.exists(DB_PATH):
        print("ERROR: Database file not found.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Overall Stats
    cursor.execute("SELECT COUNT(*) as count FROM performances")
    total_performances = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM athletes")
    total_athletes = cursor.fetchone()['count']
    
    print(f"Total Performances: {total_performances}")
    print(f"Total Athletes: {total_athletes}")
    print("-" * 40)

    # 2. Season/Year Breakdown
    print("Season and Year Coverage:")
    cursor.execute("SELECT year, season, COUNT(*) as count FROM performances GROUP BY year, season ORDER BY year DESC, season DESC")
    rows = cursor.fetchall()
    for row in rows:
        print(f"  {row['year']} {row['season']}: {row['count']} results")
    print("-" * 40)

    # 3. Missing GSA Analysis
    print("GSA (George Stevens Academy) Coverage Check (Info):")
    cursor.execute("SELECT DISTINCT year, season, meet_name FROM performances")
    all_meets = cursor.fetchall()
    
    missing_gsa = []
    for meet in all_meets:
        cursor.execute("SELECT COUNT(*) as count FROM performances WHERE year=? AND season=? AND meet_name=? AND team='George Stevens Academy'", 
                       (meet['year'], meet['season'], meet['meet_name']))
        if cursor.fetchone()['count'] == 0:
            missing_gsa.append(f"{meet['year']} {meet['season']} - {meet['meet_name']}")
    
    if missing_gsa:
        print(f"  GSA not found in {len(missing_gsa)}/{len(all_meets)} meets. (Normal for state-wide or specialized meets)")
        # Optionally list top 5 recent ones
        for m in missing_gsa[:5]:
            print(f"    - {m}")
        if len(missing_gsa) > 5:
            print(f"    ... and {len(missing_gsa)-5} more.")
    else:
        print("  GSA found in all recorded meets.")
    print("-" * 40)

    # 4. Zero Result Analysis (Archive vs DB)
    print("Parsing Failure Check (Empty Meets):")
    archive_base = os.path.join(os.path.dirname(__file__), 'data/sub5_archive')
    
    empty_meets = []
    total_archived = 0
    if os.path.exists(archive_base):
        for year in os.listdir(archive_base):
            year_path = os.path.join(archive_base, year)
            if not os.path.isdir(year_path): continue
            for season in os.listdir(year_path):
                season_path = os.path.join(year_path, season)
                if not os.path.isdir(season_path): continue
                for file in os.listdir(season_path):
                    if file.endswith('.htm') or file.endswith('.html'):
                        total_archived += 1
                        meet_name = os.path.splitext(file)[0]
                        db_season = f"{year} {season}"
                        cursor.execute("SELECT COUNT(*) as count FROM performances WHERE year=? AND season=? AND LOWER(meet_name)=LOWER(?)", 
                                       (year, db_season, meet_name))
                        if cursor.fetchone()['count'] == 0:
                            empty_meets.append(f"{year} {season} - {file}")
    
    if empty_meets:
        print(f"  FAILED/EMPTY PARSES: {len(empty_meets)}/{total_archived} archived files returned 0 results.")
        for m in empty_meets:
            print(f"    [FAIL] {m}")
    else:
        print(f"  All {total_archived} archived files returned at least one result.")
    print("-" * 40)

    # 5. Data Integrity Checks
    print("Data Integrity Flags:")
    
    # Check for empty marks
    cursor.execute("SELECT COUNT(*) as count FROM performances WHERE mark IS NULL OR mark = ''")
    empty_marks = cursor.fetchone()['count']
    if empty_marks > 0:
        print(f"  [ALERT] Found {empty_marks} performances with empty marks.")
    else:
        print("  [OK] No empty marks found.")

    # Check for digits in athlete names
    cursor.execute("""
        SELECT a.name, p.meet_name, p.year, p.season 
        FROM athletes a 
        JOIN performances p ON a.id = p.athlete_id 
        WHERE a.name GLOB '*[0-9]*'
    """)
    bad_athletes = cursor.fetchall()
    if bad_athletes:
        print(f"  [ALERT] Found {len(bad_athletes)} records where Athlete name contains digits (Possible Parsing Error).")
        unique_bad = sorted(list(set([row['name'] for row in bad_athletes])))
        for name in unique_bad[:10]:
            print(f"    - {name}")
        if len(unique_bad) > 10:
            print(f"    ... and {len(unique_bad)-10} more.")
    else:
        print("  [OK] Athlete names appear clean (no digits).")

    # Check for digits in school names (excluding common numbered ones like "Class A", "Meet 1", etc.)
    # Note: Schools like "MDI 2024" or "Bangor 2" would be flagged.
    # Actually, school names usually shouldn't have digits unless it's a "Class" or something that leaked.
    cursor.execute("""
        SELECT DISTINCT team, meet_name 
        FROM performances 
        WHERE team GLOB '*[0-9]*'
    """)
    bad_schools = cursor.fetchall()
    if bad_schools:
        print(f"  [ALERT] Found {len(bad_schools)} records where School name contains digits.")
        for row in bad_schools[:10]:
            print(f"    - {row['team']} (Meet: {row['meet_name']})")
        if len(bad_schools) > 10:
            print(f"    ... and {len(bad_schools)-10} more.")
    else:
        print("  [OK] School names appear clean (no digits).")

    # Check for suspicious marks (e.g. 0.0 or 0:00)
    cursor.execute("SELECT COUNT(*) as count FROM performances WHERE mark LIKE '0.0%' OR mark LIKE '0:00%'")
    suspicious_marks = cursor.fetchone()['count']
    if suspicious_marks > 0:
        print(f"  [WARNING] {suspicious_marks} performances have '0' results.")

    # Check for likely bad school names
    # 1. Names with commas (Athlete names)
    cursor.execute("SELECT DISTINCT team FROM performances WHERE team LIKE '%,%'")
    comma_teams = cursor.fetchall()
    
    # 2. Names with Grade prefixes (FR, SO, SR)
    cursor.execute("SELECT DISTINCT team FROM performances WHERE team LIKE 'FR %' OR team LIKE 'SO %' OR team LIKE 'SR %'")
    prefix_teams = cursor.fetchall()
    
    # 3. Names with digits (unless starting with Year)
    cursor.execute("SELECT DISTINCT team FROM performances WHERE team GLOB '*[0-9]*' AND NOT team GLOB '[12][09][0-9][0-9]*'")
    digit_teams = cursor.fetchall()
    
    # 4. Common Junk/status terms
    junk_terms = ['Finals', 'Points', 'Page', 'Prelims', 'Seed']
    junk_teams = []
    for jt in junk_terms:
        cursor.execute("SELECT DISTINCT team FROM performances WHERE team LIKE ?", (f'%{jt}%',))
        junk_teams.extend([r['team'] for r in cursor.fetchall()])
    junk_unique = list(set(junk_teams))

    if comma_teams or prefix_teams or digit_teams or junk_unique:
        print(f"  [WARNING] Anomalous team names found:")
        if comma_teams:
            print(f"    - {len(comma_teams)} names with commas (Athlete leak): {', '.join([r['team'] for r in comma_teams[:3]])}...")
        if prefix_teams:
            print(f"    - {len(prefix_teams)} names with FR/SO/SR prefixes: {', '.join([r['team'] for r in prefix_teams[:3]])}...")
        if digit_teams:
            print(f"    - {len(digit_teams)} names with digits: {', '.join([r['team'] for r in digit_teams[:3]])}...")
        if junk_unique:
            print(f"    - {len(junk_unique)} names containing fragment junk: {', '.join(junk_unique[:3])}...")
    
    # 6. Grade Consistency Analysis
    print("Grade Consistency Analysis:")
    
    # Check for missing grades that could be recovered
    # An athlete has some records with grades and some without in the same season
    cursor.execute("""
        SELECT p.athlete_id, a.name as athlete_name, p.year, p.season,
               COUNT(CASE WHEN p.grade IS NULL OR p.grade = '' THEN 1 END) as missing_count,
               GROUP_CONCAT(DISTINCT CASE WHEN p.grade != '' THEN p.grade END) as found_grades
        FROM performances p
        JOIN athletes a ON p.athlete_id = a.id
        GROUP BY p.athlete_id, p.year, p.season
        HAVING missing_count > 0 AND found_grades IS NOT NULL AND found_grades != ''
    """)
    recoverable = cursor.fetchall()
    if recoverable:
        print(f"  [INFO] {len(recoverable)} athletes have some missing grades that could be recovered from their other results in the same season.")
        for r in recoverable[:5]:
            print(f"    - {r['athlete_name']} (ID: {r['athlete_id']}) in {r['season']}: {r['missing_count']} missing, found: {r['found_grades']}")
        if len(recoverable) > 5:
            print(f"    ... and {len(recoverable)-5} more.")
    
    # Check for conflicting grades in the same season
    cursor.execute("""
        SELECT p.athlete_id, a.name as athlete_name, p.year, p.season,
               GROUP_CONCAT(DISTINCT p.grade) as grades
        FROM (
            SELECT athlete_id, year, season, grade
            FROM performances
            WHERE grade IS NOT NULL AND grade != ''
            GROUP BY athlete_id, year, season, grade
        ) p
        JOIN athletes a ON p.athlete_id = a.id
        GROUP BY p.athlete_id, p.year, p.season
        HAVING COUNT(p.grade) > 1
    """)
    conflicting = cursor.fetchall()
    if conflicting:
        print(f"  [FAIL] {len(conflicting)} athletes have MULTIPLE assigned grades in the same season (Impossible).")
        for r in conflicting:
            print(f"    - {r['athlete_name']} in {r['season']}: {r['grades']}")
    else:
        print("  [OK] No athletes with conflicting grades in same season found.")

    # Check for totally missing grades
    cursor.execute("SELECT COUNT(*) as count FROM performances WHERE grade IS NULL OR grade = ''")
    total_missing_grades = cursor.fetchone()['count']
    print(f"  [INFO] Total performances missing grade info: {total_missing_grades} ({total_missing_grades/total_performances*100:.1f}%)")

    print("-" * 40)
    has_issues = empty_meets or comma_teams or prefix_teams or digit_teams or junk_unique or conflicting
    print("QAQC Summary: " + ("Issues Found" if has_issues else "LOOKS GOOD"))
    
    conn.close()

if __name__ == "__main__":
    run_qaqc()
