import sqlite3
import os
import re

def get_db_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, 'track_app.db')

def run_tests():
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print(f"FAIL: Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    tests_passed = 0
    tests_failed = 0

    def assert_test(condition, name, fail_msg=""):
        nonlocal tests_passed, tests_failed
        if condition:
            print(f"PASS: {name}")
            tests_passed += 1
        else:
            print(f"FAIL: {name} - {fail_msg}")
            tests_failed += 1

    print("--- Running Data Integrity Unit Tests ---")

    # 1. Season Diversity
    cursor.execute("SELECT DISTINCT season FROM performances")
    seasons = [row[0] for row in cursor.fetchall()]
    assert_test(
        "2026 Outdoor" in seasons and "2025 Indoor" in seasons and "2022 Outdoor" in seasons,
        "Season Diversity",
        f"Missing expected seasons. Found: {seasons}"
    )

    # 2. Event Diversity
    cursor.execute("SELECT DISTINCT event FROM performances")
    events = [row[0] for row in cursor.fetchall()]
    has_sprint = any("100" in e and "Dash" in e for e in events)
    has_distance = any("3200" in e or "2 Mile" in e for e in events)
    has_relay = any("4x" in e or "Relay" in e for e in events)
    has_field = any("Shot Put" in e or "High Jump" in e for e in events)
    assert_test(
        has_sprint and has_distance and has_relay and has_field,
        "Event Diversity",
        "Missing representation from core event groups (sprints, distance, relays, field)."
    )

    # 3. Specific Athlete Presence (GSA Context)
    cursor.execute("""
        SELECT DISTINCT a.name
        FROM performances p
        JOIN athletes a ON p.athlete_id = a.id
        WHERE p.team = 'George Stevens Academy'
    """)
    gsa_athletes = [row[0] for row in cursor.fetchall()]
    expected_athletes = ["Bailey Townsend", "Logan Townsend"]
    missing_athletes = [a for a in expected_athletes if a not in gsa_athletes]
    assert_test(
        len(missing_athletes) == 0,
        "Specific Athlete Presence",
        f"Missing key GSA athletes: {missing_athletes}"
    )

    # 4. Team Normalization
    # We should NOT see 'George Steve' or 'GSA' or 'Bucksport.' in the team list, they should be normalized
    cursor.execute("SELECT DISTINCT team FROM performances")
    teams = [row[0] for row in cursor.fetchall()]
    bad_teams = [t for t in teams if t in ["George Steve", "GSA", "Bucksport.", "01-Unattached"]]
    assert_test(
        len(bad_teams) == 0,
        "Team Normalization",
        f"Found unnormalized team names: {bad_teams}"
    )

    # 5. Data Format Integrity (No leaking times into team names)
    bad_team_formats = [t for t in teams if re.match(r'^:?\d+[:.]\d+', str(t))]
    assert_test(
        len(bad_team_formats) == 0,
        "Data Format Integrity",
        f"Time marks leaked into team names: {bad_team_formats}"
    )

    # 6. Recent Fix Verification (Bucksport 2026 Outdoor)
    cursor.execute("SELECT COUNT(*) FROM performances WHERE season = '2026 Outdoor' AND meet_name LIKE '%Bucksport%'")
    bucksport_count = cursor.fetchone()[0]
    assert_test(
        bucksport_count > 0,
        "Recent Fix (Bucksport 2026)",
        "No results found for Bucksport 2026 Outdoor meet. Link extraction might be failing."
    )

    print("-" * 40)
    print(f"Results: {tests_passed} Passed, {tests_failed} Failed.")
    if tests_failed > 0:
        print("ACTION REQUIRED: Please fix the failing tests before proceeding.")

if __name__ == "__main__":
    run_tests()
