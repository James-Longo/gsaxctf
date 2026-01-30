from nash_engine import get_team_dataset, calculate_net_value_matrix, solve_optimal_roster, get_event_points, MeetRules, parse_mark
from collections import defaultdict
import os

def run_field_simulation(teams, team_data, events, rules, label):
    # Initial Rosters (Empty)
    rosters = {t: {ev: [] for ev in events} for t in teams}
    
    def get_current_scores():
        scores = defaultdict(float)
        for ev in events:
            field_marks = []
            for t in teams:
                aids = rosters[t].get(ev, [])
                if not aids: continue
                # Determine mark
                the_mark = None
                for r in team_data[t]['relays']:
                    if r['event'] == ev and set(aids) == set(r['member_ids']):
                        the_mark = parse_mark(r['mark'])
                        break
                if the_mark is None:
                    for aid in aids:
                        ath = next((a for a in team_data[t]['athletes'] if a['athlete_id'] == aid), None)
                        if ath and ev in ath['best_marks']:
                            field_marks.append((parse_mark(ath['best_marks'][ev]), t))
                else:
                    field_marks.append((the_mark, t))
            if field_marks:
                pts = get_event_points(field_marks, ev, rules.scoring_table)
                for t, p in pts.items():
                    scores[t] += p
        return scores

    for loop in range(15):
        changes = 0
        current_scores = get_current_scores()
        for team in teams:
            old_score = current_scores.get(team, 0.0)
            
            # 1. Build Opponent Roster
            opp_roster = defaultdict(list)
            for other_t in teams:
                if other_t == team: continue
                for ev, aids in rosters[other_t].items():
                    for aid in aids:
                        ath = next((a for a in team_data[other_t]['athletes'] if a['athlete_id'] == aid), None)
                        if ath and ev in ath['best_marks']:
                            opp_roster[ev].append((parse_mark(ath['best_marks'][ev]), other_t))
                        else:
                            for r in team_data[other_t]['relays']:
                                if r['event'] == ev and set(aids) == set(r['member_ids']):
                                    opp_roster[ev].append((parse_mark(r['mark']), other_t))
                                    break
            
            # 2. Optimize
            coeffs, r_coeffs = calculate_net_value_matrix(team_data[team], opp_roster, rules.scoring_table, events)
            new_roster = solve_optimal_roster(team_data[team], events, coeffs, r_coeffs, rules)
            
            if new_roster != rosters[team]:
                changes += 1
                rosters[team] = new_roster
                # Recalculate scores and show leaderboard
                updated_scores = get_current_scores()
                sorted_up = sorted(updated_scores.items(), key=lambda x: x[1], reverse=True)
                score_str = " | ".join([f"{t}: {s:.0f}" for t, s in sorted_up])
                print(f"[{label} Round {loop+1}] {team} Adjusted. Leaderboard: {score_str}")
                current_scores = updated_scores
                
        if changes == 0:
            print(f"[{label} Round {loop+1}] No further improvements found. Equilibrium established.")
            break
            
    return rosters, get_current_scores()

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
    
    print(f"Loading data for {len(teams)} teams ({year} {season})...")
    team_data = {t: get_team_dataset(db_path, t, season, year) for t in teams}
    
    # Hack GSA 4x200 mark
    for r in team_data["George Stevens Academy"]['relays']:
        if r['event'] == 'Boys 4x200 Meter Relay':
            r['mark'] = '1:40.00'
    
    def filter_team_data(t_data, gender):
        return {
            t: {
                'athletes': [a for a in data['athletes'] if a.get('gender') == gender],
                'relays': [r for r in data['relays'] if r.get('gender') == gender],
                'team_name': data['team_name']
            } for t, data in t_data.items()
        }

    boys_team_data = filter_team_data(team_data, 'boys')
    girls_team_data = filter_team_data(team_data, 'girls')

    boys_rosters, boys_scores = run_field_simulation(teams, boys_team_data, boys_events, rules, "BOYS")
    girls_rosters, girls_scores = run_field_simulation(teams, girls_team_data, girls_events, rules, "GIRLS")
    
    print("\n✓ Nash Equilibrium Established")
    
    print("\n--- FINAL PVC CHAMPIONSHIP BOYS SCORES ---")
    sorted_boys = sorted(boys_scores.items(), key=lambda x: x[1], reverse=True)
    for i, (t, s) in enumerate(sorted_boys):
        print(f"{i+1}. {t.ljust(35)}: {s:.1f} pts")

    print("\n--- FINAL PVC CHAMPIONSHIP GIRLS SCORES ---")
    sorted_girls = sorted(girls_scores.items(), key=lambda x: x[1], reverse=True)
    for i, (t, s) in enumerate(sorted_girls):
        print(f"{i+1}. {t.ljust(35)}: {s:.1f} pts")

if __name__ == "__main__":
    main()
