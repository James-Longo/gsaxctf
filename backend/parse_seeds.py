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
    "George Stevens Academy / Blue": "George Stevens Academy",
    "George Stevens Academy / Gold": "George Stevens Academy",
    "George Steve": "George Stevens Academy",
    "Orono High S": "Orono High School",
    "Orono High School": "Orono High School",
    "Bucksport Hi": "Bucksport High School",
    "Bucksport High School": "Bucksport High School",
    "Washington A": "Washington Academy",
    "Washington Academy": "Washington Academy",
    "Narraguagus": "Narraguagus High School",
    "Narraguagus High School": "Narraguagus High School",
    "Central High": "Central High School",
    "Central High School": "Central High School",
    "Dexter Regio": "Dexter Regional High School",
    "Dexter Regional High School": "Dexter Regional High School",
    "Bangor Chris": "Bangor Christian Schools",
    "Bangor Christian": "Bangor Christian Schools",
    "Bangor Christian Schools": "Bangor Christian Schools",
    "Houlton/GHCA": "Houlton High School",
    "Houlton High School": "Houlton High School",
    "Piscataquis": "Piscataquis Community High School",
    "Piscataquis Community High School": "Piscataquis Community High School",
    "Penquis Vall": "Penquis Valley High School",
    "Penquis Valley High School": "Penquis Valley High School",
    "Penquis Valley": "Penquis Valley High School",
    "Mattanawcook": "Mattanawcook Academy",
    "Mattanawcook Academy": "Mattanawcook Academy",
    "Sumner Memor": "Sumner Memorial High School",
    "Sumner Memorial High School": "Sumner Memorial High School",
    "Deer Isle St": "Deer Isle-Stonington High School",
    "Deer Isle-Stonington High School": "Deer Isle-Stonington High School",
    "Jonesport Be": "Jonesport-Beals High School",
    "Jonesport Beals": "Jonesport-Beals High School",
    "Jonesport-Beals High School": "Jonesport-Beals High School",
    "Searsport Di": "Searsport District High School",
    "Searsport District High School": "Searsport District High School",
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
                entries.append({
                    "event": canonical_event,
                    "gender": gender,
                    "isRelay": True,
                    "team": team,
                    "mark": mark,
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
    for label, filename in [("boys", "Small School boys PL.htm"),
                             ("girls", "Small School girls PL.htm")]:
        path = seeds_dir / filename
        print(f"Parsing {label} ({path.name})...")
        parser = Sub5ColumnParser(str(path))
        parsed = parser.parse()
        entries = convert_parsed(parsed)
        print(f"  {len(entries)} entries from {len(parsed.get('events', []))} events")
        all_entries.extend(entries)

    output = {
        "meta": {
            "meet": "2026 PVC Small School Championship",
            "date": "2026-05-29",
            "location": "Old Town High School",
            "season": "Outdoor",
            "year": "2026"
        },
        "entries": all_entries
    }

    out_path = seeds_dir / 'pvc_2026_outdoor.json'
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {len(all_entries)} total entries to {out_path}")

    from collections import Counter
    teams = Counter(e['team'] for e in all_entries)
    print("\nEntries per team:")
    for team, count in sorted(teams.items(), key=lambda x: -x[1]):
        print(f"  {team}: {count}")


if __name__ == '__main__':
    main()
