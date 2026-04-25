import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import os
import json
import shutil
from datetime import datetime
try:
    from backend.parser import Sub5ColumnParser
except ImportError:
    from parser import Sub5ColumnParser

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
    "Bangor Christian": "Bangor Christian Schools",
    "Bangor Chris": "Bangor Christian Schools",
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
    "Foxcroft Aca": "Foxcroft Academy",
    "Foxcroft": "Foxcroft Academy",
    "Sumner/Narra": "Sumner/Narragaugus",
    "Sumner": "Sumner/Narragaugus",
    "Central High": "Central High School",
    "Central Hig": "Central High School",
    "Central": "Central High School",
    "Presque Isle": "Presque Isle High School",
    "Piscataquis": "Piscataquis Community High School",
    "Penquis Vall": "Penquis Valley High School",
    "Maine Centra": "Maine Central Institute",
    "MCI": "Maine Central Institute",
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
    "Gardiner": "Gardiner High School",
    "Nokomis High": "Nokomis High School",
    "Nokomis": "Nokomis High School",
    "Skowhegan Ar": "Skowhegan Area High School",
    "Skowhegan": "Skowhegan Area High School",
    "Erskine Acad": "Erskine Academy",
    "Erskine": "Erskine Academy",
    "Biddeford High": "Biddeford High School",
    "Biddeford Hi": "Biddeford High School",
    "Bonny Eagle High": "Bonny Eagle High School",
    "Cape Elizabeth High": "Cape Elizabeth High School",
    "Cape Elizabe": "Cape Elizabeth High School",
    "Cheverus High": "Cheverus High School",
    "Cheverus Hig": "Cheverus High School",
    "Deering High": "Deering High School",
    "Deering Hig": "Deering High School",
    "Falmouth High": "Falmouth High School",
    "Falmouth Hig": "Falmouth High School",
    "Freeport High": "Freeport High School",
    "Freeport Hig": "Freeport High School",
    "Fryeburg Acad": "Fryeburg Academy",
    "Gorham High": "Gorham High School",
    "Greely High": "Greely High School",
    "Kennebunk High": "Kennebunk High School",
    "Lewiston High": "Lewiston High School",
    "Marshwood High": "Marshwood High School",
    "Noble High": "Noble High School",
    "Oceanside High": "Oceanside High School",
    "Portland High": "Portland High School",
    "Scarborough High": "Scarborough High School",
    "South Portland High": "South Portland High School",
    "Thornton Acad": "Thornton Academy",
    "Windham High": "Windham High School",
    "Yarmouth High": "Yarmouth High School",
    "York High": "York High School",
    "Boothbay/Wis": "Boothbay/Wiscasset",
    "Boothbay Reg": "Boothbay/Wiscasset",
    "Camden Hills": "Camden Hills Regional High School",
    "Gray New Glo": "Gray New Gloucester High School",
    "Oxford Hills": "Oxford Hills Comprehensive High School",
    "Sacopee Vall": "Sacopee Valley High School",
    "St. Dominic": "St. Dominic Regional High School",
    "Thornton Academy MS": "Thornton Academy",
    "Winthrop Hig": "Winthrop High School",
    "Wiscasset Hi": "Boothbay/Wiscasset",
    "York High Sc": "York High School",
    "Medomak Vall": "Medomak Valley High School",
    "Mountain Val": "Mountain Valley High School",
    "Traip Academ": "Traip Academy",
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
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.synced_meets = set() # (year, meet_name)

    def _get_with_retry(self, url, max_retries=3):
        for i in range(max_retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return response
            except Exception as e:
                if i == max_retries - 1:
                    print(f"Failed to fetch {url} after {max_retries} attempts: {e}")
                    raise
                import time
                time.sleep(2 ** i) # Exponential backoff
        return None

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

    def normalize_team_name(self, name, all_teams=None):
        if not name: return "Unknown"
        name = name.strip()
        
        # 1. Clean leading numeric status codes (e.g., "01-Unattached" -> "Unattached")
        name = re.sub(r'^\d+[-\s]*', '', name)

        # 2. Normalize Unattached
        if "unattach" in name.lower() or name.lower() == "un":
            return "Unattached"

        # 3. Clean trailing years (e.g., "School 2021" -> "School")
        name = re.sub(r'\s+\d{4}$', '', name)

        # 4. Protection: If name looks like a time mark, it's a leak
        # e.g., ":05.82", "4:33.18"
        if re.match(r'^:?\d+[:.]\d+', name) or re.match(r'^\d+-\d+\.?\d*$', name):
            return "Unknown"

        # Pre-process: strip common prefixes
        # (Case-insensitive removal of "M ", "JR ", "W ", "FR ", "SO ", "SR ")
        name = re.sub(r'^(M|JR|W|FR|SO|SR)\s+', '', name, flags=re.IGNORECASE)
        
        # Clean up any suffix artifacts
        name = re.sub(r'\s+J[\d\.\-\':]+.*', '', name)
        
        name = name.strip()
        
        # Strip geographic suffixes like ", ME" or ", Freeport"
        if "," in name:
            name = name.split(',')[0].strip()
        
        # 4. Dynamic Acronym Matching (Objective Matcher)
        # Handles cases like PCHS -> Piscataquis Community High School, SMC -> Southern Maine Catholic
        if all_teams and len(name) >= 2 and len(name) <= 5 and name.isupper():
            matches = []
            for fuller_name in all_teams:
                if len(fuller_name) <= len(name): continue
                
                # Case 1: First letter of every word
                acr_full = "".join(re.findall(r'\b\w', fuller_name)).upper()
                
                # Case 2: Scrub common suffixes like "High School"
                base = re.sub(r'\s+(High School|Academy|Regional High School|Area High School|Schools|Memorial High School|Comprehensive High School|Christian Schools)$', '', fuller_name, flags=re.IGNORECASE)
                acr_base = "".join(re.findall(r'\b\w', base)).upper()
                
                if name in [acr_full, acr_base]:
                    matches.append(fuller_name)
            
            unique_matches = list(set(matches))
            if len(unique_matches) == 1:
                return unique_matches[0]

        # 5. Middle School / Junior High Protection
        # Avoid lumping MS/JH into High School mappings
        ms_tokens = ["ms", "middle", "junior high", "jh", "elementary", "elem", "elementa", "primary", "interme"]
        is_ms_token = any(f" {t}" in name.lower() or name.lower().endswith(f" {t}") or name.lower().endswith(t) for t in ms_tokens)
        
        # 6. Manual Mappings
        for key, val in TEAM_MAPPING.items():
            # If it's an MS name, only accept exact or very specific mappings
            if is_ms_token:
                if name.lower() == key.lower():
                    return val
                continue
                
            if name.lower().startswith(key.lower()):
                return val

        # 7. Dynamic Substring Absorption
        if all_teams:
            for fuller_name in sorted(all_teams, key=len, reverse=True):
                # Don't absorb if one is MS and the other isn't
                fuller_is_ms = any(f" {t}" in fuller_name.lower() or fuller_name.lower().endswith(t) for t in ms_tokens)
                if is_ms_token != fuller_is_ms:
                    continue
                    
                if len(fuller_name) > len(name) and fuller_name.lower().startswith(name.lower()):
                    return fuller_name
            
        return name

    def normalize_athlete_name(self, name):
        if not name: return ""
        name = name.strip()
        # strip leading rank leakage (insurance)
        name = re.sub(r'^[\s#\-]*\d+[\s.\-]*', '', name).strip()
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
        
        # 1. If it's a known school name (with school keywords), it's not an athlete
        school_keywords = ['High', 'School', 'Academy', 'Acad', 'Institute', 'MCI', 'GSA', 'MDI', 'GSA', 'EMITL', 'PVC', 'Relay', 'Track', 'Field', 'Team', 'Club', 'Middle', 'University', 'College']
        if any(k.lower() in name_clean.lower() for k in school_keywords):
            return False
            
        short_keywords = ['EL', 'HS', 'MS', 'U VT']
        for sk in short_keywords:
            if re.search(r'\b' + re.escape(sk) + r'\b', name_clean, re.I):
                return False

        # 2. If it looks like a person's name: "First Last" or "First M. Last"
        if re.match(r'^[A-Z][a-z.\']+\s+([A-Z][a-z.\']+\s*){1,2}$', name_clean):
            return True

        # 3. If it contains a comma, it's almost certainly an athlete "Last, First"
        if ',' in name_clean:
            return True

        # If it looks like a track mark (digits + special chars)
        # e.g. "12.34", "4-05", "1:23.45", "12-01.50", "12.34q"
        # We check for digits and symbols common in marks
        if re.search(r'\d', name_clean) and any(c in name_clean for c in '.:-\''):
            return False

        # If it contains 3 or more consecutive spaces, it's likely a merged column error
        if '   ' in name_clean:
            return True
            
        # Very short names that aren't known schools
        if len(name_clean) < 3:
            return True
            
        return False

    def mark_is_reasonable(self, mark, event_name):
        """
        Validates if a track & field mark is reasonable for the given event.
        Prevents garbage data from being inserted.
        """
        if not mark: return False
        
        m = mark.upper().strip()
        # Accept standard non-numeric marks
        if m in ["DQ", "DNS", "DNF", "NH", "NM", "FOUL", "SCR", "ND", "NT", "X", "ND"]:
            return True
            
        # Basic numeric check
        if not re.search(r'\d', m):
            return False
            
        # If it has many colons or dots, it might be a series or garbage
        if m.count(':') > 2 or m.count('.') > 2:
            return False

        try:
            # Event-specific bounds (very loose to avoid false positives)
            
            # Distance events (High Jump, Long Jump, Shot Put, etc.)
            if any(x in event_name.lower() for x in ["jump", "put", "throw", "vault", "discus", "javelin"]):
                # Should have ' or " or - or be a simple float. 
                # Avoid very long strings.
                if len(m) > 10: return False
                return True
                
            # Time events
            # Convert to seconds for easier bounds check
            total_seconds = 0
            parts = m.split(':')
            if len(parts) == 1:
                total_seconds = float(parts[0])
            elif len(parts) == 2:
                total_seconds = float(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                total_seconds = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            
            # 55m / 60m / 100m dashes (usually 6-25 seconds)
            if any(x in event_name for x in ["55", "60", "100"]):
                return 5.0 < total_seconds < 40.0
                
            # 1600m / 1 Mile (usually 4-10 mins)
            if "1600" in event_name or "1 Mile" in event_name:
                return 180.0 < total_seconds < 900.0
            
            # Relays / Longer runs (avoid > 2 hours)
            if total_seconds > 7200:
                return False

            return True 
        except:
            # If we can't parse it as a number but it has digits, let's be safe and reject if it looks like garbage
            if len(m) > 12: return False
            return True

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
                    grade TEXT,
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
        print(f"Fetching meet links and dates from: {year_url}")
        try:
            response = self._get_with_retry(year_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            links_with_dates = {} # {url: date_text}
            
            # Sub5 pages sometimes have frames
            frames = soup.find_all(['frame', 'iframe'], src=True)
            if frames:
                for frame in frames:
                    from urllib.parse import urljoin
                    frame_url = urljoin(year_url, frame['src'])
                    links_with_dates.update(self.get_meet_links_with_dates(frame_url))
            
            # Parse main page
            links_with_dates.update(self.get_meet_links_with_dates(year_url, soup))
            
            return links_with_dates
        except Exception as e:
            print(f"Error fetching meet links from {year_url}: {e}")
            return {}

    def get_meet_links_with_dates(self, url, soup=None):
        if not soup:
            try:
                res = self._get_with_retry(url)
                soup = BeautifulSoup(res.text, 'html.parser')
            except:
                return {}
        
        mapping = {}
        
        # Filter link function
        def is_valid_result_link(h):
            h = h.lower()
            if not (h.endswith('.htm') or h.endswith('.html')): return False
            
            # Explicitly ignore known non-result patterns or large archive files
            if any(x in h for x in ['meetresults', 'resultspPVC', 'index.htm', 'contact.htm', 'about.htm', 'links.htm']):
                return False 
            
            # Core keywords that always indicate results
            keywords = [
                'result', 'emitl', 'pvc', 'states', 'class', 'champ', 'meet', 'inv', 
                'scores', 'relays', 'festival', 'open', 'youth', 'ms', 'jh', 'middle', 'junior',
                'boys', 'girls', 'kvac', 'wmc', 'smaa', 'mvc', 'frosh', 'freshman', 'bangor',
                'gsa', 'bucksport', 'ellsworth', 'mdi', 'orono', 'oldtown', 'brewer', 'falmouth'
            ]
            if any(x in h for x in keywords): return True
            
            # Heuristic: Filenames with digits are almost always specific meet results (dates/meet numbers)
            # e.g., 'oldtown20may2023.htm', 'brewer19april2023.htm'
            filename = h.split('/')[-1]
            if re.search(r'\d', filename):
                return True
                
            return False

        # Search for tables
        for row in soup.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) >= 2:
                # First column is usually the date
                date_text = cols[0].get_text(strip=True)
                # Second/Third usually has the links
                for col in cols[1:]:
                    for a in col.find_all('a', href=True):
                        href = a['href']
                        if is_valid_result_link(href):
                            if not href.startswith('http'):
                                from urllib.parse import urljoin
                                href = urljoin(url, href)
                            mapping[href] = date_text
        
        # Fallback for links NOT in tables
        for a in soup.find_all('a', href=True):
            href = a['href']
            if is_valid_result_link(href):
                if href not in mapping:
                    if not href.startswith('http'):
                        from urllib.parse import urljoin
                        href = urljoin(url, href)
                    mapping[href] = None # No date found in table context
        
        return mapping

    def download_missing_files(self, index_url, archive_dir, synced_meets=None, curr_year=None, curr_season=None):
        """Downloads new .htm/.html files from the index URL to the archive directory."""
        if not os.path.exists(archive_dir):
            os.makedirs(archive_dir)
            
        print(f"Checking for new files at {index_url}...")
        links_map = self.get_meet_links(index_url)
        print(f"Found {len(links_map)} meet links.")
        
        saved_files = []
        mapping_changed = False

        for link, date_str in links_map.items():
            filename = link.split('/')[-1]
            if '?' in filename: filename = filename.split('?')[0]
            if not filename.lower().endswith(('.htm', '.html')):
                filename += ".htm"
                
            # Update internal mapping
            if date_str:
                self.web_date_mapping[filename] = date_str
                mapping_changed = True

            save_path = os.path.join(archive_dir, filename)
            meet_name = os.path.splitext(filename)[0]

            # SKIP if already in DB
            if synced_meets and curr_year and curr_season and (curr_year, curr_season, meet_name) in synced_meets:
                continue
            
            if not os.path.exists(save_path):
                print(f"Downloading {filename}...")
                try:
                    res = self._get_with_retry(link)
                    with open(save_path, 'wb') as f:
                        f.write(res.content)
                    saved_files.append(save_path)
                except Exception as e:
                    print(f"Failed to download {link}: {e}")
        
        if mapping_changed:
            self.save_web_date_mapping()
                
        return saved_files

    def save_web_date_mapping(self):
        mapping_path = os.path.join(os.path.dirname(__file__), 'web_date_mapping.json')
        try:
            with open(mapping_path, 'w') as f:
                json.dump(self.web_date_mapping, f, indent=4)
        except Exception as e:
            print(f"Error saving web_date_mapping: {e}")

    def parse_all_files(self, archive_dir, json_dir):
        """Runs the Sub5ColumnParser on all files in the archive dir."""
        if not os.path.exists(json_dir):
            os.makedirs(json_dir)
            
        files = [f for f in os.listdir(archive_dir) if f.lower().endswith(('.htm', '.html'))]
        total = len(files)
        self.report_progress(f"Parsing {total} files...", 0)
        
        detector = FormatDetector(self)
        parsed_count = 0
        for i, filename in enumerate(files):
            input_path = os.path.join(archive_dir, filename)
            output_filename = os.path.splitext(filename)[0] + ".json"
            output_path = os.path.join(json_dir, output_filename)
            
            try:
                # Skip if already parsed (Always re-parse for now)
                # if os.path.exists(output_path):
                #     continue

                with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                
                # Use strategy chain for parsing
                # (Note: we don't have the full meet_url here easily, 
                # but filename is often enough for the detector's secondary checks if needed)
                parser_instance = detector.get_parser(text, filename)
                
                # determine season from the archive_dir path components
                # path is .../sub5_archive/year/season/filename.htm
                path_parts = input_path.split(os.sep)
                season_label = path_parts[-2] if len(path_parts) > 2 else "Indoor"
                
                results = parser_instance.parse(text, filename, season_label)
                
                # Support structured output from newer parsers or list output from Sub5ColumnParser
                data_to_save = results
                if isinstance(results, list) and len(results) > 0 and "event" in results[0]:
                    # Format for new DB sync logic
                    data_to_save = {"events": results, "date": results[0].get("date")} if "date" in results[0] else results

                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(data_to_save, f, indent=4, ensure_ascii=False)
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
        # Check `parser.py`: It returns `event_results` list.
        # Checking `parser.py`... 
        # logic extracts data from the file content but maybe doesn't return the global meet date ?
        # Checking `parser.py`... 
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

        # Get list of already synced meet names and all unique team names for dynamic normalization
        synced_meets = set()
        all_teams = set()
        
        # Seed all_teams with our known canonical names from TEAM_MAPPING
        for val in TEAM_MAPPING.values():
            all_teams.add(val)

        cursor.execute("SELECT DISTINCT year, meet_name FROM performances")
        for row in cursor.fetchall():
            synced_meets.add((row['year'], row['meet_name']))
        
        cursor.execute("SELECT DISTINCT team FROM performances")
        for row in cursor.fetchall():
            if row['team']: all_teams.add(row['team'])

        # PRE-SYNC PASS: Collect all team names from the JSON files about to be synced
        # This prevents order-dependency issues (e.g. seeing "Fryeburg Aca" before "Fryeburg Academy")
        self.report_progress("Pre-scanning team names for normalization...", 0)
        for filename in files:
            if (year, os.path.splitext(filename)[0]) in synced_meets: continue
            try:
                with open(os.path.join(json_dir, filename), 'r') as f:
                    data = json.load(f)
                    events = data.get("events", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    for eb in events:
                        for res in eb.get("results", []):
                            team = res.get("school")
                            if team: 
                                # We MUST normalize through TEAM_MAPPING here too so all_teams 
                                # gets the canonical version of everything we find in the files.
                                team_clean = team.strip()
                                # Basic normalization for pre-scan
                                team_norm = self.normalize_team_name(team_clean, all_teams=all_teams)
                                all_teams.add(team_norm)
            except: pass

        for i, filename in enumerate(files):
            file_path = os.path.join(json_dir, filename)
            meet_name = os.path.splitext(filename)[0]

            # OPTIMIZATION: Skip if already synced
            if (year, meet_name) in synced_meets:
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
                
                # Reconstruct meet_url if possible, otherwise use filename
                # (Note: full URL is hard to recover here without a mapping, but filename is what qaqc uses)
                meet_url = filename
                
                if filename == "ResultsSMAA2.json":
                    print(f"  [DEBUG] Syncing {filename}, events found: {len(parsed_events)}")
                
                # Reconstruct meet_url if possible, otherwise use filename
                meet_url = filename
                
                for event_block in parsed_events:
                    # Check if this is an event block (has 'results') or a flat performance record
                    if isinstance(event_block, dict) and "results" in event_block:
                        # Nested Format (Event block with multiple results)
                        gender = event_block.get("gender", "")
                        event_name = event_block.get("event", "")
                        full_event = f"{gender} {event_name}".strip()
                        is_relay = event_block.get("is_relay", False)
                        results_list = event_block.get("results", [])
                        if filename == "ResultsSMAA2.json":
                            print(f"    [DEBUG] Event: {full_event}, Results: {len(results_list)}")
                    else:
                        # Flat Format (Single performance record per entry)
                        full_event = event_block.get("event", "").strip()
                        is_relay = "Relay" in full_event
                        results_list = [event_block]

                    for r in results_list:
                        athlete_name = r.get("athlete") or r.get("athlete_name") or ""
                        school = r.get("school") or r.get("team") or ""
                        mark = r.get("result") or r.get("mark") or ""
                        
                        # Handle Relays: Use list of athletes if available, else school name
                        relay_athletes = r.get("athletes", [])
                        if is_relay:
                            if relay_athletes:
                                athlete_name = ", ".join(relay_athletes)
                            elif not athlete_name:
                                athlete_name = f"{school} Relay"

                        # Apply Athlete Name Fixes
                        athlete_name = self.normalize_athlete_name(athlete_name)

                        # Validation
                        if not athlete_name or not mark or mark.upper() in ["DNS", "SCR"]:
                            continue
                            
                        # Normalize Team
                        team_norm = self.normalize_team_name(school, all_teams=all_teams)
                        # Add to known teams if it looks like a "canonical" (longer) version
                        if team_norm and team_norm not in all_teams:
                            all_teams.add(team_norm)
                        
                        # Skip if it is a numeric mark that leaked into the team field
                        if self.is_likely_athlete_name(team_norm):
                             if filename == "ResultsSMAA2.json":
                                 print(f"      [DEBUG] Rejected Team {team_norm} for athlete {athlete_name}")
                             continue
                        
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
                        # Deduplication check
                        cursor.execute('''
                            SELECT id FROM performances 
                            WHERE athlete_id=? AND event=? AND mark=? AND date=? AND meet_name=?
                        ''', (athlete_id, full_event, mark, performance_date, meet_name))
                        
                        if not cursor.fetchone():
                            cursor.execute('''
                                INSERT INTO performances 
                                (athlete_id, event, mark, team, date, season, year, meet_name, meet_url, splits, grade)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (athlete_id, full_event, mark, team_norm, performance_date, f"{year} {season}", year, meet_name, meet_url, splits_json, r.get("grade", "")))
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
                "year": "2022",
                "season": "Indoor",
                "url": "https://sub5.com/youth-pages/indoor-track/2022-indoor-results/"
            },
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
            },
            {
                "year": "2022",
                "season": "Outdoor",
                "url": "https://sub5.com/youth-pages/outdoor-track/2022-outdoor-results/"
            },
            {
                "year": "2023",
                "season": "Outdoor",
                "url": "https://sub5.com/youth-pages/outdoor-track/2023-outdoor-results/"
            },
            {
                "year": "2024",
                "season": "Outdoor",
                "url": "https://sub5.com/youth-pages/outdoor-track/2024-outdoor-results/"
            },
            {
                "year": "2025",
                "season": "Outdoor",
                "url": "https://sub5.com/youth-pages/outdoor-track/2025-outdoor-results/"
            },
            {
                "year": "2026",
                "season": "Outdoor",
                "url": "https://sub5.com/youth-pages/outdoor-track/2026-outdoor-results/"
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
                cursor.execute("SELECT DISTINCT year, season, meet_name FROM performances")
                for row in cursor.fetchall():
                    synced_meets.add((row['year'], row['season'], row['meet_name']))
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

            # 2. Directories
            archive_dir = os.path.join(base_dir, f'backend/data/sub5_archive/{year}/{season}')
            json_dir = os.path.join(base_dir, f'backend/data/parsed_results/{year}/{season}')
            
            # 3. Download New Files
            self.report_progress(f"Downloading files for {season} {year}...")
            self.download_missing_files(index_url, archive_dir, synced_meets=synced_meets, curr_year=year, curr_season=season)
            
            # 4. Parse All Files -> JSON
            self.parse_all_files(archive_dir, json_dir)
            
            # 5. Sync JSON to DB
            count = self.sync_json_to_db(json_dir, season=season, year=year)
            total_count += count
        
        self.report_progress("Scrape Complete!", 100)
        return total_count

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Sub5 Track Scraper')
    parser.add_argument('--year', help='Specific year to scrape')
    parser.add_argument('--season', help='Specific season (Indoor/Outdoor) to scrape')
    parser.add_argument('--no-wipe', action='store_true', help='Do not wipe database before scraping')
    args = parser.parse_args()

    scraper = Sub5Scraper()
    wipe = not args.no_wipe
    
    if args.year or args.season:
        # Targeted scrape
        all_seasons = [
            {"year": "2022", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2022-indoor-results/"},
            {"year": "2023", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2023-indoor-results/"},
            {"year": "2024", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2024-indoor-results/"},
            {"year": "2025", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2025-indoor-results/"},
            {"year": "2026", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2026-indoor-results/"},
            {"year": "2022", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2022-outdoor-results/"},
            {"year": "2023", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2023-outdoor-results/"},
            {"year": "2024", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2024-outdoor-results/"},
            {"year": "2025", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2025-outdoor-results/"},
            {"year": "2026", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2026-outdoor-results/"}
        ]
        
        filtered = [s for s in all_seasons if 
                    (not args.year or s['year'] == args.year) and 
                    (not args.season or s['season'].lower() == args.season.lower())]
        
        if not filtered:
            print(f"No matching season found for Year: {args.year}, Season: {args.season}")
        else:
            # Modify run_full_scrape to accept a custom list or just do manual loop
            # For simplicity, we'll just modify the scraper instance's internal list if we could, 
            # but run_full_scrape rebuilds it. Let's just run initialize_db and then loop.
            
            wipe = not args.no_wipe
            scraper.initialize_db(wipe=wipe)
            base_dir = os.path.dirname(os.path.dirname(__file__))
            
            for config in filtered:
                year = config["year"]
                season = config["season"]
                index_url = config["url"]
                print(f"Targeted Scrape: {season} {year}")
                
                archive_dir = os.path.join(base_dir, f'backend/data/sub5_archive/{year}/{season}')
                json_dir = os.path.join(base_dir, f'backend/data/parsed_results/{year}/{season}')
                
                scraper.download_missing_files(index_url, archive_dir, synced_meets=set(), curr_year=year, curr_season=season)
                scraper.parse_all_files(archive_dir, json_dir)
                scraper.sync_json_to_db(json_dir, season=season, year=year)
            
            print("Targeted Scrape Complete!")
    else:
        # Run Scrape (Everything)
        scraper.run_full_scrape(wipe=wipe)
