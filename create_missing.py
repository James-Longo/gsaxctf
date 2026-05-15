import os
import json
from backend.json_store import rebuild_manifest

missing = [
    "Calais_High_School.json",
    "Madawaska_High_School.json",
    "Easton_High_School.json",
    "Vinalhaven_High_School.json",
    "Chop_Point_High_School.json"
]

teams_dir = "ui/public/data/teams"
for m in missing:
    path = os.path.join(teams_dir, m)
    if not os.path.exists(path):
        with open(path, 'w') as f:
            json.dump([], f)
        print("Created", path)

rebuild_manifest()
print("Manifest rebuilt.")
