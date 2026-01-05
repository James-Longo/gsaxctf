import sqlite3

db_path = 'backend/track_field.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- Unique Teams with 'Bangor', 'Central', or 'MCI' ---")
cursor.execute("SELECT DISTINCT team FROM performances WHERE team LIKE '%Bangor%' OR team LIKE '%Central%' OR team LIKE '%MCI%' OR team LIKE '%Maine Central%'")
for row in cursor.fetchall():
    print(row[0])

print("\n--- Events in 2024 (should be typical) ---")
cursor.execute("SELECT DISTINCT event FROM performances WHERE date LIKE '2024%' LIMIT 50")
for row in cursor.fetchall():
    print(row[0])

conn.close()
