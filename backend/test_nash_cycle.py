from nash_engine import get_team_dataset, run_simulation, MeetRules, parse_mark, get_event_points
from collections import defaultdict
import os

def main():
    db_path = "/home/james-longo/Projects/gsaxctf/track_app.db"
    team_a = "George Stevens Academy"
    team_b = "Bucksport High School"
    season = "Indoor"
    year = "2026"
    
    print(f"Loading data for {year} {season}...")
    team_a_data = get_team_dataset(db_path, team_a, season, year)
    team_b_data = get_team_dataset(db_path, team_b, season, year)
    
    # Hack GSA 4x2 mark to be competitive (1:40.00)
    for r in team_a_data['relays']:
        if r['event'] == 'Boys 4x200 Meter Relay':
            r['mark'] = '1:40.00'
            print("HACKED GSA 4x200 to 1:40.00")
    
    print(f"GSA Athletes: {len(team_a_data['athletes'])} (Relays: {len(team_a_data['relays'])})")
    print(f"Bucksport Athletes: {len(team_b_data['athletes'])} (Relays: {len(team_b_data['relays'])})")
    
    events = [
        "Boys 55 Meter Dash", "Boys 200 Meter Dash", "Boys 400 Meter Dash",
        "Boys 800 Meter Run", "Boys 1 Mile Run", "Boys 2 Mile Run",
        "Boys 55 Meter Hurdles", "Boys 4x200 Meter Relay", "Boys 4x800 Meter Relay",
        "Boys High Jump", "Boys Long Jump", "Boys Triple Jump", "Boys Shot Put", "Boys Pole Vault"
    ]
    
    rules = MeetRules(max_events_per_athlete=3)
    
    print(f"\nStarting Nash Equilibrium Simulation (GSA vs Bucksport)...")
    result = run_simulation(team_a_data, team_b_data, events, rules)
    
    if isinstance(result, tuple) and len(result) == 2:
        roster_a, roster_b = result
        print("\n--- FINAL EQUILIBRIUM ROSTERS ---")
        
        # Simple score calc for verification
        def get_team_score(team_roster, other_roster, team_id, other_id):
            total = 0
            for ev2 in events:
                marks2 = []
                for aid in team_roster.get(ev2, []):
                    # Find mark for athlete aid in event ev2
                    ath = next((a for a in team_a_data['athletes'] if a['athlete_id'] == aid), None) if team_id == 'GSA' else next((a for a in team_b_data['athletes'] if a['athlete_id'] == aid), None)
                    if ath and ev2 in ath['best_marks']:
                        marks2.append((parse_mark(ath['best_marks'][ev2]), team_id))
                    else:
                        # Check relays
                        team_relays = team_a_data['relays'] if team_id == 'GSA' else team_b_data['relays']
                        for r in team_relays:
                            if r['event'] == ev2 and set(team_roster[ev2]) == set(r['member_ids']):
                                marks2.append((parse_mark(r['mark']), team_id))
                                break
                
                for aid in other_roster.get(ev2, []):
                    ath = next((a for a in team_b_data['athletes'] if a['athlete_id'] == aid), None) if team_id == 'GSA' else next((a for a in team_a_data['athletes'] if a['athlete_id'] == aid), None)
                    if ath and ev2 in ath['best_marks']:
                        marks2.append((parse_mark(ath['best_marks'][ev2]), other_id))
                    else:
                        other_relays = team_b_data['relays'] if team_id == 'GSA' else team_a_data['relays']
                        for r in other_relays:
                            if r['event'] == ev2 and set(other_roster[ev2]) == set(r['member_ids']):
                                marks2.append((parse_mark(r['mark']), other_id))
                                break
                
                if marks2:
                    sc = get_event_points(marks2, ev2, rules.scoring_table)
                    total += sc.get(team_id, 0)
            return total

        score_a = get_team_score(roster_a, roster_b, 'GSA', 'BUCK')
        score_b = get_team_score(roster_b, roster_a, 'BUCK', 'GSA')
        
        print(f"GSA: {score_a} | Bucksport: {score_b}")
        
        for name, roster in [("GSA", roster_a), ("Bucksport", roster_b)]:
            print(f"\n{name} Detail:")
            for ev2 in sorted(roster.keys()):
                if roster[ev2]:
                    data = team_a_data if name == "GSA" else team_b_data
                    anames = []
                    for aid in roster[ev2]:
                        ath = next((a for a in data['athletes'] if a['athlete_id'] == aid), None)
                        if ath: anames.append(ath['athlete_name'])
                        else: anames.append(f"Member({aid})")
                    print(f"  {ev2.ljust(25)}: {', '.join(anames)}")
    else:
        print("\nCycle detected.")

if __name__ == "__main__":
    main()
