import json
import os
import re

json_path = r"backend/data/parsed_results/2025/Class-B-Boys-results-1.json"
# Try looking for other casing if not found
if not os.path.exists(json_path):
    print(f"Not found: {json_path}")
    # List dir to help debug
    print(os.listdir(os.path.dirname(json_path)))
    exit()

print(f"Auditing {json_path}...")

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

events = data.get("events", []) if isinstance(data, dict) else data

for ev in events:
    for res in ev.get("results", []):
         name = res.get("athlete", "")
         if re.search(r'\d', name):
             print(f"BAD: '{name}' (Len: {len(name)})")
             if re.match(r'^[0-9.-]+$', name): print("  Match pattern: YES")
             else: print("  Match pattern: NO")
             
             if len(name) < 10: print("  Len < 10: YES")
             else: print("  Len < 10: NO")
