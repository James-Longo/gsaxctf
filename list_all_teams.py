import sqlite3

db_path = 'track_app.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- All Unique Teams (Sorted) ---")
cursor.execute("SELECT DISTINCT team FROM performances")
teams = [row[0] for row in cursor.fetchall() if row[0]]
for t in sorted(teams):
    print(t)

conn.close()
