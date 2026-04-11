import sqlite3
import os
from collections import Counter

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'track_app.db')

def fix_grades():
    print("=== Track & Field Grade Fixer ===")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Identify fixable grades
    # Find combinations of (athlete_id, year, season) that have at least one grade and at least one blank
    cursor.execute("""
        SELECT p.athlete_id, p.year, p.season,
               GROUP_CONCAT(p.grade) as all_grades
        FROM performances p
        GROUP BY p.athlete_id, p.year, p.season
        HAVING SUM(CASE WHEN p.grade IS NULL OR p.grade = '' THEN 1 ELSE 0 END) > 0
           AND SUM(CASE WHEN p.grade IS NOT NULL AND p.grade != '' THEN 1 ELSE 0 END) > 0
    """)
    candidates = cursor.fetchall()
    print(f"Checking {len(candidates)} athletes for fixable missing grades...")

    fixed_count = 0
    conflict_count = 0

    for cand in candidates:
        athlete_id = cand['athlete_id']
        year = cand['year']
        season = cand['season']
        
        # Parse all found grades (GROUP_CONCAT gives "11,11,11")
        found_grades = [g for g in cand['all_grades'].split(',') if g.strip()]
        unique_grades = sorted(list(set(found_grades)))
        
        if len(unique_grades) == 1:
            # Safe to fix!
            true_grade = unique_grades[0]
            cursor.execute("""
                UPDATE performances 
                SET grade = ? 
                WHERE athlete_id = ? AND year = ? AND season = ? AND (grade IS NULL OR grade = '')
            """, (true_grade, athlete_id, year, season))
            fixed_count += cursor.rowcount
        else:
            # Conflict!
            conflict_count += 1
            # print(f"  Conflict for Athlete {athlete_id} in {season}: {unique_grades}")

    conn.commit()
    print(f"Successfully fixed {fixed_count} missing grade values.")
    print(f"Skipped {conflict_count} athletes due to ambiguous/conflicting seasonal grades.")
    
    conn.close()

if __name__ == "__main__":
    fix_grades()
