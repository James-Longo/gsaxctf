from simulator import TrackSimulator
import os

def main():
    db_path = "/home/james-longo/Projects/gsaxctf/track_app.db"
    if not os.path.exists(db_path):
        print(f"Error: DB not found at {db_path}")
        return

    sim = TrackSimulator(db_path)
    season = "Indoor"
    year = "2026"

    print(f"Loading PVC Data for {year} {season}...")
    all_perfs = sim.get_pvc_data(season, year)
    
    # Split by gender
    boys_perfs = [p for p in all_perfs if 'boys' in p['event'].lower()]
    girls_perfs = [p for p in all_perfs if 'girls' in p['event'].lower()]
    
    def simulate_strict(perfs):
        pools = sim.get_athlete_pools(perfs)
        # Generate entries
        team_entries = {}
        for team, pool in pools.items():
            team_entries[team] = sim.get_greedy_entries(pool)
            
        # Group by event
        event_groups = {}
        for team, entries in team_entries.items():
            for entry in entries:
                ev = entry['event']
                if ev not in event_groups: event_groups[ev] = []
                event_groups[ev].append({**entry, 'source_team': team})
        
        event_scores = []
        scores = {}
        for ev, entries in event_groups.items():
            # Sort entries
            is_time = any(t in ev.lower() for t in ['dash', 'run', 'hurdles', 'mile', 'relay', '4x'])
            entries.sort(key=lambda x: sim.parse_mark(x['mark']), reverse=not is_time)
            
            # Apply points with strict limits
            scoring_idx = 0
            team_relay_count = {}
            team_indiv_count = {}
            is_relay = 'relay' in ev.lower() or '4x' in ev.lower()
            
            for i, e in enumerate(entries):
                if scoring_idx >= len(sim.scoring_rules): break
                
                team = e['source_team']
                can_score = False
                if is_relay:
                    if team_relay_count.get(team, 0) < 1:
                        can_score = True
                        team_relay_count[team] = 1
                else:
                    if team_indiv_count.get(team, 0) < 3:
                        can_score = True
                        team_indiv_count[team] = team_indiv_count.get(team, 0) + 1
                
                if can_score:
                    pts = sim.scoring_rules[scoring_idx]
                    scores[team] = scores.get(team, 0) + pts
                    if team == "George Stevens Academy":
                        event_scores.append((ev, e.get('athlete_name', 'Relay'), pts))
                    scoring_idx += 1
        return scores, event_scores

    print("\n--- BOYS CHAMPIONSHIP ---")
    boys_scores, gsa_breakdown = simulate_strict(boys_perfs)
    for i, (team, score) in enumerate(sorted(boys_scores.items(), key=lambda x: x[1], reverse=True)):
        print(f"{i+1}. {team.ljust(35)}: {score} pts")

    print("\n--- GSA BOYS BREAKDOWN ---")
    for ev, name, pts in sorted(gsa_breakdown, key=lambda x: x[2], reverse=True):
        print(f"  {ev.ljust(25)}: {name.ljust(20)} {pts} pts")

    print("\n--- GIRLS CHAMPIONSHIP ---")
    girls_scores, _ = simulate_strict(girls_perfs)
    for i, (team, score) in enumerate(sorted(girls_scores.items(), key=lambda x: x[1], reverse=True)):
        print(f"{i+1}. {team.ljust(35)}: {score} pts")

if __name__ == "__main__":
    main()
