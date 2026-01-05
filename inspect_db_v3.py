import sqlite3
import os

db_path = 'track_app.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- All Events ---")
cursor.execute("SELECT DISTINCT event FROM performances")
events = [row[0] for row in cursor.fetchall()]
for e in sorted(events):
    print(e)

print("\n--- Teams with 'Bangor' ---")
cursor.execute("SELECT DISTINCT team FROM performances WHERE team LIKE '%Bangor%'")
for row in cursor.fetchall():
    print(row[0])

print("\n--- Teams with 'Christian' ---")
cursor.execute("SELECT DISTINCT team FROM performances WHERE team LIKE '%Christian%'")
for row in cursor.fetchall():
    print(row[0])

conn.close()
