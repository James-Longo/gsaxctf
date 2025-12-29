import sqlite3
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
import requests
from bs4 import BeautifulSoup
import re
try:
    from backend.scraper import Sub5Scraper
except ImportError:
    from scraper import Sub5Scraper

app = FastAPI()

# Allow CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'track_app.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Global status for progress tracking
scrape_status = {
    "is_active": False,
    "message": "Idle",
    "progress": 0,
    "inserted": 0
}

@app.get("/athletes")
def get_athletes(team: Optional[str] = None, year: Optional[str] = None, season: Optional[str] = None):
    conn = get_db_connection()
    query = '''
        SELECT DISTINCT athletes.* 
        FROM athletes 
        JOIN performances ON athletes.id = performances.athlete_id 
        WHERE 1=1
    '''
    params = []
    if team and team != 'All':
        query += ' AND performances.team = ?'
        params.append(team)
    if year and year != 'All':
        query += ' AND performances.season LIKE ?'
        params.append(f'{year}%')
    if season and season != 'All':
        query += ' AND performances.season LIKE ?'
        params.append(f'%{season}')
    
    athletes = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(ix) for ix in athletes]

@app.get("/teams")
def get_teams():
    conn = get_db_connection()
    # Fetch teams and apply a basic filter to exclude likely junk (like stray athlete names)
    raw_teams = conn.execute('SELECT DISTINCT team FROM performances WHERE team IS NOT NULL AND team != "Unknown" AND team != "" ORDER BY team').fetchall()
    conn.close()
    
    filtered_teams = []
    for row in raw_teams:
        team = row['team']
        # Rule: Exclude if very short and doesn't look like an acronym or Maine school keyword
        if len(team) < 4:
            if not team.isupper(): continue
        
        # Rule: Exclude common first names that might have leaked
        if team in ["Sam", "Sarah", "Thomas", "John", "David", "Emma", "Madison"]:
             continue
             
        filtered_teams.append(team)
        
    return filtered_teams

@app.get("/athletes/{athlete_id}/performances")
def get_athlete_performances(athlete_id: int, team: Optional[str] = None):
    conn = get_db_connection()
    query = 'SELECT * FROM performances WHERE athlete_id = ?'
    params = [athlete_id]
    if team:
        query += ' AND team = ?'
        params.append(team)
    query += ' ORDER BY date DESC'
    performances = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(ix) for ix in performances]

@app.get("/performances")
def get_all_performances(team: Optional[str] = None):
    conn = get_db_connection()
    query = '''
        SELECT performances.*, athletes.name as athlete_name 
        FROM performances 
        JOIN athletes ON performances.athlete_id = athletes.id 
    '''
    params = []
    if team:
        query += ' WHERE performances.team = ?'
        params.append(team)
    query += ' ORDER BY date DESC'
    performances = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(ix) for ix in performances]

class PerformanceListRequest(BaseModel):
    url: str

PVC_SMALL_SCHOOLS = {
    "Bangor Chris": "Bangor Christian",
    "Bucksport": "Bucksport",
    "Central": "Central",
    "Dexter": "Dexter Regional",
    "Foxcroft": "Foxcroft Academy",
    "George Steve": "George Stevens Academy",
    "Houlton": "Houlton/Hodgdon/GHCA",
    "Jonesport-Beals": "Jonesport-Beals",
    "Mattanawcook": "Mattanawcook Academy",
    "Narraguagus": "Narraguagus",
    "Orono": "Orono",
    "Penquis Vall": "Penquis Valley",
    "Piscataquis": "Piscataquis Community (PCHS)",
    "Searsport": "Searsport",
    "Sumner": "Sumner",
    "Washington A": "Washington Academy"
}

