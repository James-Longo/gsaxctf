import sqlite3
import re
from collections import defaultdict

# Attempt to import PuLP, fallback to a robust hill-climber
try:
    import pulp
    PULP_AVAILABLE = True
except ImportError:
    PULP_AVAILABLE = False

class MeetRules:
    def __init__(self, max_events_per_athlete=3):
        self.max_events_per_athlete = max_events_per_athlete
        self.scoring_table = {0: 10, 1: 8, 2: 6, 3: 4, 4: 2, 5: 1}

def parse_mark(mark):
    if not mark or not isinstance(mark, str):
        return None
    m = mark.strip().upper()
    if any(b in m for b in ['DNF', 'DQ', 'NH', 'ND', 'SCR', 'FOUL']):
        return None
    dist_match = re.match(r"(\d+)'?\s*[-]?\s*(\d+(?:\.\d+)?)\"?", m)
    if dist_match:
        return float(dist_match.group(1)) * 12 + float(dist_match.group(2))
    if ':' in m:
        parts = m.split(':')
        return float(parts[0]) * 60 + float(parts[1])
    try:
        return float(m)
    except:
        return None

def is_better(m1, m2, event):
    if m1 is None: return False
    if m2 is None: return True
    event_low = event.lower()
    is_time = any(x in event_low for x in ['dash', 'run', 'hurdles', 'mile', 'relay', '4x'])
    return m1 < m2 if is_time else m1 > m2

def get_event_points(marks, event, scoring_table, scoring_limit=3):
    """
    marks: sorted list of (mark, team_id, is_my_team)
    Returns: {team_id: total_points}
    """
    is_relay = 'relay' in event.lower() or '4x' in event.lower()
    limit = 1 if is_relay else scoring_limit
    
    team_counts = defaultdict(int)
    team_points = defaultdict(float)
    
    scoring_idx = 0
    i = 0
    while i < len(marks) and scoring_idx < len(scoring_table):
        j = i
        while j < len(marks) and marks[j][0] == marks[i][0]:
            j += 1
        
        tied_marks = marks[i:j]
        scorable_tied_marks = [m for m in tied_marks if team_counts[m[1]] < limit]
        
        if not scorable_tied_marks:
            i = j
            continue
            
        num_to_award = min(len(scorable_tied_marks), len(scoring_table) - scoring_idx)
        total_pts = sum(scoring_table.get(scoring_idx + k, 0) for k in range(num_to_award))
        
        avg_pts = total_pts / len(scorable_tied_marks)
        for m in scorable_tied_marks:
            team_points[m[1]] += avg_pts
            team_counts[m[1]] += 1
            
        scoring_idx += num_to_award
        i = j
        
    return team_points

def calculate_net_value_matrix(my_team, opponent_roster, scoring_table):
    coeffs = {}
    events = set(opponent_roster.keys())
    for ath in my_team:
        events.update(ath['best_marks'].keys())
    
    for event in events:
        is_relay = 'relay' in event.lower() or '4x' in event.lower()
        is_time = any(x in event.lower() for x in ['dash', 'run', 'hurdles', 'mile', 'relay', '4x'])
        
        opp_marks = opponent_roster.get(event, [])
        opp_marks_sorted = sorted(opp_marks, key=lambda x: x[0], reverse=not is_time)
        initial_scores = get_event_points(opp_marks_sorted, event, scoring_table)
        opp_total_initial = sum(v for k, v in initial_scores.items() if k != 'MY_TEAM')
        
        if is_relay:
            relay_marks = [parse_mark(ath['best_marks'][event]) for ath in my_team if event in ath['best_marks']]
            if not relay_marks: continue
            best_r_mark = min(relay_marks) if is_time else max(relay_marks)
            
            new_marks = sorted(opp_marks_sorted + [(best_r_mark, 'MY_TEAM')], key=lambda x: x[0], reverse=not is_time)
            new_scores = get_event_points(new_marks, event, scoring_table)
            
            p_scored = new_scores.get('MY_TEAM', 0)
            opp_total_after = sum(v for k, v in new_scores.items() if k != 'MY_TEAM')
            v_relay = p_scored + (opp_total_initial - opp_total_after)
            for ath in my_team:
                coeffs[(ath['athlete_id'], event)] = v_relay / 4.0
        else:
            for ath in my_team:
                if event not in ath['best_marks']: continue
                my_mark = parse_mark(ath['best_marks'][event])
                if my_mark is None: continue
                
                new_marks = sorted(opp_marks_sorted + [(my_mark, 'MY_TEAM')], key=lambda x: x[0], reverse=not is_time)
                new_scores = get_event_points(new_marks, event, scoring_table)
                p_scored = new_scores.get('MY_TEAM', 0)
                opp_total_after = sum(v for k, v in new_scores.items() if k != 'MY_TEAM')
                coeffs[(ath['athlete_id'], event)] = p_scored + (opp_total_initial - opp_total_after)
                
    return coeffs

