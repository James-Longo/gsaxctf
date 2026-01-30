from championship_engine import ChampionshipEngine
from nash_engine import get_team_dataset, MeetRules
import os

def main():
    db_path = "/home/james-longo/Projects/gsaxctf/track_app.db"
    season = "Indoor"
    year = "2026"
    
    teams = [
        "Orono High School", "Bucksport High School", "George Stevens Academy",
        "Central High School", "Piscataquis Community High School", "Sumner/Narragaugus",
        "Bangor Christian Schools", "Foxcroft Academy", "Penquis Valley High School"
    ]
    
    boys_events = [
        "Boys 55 Meter Dash", "Boys 200 Meter Dash", "Boys 400 Meter Dash",
        "Boys 800 Meter Run", "Boys 1 Mile Run", "Boys 2 Mile Run",
        "Boys 55 Meter Hurdles", "Boys 4x200 Meter Relay", "Boys 4x800 Meter Relay",
        "Boys High Jump", "Boys Long Jump", "Boys Triple Jump", "Boys Shot Put", "Boys Pole Vault"
    ]
    
    girls_events = [
        "Girls 55 Meter Dash", "Girls 200 Meter Dash", "Girls 400 Meter Dash",
        "Girls 800 Meter Run", "Girls 1 Mile Run", "Girls 2 Mile Run",
        "Girls 55 Meter Hurdles", "Girls 4x200 Meter Relay", "Girls 4x800 Meter Relay",
        "Girls High Jump", "Girls Long Jump", "Girls Triple Jump", "Girls Shot Put", "Girls Pole Vault"
    ]
    
    rules = MeetRules(max_events_per_athlete=3)
    
    # Load all team data
    team_data = {t: get_team_dataset(db_path, t, season, year) for t in teams}
    
    print("\nRunning PVC Championship Simulation (King of the Hill Logic)")
    
    # BOYS
    print("\n--- BOYS DIVISION ---")
    engine_boys = ChampionshipEngine(list(team_data.values()), boys_events, rules)
    engine_boys.solve_championship(label="BOYS")
    standings_boys = engine_boys.get_full_standings()
    
    # GIRLS
    print("\n--- GIRLS DIVISION ---")
    engine_girls = ChampionshipEngine(list(team_data.values()), girls_events, rules)
    engine_girls.solve_championship(label="GIRLS")
    standings_girls = engine_girls.get_full_standings()

    print("\n--- FINAL PVC CHAMPIONSHIP BOYS SCORES ---")
    for i, (team, score) in enumerate(standings_boys):
        print(f"{i+1}. {team.ljust(35)} : {score:.1f} pts")

    print("\n--- FINAL PVC CHAMPIONSHIP GIRLS SCORES ---")
    for i, (team, score) in enumerate(standings_girls):
        print(f"{i+1}. {team.ljust(35)} : {score:.1f} pts")

    print("\n✓ Nash Equilibrium (King of the Hill) Established")

if __name__ == "__main__":
    main()
