from championship_engine import ChampionshipEngine
from nash_engine import get_team_dataset, MeetRules
import sqlite3
import os

def get_all_season_events(db_path, season, year):
    conn = sqlite3.connect(db_path)
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
    
    teams = [
        "Orono High School", "Bucksport High School", "George Stevens Academy",
        "Central High School", "Piscataquis Community High School", "Sumner/Narragaugus",
        "Bangor Christian Schools", "Foxcroft Academy", "Penquis Valley High School"
    ]
    
    rules = MeetRules(max_events_per_athlete=3)
    team_data = {t: get_team_dataset(db_path, t, season, year) for t in teams}
    
    print("# PVC STRATEGIC COACHING INSIGHTS REPORT (2026)")
    
    for gender_label, events in [("BOYS", boys_events), ("GIRLS", girls_events)]:
        print(f"\n## {gender_label} DIVISION ANALYSIS")
        engine = ChampionshipEngine(list(team_data.values()), events, rules, average_ties=False)
        engine.solve_championship(label=gender_label)
        
        standings = engine.get_full_standings()
        
        for i, (team_name, score) in enumerate(standings):
            print(f"\n### {i+1}. {team_name} ({score:.1f} pts)")
            insights = engine.get_strategic_insights(team_name)
            
            if insights['no_brainer_swaps']:
                print("#### 💡 No-Brainer Swaps (Low-Hanging Fruit)")
                for s in insights['no_brainer_swaps']:
                    if 'from_event' in s:
                        print(f"- **{s['athlete_name']}**: Swap from 0-point {s['from_event']} to **{s['to_event']}** (+{s['gain']} pts gain)")
                    else:
                        print(f"- **{s['athlete_name']}**: Enter **{s['event']}** in open slot (+{s['gain']} pts gain)")

            if insights['congested_athletes']:
                print("#### Athlete Congestion (High-End Talent Blocks)")
                by_ath = {}
                for c in insights['congested_athletes']:
                    name = c['athlete_name']
                    if name not in by_ath: by_ath[name] = []
                    gain = c['potential_points'] - c['lowest_scoring_active']
                    gain_str = f"(+{gain:.1f} pts upgrade)" if gain > 0 else f"({c['potential_points']:.1f} pts raw potential)"
                    by_ath[name].append(f"{c['event']} {gain_str}, current low: {c['lowest_scoring_active']} pts")
                
                for name, potentials in by_ath.items():
                    print(f"- **{name}**: Maxed out. Potentially sitting on: {', '.join(potentials)}")
            
            if insights['relay_bottlenecks']:
                print("#### Relay Bottlenecks")
                for rb in insights['relay_bottlenecks']:
                    ev = rb['event']
                    print(f"- **{ev}**:")
                    
                    if rb['maxed_and_scoring']:
                        print("  * **Blocked by scoring individual talent:**")
                        for info in rb['maxed_and_scoring']:
                            ev_list = [f"{e} ({p} pts)" for e, p in info['scoring_events'].items()]
                            print(f"    - **{info['name']}**: Currently prioritized in: {', '.join(ev_list)}.")
                    
                    if rb['maxed_but_free']:
                        print("  * **⚠️ HEAVY BURDEN (Sub-optimal Allocation):**")
                        for info in rb['maxed_but_free']:
                            print(f"    - **{info['name']}**: Maxed out but scoring **0 pts** in: {', '.join(info['zero_events'])}.")
                            print(f"      *Tactical Note: This athlete should be moved into the relay immediately.*")
                    
                    if not rb['maxed_and_scoring'] and not rb['maxed_but_free']:
                        print("  * *Currently under-prioritized in optimization.*")

            if not insights['congested_athletes'] and not insights['relay_bottlenecks'] and not insights['no_brainer_swaps']:
                print("*Roster is currently fully optimized.*")

    print("\n\n✓ Strategic Insights Generated")

if __name__ == "__main__":
    main()
