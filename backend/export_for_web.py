import sqlite3
import json
import os

def export_data():
    backend_dir = os.path.dirname(__file__)
    db_path = os.path.join(backend_dir, '..', 'track_app.db')
    output_dir = os.path.join(backend_dir, '..', 'ui', 'public', 'data')
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    print(f"Reading database from {db_path}...")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Map athletes to their seasons
    print("Mapping athletes to seasons...")
    athlete_seasons = cursor.execute("""
        SELECT DISTINCT athlete_id, year, season
        FROM performances
    """).fetchall()
    
    athlete_map = {} # id -> {id, name, seasons: []}
    for row in athlete_seasons:
        aid = row['athlete_id']
        year = row['year']
        full_s = row['season']
        s_type = full_s.replace(str(year), '').strip()
        key = f"{year}_{s_type}".replace(' ', '_')
        
        if aid not in athlete_map:
            athlete_map[aid] = {"id": aid, "name": "", "seasons": []}
        athlete_map[aid]["seasons"].append(key)

    print("Exporting athletes.json...")
    athletes = cursor.execute("SELECT id, name FROM athletes").fetchall()
    for row in athletes:
        if row['id'] in athlete_map:
            athlete_map[row['id']]['name'] = row['name']
    
    # Filter out athletes who somehow have no performances (shouldn't happen)
    final_athletes = sorted(
        [v for v in athlete_map.values() if v['name']], 
        key=lambda x: x['name']
    )
    
    with open(os.path.join(output_dir, 'athletes.json'), 'w', encoding='utf-8') as f:
        json.dump(final_athletes, f)

    # 2. Get all unique year/season combinations
    print("Identifying seasons...")
    seasons = cursor.execute("SELECT DISTINCT year, season FROM performances").fetchall()
    
    manifest = []
    
    for s_row in seasons:
        year = s_row['year']
        full_season = s_row['season'] # e.g. "2026 Indoor" or just "Indoor"
        
        # Clean up season name for filename (remove year if present)
        season_type = full_season.replace(str(year), '').strip()
        file_key = f"{year}_{season_type}".replace(' ', '_')
        
        print(f"  Exporting {file_key}...")
        
        # Fetch performances for this specific season
        query = '''
            SELECT p.id, p.athlete_id, p.event, p.mark, p.team, p.date, p.season, p.year, p.meet_name, p.splits, p.grade, a.name as athlete_name 
            FROM performances p
            JOIN athletes a ON p.athlete_id = a.id
            WHERE p.year = ? AND p.season = ?
            ORDER BY p.date DESC
        '''
        performances = cursor.execute(query, (year, full_season)).fetchall()
        
        data = []
        for row in performances:
            p = dict(row)
            # Remove unused fields to save space
            if p.get('splits'):
                try:
                    p['splits'] = json.loads(p['splits'])
                    if not p['splits']: del p['splits']
                except:
                    del p['splits']
            else:
                if 'splits' in p: del p['splits']
            data.append(p)
            
        with open(os.path.join(output_dir, f"{file_key}.json"), 'w', encoding='utf-8') as f:
            json.dump(data, f)
            
        manifest.append({
            "key": file_key,
            "year": year,
            "season": season_type,
            "count": len(data)
        })

    # 3. Export Manifest
    print("Exporting manifest.json...")
    with open(os.path.join(output_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f)
        
    print("Split Data Export Complete!")

if __name__ == "__main__":
    export_data()
