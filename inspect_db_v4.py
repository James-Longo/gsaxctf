import sqlite3
import os

db_path = 'track_app.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- Teams with 'BC' or 'Christian' or 'Bangor' ---")
cursor.execute("SELECT DISTINCT team FROM performances WHERE team LIKE 'BC%' OR team LIKE '%Christian%' OR team LIKE '%Bangor%'")
for row in cursor.fetchall():
    print(row[0])

print("\n--- Teams starting with 'B' (first 50) ---")
cursor.execute("SELECT DISTINCT team FROM performances WHERE team LIKE 'B%' LIMIT 50")
for row in cursor.fetchall():
    print(row[0])

conn.close()
