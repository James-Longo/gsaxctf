from nash_engine import get_team_dataset, run_simulation, MeetRules
from collections import defaultdict
import os

def main():
    db_path = "/home/james-longo/Projects/gsaxctf/track_app.db"
    if not os.path.exists(db_path):
        print(f"Error: DB not found at {db_path}")
        return

    season = "Indoor"
    year = "2026"
    
    print(f"Loading data for {year} {season}...")
    team_a_data = get_team_dataset(db_path, "Orono High School", season, year)
    team_b_data = get_team_dataset(db_path, "Bucksport High School", season, year)
    
    if not team_a_data or not team_b_data:
        print("Error: Could not find data for one or both teams.")
        return

    print(f"Orono Athletes: {len(team_a_data)}")
    print(f"Bucksport Athletes: {len(team_b_data)}")

    # Define common events
    events = [
        "Boys 55 Meter Dash", "Boys 200 Meter Dash", "Boys 400 Meter Dash",
        "Boys 800 Meter Run", "Boys 1 Mile Run", "Boys 2 Mile Run",
        "Boys 55 Meter Hurdles", "Boys 4x200 Meter Relay", "Boys 4x800 Meter Relay",
        "Boys High Jump", "Boys Long Jump", "Boys Triple Jump", "Boys Shot Put", "Boys Pole Vault"
    ]

    rules = MeetRules(max_events_per_athlete=3)
    
    print("\nStarting Nash Equilibrium Simulation (Iterative Best Response)...")
    result = run_simulation(team_a_data, team_b_data, events, rules)
    
    if isinstance(result, tuple) and len(result) == 2:
        roster_a, roster_b = result
        print("\n--- FINAL EQUILIBRIUM ROSTERS (Pure Nash) ---")
        
        # Calculate Final Scores
        from nash_engine import get_event_points, parse_mark
        final_scores = defaultdict(float)
        
        for ev in events:
            marks = []
            # Team A marks
            for aid in roster_a.get(ev, []):
                ath = next(a for a in team_a_data if a['athlete_id'] == aid)
                if ev in ath['best_marks']:
                    marks.append((parse_mark(ath['best_marks'][ev]), 'TEAM_A'))
            # Team B marks
            for aid in roster_b.get(ev, []):
                ath = next(a for a in team_b_data if a['athlete_id'] == aid)
                if ev in ath['best_marks']:
                    marks.append((parse_mark(ath['best_marks'][ev]), 'TEAM_B'))
            
            if marks:
                is_time = any(x in ev.lower() for x in ['dash', 'run', 'hurdles', 'mile', 'relay', '4x'])
                marks.sort(key=lambda x: x[0], reverse=not is_time)
                ev_pts = get_event_points(marks, ev, rules.scoring_table)
                for t, p in ev_pts.items():
                    final_scores[t] += p

        print(f"\nFINAL SCORE:")
        print(f"Orono High School: {final_scores.get('TEAM_A', 0)}")
        print(f"Bucksport High School: {final_scores.get('TEAM_B', 0)}")
        
        for team_name, roster in [("Orono High School", roster_a), ("Bucksport High School", roster_b)]:
            print(f"\n{team_name} Detail:")
            for ev in sorted(roster.keys()):
                if roster[ev]:
                    data_source = team_a_data if team_name == "Orono High School" else team_b_data
                    names = []
                    for aid in roster[ev]:
                        ath = next((a for a in data_source if a['athlete_id'] == aid), None)
                        if ath:
                            names.append(ath['athlete_name'])
                    print(f"  {ev.ljust(25)}: {', '.join(names)}")

if __name__ == "__main__":
    main()
