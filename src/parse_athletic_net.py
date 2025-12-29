import os
import glob
import sqlite3
from bs4 import BeautifulSoup
import re

# Configuration
DB_PATH = 'track_app.db'
PAGES_DIR = os.path.join(os.getcwd(), 'athletic.net pages')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS athletes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        athletic_id TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS performances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        athlete_id INTEGER,
        date TEXT,
        season TEXT,
        event TEXT,
        mark TEXT,
        place TEXT,
        meet_name TEXT,
        is_pr BOOLEAN,
        is_sb BOOLEAN,
        round TEXT,
        FOREIGN KEY(athlete_id) REFERENCES athletes(id)
    )
    ''')
    
    conn.commit()
    return conn

def clean_text(text):
    if text:
        return text.strip()
    return ""

def parse_html_file(file_path, conn):
    print(f"Parsing: {os.path.basename(file_path)}")
    with open(file_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    # Extract Athlete Name
    # <h2 ...><a ...> Reese Renwick </a>...</h2>
    # Or in the breadcrumbs / twin-avatar
    # Looking at the file content: line 75 -> <h2 ...> ... Reese Renwick ... </h2>
    
    # Try getting it from the <title> or <meta name="favTitle">
    athlete_name = ""
    meta_title = soup.find('meta', {'name': 'favTitle'})
    if meta_title:
        # Content is "TF - Reese Renwick"
        athlete_name = meta_title.get('content', '').replace('TF - ', '').strip()
    
    if not athlete_name:
        # Fallback to <title>
        title = soup.find('title')
        if title:
            # "Reese Renwick - ME Track & Field Bio"
            athlete_name = title.text.split('-')[0].strip()

    print(f"  Athlete: {athlete_name}")
    
    if not athlete_name:
        print("  Skipping: Could not find athlete name")
        return

    # Insert or Get Athlete
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM athletes WHERE name = ?', (athlete_name,))
    row = cursor.fetchone()
    if row:
        athlete_id = row[0]
    else:
        cursor.execute('INSERT INTO athletes (name) VALUES (?)', (athlete_name,))
        athlete_id = cursor.lastrowid
    
    # Parse Results
    # Identify Season sections
    # They are in <div class="card mb-2 ..."> with a header containing the season
    
    # We want "shared-athlete-bio-results" -> "card"
    # But checking the snippet, the hierarchy is:
    # <shared-athlete-bio-results>
    #   <div class="card mb-2 ...">
    #     <div class="card-header ..."> <h5> ... 2026 Indoor ... </h5> </div>
    #     <div class="card-block ..."> ... table ... </div>
    
    result_containers = soup.find_all('shared-athlete-bio-results')
    
    count = 0
    for container in result_containers:
        cards = container.find_all('div', class_='card')
        for card in cards:
            header = card.find('div', class_='card-header')
            if not header:
                continue
            
            season_text = clean_text(header.text)
            # season_text might be "2026 Indoor  George Stevens HS  11th Grade"
            # Let's extract just the season if possible. Usually starts with Year Season.
            season_match = re.match(r'(\d{4}\s+(Indoor|Outdoor|XC))', season_text)
            season = season_match.group(1) if season_match else season_text.splitlines()[0].strip()

            table_block = card.find('div', class_='card-block')
            if not table_block:
                continue

            # In the table, we have headers for Events: <tr ...><td ...><h5> 55 Meter </h5></td></tr>
            # Then result rows.
            
            rows = table_block.find_all('tr')
            current_event = None
            
            for row in rows:
                # Check for event header
                h5 = row.find('h5')
                if h5:
                    current_event = h5.text.strip()
                    continue
                
                # Check for result row
                # They have 'result-id' attribute usually, or we can check structure
                if row.has_attr('result-id') or (row.find('shared-result-and-comment-tf')):
                    tds = row.find_all('td')
                    if len(tds) < 5:
                        continue
                    
                    # 0: Place
                    place = clean_text(tds[0].text)
                    
                    # 2: Mark
                    mark_div = tds[2].find('div', class_='text-nowrap')
                    mark = ""
                    is_sb = False
                    is_pr = False
                    if mark_div:
                        mark_a = mark_div.find('a')
                        if mark_a:
                            mark = clean_text(mark_a.text)
                        
                        # Check labels
                        if "SR" in mark_div.text:
                            is_sb = True
                        if "PR" in mark_div.text:
                            is_pr = True # Often PR is in a small tag or different structure, check for 'PR' text
                    
                    # 3: Date
                    date = clean_text(tds[3].text)
                    
                    # 4: Meet
                    meet_a = tds[4].find('a')
                    meet_name = clean_text(meet_a.text) if meet_a else clean_text(tds[4].text)

                    # Insert
                    cursor.execute('''
                        INSERT INTO performances (athlete_id, season, event, mark, place, date, meet_name, is_pr, is_sb)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (athlete_id, season, current_event, mark, place, date, meet_name, is_pr, is_sb))
                    count += 1
    
    print(f"  Inserted {count} performances.")
    conn.commit()

def main():
    conn = init_db()
    
    # Check if files exist
    html_files = glob.glob(os.path.join(PAGES_DIR, "*.html"))
    if not html_files:
        print(f"No HTML files found in {PAGES_DIR}")
        return

    for file_path in html_files:
        try:
            parse_html_file(file_path, conn)
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            import traceback
            traceback.print_exc()
    
    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()
