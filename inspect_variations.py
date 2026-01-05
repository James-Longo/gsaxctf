import sqlite3

db_path = 'track_app.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

pvc_teams = [
    "Bangor Christian", "Bucksport", "Central", "Foxcroft",
    "George Stevens", "Orono", "PCHS", "Sumner", "Dexter",
    "Penquis", "Searsport", "Mattanawcook", "Lee Academy",
    "Deer Isle", "Penobscot", "Greenville", "Narraguagus",
    "Washington Acad", "Calais", "Shead", "Fort Kent",
    "Caribou", "Presque Isle", "Houlton"
]

print("--- Team Variations Found ---")
for team in pvc_teams:
    cursor.execute("SELECT DISTINCT team FROM performances WHERE team LIKE ?", (f"%{team}%",))
    variations = [row[0] for row in cursor.fetchall()]
    if variations:
        print(f"Goal: {team}")
        for v in variations:
            print(f"  - {v}")
    else:
        print(f"Goal: {team} (No matches found)")

conn.close()
