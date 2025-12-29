import sqlite3
import os

DB_PATH = 'track_app.db'

def inspect():
    if not os.path.exists(DB_PATH):
        print("DB not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    for name, sql in tables:
        print(f"--- Table: {name} ---")
        print(sql)
        print()
    conn.close()

if __name__ == "__main__":
    inspect()
