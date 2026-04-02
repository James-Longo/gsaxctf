import sqlite3
import json
import os
import csv
import io
import statistics
import requests

def export_data():
    backend_dir = os.path.dirname(__file__)
    db_path = os.path.join(backend_dir, '..', 'track_app.db')
    output_path = os.path.join(backend_dir, '..', 'ui', 'public', 'data.json')
    
    print(f"Reading database from {db_path}...")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Fetch all performances with athlete names
    query = '''
        SELECT performances.*, athletes.name as athlete_name 
        FROM performances 
        JOIN athletes ON performances.athlete_id = athletes.id 
        ORDER BY date DESC
    '''
    performances = cursor.execute(query).fetchall()
    
    data = []
    for row in performances:
        p = dict(row)
        if p.get('splits'):
            try:
                p['splits'] = json.loads(p['splits'])
            except:
                p['splits'] = []
        else:
            p['splits'] = []
        data.append(p)
    
    print(f"Exporting {len(data)} records to {output_path}...")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        
    print("Main Data Export Complete!")

def export_practice_results():
    backend_dir = os.path.dirname(__file__)
    output_path = os.path.join(backend_dir, '..', 'ui', 'public', 'practice_results.json')
    sheet_url = "https://docs.google.com/spreadsheets/d/1fql3yYQs_9OZZmS8-KHDliEPTKl__ZFZ592E8dkZD7Q/export?format=csv"
    
    print(f"Fetching practice results from {sheet_url}...")
    try:
        response = requests.get(sheet_url)
        response.raise_for_status()
        csv_data = response.text
        
        f = io.StringIO(csv_data)
        reader = csv.DictReader(f)
        
        events_config = [
            {"col": "20m Fly", "type": "time", "surface_col": "20m Fly Surface"},
            {"col": "Half Court Dash", "type": "time", "surface": "Gym"},
            {"col": "Triple Broad Jump", "type": "distance", "surface_col": "Triple Broad Jump Surface"},
            {"col": "Shuttle Run", "type": "time", "surface_col": "Shuttle Run Surface"},
            {"col": "Quintuple Bound", "type": "distance", "surface_col": "Quintuple Bound Surface"}
        ]
        
        def parse_distance(val):
            if '-' not in val: return None
            try:
                ft, ins = map(float, val.split('-'))
                return ft * 12 + ins
            except: return None

        def format_distance(inches):
            if inches is None: return "x"
            ft = int(inches // 12)
            ins = round(inches % 12, 2)
            return f"{ft}-{ins}"

        results = []
        for row in reader:
            if not row.get('Name') or not row['Name'].strip():
                continue
                
            date = row['Date'].strip()
            name = row['Name'].strip()
            for event in events_config:
                col_name = event['col']
                raw_val = row.get(col_name, '').strip()
                if not raw_val: continue
                
                event_surface = 'Track'
                if 'surface' in event: event_surface = event['surface']
                elif 'surface_col' in event: event_surface = row.get(event['surface_col'], '').strip() or 'Track'
                
                trials = [t.strip() for t in raw_val.split(',')]
                valid_trials = []
                is_hand = any('h' in t.lower() for t in trials)
                
                for t in trials:
                    t = t.strip()
                    if not t or t.lower() == 'x': continue
                    clean_t = t.lower().replace('h', '')
                    if event['type'] == 'time':
                        try: valid_trials.append(float(clean_t))
                        except: pass
                    else:
                        d = parse_distance(clean_t)
                        if d is not None: valid_trials.append(d)
                
                if not valid_trials: continue
                
                performance_val = max(valid_trials) if event['type'] == 'distance' else statistics.median(valid_trials)
                if event['col'] == 'Half Court Dash': performance_val = min(valid_trials)
                
                results.append({
                    "name": name,
                    "date": date,
                    "event": col_name,
                    "surface": event_surface,
                    "trials": trials,
                    "is_hand_timed": is_hand,
                    "median_mark": performance_val,
                    "mark_type": event['type'],
                    "formatted_median": format_distance(performance_val) if event['type'] == 'distance' else str(round(performance_val, 2))
                })
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"Practice Results Exported to {output_path}")
        
    except Exception as e:
        print(f"Error exporting practice results: {e}")

if __name__ == "__main__":
    export_data()
    export_practice_results()
