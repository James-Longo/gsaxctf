import sqlite3
conn = sqlite3.connect('track_app.db')
cursor = conn.cursor()
cursor.execute("SELECT mark, COUNT(*) FROM performances WHERE mark IN ('DNF', 'NH', 'DQ', 'DNS', 'ND', 'SCR', 'FOUL') GROUP BY mark")
results = cursor.fetchall()
print("Special Marks Count:")
for r in results:
    print(r)
conn.close()
