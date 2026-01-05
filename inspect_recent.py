import sqlite3

db_path = 'track_app.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- Recent Performances (Last 100) ---")
cursor.execute("SELECT date, team, event, athlete_name FROM performances ORDER BY date DESC LIMIT 100")
for row in cursor.fetchall():
    print(f"{row[0]} | {row[1]} | {row[2]} | {row[3]}")

conn.close()