def parse_sub5_text(text, current_results, season):
    # Pattern to identify event headers: e.g. "Girls 55m Dash"
    # Pattern for individual result line: rank, mark, type, name, grade, team, date
    performance_pattern = re.compile(r'^\s*(\d+)\s+([\d:.\'-]+)\s+([FP])\s+(.+?)\s+(\d+|--)\s+(.+?)\s+(\d{1,2}/\d{1,2}/(\d{4}))')
    # Pattern for relay result line: rank, mark, type, heat, team (in quotes), date
    relay_pattern = re.compile(r'^\s*(\d+)\s+([\d:.\'-]+)\s+([FP])\s+([A-D])\s+\'(.+?)\'\s+(\d{1,2}/\d{1,2}/(\d{4}))')
    
    current_event = None
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check for event header
        if ('Girls' in line or 'Boys' in line) and ('Dash' in line or 'Run' in line or 'Hurdles' in line or 'Jump' in line or 'Shot' in line or 'Vault' in line or 'Relay' in line):
            header_match = re.match(r'^((?:Girls|Boys)\s+[^=]+)', line)
            if header_match:
                current_event = header_match.group(1).strip()
            continue
        
        if not current_event:
            continue

        # Try individual first
        perf_match = performance_pattern.search(line)
        if perf_match:
            rank = perf_match.group(1)
            mark = perf_match.group(2)
            name = perf_match.group(4).strip()
            grade = perf_match.group(5)
            team = perf_match.group(6).strip()
            full_date = perf_match.group(7)
            # Correct year to Season Year
            try:
                m, d, y = map(int, full_date.split('/'))
                season_year = str(y + 1) if season == "Indoor" and m == 12 else str(y)
            except:
                season_year = perf_match.group(8)
            
            # Filter for PVC Small Schools
            matched_pvc = next((full for abbrev, full in PVC_SMALL_SCHOOLS.items() if abbrev.lower() in team.lower()), None)
            
            if matched_pvc:
                current_results.append({
                    "event": current_event,
                    "rank": rank,
                    "mark": mark,
                    "name": name,
                    "grade": grade,
                    "team": matched_pvc,
                    "date": full_date,
                    "season": season,
                    "year": season_year
                })
            continue

        # Try relay
        relay_match = relay_pattern.search(line)
        if relay_match:
            rank = relay_match.group(1)
            mark = relay_match.group(2)
            team = relay_match.group(5).strip()
            full_date = relay_match.group(6)
            # Correct year to Season Year
            try:
                m, d, y = map(int, full_date.split('/'))
                season_year = str(y + 1) if season == "Indoor" and m == 12 else str(y)
            except:
                season_year = relay_match.group(7)
            
            # Filter for PVC Small Schools
            matched_pvc = next((full for abbrev, full in PVC_SMALL_SCHOOLS.items() if abbrev.lower() in team.lower()), None)
            
            if matched_pvc:
                current_results.append({
                    "event": current_event,
                    "rank": rank,
                    "mark": mark,
                    "name": f"{matched_pvc} Relay",
                    "grade": "--",
                    "team": matched_pvc,
                    "date": full_date,
                    "season": season,
                    "year": season_year
                })

@app.post("/analyze-performance-list")
def analyze_performance_list(request: PerformanceListRequest):
    print(f"Analyzing URL: {request.url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(request.url, headers=headers)
        response.raise_for_status()
        text = BeautifulSoup(response.text, 'html.parser').get_text()
        
        season = "Outdoor" if "pvc" in request.url.lower() else "Indoor"
        results = []
        parse_sub5_text(text, results, season)
        return results
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze-latest-emitl")
def analyze_latest_emitl():
    configs = [
        {"url": "https://sub5.com/youth-pages/indoor-track/", "season": "Indoor"},
        {"url": "https://sub5.com/youth-pages/outdoor-track/", "season": "Outdoor"}
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    all_results = []
    
    try:
        for config in configs:
            print(f"Fetching index: {config['url']}")
            response = requests.get(config['url'], headers=headers)
            if not response.ok: continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            links = []
            
            # Look for performance list links
            for a in soup.find_all('a', href=True):
                href = a['href']
                # Patterns: emitl...htm (indoor) or pvc...htm (outdoor)
                if re.search(r'(emitl|pvc)(girls|boys)(relays)?\d+.*\.htm', href):
                    if href.startswith('/'):
                        href = "https://sub5.com" + href
                    elif not href.startswith('http'):
                        href = config['url'] + href
                    if href not in links:
                        links.append(href)
            
            for url in links:
                print(f"Fetching {url}...")
                res = requests.get(url, headers=headers)
                if res.ok:
                    text = BeautifulSoup(res.text, 'html.parser').get_text()
                    parse_sub5_text(text, all_results, config['season'])
        
        return all_results
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

def run_scrape_in_background(full=False):
    global scrape_status
    scrape_status["is_active"] = True
    scrape_status["message"] = "Starting scrape..."
    scrape_status["progress"] = 0
    scrape_status["inserted"] = 0
    
    def on_progress(msg, prog):
        scrape_status["message"] = msg
        if prog is not None:
            scrape_status["progress"] = prog

    try:
        scraper = Sub5Scraper(progress_callback=on_progress)
        count = scraper.run_full_scrape(wipe=full)
        scrape_status["inserted"] = count
        scrape_status["message"] = f"Finished. {count} results updated."
    except Exception as e:
        scrape_status["message"] = f"Error: {str(e)}"
    finally:
        scrape_status["is_active"] = False

@app.post("/scrape/sub5")
def scrape_sub5(background_tasks: BackgroundTasks, full: bool = False):
    """Scrapes only the current 2025-2026 indoor season."""
    if scrape_status["is_active"]:
        return {"status": "busy", "message": "Scrape already in progress"}
    
    background_tasks.add_task(run_scrape_in_background, full=full)
    return {"status": "started"}

@app.get("/scrape/status")
def get_scrape_status():
    return scrape_status

@app.get("/health")
def health_check():
    return {"status": "ok"}
