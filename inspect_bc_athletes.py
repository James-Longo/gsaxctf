import sqlite3

db_path = 'track_app.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Searching for Bangor Christian athletes (found via search/memory)
# Common BC athletes: "S. Martin"? No, user said Scott Martin is MCI.
# Let's search for "Bangor Christian" in the scraper files or just look for athletes at specific meets.

print("--- Searching for athletes with 'Bangor' in their team name (excluding Bangor High School) ---")
cursor.execute("SELECT DISTINCT athlete_id, team FROM performances WHERE team LIKE '%Bangor%' AND team != 'Bangor High School'")
for row in cursor.fetchall():
    # Get athlete name
    cursor.execute("SELECT name FROM athletes WHERE id = ?", (row[0],))
    name = cursor.fetchone()
    print(f"Athlete: {name[0] if name else 'Unknown'} | Team: {row[1]}")

print("\n--- Searching for athletes with 'Christian' in their team name ---")
cursor.execute("SELECT DISTINCT athlete_id, team FROM performances WHERE team LIKE '%Christian%'")
for row in cursor.fetchall():
    cursor.execute("SELECT name FROM athletes WHERE id = ?", (row[0],))
    name = cursor.fetchone()
    print(f"Athlete: {name[0] if name else 'Unknown'} | Team: {row[1]}")

conn.close()
