"""
Convert Sub5-format Performance List HTML files into a JSON structure
compatible with the PostseasonSimulator's Seeds scoring mode.

Uses the existing Sub5ColumnParser (backend/parser.py) to do the heavy lifting.

Usage:
    python3 backend/parse_seeds.py
Output:
    ui/public/data/seeds/pvc_2026_outdoor.json
"""

import re
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from parser import Sub5ColumnParser

# Team name normalization: seed file form -> canonical name in our system
TEAM_MAP = {
    "Wells": "Wells High School", "Winslow": "Winslow High School", "Houlton": "Houlton High School",
    "Washington A": "Washington Academy", "Spruce Mountai": "Spruce Mountain High School",
    "Spruce Mount": "Spruce Mountain High School",
    "Mountain Valle": "Mountain Valley High School", "Mountain Val": "Mountain Valley High School",
    "Maranacook": "Maranacook Community High School",
    "Bucksport": "Bucksport High School", "Mt. View": "Mount View High School",
    "Maine Central": "Maine Central Institute", "Maine Centra": "Maine Central Institute",
    "Orono": "Orono High School", "Lisbon": "Lisbon/Oak Hill", "George Stevens": "George Stevens Academy",
    "Sacopee Valle": "Sacopee Valley High School", "Sacopee Vall": "Sacopee Valley High School",
    "Mattanawcook": "Mattanawcook Academy", "Central": "Central High School",
    "Hall-Dale": "Hall-Dale High School", "Dexter": "Dexter Regional High School",
    "Traip": "Traip Academy", "Fort Kent": "Fort Kent Community High School",
    "Calais": "Calais High School", "Sumner": "Sumner Memorial High School",
    "Winthrop": "Winthrop High School", "Kents Hill": "Kents Hill School",
    "Gould": "Gould Academy", "Dirigo": "Dirigo High School", "Mt. Abram": "Mt. Abram High School",
    "Madison": "Madison High School", "Old Orchard": "Old Orchard Beach High School",
    "North Yarmouth": "North Yarmouth Academy", "North Yarmou": "North Yarmouth Academy",
    "Maine Coast": "Maine Coast Waldorf School", "Monmouth": "Monmouth Academy",
    "Narraguagus": "Narraguagus High School", "Carrabec": "Carrabec High School",
    "Piscataquis": "Piscataquis Community High School", "Telstar": "Telstar Regional High School",
    "Penquis": "Penquis Valley High School", "Wiscasset": "Wiscasset/Boothbay",
    "Boothbay": "Wiscasset/Boothbay", "Buckfield": "Buckfield High School",
    "Madawaska": "Madawaska High School", "Penobscot Vall": "Penobscot Valley High School",
    "Fort Fairfiel": "Fort Fairfield High School", "Fort Fairfie": "Fort Fairfield High School",
    "Searsport": "Searsport District High School", "Richmond": "Richmond High School",
    "Lee": "Lee Academy", "Deer Isle": "Deer Isle-Stonington High School",
    "MSSM": "Maine School of Science and Mathematics", "Maine School": "Maine School of Science and Mathematics",
    "Washburn": "Washburn District High School", "Bangor Chris": "Bangor Christian Schools",
    "Easton": "Easton High School", "Greenville": "Greenville High School",
    "Blue Hill Harb": "Blue Hill Harbor School", "Vinalhaven": "Vinalhaven School",
    "Greater Portl": "Greater Portland Christian School", "Seacoast": "Seacoast Christian School",
    "Chop Point": "Chop Point School", "North Haven": "North Haven Community School",
    "Jonesport": "Jonesport-Beals High School", "Islesboro Ce": "Islesboro Central School"
}


def normalize_team(raw: str) -> str | None:
    raw = raw.strip()
    if raw in TEAM_MAP:
        return TEAM_MAP[raw]
    # Prefix/suffix match as fallback
    for key, val in TEAM_MAP.items():
        if raw.startswith(key) or key.startswith(raw):
            return val
    return None


def slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def convert_parsed(parsed: dict) -> list[dict]:
    """Convert Sub5ColumnParser output to flat seed entry list."""
    entries = []
    for ev in parsed.get("events", []):
        gender = ev["gender"]          # "Boys" or "Girls"
        event_name = ev["event"]       # e.g. "4x800 Meter Relay"
        is_relay = ev["is_relay"]

        # Derive canonical event label used in the UI
        canonical_event = f"{gender} {event_name}"
        # Strip " Prelims" / " Finals" suffix so it matches normalizeEvent() output
        canonical_event = re.sub(r'\s+(Prelims|Finals)$', '', canonical_event, flags=re.IGNORECASE)

        for result in ev.get("results", []):
            mark = result.get("result", "")
            if not mark or mark.upper() in ("NT", "NM", "NH", "DQ", "DNS", "DNF", "FOUL", "SCR"):
                continue

            if is_relay:
                school_raw = result.get("school", "")
                team = normalize_team(school_raw)
                if not team:
                    print(f"  WARN: unmapped relay team '{school_raw}'")
                    continue
                # First 4 athletes are the relay legs; extras are alternates
                members = [a for a in result.get("athletes", []) if a][:4]
                entries.append({
                    "event": canonical_event,
                    "gender": gender,
                    "isRelay": True,
                    "team": team,
                    "mark": mark,
                    "members": members,
                })
            else:
                name = result.get("athlete", "")
                school_raw = result.get("school", "")
                grade = result.get("grade", "")
                team = normalize_team(school_raw)
                if not team:
                    print(f"  WARN: unmapped school '{school_raw}' for {name}")
                    continue
                if not name:
                    continue
                entries.append({
                    "event": canonical_event,
                    "gender": gender,
                    "isRelay": False,
                    "team": team,
                    "mark": mark,
                    "name": name,
                    "grade": grade,
                    "athleteId": slugify(f"{name} {team}"),
                })

    return entries


def main():
    seeds_dir = Path(__file__).parent.parent / 'ui' / 'public' / 'data' / 'seeds'

    all_entries = []
    for label, filename in [("boys", "Class-C-boys-seeds.htm"),
                             ("girls", "Class-C-girls-seeds.htm")]:
        path = seeds_dir / filename
        print(f"Parsing {label} ({path.name})...")
        parser = Sub5ColumnParser(str(path))
        parsed = parser.parse()
        entries = convert_parsed(parsed)
        print(f"  {len(entries)} entries from {len(parsed.get('events', []))} events")
        all_entries.extend(entries)

    output = {
        "meta": {
            "meet": "2026 Class C State Championship",
            "date": "2026-06-06",
            "location": "St. Joseph's College",
            "season": "Outdoor",
            "year": "2026"
        },
        "entries": all_entries
    }

    out_path = seeds_dir / 'states_2026_outdoor.json'
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {len(all_entries)} total entries to {out_path}")

    from collections import Counter
    teams = Counter(e['team'] for e in all_entries)
    print("\nEntries per team:")
    for team, count in sorted(teams.items(), key=lambda x: -x[1]):
        print(f"  {team}: {count}")


if __name__ == '__main__':
    main()
