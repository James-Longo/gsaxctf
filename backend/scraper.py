import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import os
import json
import shutil
from datetime import datetime
try:
    from backend.prototype_parser import Sub5ColumnParser
except ImportError:
    from prototype_parser import Sub5ColumnParser

# Configuration
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'track_app.db')
FIXES_PATH = os.path.join(os.path.dirname(__file__), 'manual_fixes.json')

TEAM_MAPPING = {
    "George Steve": "George Stevens Academy",
    "George Stevens": "George Stevens Academy",
    "GSA": "George Stevens Academy",
    "Blue Hill Ha": "George Stevens Academy",
    "Blue Hill Harbor": "George Stevens Academy",
    "Mt. Desert I": "Mt. Desert Island High School",
    "MDI": "Mt. Desert Island High School",
    "Mt. Ararat H": "Mt. Ararat High School",
    "Mt. Ararat": "Mt. Ararat High School",
    "Mt. Blue Hig": "Mt. Blue High School",
    "Mt. Blue": "Mt. Blue High School",
    "Old Town Hig": "Old Town High School",
    "Old Town": "Old Town High School",
    "John Bapst M": "John Bapst Memorial High School",
    "John Bapst": "John Bapst Memorial High School",
    "Hampden Acad": "Hampden Academy",
    "Hampden": "Hampden Academy",
    "Bangor High": "Bangor High School",
    "Bangor Hig": "Bangor High School",
    "Bangor": "Bangor High School",
    "Orono High S": "Orono High School",
    "Orono": "Orono High School",
    "Brewer High": "Brewer High School",
    "Brewer Hig": "Brewer High School",
    "Brewer": "Brewer High School",
    "Hermon High": "Hermon High School",
    "Hermon Hig": "Hermon High School",
    "Hermon": "Hermon High School",
    "Bucksport Hi": "Bucksport High School",
    "Bucksport": "Bucksport High School",
    "Ellsworth Hi": "Ellsworth High School",
    "Ellsworth": "Ellsworth High School",
    "Bangor Chris": "Bangor Christian Schools",
    "Bangor Christian": "Bangor Christian Schools",
    "PCHS": "Piscataquis Community High School",
    "Presque Isle": "Presque Isle High School",
    "Piscataquis": "Piscataquis Community High School",
    "Penquis Vall": "Penquis Valley High School",
    "Maine Centra": "Maine Central Institute",
    "MCI": "Maine Central Institute",
    "Caribou Hig": "Caribou High School",
    "Caribou": "Caribou High School",
    "Edward Littl": "Edward Little High School",
    "Edward Little": "Edward Little High School",
    "EL": "Edward Little High School",
    "Cony High Sc": "Cony High School",
    "Cony High": "Cony High School",
    "Cony": "Cony High School",
    "Lawrence Hig": "Lawrence High School",
    "Lawrence": "Lawrence High School",
    "Messalonskee": "Messalonskee High School",
    "Winslow High": "Winslow High School",
    "Winslow": "Winslow High School",
    "Leavitt Area": "Leavitt Area High School",
    "Leavitt": "Leavitt Area High School",
    "Lincoln Acad": "Lincoln Academy",
    "Lincoln": "Lincoln Academy",
    "Waterville H": "Waterville High School",
    "Waterville": "Waterville High School",
    "Belfast Area": "Belfast Area High School",
    "Belfast": "Belfast Area High School",
    "Morse High S": "Morse High School",
    "Morse High": "Morse High School",
    "Morse": "Morse High School",
    "Brunswick Hi": "Brunswick High School",
    "Brunswick": "Brunswick High School",
    "Gardiner Hig": "Gardiner High School",
    "Gardiner": "Gardiner High School",
    "Nokomis High": "Nokomis High School",
    "Nokomis": "Nokomis High School",
    "Skowhegan Ar": "Skowhegan Area High School",
    "Skowhegan": "Skowhegan Area High School",
    "Erskine Acad": "Erskine Academy",
    "Erskine": "Erskine Academy",
}

try:
    from backend.parsers.detector import FormatDetector
except ImportError:
    from parsers.detector import FormatDetector

