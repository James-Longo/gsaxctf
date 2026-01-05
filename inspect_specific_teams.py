import sqlite3

db_path = 'track_app.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Search for anything that might be Bangor Christian
search_terms = ['Bangor', 'Christian', 'BC', 'PCHS', 'Piscataquis', 'Central']

print("--- Searching for specific teams ---")
for term in search_terms:
    cursor.execute("SELECT DISTINCT team FROM performances WHERE team LIKE ?", (f"%{term}%",))
    print(f"Results for '{term}':")
    for row in cursor.fetchall():
        print(f"  - {row[0]}")

print("\n--- Spot check 'BC' in recent data ---")
cursor.execute("SELECT DISTINCT team FROM performances WHERE team LIKE 'BC%'")
for row in cursor.fetchall():
    print(f"  - {row[0]}")

conn.close()
