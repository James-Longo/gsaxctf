import sqlite3
import json
import os

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
        
    print("Export Complete!")

if __name__ == "__main__":
    export_data()
