from championship_engine import ChampionshipEngine
from nash_engine import get_team_dataset, MeetRules, parse_mark
import sqlite3
import os

def get_all_season_events(db_path, season, year):
    conn = sqlite3.connect(db_path)
    # Get all events that have any performances in this season/year
    query = "SELECT DISTINCT event FROM performances WHERE season = ? AND year = ?"
    rows = conn.execute(query, (season, year)).fetchall()
    events = [r[0] for r in rows]
    conn.close()
    return events

def main():
    db_path = "/home/james-longo/Projects/gsaxctf/track_app.db"
    season = "Indoor"
    year = "2026"
    
    all_events = get_all_season_events(db_path, season, year)
    boys_events = [e for e in all_events if "Boys" in e]
    girls_events = [e for e in all_events if "Girls" in e]

    # Exclude Pentathlon and 5000m commonly not in standard Championship scoring or just too rare
    # But for troubleshooting site, let's include everything the site likely has.
    # The site likely matches on "Boys" / "Girls" prefix.
    
    teams = [
        "Orono High School", "Bucksport High School", "George Stevens Academy",
        "Central High School", "Piscataquis Community High School", "Sumner/Narragaugus",
        "Bangor Christian Schools", "Foxcroft Academy", "Penquis Valley High School"
    ]
    
    rules = MeetRules(max_events_per_athlete=3)
    team_data = {t: get_team_dataset(db_path, t, season, year) for t in teams}
    
    print(f"\nRunning PVC Championship Simulation (UI Mode: No Tie Averaging)")
    print(f"Events loaded: {len(boys_events)} Boys, {len(girls_events)} Girls")
    
    # BOYS
    print("\n--- BOYS DIVISION ---")
    # UI Mode: average_ties=False
    engine_boys = ChampionshipEngine(list(team_data.values()), boys_events, rules, average_ties=False)
    engine_boys.solve_championship(label="BOYS")
    standings_boys = engine_boys.get_full_standings()
    
    # Analyze Orono
    print("\n--- ORONO HIGH SCHOOL ROSTER (BOYS) ---")
    orono_roster = engine_boys.current_rosters.get("Orono High School", {})
    for ev, aids in orono_roster.items():
        if aids:
            print(f"  {ev}:")
            for aid in aids:
                ath = next((a for a in engine_boys.teams_dict["Orono High School"]['athletes'] if a['athlete_id'] == aid), None)
                if ath:
                    print(f"    - {ath['athlete_name']} ({ath['best_marks'].get(ev)})")

    # GIRLS
    print("\n--- GIRLS DIVISION ---")
    engine_girls = ChampionshipEngine(list(team_data.values()), girls_events, rules, average_ties=False)
    engine_girls.solve_championship(label="GIRLS")
    standings_girls = engine_girls.get_full_standings()

    print("\n--- FINAL PVC CHAMPIONSHIP BOYS SCORES (UI MODE) ---")
    for i, (team, score) in enumerate(standings_boys):
        print(f"{i+1}. {team.ljust(35)} : {score:.1f} pts")

    print("\n--- FINAL PVC CHAMPIONSHIP GIRLS SCORES (UI MODE) ---")
    for i, (team, score) in enumerate(standings_girls):
        print(f"{i+1}. {team.ljust(35)} : {score:.1f} pts")

    print(f"\nNash Equilibrium Established (Events: {len(boys_events)})")

if __name__ == "__main__":
    main()
