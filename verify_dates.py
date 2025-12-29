import json
import os
import re
from datetime import datetime

def verify_dates(json_dir, season_name, season_year):
    print(f"--- Verifying Dates for {season_name} {season_year} ---")
    files = [f for f in os.listdir(json_dir) if f.endswith('.json')]
    
    results = {
        "valid": [],
        "placeholder": [],
        "invalid_season": [],
        "missing": []
    }
    
    for filename in files:
        path = os.path.join(json_dir, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, dict):
                results["missing"].append((filename, "Not a dictionary format"))
                continue
                
            meet_date = data.get("date")
            meet_name = data.get("meet_name")
            
            if not meet_date:
                results["missing"].append((filename, "Date is null/empty"))
            elif meet_date == "2026-01-01":
                results["placeholder"].append((filename, meet_name, meet_date))
            else:
                # Check consistency
                try:
                    dt = datetime.strptime(meet_date, "%Y-%m-%d")
                    # For Indoor 2026, valid years are likely 2025 and 2026
                    year_int = int(season_year)
                    if dt.year < year_int - 1 or dt.year > year_int:
                        results["invalid_season"].append((filename, meet_name, meet_date, "Year mismatch"))
                    else:
                        results["valid"].append((filename, meet_name, meet_date))
                except Exception as e:
                    results["missing"].append((filename, f"Date format error: {meet_date}"))
                    
        except Exception as e:
            results["missing"].append((filename, str(e)))

    print(f"\nSummary:")
    print(f"  Valid: {len(results['valid'])}")
    print(f"  Placeholder: {len(results['placeholder'])}")
    print(f"  Season Mismatch: {len(results['invalid_season'])}")
    print(f"  Missing/Error: {len(results['missing'])}")
    
    if results["invalid_season"]:
        print("\n--- Season Mismatches ---")
        for f, name, d, reason in results["invalid_season"]:
            print(f"  {f}: {d} ({name}) - {reason}")

    if results["placeholder"]:
        print("\n--- Placeholders ---")
        for f, name, d in results["placeholder"]:
            print(f"  {f}: {d} ({name})")

    if results["missing"]:
        print("\n--- Missing/Errors ---")
        for f, err in results["missing"]:
            print(f"  {f}: {err}")

if __name__ == "__main__":
    json_dir = r"c:\Users\james\OneDrive\Documents\track_field\backend\data\parsed_results\2026"
    if os.path.exists(json_dir):
        verify_dates(json_dir, "Indoor", "2026")
    else:
        print(f"Directory not found: {json_dir}")