class Sub5Scraper:
    def __init__(self, db_path=DB_PATH, progress_callback=None):
        self.db_path = db_path
        self.headers = {'User-Agent': 'Mozilla/5.0'}
        self.manual_fixes = self.load_manual_fixes()
        self.web_date_mapping = self.load_web_date_mapping()
        self.progress_callback = progress_callback

    def report_progress(self, message, progress=None):
        if self.progress_callback:
            self.progress_callback(message, progress)
        else:
            p_str = f" [{progress}%]" if progress is not None else ""
            print(f"{message}{p_str}")

    def load_web_date_mapping(self):
        mapping_path = os.path.join(os.path.dirname(__file__), 'web_date_mapping.json')
        if os.path.exists(mapping_path):
            try:
                with open(mapping_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def parse_web_date(self, date_str):
        """Converts 'December 27, 2025' or 'Dec 20-22, 2025' to YYYY-MM-DD."""
        if not date_str: return None
        # Handle ranges like "December 20-22, 2025" -> take first day
        date_str = re.sub(r'(\d{1,2})-\d{1,2}', r'\1', date_str)
        try:
            # Try full month name
            dt = datetime.strptime(date_str, "%B %d, %Y")
            return dt.strftime("%Y-%m-%d")
        except:
            try:
                # Try abbreviated month name
                dt = datetime.strptime(date_str, "%b %d, %Y")
                return dt.strftime("%Y-%m-%d")
            except:
                return None

    def load_manual_fixes(self):
        if os.path.exists(FIXES_PATH):
            try:
                with open(FIXES_PATH, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"meet_corrections": [], "athlete_corrections": []}

    def apply_manual_fixes(self, results):
        for r in results:
            # Meet Date Corrections
            for mc in self.manual_fixes.get('meet_corrections', []):
                if mc['meet_name_fragment'].lower() in r['meet_name'].lower() or \
                   mc['meet_name_fragment'].lower() in r.get('meet_url', '').lower():
                    r['date'] = mc['new_date']
                    # Adjust season if necessary (shorthand logic)
                    if '2025' in mc['new_date']:
                        r['season'] = r['season'].replace('2024', '2025')
        return results

    def normalize_team_name(self, name):
        if not name: return "Unknown"
        name = name.strip()
        name = re.sub(r'\s+J[\d\.\-\':]+.*', '', name)
        for key, val in TEAM_MAPPING.items():
            if name.lower().startswith(key.lower()):
                return val
        return name

    def normalize_athlete_name(self, name):
        if not name: return ""
        name = name.strip()
        for ac in self.manual_fixes.get('athlete_corrections', []):
            if ac['old_name'].lower() == name.lower():
                return ac['new_name']
        return name

    def is_date_in_season(self, date_str, season, year):
        """Strictly validates if a date belongs to a given season."""
        if not date_str: return False
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            year_val = int(year)
            if season == "Indoor":
                # Indoor Y goes from Nov (Y-1) to Mar (Y)
                start_date = datetime(year_val - 1, 11, 1)
                end_date = datetime(year_val, 3, 31)
                return start_date <= dt <= end_date
            elif season == "Outdoor":
                # Outdoor Y goes from Mar (Y) to June (Y)
                start_date = datetime(year_val, 3, 1)
                end_date = datetime(year_val, 6, 30)
                return start_date <= dt <= end_date
            return True
        except:
            return False

    def is_likely_athlete_name(self, name):
        if not name: return True
        name_clean = name.strip()
        
        # If it looks like a track mark (digits + special chars)
        # e.g. "12.34", "4-05", "1:23.45"
        if re.search(r'\d', name_clean) and any(c in name_clean for c in '.:-'):
            # But exceptions for schools with numbers? (None common in ME except "U-32" in VT)
            if 'U-32' not in name_clean:
                return True

        # If it contains 3 or more consecutive spaces, it's likely a merged column error
        if '   ' in name_clean:
            return True

        # If it's a known school name (with school keywords), it's not an athlete
        school_keywords = ['High', 'School', 'Academy', 'Acad', 'Institute', 'MCI', 'GSA', 'MDI', 'GSA', 'EMITL', 'PVC', 'Relay', 'Track', 'Field', 'Team', 'Club', 'Middle', 'University', 'College']
        if any(k.lower() in name_clean.lower() for k in school_keywords):
            return False
            
        short_keywords = ['EL', 'HS', 'MS', 'U VT']
        for sk in short_keywords:
            if re.search(r'\b' + re.escape(sk) + r'\b', name_clean, re.I):
                return False

        # If it contains a comma, it's almost certainly an athlete "Last, First"
        if ',' in name_clean:
            return True

        # If it looks like a person's name: "First Last" or "First M. Last"
        if re.match(r'^[A-Z][a-z.\']+\s+([A-Z][a-z.\']+\s*){1,2}$', name_clean):
            return True
        
        # Very short names that aren't known schools
        if len(name_clean) < 3:
            return True
            
        return False

    def get_db_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize_db(self, wipe=True):
        """Initializes the database. Optionally wipes it first."""
        if wipe:
            print("Initializing Database (Fresh Start)...")
        else:
            print("Ensuring Database Schema...")
        
        conn = self.get_db_connection()
        try:
            if wipe:
                conn.execute('DROP TABLE IF EXISTS performances')
                conn.execute('DROP TABLE IF EXISTS athletes')
                conn.execute('DROP TABLE IF EXISTS scraper_history')
            
            # Create Tables
            conn.execute('''
                CREATE TABLE IF NOT EXISTS athletes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS performances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    athlete_id INTEGER,
                    event TEXT,
                    mark TEXT,
                    place TEXT,
                    team TEXT,
                    date TEXT,
                    season TEXT,
                    year TEXT,
                    meet_name TEXT,
                    meet_url TEXT,
                    splits TEXT,
                    FOREIGN KEY(athlete_id) REFERENCES athletes(id)
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS scraper_history (
                    url TEXT PRIMARY KEY,
                    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Add Indexes for performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_athlete_name ON athletes(name)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_perf_athlete_id ON performances(athlete_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_perf_meet_name ON performances(meet_name)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_perf_composite ON performances(athlete_id, event, mark, date)')
            conn.commit()
            print("Database initialized successfully.")
        finally:
            conn.close()


    def get_meet_links(self, year_url):
        print(f"Fetching meet links from: {year_url}")
        try:
            response = requests.get(year_url, headers=self.headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            links = []
            
            # Sub5 pages sometimes have frames
            frames = soup.find_all(['frame', 'iframe'], src=True)
            if frames:
                for frame in frames:
                    from urllib.parse import urljoin
                    frame_url = urljoin(year_url, frame['src'])
                    links.extend(self.get_meet_links(frame_url))
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                # Search for .htm or .html result files
                if href.endswith('.htm') or href.endswith('.html'):
                    # Prioritize emitl, pvc, results patterns
                    if any(x in href.lower() for x in ['results', 'emitl', 'pvc']):
                        if not href.startswith('http'):
                            from urllib.parse import urljoin
                            href = urljoin(year_url, href)
                        if href not in links:
                            links.append(href)
            return list(set(links))
        except Exception as e:
            print(f"Error fetching meet links from {year_url}: {e}")
            return []

    def download_missing_files(self, index_url, archive_dir, synced_meets=None):
        """Downloads new .htm/.html files from the index URL to the archive directory."""
        if not os.path.exists(archive_dir):
            os.makedirs(archive_dir)
            
        print(f"Checking for new files at {index_url}...")
        links = self.get_meet_links(index_url)
        print(f"Found {len(links)} meet links.")
        
        saved_files = []
        for link in links:
            filename = link.split('/')[-1]
            # Handle query params if any
            if '?' in filename: filename = filename.split('?')[0]
            if not filename.lower().endswith(('.htm', '.html')):
                filename += ".htm"
                
            save_path = os.path.join(archive_dir, filename)
            meet_name = os.path.splitext(filename)[0]

            # SKIP if already in DB (unless force override which we don't have yet)
            if synced_meets and meet_name in synced_meets:
                continue
            
            if not os.path.exists(save_path):
                print(f"Downloading {filename}...")
                try:
                    res = requests.get(link, headers=self.headers)
                    res.raise_for_status()
                    with open(save_path, 'wb') as f:
                        f.write(res.content)
                    saved_files.append(save_path)
                except Exception as e:
                    print(f"Failed to download {link}: {e}")
            else:
                pass # Already exists
                
        return saved_files

    def parse_all_files(self, archive_dir, json_dir):
        """Runs the Sub5ColumnParser on all files in the archive dir."""
        if not os.path.exists(json_dir):
            os.makedirs(json_dir)
            
        files = [f for f in os.listdir(archive_dir) if f.lower().endswith(('.htm', '.html'))]
        total = len(files)
        self.report_progress(f"Parsing {total} files...", 0)
        
        parsed_count = 0
        for i, filename in enumerate(files):
            input_path = os.path.join(archive_dir, filename)
            output_filename = os.path.splitext(filename)[0] + ".json"
            output_path = os.path.join(json_dir, output_filename)
            
            try:
                # Skip if already parsed (Always re-parse for now)
                # if os.path.exists(output_path):
                #     continue

                parser = Sub5ColumnParser(input_path)
                events = parser.parse()
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(events, f, indent=4, ensure_ascii=False)
                parsed_count += 1
                
                if i % 5 == 0 or i == total - 1:
                    prog = int(((i + 1) / total) * 100)
                    self.report_progress(f"Parsed {i+1}/{total} files", prog)
            except Exception as e:
                print(f"Error parsing {filename}: {e}")
                
        return parsed_count

    def sync_json_to_db(self, json_dir, season="Indoor", year="2026"):
        """Reads parsed JSON files and inserts them into the database."""
        if not os.path.exists(json_dir):
            print("No JSON directory found.")
            return 0
            
        files = [f for f in os.listdir(json_dir) if f.endswith('.json')]
        print(f"Syncing {len(files)} JSON files to DB for {season} {year}...")
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        total_performances = 0
        
        # We need to map the JSON structure to DB structure:
        # JSON: { event: "...", gender: "...", results: [{athlete, school, result, type, splits?}] }
        # DB: athlete_id, event, mark, place, team, date, season, year, meet_name, meet_url
        
        # Since JSONs don't currently store the "Date" or "Meet Name" explicitly in the event object (they rely on filename context maybe?),
        # We might need to extract date from the filename or the file content if `Sub5ColumnParser` extracted it.
        # Wait, `Sub5ColumnParser` DOES NOT currently extract meet name or date into the JSON output directly, 
        # it just returns a list of events.
        # Check `prototype_parser.py`: It returns `event_results` list.
        # The parser logic extracts data from the file content but maybe doesn't return the global meet date ?
        # Checking `prototype_parser.py`... 
        # It seems `parse()` returns a list of dictionaries, one per event.
        # It does not seem to include a top-level "meet_metadata" object.
        # I need to infer date/meet from filename or add metadata parsing.
        
        # QUICK FIX: Use manual fixes or filename heuristics for Date/Meet Name.
        # Or, assume 2026 Season.
        
        # I will iterate files and try to map filenames to dates if possible, or just default to "2025-2026" season.
        
        files = [f for f in os.listdir(json_dir) if f.endswith('.json')]
        total = len(files)
        self.report_progress(f"Syncing {total} JSON files to DB", 0)
        
        # In-memory athlete cache to avoid thousands of SELECTs
        athlete_cache = {} # {name: id}
        cursor.execute("SELECT name, id FROM athletes")
        for row in cursor.fetchall():
            athlete_cache[row['name']] = row['id']

        # Get list of already synced meet names to skip them
        synced_meets = set()
        cursor.execute("SELECT DISTINCT meet_name FROM performances")
        for row in cursor.fetchall():
            synced_meets.add(row['meet_name'])

        for i, filename in enumerate(files):
            file_path = os.path.join(json_dir, filename)
            meet_name = os.path.splitext(filename)[0]

            # OPTIMIZATION: Skip if already synced
            if meet_name in synced_meets:
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    
                # Check format of JSON
                # Use filename as meet name as requested
                meet_name = os.path.splitext(filename)[0]

                # Check format of JSON
                if isinstance(file_data, dict) and "events" in file_data:
                    # New Format
                    parsed_events = file_data.get("events", [])
                    date = file_data.get("date")
                else:
                    # Old Format (List)
                    parsed_events = file_data if isinstance(file_data, list) else []
                    date = None

                # 0. Try Web Date Mapping (User's preferred source)
                date = None
                web_date_raw = self.web_date_mapping.get(filename) or self.web_date_mapping.get(os.path.splitext(filename)[0] + ".htm")
                if web_date_raw:
                    date = self.parse_web_date(web_date_raw)
                    if not self.is_date_in_season(date, season, year):
                        date = None
                    else:
                        print(f"  [INFO] Using web date mapping for {filename}: {date}")

                # 1. Try Parsed Date (Content)
                if not date:
                    date = file_data.get("date") if isinstance(file_data, dict) else None
                    if not self.is_date_in_season(date, season, year):
                        if date: print(f"  [INFO] Rejecting content date {date} for {filename} (outside {season} {year})")
                        date = None

                # 2. Filename Date Fallback
                if not date:
                    fn_low = filename.lower()
                    m1 = re.search(r'(\d{1,2})([a-z]{3})(\d{4})', fn_low)
                    m2 = re.search(r'(\d{1,2})[-_](\d{1,2})[-_](\d{4})', fn_low)
                    
                    fn_date = None
                    month_map = {'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
                                'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'}
                    
                    if m1:
                        d_part, m_part, y_part = m1.group(1).zfill(2), m1.group(2), m1.group(3)
                        if m_part in month_map: fn_date = f"{y_part}-{month_map[m_part]}-{d_part}"
                    elif m2:
                        m_part, d_part, y_part = m2.group(1).zfill(2), m2.group(2).zfill(2), m2.group(3)
                        fn_date = f"{y_part}-{m_part}-{d_part}"
                    
                    if self.is_date_in_season(fn_date, season, year):
                        date = fn_date
                
                # 3. Apply manual fixes (Manual Fixes take priority over everything)
                for mc in self.manual_fixes.get('meet_corrections', []):
                    # Check if fragment matches meet_name or filename
                    if mc['meet_name_fragment'].lower() in meet_name.lower() or \
                       mc['meet_name_fragment'].lower() in filename.lower():
                        date = mc['new_date']
                        print(f"  [INFO] Applied manual fix for {filename}: {date}")
                        break

                # 4. Final Fallback Alert
                if not date:
                    date = "Unknown"
                    print(f"\n!!! [ALERT] MISSING DATE: {filename}")
                    print(f"!!! Meet Name: {meet_name}")
                    print(f"!!! No valid date found in content, filename, or manual_fixes.json.")
                    print(f"!!! PLEASE ADD THIS TO backend/manual_fixes.json:")
                    print(f"!!! {{ \"meet_name_fragment\": \"{os.path.splitext(filename)[0]}\", \"new_date\": \"YYYY-MM-DD\" }}\n")
                
                for event_block in parsed_events:
                    # Construct full event name: "Girls 55 Meter Dash"
                    gender = event_block.get("gender", "")
                    event_name = event_block.get("event", "")
                    full_event = f"{gender} {event_name}".strip()
                    
                    for r in event_block.get("results", []):
                        athlete_name = r.get("athlete", "")
                        school = r.get("school", "")
                        mark = r.get("result", "")
                        
                        # Handle Relays: Use list of athletes if available, else school name
                        relay_athletes = r.get("athletes", [])
                        if event_block.get("is_relay"):
                            if relay_athletes:
                                athlete_name = ", ".join(relay_athletes)
                            else:
                                athlete_name = f"{school} Relay"

                        # Apply Athlete Name Fixes
                        athlete_name = self.normalize_athlete_name(athlete_name)

                        # Validation
                        if not athlete_name or not mark or mark.upper() in ["DNS", "SCR"]:
                            continue
                            
                        # Normalize Team
                        team_norm = self.normalize_team_name(school)
                        
                        # Skip if it is still a likely athlete name (bad parse)
                        if self.is_likely_athlete_name(team_norm):
                             # Actually `Sub5ColumnParser` is pretty good, but safety first
                             pass
                        
                        # Insert Athlete (using cache)
                        if athlete_name in athlete_cache:
                            athlete_id = athlete_cache[athlete_name]
                        else:
                            cursor.execute('INSERT INTO athletes (name) VALUES (?)', (athlete_name,))
                            athlete_id = cursor.lastrowid
                            athlete_cache[athlete_name] = athlete_id
                        
                        # Handle Date Sorting (Prelims vs Finals)
                        performance_date = date
                        if date and date != "Unknown":
                            res_type = r.get("type", "").lower()
                            if "prelim" in res_type:
                                performance_date = f"{date}T09:00:00"
                            elif "final" in res_type:
                                performance_date = f"{date}T15:00:00"
                            else:
                                performance_date = f"{date}T12:00:00"

                        # Handle Splits
                        splits_json = json.dumps(r.get("splits", []))

                        # Insert Performance
                        # Deduplication check?
                        cursor.execute('''
                            SELECT id FROM performances 
                            WHERE athlete_id=? AND event=? AND mark=? AND date=?
                        ''', (athlete_id, full_event, mark, performance_date))
                        
                        if not cursor.fetchone():
                            cursor.execute('''
                                INSERT INTO performances 
                                (athlete_id, event, mark, team, date, season, year, meet_name, meet_url, splits)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (athlete_id, full_event, mark, team_norm, performance_date, season, year, meet_name, "", splits_json))
                            total_performances += 1
                            
                if i % 10 == 0 or i == total - 1:
                    prog = int(((i + 1) / total) * 100)
                    self.report_progress(f"Synced {i+1}/{total} files", prog)

            except Exception as e:
                print(f"Error syncing {filename}: {e}")
                
        conn.commit()
        conn.close()
        return total_performances

    def run_full_scrape(self, wipe=True):
        """MAIN ENTRY POINT."""
        # Define the seasons to scrape
        seasons_to_scrape = [
            {
                "year": "2023",
                "season": "Indoor",
                "url": "https://sub5.com/youth-pages/indoor-track/2023-indoor-results/"
            },
            {
                "year": "2024",
                "season": "Indoor",
                "url": "https://sub5.com/youth-pages/indoor-track/2024-indoor-results/"
            },
            {
                "year": "2025",
                "season": "Indoor",
                "url": "https://sub5.com/youth-pages/indoor-track/2025-indoor-results/"
            },
            {
                "year": "2026",
                "season": "Indoor",
                "url": "https://sub5.com/youth-pages/indoor-track/2026-indoor-results/"
            }
        ]

        # 1. Initialize DB
        if wipe:
            self.report_progress("Initializing Database (Fresh Start)...", 0)
        else:
            self.report_progress("Ensuring Database Schema...", 0)
        self.initialize_db(wipe=wipe)
        
        # Get list of already synced meets to skip downloads
        synced_meets = set()
        if not wipe:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT DISTINCT meet_name FROM performances")
                for row in cursor.fetchall():
                    synced_meets.add(row['meet_name'])
            except Exception:
                pass # Table might not exist or be empty
            conn.close()

        total_count = 0
        base_dir = os.path.dirname(os.path.dirname(__file__))

        total_seasons = len(seasons_to_scrape)
        for s_idx, config in enumerate(seasons_to_scrape):
            year = config["year"]
            season = config["season"]
            index_url = config["url"]

            self.report_progress(f"Processing {season} {year}...", int((s_idx / total_seasons) * 100))

            # 2. Directories ...
            archive_dir = os.path.join(base_dir, f'backend/data/sub5_archive/{year}')
            json_dir = os.path.join(base_dir, f'backend/data/parsed_results/{year}')
            
            # 3. Download New Files
            self.report_progress(f"Downloading files for {year}...")
            self.download_missing_files(index_url, archive_dir, synced_meets=synced_meets)
            
            # 4. Parse All Files -> JSON
            self.parse_all_files(archive_dir, json_dir)
            
            # 5. Sync JSON to DB
            count = self.sync_json_to_db(json_dir, season=season, year=year)
            total_count += count
        
        self.report_progress("Scrape Complete!", 100)
        return total_count

if __name__ == "__main__":
    scraper = Sub5Scraper()
    # Run Fresh Start Scrape
    scraper.run_full_scrape()
