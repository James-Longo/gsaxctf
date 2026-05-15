import json
import os
import re

requested_teams = [
    "Wells", "Winslow", "Houlton/Greater Houlton", "Washington", "Spruce Mountain", 
    "Mountain Valley", "Maranacook", "Bucksport", "Mt. View", "Maine Central", 
    "Orono", "Lisbon/Oak Hill", "George Stevens", "Sacopee Valley", "Mattanawcook", 
    "Central", "Hall-Dale", "Dexter", "Traip", "Fort Kent", "Calais", "Sumner", 
    "Winthrop", "Kents Hill", "Gould", "Dirigo", "Mt. Abram", "Madison", "Old Orchard", 
    "North Yarmouth/Maine Coast Waldorf", "Monmouth", "Narraguagus", "Carrabec", 
    "Piscataquis", "Telstar", "Penquis Valley", "Wiscasset/Boothbay", "Buckfield", 
    "Madawaska", "Penobscot Valley", "Fort Fairfield", "Searsport", "Richmond", 
    "Lee", "Deer Isle-Stonington", "MSSM", "Washburn", "Bangor Christian/Penobscot Christian", 
    "Easton", "Greenville", "Blue Hill Harbor", "Vinalhaven", "Greater Portland", 
    "Seacoast", "Chop Point", "North Haven"
]

manifest_path = "ui/public/data/manifest.json"
with open(manifest_path, "r") as f:
    manifest = json.load(f)

existing_slugs = {t['slug'] for t in manifest['teams']}
existing_names = {t['name'] for t in manifest['teams']}

# Let's import scraper's TEAM_MAPPING to understand aliases
from backend.scraper_v2 import Sub5ScraperV2
scraper = Sub5ScraperV2()
all_known_teams = existing_names

missing = []

for rt in requested_teams:
    # Some strings have multiple teams or aliases separated by /
    parts = rt.split('/')
    found = False
    for p in parts:
        p = p.strip()
        norm = scraper.normalize_team_name(p, all_teams=all_known_teams)
        if norm == "Unknown" or scraper.is_likely_athlete_name(norm):
            continue
            
        # check if it exists in manifest
        from backend.json_store import slugify_team
        slug = slugify_team(norm)
        if slug in existing_slugs or norm in existing_names:
            found = True
            break
            
    if not found:
        missing.append(rt)

print(f"Missing teams out of {len(requested_teams)}:")
for m in missing:
    print(" -", m)

