import os
import json
import re

def audit_json_files():
    json_dir = os.path.join(os.path.dirname(__file__), 'data', 'parsed_results')
    
    total_files = 0
    total_events = 0
    total_entries = 0
    
    warnings_athlete = []
    warnings_school = []
    
    print(f"Scanning {json_dir}...")
    
    for root, dirs, files in os.walk(json_dir):
        for filename in files:
            if not filename.endswith('.json'): continue
            
            path = os.path.join(root, filename)
            total_files += 1
            
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Data structure: list of events, each has "results" list
                if isinstance(data, dict): # Handle wrapped structure if any, likely list
                     if "events" in data: data = data["events"]
                     else: continue # Skip if not standard list or events dict
                
                if isinstance(data, list):
                    for event in data:
                        total_events += 1
                        if "results" in event:
                            for res in event["results"]:
                                total_entries += 1
                                
                                # Check Athlete/Name
                                name = res.get("athlete", "")
                                if name and re.search(r'\d', name):
                                    warnings_athlete.append({
                                        "file": filename,
                                        "event": event.get("event", "Unknown"),
                                        "value": name,
                                        "context": res
                                    })
                                    
                                # Check School/Team
                                school = res.get("school", "")
                                if school and re.search(r'\d', school):
                                    # Ignore valid schools with numbers if any? (e.g. "MSAD 54")
                                    # For now, just capture all
                                    warnings_school.append({
                                        "file": filename,
                                        "event": event.get("event", "Unknown"),
                                        "value": school,
                                        "context": res
                                    })
            except Exception as e:
                print(f"Error reading {filename}: {e}")

    with open('audit_out.txt', 'w', encoding='utf-8') as f:
        f.write(f"Scanned {total_files} files, {total_events} events, {total_entries} entries.\n")
        f.write("-" * 40 + "\n")
        f.write(f"Athlete Name Warnings: {len(warnings_athlete)}\n")
        f.write(f"School Name Warnings: {len(warnings_school)}\n")
        f.write("-" * 40 + "\n")
        
        f.write("\nTop 20 Athlete Warnings:\n")
        for w in warnings_athlete[:20]:
            f.write(f"[{w['file']}] {w['value']} (School: {w['context'].get('school')})\n")
            
        f.write("\nTop 20 School Warnings:\n")
        for w in warnings_school[:20]:
            f.write(f"[{w['file']}] {w['value']} (Athlete: {w['context'].get('athlete')})\n")
            
    print("Audit written to audit_out.txt")

if __name__ == "__main__":
    audit_json_files()
