import requests
from bs4 import BeautifulSoup
import re
import os
import json
from datetime import datetime
from backend.parser import Sub5ColumnParser
from backend.parsers.detector import FormatDetector
from backend.json_store import (
    load_scrape_state, save_scrape_state, load_athletes, save_athletes,
    add_performances_for_team, rebuild_manifest, slugify_athlete,
    TEAMS_DIR, SCRAPE_STATE_PATH
)

# Configuration
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
    "Deer Isle St": "Deer Isle-Stonington High School",
    "DI- Stonington": "Deer Isle-Stonington High School",
    "DI Stonington": "Deer Isle-Stonington High School",
    "Spruce Mountain": "Spruce Mountain High School",
    "Mt. View": "Mt. View High School",
    "Mt View": "Mt. View High School",
    "Calais": "Calais High School",
    "Mt. Abram": "Mt. Abram High School",
    "Mt Abram": "Mt. Abram High School",
    "Madawaska": "Madawaska High School",
    "Penobscot Valley": "Penobscot Valley High School",
    "Richmond": "Richmond High School",
    "Easton": "Easton High School",
    "Vinalhaven": "Vinalhaven High School",
    "Greater Portland": "Greater Portland High School",
    "Chop Point": "Chop Point High School",
    "Old Orchard": "Old Orchard Beach High School",
    "Greater Houlton": "Houlton High School",
    "Houlton": "Houlton High School",
    "Maine Coast Waldorf": "NYA Maine Coast Waldorf",
    "Wiscasset": "Boothbay/Wiscasset",
}

