import requests
import json

def test_parse():
    sheet_url = "https://docs.google.com/spreadsheets/d/1iWUERpoQgetunqBOCZM2ep8HOhdX1RcLw59uJaA5hCY/export?format=csv"
    response = requests.get(sheet_url)
    response.raise_for_status()
    csv_data = response.text
    
    lines = csv_data.split('\n')
    
    event_map = {
        "4x8": "4X800m Relay",
        "55H": "55 M. Hurdles",
        "55": "55 M. Dash",
        "1mi": "One Mile",
        "400": "400 M. Run",
        "800": "800 M. Run",
        "200": "200 M. Dash",
        "2mi": "Two Mile Run",
        "4x2": "4X200m Relay",
        "LJ": "Long Jump",
        "TJ": "Triple Jump",
        "HJ": "High Jump",
        "PV": "Pole Vault",
        "SP": "Shot Put"
    }
    
    def parse_table(lines_chunk):
        if not lines_chunk:
            return []
        
        header = None
        data_start = 0
        for i, line in enumerate(lines_chunk):
            if "4x8" in line and "55H" in line:
                header = line.split(',')
                data_start = i + 1
                break
        
        if not header:
            return []
        
        results = []
        for line in lines_chunk[data_start:]:
            cols = line.split(',')
            if not cols or not cols[0].strip() or cols[0] == "Total":
                continue
            
            athlete_name = cols[0].strip()
            athlete_events = []
            
            for i in range(1, len(header)):
                if i >= len(cols):
                    continue
                
                val = cols[i].strip().lower()
                if val in ["x", "y", "?", "(y)"]:
                    event_abbrev = header[i].strip()
                    if event_abbrev in event_map:
                        athlete_events.append(event_map[event_abbrev])
            
            if athlete_events:
                results.append({
                    "name": athlete_name,
                    "events": athlete_events
                })
        return results

    girls_chunk = []
    boys_chunk = []
    current_chunk = girls_chunk
    
    seen_first_table = False
    for line in lines:
        if "4x8" in line and "55H" in line:
            if seen_first_table:
                current_chunk = boys_chunk
            seen_first_table = True
        current_chunk.append(line)
        
    data = {
        "girls": parse_table(girls_chunk),
        "boys": parse_table(boys_chunk)
    }
    print(f"Girls: {len(data['girls'])}")
    print(f"Boys: {len(data['boys'])}")
    if data['girls']:
        print(f"First Girl: {data['girls'][0]}")
    if data['boys']:
        print(f"First Boy: {data['boys'][0]}")

if __name__ == "__main__":
    test_parse()