def solve_optimal_roster(my_team, events, coeffs, rules):
    # --- Hill-Climbing Strategy ---
    # Start with an empty roster or some baseline
    # Repeatedly attempt to improve by adding or swapping events
    
    current_roster = defaultdict(list)
    usage = defaultdict(int)
    
    def get_total_val(roster):
        total = 0
        for ev, aids in roster.items():
            for aid in aids:
                total += coeffs.get((aid, ev), 0)
        return total

    # Initial Greedy Pass
    potential = sorted(coeffs.items(), key=lambda x: x[1], reverse=True)
    for (aid, ev), val in potential:
        if val <= 0.01: continue # Ignore non-scoring
        is_relay = 'relay' in ev.lower() or '4x' in ev.lower()
        if usage[aid] < rules.max_events_per_athlete:
            if is_relay:
                if len(current_roster[ev]) < 4:
                    current_roster[ev].append(aid)
                    usage[aid] += 1
            else:
                current_roster[ev].append(aid)
                usage[aid] += 1

    # Hill-Climbing Swaps
    improved = True
    while improved:
        improved = False
        current_val = get_total_val(current_roster)
        
        # 1. Try adding something new (if possible)
        for (aid, ev), val in coeffs.items():
            if val <= 0.01: continue
            if aid in current_roster[ev]: continue
            
            is_relay = 'relay' in ev.lower() or '4x' in ev.lower()
            relay_cap = 4 if is_relay else 100
            
            if usage[aid] < rules.max_events_per_athlete and len(current_roster[ev]) < relay_cap:
                current_roster[ev].append(aid)
                usage[aid] += 1
                new_val = get_total_val(current_roster)
                if new_val > current_val + 0.001:
                    current_val = new_val
                    improved = True
                else:
                    current_roster[ev].remove(aid)
                    usage[aid] -= 1

        # 2. Try swapping 1-for-1 for athletes at limit
        for ath in my_team:
            aid = ath['athlete_id']
            if usage[aid] >= rules.max_events_per_athlete:
                # Find events this athlete is currently in
                my_events = [ev for ev, aids in current_roster.items() if aid in aids]
                # Find events they are NOT in
                other_events = [(ev, v) for (a, ev), v in coeffs.items() if a == aid and ev not in my_events]
                
                for ev_to_drop in my_events:
                    for ev_to_add, add_val in other_events:
                        drop_val = coeffs.get((aid, ev_to_drop), 0)
                        
                        is_relay_add = 'relay' in ev_to_add.lower() or '4x' in ev_to_add.lower()
                        relay_cap = 4 if is_relay_add else 100
                        
                        if add_val > drop_val + 0.001 and len(current_roster[ev_to_add]) < relay_cap:
                            current_roster[ev_to_drop].remove(aid)
                            current_roster[ev_to_add].append(aid)
                            new_val = get_total_val(current_roster)
                            if new_val > current_val + 0.001:
                                current_val = new_val
                                improved = True
                                break # Move to next athlete
                            else:
                                # Revert
                                current_roster[ev_to_add].remove(aid)
                                current_roster[ev_to_drop].append(aid)
                    if improved: break

    return dict(current_roster)

