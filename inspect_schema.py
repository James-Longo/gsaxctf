import sqlite3

db_path = 'track_app.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- Performances Schema ---")
cursor.execute("PRAGMA table_info(performances)")
for row in cursor.fetchall():
    print(row)

print("\n--- Athletes Schema ---")
cursor.execute("PRAGMA table_info(athletes)")
for row in cursor.fetchall():
    print(row)

conn.close()
