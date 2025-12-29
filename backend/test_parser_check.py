from backend.prototype_parser import Sub5ColumnParser
import json
import os
import re

source_file = "backend/data/sub5_archive/2025/Class-B-boys-results.htm"
output_file = "backend/debug_new_parser.json"

if os.path.exists(source_file):
    print(f"Parsing {source_file}...")
    parser = Sub5ColumnParser(source_file)
    results = parser.parse()
    
    # Analyze results for the specific bug
    # Look for entries where athlete name looks like a mark "20-04.25"
    
    bad_count = 0
    fixed_count = 0
    
    if "events" in results:
        for ev in results["events"]:
            for res in ev.get("results", []):
                name = res.get("athlete", "")
                school = res.get("school", "")
                mark = res.get("result", "")
                
                # Check for the specific type of error we saw
                if re.search(r'\d', name) and len(name) < 10:
                    print(f"BAD: Name='{name}' School='{school}' Mark='{mark}'")
                    bad_count += 1
                else:
                    # Check if this might be a fixed entry?
                    # Hard to know without ground truth, but we can check if likely candidates are now clean
                    if "Coulter" in name or "Renwick" in name: 
                        # We saw Bruce Coulter had the smashed issue
                        pass

    print(f"Total Bad Name Entries: {bad_count}")
    
    # Save output
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4)
        
else:
    print(f"File not found: {source_file}")