def run_simulation(team_a_data, team_b_data, events, rules):
    roster_a = {ev: [] for ev in events}
    roster_b = {ev: [] for ev in events}
    
    history = []
    
    print(f"Starting Iterative Best Response...")
    for i in range(100):
        # Step 1: Team B optimizes against A
        opp_roster_for_b = {}
        for ev, aids in roster_a.items():
            opp_roster_for_b[ev] = []
            for aid in aids:
                ath = next((a for a in team_a_data if a['athlete_id'] == aid), None)
                if ath and ev in ath['best_marks']:
                    opp_roster_for_b[ev].append((parse_mark(ath['best_marks'][ev]), 'TEAM_A'))
        
        coeffs_b = calculate_net_value_matrix(team_b_data, opp_roster_for_b, rules.scoring_table)
        new_roster_b = solve_optimal_roster(team_b_data, events, coeffs_b, rules)
        
        # Diff for logging
        for ev in events:
            old = set(roster_b.get(ev, []))
            new = set(new_roster_b.get(ev, []))
            added = new - old
            removed = old - new
            for a in added: 
                name = next(ath['athlete_name'] for ath in team_b_data if ath['athlete_id'] == a)
                print(f"  [B-Turn {i+1}] + {name} added to {ev}")
            for a in removed:
                name = next(ath['athlete_name'] for ath in team_b_data if ath['athlete_id'] == a)
                print(f"  [B-Turn {i+1}] - {name} removed from {ev}")
        
        # Step 2: Team A optimizes against B
        opp_roster_for_a = {}
        for ev, aids in new_roster_b.items():
            opp_roster_for_a[ev] = []
            for aid in aids:
                ath = next((a for a in team_b_data if a['athlete_id'] == aid), None)
                if ath and ev in ath['best_marks']:
                    opp_roster_for_a[ev].append((parse_mark(ath['best_marks'][ev]), 'TEAM_B'))
        
        coeffs_a = calculate_net_value_matrix(team_a_data, opp_roster_for_a, rules.scoring_table)
        new_roster_a = solve_optimal_roster(team_a_data, events, coeffs_a, rules)

        for ev in events:
            old = set(roster_a.get(ev, []))
            new = set(new_roster_a.get(ev, []))
            added = new - old
            removed = old - new
            for a in added: 
                name = next(ath['athlete_name'] for ath in team_a_data if ath['athlete_id'] == a)
                print(f"  [A-Turn {i+1}] + {name} added to {ev}")
            for a in removed:
                name = next(ath['athlete_name'] for ath in team_a_data if ath['athlete_id'] == a)
                print(f"  [A-Turn {i+1}] - {name} removed from {ev}")

        state = (tuple(sorted((k, tuple(sorted(v))) for k, v in new_roster_a.items())),
                 tuple(sorted((k, tuple(sorted(v))) for k, v in new_roster_b.items())))
        
        if new_roster_a == roster_a and new_roster_b == roster_b:
            print(f"Convergence reached at iteration {i+1}.")
            return new_roster_a, new_roster_b
            
        if state in history:
            print(f"Cycle detected at iteration {i+1}.")
            # Find where the cycle starts
            cycle_start = history.index(state)
            return history[cycle_start:]
            
        history.append(state)
        roster_a = new_roster_a
        roster_b = new_roster_b
        
    return roster_a, roster_b

def get_team_dataset(db_path, team_name, season, year):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    query = """
        SELECT athletes.id as aid, athletes.name as aname, p.event, p.mark
        FROM performances p
        JOIN athletes ON p.athlete_id = athletes.id
        WHERE p.team = ? AND p.season = ? AND p.year = ?
    """
    rows = cursor.execute(query, (team_name, season, year)).fetchall()
    conn.close()
    
    athletes_dict = {}
    for r in rows:
        aid, ev, mark = r['aid'], r['event'], r['mark']
        if aid not in athletes_dict:
            athletes_dict[aid] = {'athlete_id': aid, 'athlete_name': r['aname'], 'best_marks': {}}
        m = parse_mark(mark)
        if m is not None:
            existing = parse_mark(athletes_dict[aid]['best_marks'].get(ev))
            if existing is None or is_better(m, existing, ev):
                athletes_dict[aid]['best_marks'][ev] = mark
    return list(athletes_dict.values())
