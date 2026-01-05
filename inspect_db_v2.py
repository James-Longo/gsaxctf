import sqlite3
import os

db_paths = ['track_app.db', 'backend/track_field.db']

for db_path in db_paths:
    if os.path.exists(db_path):
        print(f"--- Checking {db_path} ---")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"Tables: {[t[0] for t in tables]}")
        
        if any('performance' in t[0].lower() for t in tables):
            table_name = [t[0] for t in tables if 'performance' in t[0].lower()][0]
            print(f"Inspecting table: {table_name}")
            
            cursor.execute(f"SELECT DISTINCT team FROM {table_name} WHERE team LIKE '%Bangor Christian%' OR team LIKE '%Central%' OR team LIKE '%MCI%' OR team LIKE '%Maine Central%' LIMIT 20")
            print("Teams Found:")
            for row in cursor.fetchall():
                print(row[0])
                
            cursor.execute(f"SELECT DISTINCT event FROM {table_name} LIMIT 20")
            print("\nEvents Found:")
            for row in cursor.fetchall():
                print(row[0])
        conn.close()
    else:
        print(f"{db_path} does not exist.")