class Sub5ScraperV2:
    def __init__(self, progress_callback=None):
        self.headers = {'User-Agent': 'Mozilla/5.0'}
        self.manual_fixes = self.load_manual_fixes()
        self.web_date_mapping = self.load_web_date_mapping()
        self.progress_callback = progress_callback
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def mark_is_reasonable(self, mark, event):
        """Basic sanity check to avoid parsing junk like 'H# 1' as a result."""
        if not mark or len(mark) < 2: return False
        # Field event marks like "38-05" or "5-02"
        if '-' in mark: return True
        # Track marks like "4:55.22" or "10.55"
        if '.' in mark: return True
        # Standard status codes
        if mark.upper() in ["DQ", "NH", "FOUL", "NM", "DNS", "DNF", "SCR"]:
            return True
        return False

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
                time.sleep(2 ** i)
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
        if not date_str: return None
        date_str = re.sub(r'(\d{1,2})-\d{1,2}', r'\1', date_str)
        try:
            dt = datetime.strptime(date_str, "%B %d, %Y")
            return dt.strftime("%Y-%m-%d")
        except:
            try:
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

    def normalize_team_name(self, name, all_teams=None):
        if not name: return "Unknown"
        name = name.strip()
        name = re.sub(r'^\d+[-\s]*', '', name)
        if "unattach" in name.lower() or name.lower() == "un":
            return "Unattached"
        name = re.sub(r'\s+\d{4}$', '', name)
        if re.match(r'^:?\d+[:.]\d+', name) or re.match(r'^\d+-\d+\.?\d*$', name):
            return "Unknown"
        name = re.sub(r'^(M|JR|W|FR|SO|SR)\s+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+J[\d\.\-\':]+.*', '', name)
        name = name.strip()
        if "," in name:
            name = name.split(',')[0].strip()
        
        # Dynamic Acronym Matching
        if all_teams and len(name) >= 2 and len(name) <= 5 and name.isupper():
            matches = []
            for fuller_name in all_teams:
                if len(fuller_name) <= len(name): continue
                acr_full = "".join(re.findall(r'\b\w', fuller_name)).upper()
                base = re.sub(r'\s+(High School|Academy|Regional High School|Area High School|Schools|Memorial High School|Comprehensive High School|Christian Schools)$', '', fuller_name, flags=re.IGNORECASE)
                acr_base = "".join(re.findall(r'\b\w', base)).upper()
                if name in [acr_full, acr_base]:
                    matches.append(fuller_name)
            unique_matches = list(set(matches))
            if len(unique_matches) == 1:
                return unique_matches[0]

        ms_tokens = ["ms", "middle", "junior high", "jh", "elementary", "elem", "elementa", "primary", "interme"]
        is_ms_token = any(f" {t}" in name.lower() or name.lower().endswith(f" {t}") or name.lower().endswith(t) for t in ms_tokens)
        
        for key, val in TEAM_MAPPING.items():
            if is_ms_token:
                if name.lower() == key.lower():
                    return val
                continue
            if name.lower().startswith(key.lower()):
                return val

        if all_teams:
            for fuller_name in sorted(all_teams, key=len, reverse=True):
                fuller_is_ms = any(f" {t}" in fuller_name.lower() or fuller_name.lower().endswith(t) for t in ms_tokens)
                if is_ms_token != fuller_is_ms:
                    continue
                if len(fuller_name) > len(name) and fuller_name.lower().startswith(name.lower()):
                    return fuller_name
            
        return name

    def normalize_athlete_name(self, name):
        if not name: return ""
        name = name.strip()
        name = re.sub(r'^[\s#\-]*\d+[\s.\-]*', '', name).strip()
        for ac in self.manual_fixes.get('athlete_corrections', []):
            if ac['old_name'].lower() == name.lower():
                return ac['new_name']
        return name

    def is_date_in_season(self, date_str, season, year):
        if not date_str: return False
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            year_val = int(year)
            if season == "Indoor":
                start_date = datetime(year_val - 1, 11, 1)
                end_date = datetime(year_val, 3, 31)
                return start_date <= dt <= end_date
            elif season == "Outdoor":
                start_date = datetime(year_val, 3, 1)
                end_date = datetime(year_val, 6, 30)
                return start_date <= dt <= end_date
            return True
        except:
            return False

    def is_likely_athlete_name(self, name):
        if not name: return True
        name_clean = name.strip()
        school_keywords = ['High', 'School', 'Academy', 'Acad', 'Institute', 'MCI', 'GSA', 'MDI', 'GSA', 'EMITL', 'PVC', 'Relay', 'Track', 'Field', 'Team', 'Club', 'Middle', 'University', 'College', 'Mt.', 'Mountain', 'Valley', 'Point', 'Portland', 'Christian', 'Catholic', 'Prep', 'Charter', 'Regional', 'Community', 'Consolidated']
        if any(k.lower() in name_clean.lower() for k in school_keywords):
            return False
        short_keywords = ['EL', 'HS', 'MS', 'U VT']
        for sk in short_keywords:
            if re.search(r'\b' + re.escape(sk) + r'\b', name_clean, re.I):
                return False
        if re.match(r'^[A-Z][a-z.\']+\s+([A-Z][a-z.\']+\s*){1,2}$', name_clean):
            return True
        if ',' in name_clean:
            return True
        if re.search(r'\d', name_clean) and any(c in name_clean for c in '.:-\''):
            return False
        if '   ' in name_clean:
            return True
        if len(name_clean) < 3:
            return True
        return False

    def get_meet_links(self, year_url):
        try:
            response = self._get_with_retry(year_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            links_with_dates = {}
            frames = soup.find_all(['frame', 'iframe'], src=True)
            if frames:
                for frame in frames:
                    from urllib.parse import urljoin
                    frame_url = urljoin(year_url, frame['src'])
                    links_with_dates.update(self.get_meet_links_with_dates(frame_url))
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
        def is_valid_result_link(h):
            h = h.lower()
            if not (h.endswith('.htm') or h.endswith('.html') or h.endswith('.pdf')): return False
            if any(x in h for x in ['meetresults', 'resultspPVC', 'index.htm', 'contact.htm', 'about.htm', 'links.htm']):
                return False 
            keywords = ['result', 'emitl', 'pvc', 'states', 'class', 'champ', 'meet', 'inv', 'scores', 'relays', 'festival', 'open', 'youth', 'ms', 'jh', 'middle', 'junior', 'boys', 'girls', 'kvac', 'wmc', 'smaa', 'mvc', 'frosh', 'freshman', 'bangor', 'gsa', 'bucksport', 'ellsworth', 'mdi', 'orono', 'oldtown', 'brewer', 'falmouth']
            if any(x in h for x in keywords): return True
            filename = h.split('/')[-1]
            if re.search(r'\d', filename): return True
            return False

        for row in soup.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) >= 2:
                date_text = cols[0].get_text(strip=True)
                for col in cols[1:]:
                    for a in col.find_all('a', href=True):
                        href = a['href']
                        if is_valid_result_link(href):
                            if not href.startswith('http'):
                                from urllib.parse import urljoin
                                href = urljoin(url, href)
                            mapping[href] = date_text
        for a in soup.find_all('a', href=True):
            href = a['href']
            if is_valid_result_link(href):
                if href not in mapping:
                    if not href.startswith('http'):
                        from urllib.parse import urljoin
                        href = urljoin(url, href)
                    mapping[href] = None
        return mapping

    def download_missing_files(self, index_url, archive_dir, synced_meets=None, curr_year=None, curr_season=None):
        if not os.path.exists(archive_dir):
            os.makedirs(archive_dir)
        links_map = self.get_meet_links(index_url)
        saved_files = []
        mapping_changed = False
        for link, date_str in links_map.items():
            filename = link.split('/')[-1]
            if '?' in filename: filename = filename.split('?')[0]
            # Preserve .pdf extension; only append .htm for non-typed links
            if not filename.lower().endswith(('.htm', '.html', '.pdf')):
                filename += ".htm"
            if date_str:
                self.web_date_mapping[filename] = date_str
                mapping_changed = True
            save_path = os.path.join(archive_dir, filename)
            meet_name = os.path.splitext(filename)[0]
            meet_key = f"{curr_year}_{curr_season}_{meet_name}"
            if synced_meets and meet_key in synced_meets:
                continue
            if not os.path.exists(save_path):
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
        if not os.path.exists(json_dir):
            os.makedirs(json_dir)
        files = [f for f in os.listdir(archive_dir) if f.lower().endswith(('.htm', '.html', '.pdf'))]
        total = len(files)
        detector = FormatDetector(self)
        parsed_count = 0
        for i, filename in enumerate(files):
            input_path = os.path.join(archive_dir, filename)
            output_filename = os.path.splitext(filename)[0] + ".json"
            output_path = os.path.join(json_dir, output_filename)
            try:
                if filename.lower().endswith('.pdf'):
                    from backend.parser import Sub5ColumnParser
                    raw = Sub5ColumnParser.pdf_to_text(input_path)
                    if raw is None:
                        print(f"Skipping PDF (pdftotext unavailable): {filename}")
                        continue
                    text = Sub5ColumnParser.clean_pdf_text(raw)
                else:
                    with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                parser_instance = detector.get_parser(text, filename)
                path_parts = input_path.split(os.sep)
                season_label = path_parts[-2] if len(path_parts) > 2 else "Indoor"
                results = parser_instance.parse(text, filename, season_label)
                data_to_save = results
                if isinstance(results, list) and len(results) > 0 and "event" in results[0]:
                    data_to_save = {"events": results, "date": results[0].get("date")} if "date" in results[0] else results
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(data_to_save, f, indent=4, ensure_ascii=False)
                parsed_count += 1
                if i % 10 == 0 or i == total - 1:
                    prog = int(((i + 1) / total) * 100)
                    self.report_progress(f"Parsed {i+1}/{total} files", prog)
            except Exception as e:
                print(f"Error parsing {filename}: {e}")
        return parsed_count

    def sync_json_to_store(self, json_dir, season="Indoor", year="2026", athletes=None, scrape_state=None):
        if not os.path.exists(json_dir):
            return 0
        files = [f for f in os.listdir(json_dir) if f.endswith('.json')]
        total = len(files)
        total_performances = 0
        all_teams_data = {} # team_slug -> list of new perfs

        synced_meets = scrape_state.get('synced_meets', {})
        
        # Pre-scan for team normalization
        all_known_teams = set()
        for fn in os.listdir(TEAMS_DIR):
            if fn.endswith('.json'):
                all_known_teams.add(fn[:-5].replace('_', ' '))

        for i, filename in enumerate(files):
            file_path = os.path.join(json_dir, filename)
            meet_name = os.path.splitext(filename)[0]
            meet_key = f"{year}_{season}_{meet_name}"
            if meet_key in synced_meets:
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                
                if isinstance(file_data, dict) and "events" in file_data:
                    parsed_events = file_data.get("events", [])
                    date = file_data.get("date")
                else:
                    parsed_events = file_data if isinstance(file_data, list) else []
                    date = None

                web_date_raw = (
                    self.web_date_mapping.get(filename)
                    or self.web_date_mapping.get(os.path.splitext(filename)[0] + ".htm")
                    or self.web_date_mapping.get(os.path.splitext(filename)[0] + ".pdf")
                )
                if web_date_raw:
                    parsed_d = self.parse_web_date(web_date_raw)
                    if self.is_date_in_season(parsed_d, season, year):
                        date = parsed_d
                
                # Manual fixes
                for mc in self.manual_fixes.get('meet_corrections', []):
                    if mc['meet_name_fragment'].lower() in meet_name.lower() or mc['meet_name_fragment'].lower() in filename.lower():
                        date = mc['new_date']
                        break
                
                if not date: date = "Unknown"
                meet_url = filename

                for event_block in parsed_events:
                    if isinstance(event_block, dict) and "results" in event_block:
                        gender = event_block.get("gender", "")
                        event_name = event_block.get("event", "")
                        full_event = f"{gender} {event_name}".strip()
                        is_relay = event_block.get("is_relay", False)
                        results_list = event_block.get("results", [])
                    else:
                        full_event = event_block.get("event", "").strip()
                        is_relay = "Relay" in full_event
                        results_list = [event_block]

                    for r in results_list:
                        athlete_name = r.get("athlete") or r.get("athlete_name") or ""
                        school = r.get("school") or r.get("team") or ""
                        mark = r.get("result") or r.get("mark") or ""
                        relay_athletes = r.get("athletes", [])
                        if is_relay:
                            if relay_athletes: athlete_name = ", ".join(relay_athletes)
                            elif not athlete_name: athlete_name = f"{school} Relay"
                            # Reject relay records whose school field looks like "LastName, FirstName ..."
                            # — these are individual-event rows from two-column PDFs that bled into
                            # the relay section during parsing.
                            if re.match(r'^[A-Za-z][A-Za-z\'-]+,\s+[A-Za-z]', school):
                                continue

                        athlete_name = self.normalize_athlete_name(athlete_name)
                        if not athlete_name or not mark or mark.upper() in ["DNS", "SCR"]: continue

                        # Reject marks whose format contradicts the event type:
                        # time-format (M:SS.ss) in a field event, or distance-format (F-I) in a running event.
                        _ev_low = full_event.lower()
                        _is_field_ev = any(k in _ev_low for k in ('jump', 'put', 'throw', 'vault', 'discus', 'javelin'))
                        _is_track_ev = any(k in _ev_low for k in ('dash', 'run', 'hurdles', 'mile', 'relay', '4x', 'walk'))
                        _has_time_fmt = ':' in mark and '.' in mark
                        _has_dist_fmt = bool(re.match(r'^\d+-\d+', mark))
                        if _is_field_ev and _has_time_fmt and not _has_dist_fmt:
                            continue
                        if _is_track_ev and _has_dist_fmt and not _has_time_fmt:
                            continue

                        team_norm = self.normalize_team_name(school, all_teams=all_known_teams)
                        if team_norm == "Unknown" or self.is_likely_athlete_name(team_norm): continue
                        
                        athlete_id = slugify_athlete(athlete_name, team_norm)
                        performance_date = f"{date}T12:00:00" if date != "Unknown" else "Unknown"
                        
                        p = {
                            'athlete_name': athlete_name,
                            'athlete_id': athlete_id,
                            'event': full_event,
                            'mark': mark,
                            'grade': r.get("grade", ""),
                            'team': team_norm,
                            'date': performance_date,
                            'season': season,
                            'year': year,
                            'meet_name': meet_name,
                            'splits': r.get("splits", [])
                        }
                        
                        team_slug = team_norm # Will be slugified in json_store
                        if team_slug not in all_teams_data:
                            all_teams_data[team_slug] = []
                        all_teams_data[team_slug].append(p)
                
                # Mark as synced
                synced_meets[meet_key] = date if date != "Unknown" else datetime.now().strftime("%Y-%m-%d")
                
            except Exception as e:
                print(f"Error syncing {filename}: {e}")

        # Bulk update each team
        for team_name, perfs in all_teams_data.items():
            athletes, count = add_performances_for_team(team_name, perfs, athletes)
            total_performances += count
        
        return total_performances

    def run_full_scrape(self, wipe=False):
        seasons_to_scrape = [
            {"year": "2022", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2022-indoor-results/"},
            {"year": "2022", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2022-outdoor-results/"},
            {"year": "2023", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2023-indoor-results/"},
            {"year": "2023", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2023-outdoor-results/"},
            {"year": "2024", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2024-indoor-results/"},
            {"year": "2024", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2024-outdoor-results/"},
            {"year": "2025", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2025-indoor-results/"},
            {"year": "2025", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2025-outdoor-results/"},
            {"year": "2026", "season": "Indoor", "url": "https://sub5.com/youth-pages/indoor-track/2026-indoor-results/"},
            {"year": "2026", "season": "Outdoor", "url": "https://sub5.com/youth-pages/outdoor-track/2026-outdoor-results/"}
        ]
        
        scrape_state = load_scrape_state()
        athletes = load_athletes()
        base_dir = os.path.dirname(os.path.dirname(__file__))
        
        if wipe:
            self.report_progress("Wiping scrape state and athletes for full re-sync...")
            scrape_state['synced_meets'] = {}
            athletes = {}
            teams_dir = os.path.join(base_dir, 'ui', 'public', 'data', 'teams')
            if os.path.exists(teams_dir):
                import shutil
                for filename in os.listdir(teams_dir):
                    if filename.endswith(".json"):
                        os.remove(os.path.join(teams_dir, filename))
                        
        total_count = 0

        for config in seasons_to_scrape:
            year, season, index_url = config["year"], config["season"], config["url"]
            self.report_progress(f"Processing {season} {year}...")
            archive_dir = os.path.join(base_dir, f'backend/data/sub5_archive/{year}/{season}')
            json_dir = os.path.join(base_dir, f'backend/data/parsed_results/{year}/{season}')
            self.download_missing_files(index_url, archive_dir, synced_meets=scrape_state['synced_meets'], curr_year=year, curr_season=season)
            self.parse_all_files(archive_dir, json_dir)
            count = self.sync_json_to_store(json_dir, season=season, year=year, athletes=athletes, scrape_state=scrape_state)
            total_count += count
        # Apply manual performance corrections / injections
        self.report_progress("Applying manual performance corrections...")
        pc_by_team = {}
        for pc in self.manual_fixes.get('performance_corrections', []):
            team_name = pc['team_name']
            athlete_name = pc['athlete_name']
            athlete_id = slugify_athlete(athlete_name, team_name)
            
            p = {
                'athlete_name': athlete_name,
                'athlete_id': athlete_id,
                'event': pc['event'],
                'mark': pc['mark'],
                'grade': pc.get('grade', ''),
                'team': team_name,
                'date': f"{pc['date']}T12:00:00" if pc.get('date') else "Unknown",
                'season': pc.get('season', 'Outdoor'),
                'year': pc.get('year', '2026'),
                'meet_name': pc.get('meet_name', 'Manual Correction'),
                'splits': pc.get('splits', [])
            }
            if team_name not in pc_by_team:
                pc_by_team[team_name] = []
            pc_by_team[team_name].append(p)
            
        for team_name, perfs in pc_by_team.items():
            athletes, count = add_performances_for_team(team_name, perfs, athletes)
            total_count += count
            
        save_scrape_state(scrape_state)
        save_athletes(athletes)
        rebuild_manifest()
        self.report_progress("Scrape Complete!", 100)
        return total_count

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scrape Track & Field data from sub5.com")
    parser.add_argument('--wipe', action='store_true', help="Force a full re-scrape, clearing all existing processed JSON state.")
    args = parser.parse_args()
    
    scraper = Sub5ScraperV2()
    scraper.run_full_scrape(wipe=args.wipe)
