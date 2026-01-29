import sqlite3
import re
from collections import defaultdict

# Attempt to import PuLP, fallback to a robust greedy solver if not available
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
    """
    my_team: list of {athlete_id, athlete_name, best_marks, is_relay_athlete}
    opponent_roster: {event: [(mark, team_id)]}
    """
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
            # For relays, we calculate a single team value and distribute it
            # Find the best relay mark for my team
            relay_marks = [parse_mark(ath['best_marks'][event]) for ath in my_team if event in ath['best_marks']]
            if not relay_marks: continue
            best_r_mark = min(relay_marks) if is_time else max(relay_marks)
            
            new_marks = sorted(opp_marks_sorted + [(best_r_mark, 'MY_TEAM')], key=lambda x: x[0], reverse=not is_time)
            new_scores = get_event_points(new_marks, event, scoring_table)
            
            p_scored = new_scores.get('MY_TEAM', 0)
            opp_total_after = sum(v for k, v in new_scores.items() if k != 'MY_TEAM')
            v_relay = p_scored + (opp_total_initial - opp_total_after)
            
            # Distribute to all athletes who *could* run it
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
    if not PULP_AVAILABLE:
        # Robust Greedy Fallback
        selected = []
        usage = defaultdict(int)
        event_counts = defaultdict(int)
        
        potential = sorted(coeffs.items(), key=lambda x: x[1], reverse=True)
        
        for (aid, ev), val in potential:
            if val <= 0: continue
            is_relay = 'relay' in ev.lower() or '4x' in ev.lower()
            relay_limit = 1 if is_relay else 100 # Unlimited individual as per user
            
            # Limit check
            if usage[aid] < rules.max_events_per_athlete:
                if is_relay:
                    # Check if we can still add to this relay (max 4)
                    current_relay_count = sum(1 for ra, re in selected if re == ev)
                    if current_relay_count < 4:
                        selected.append((aid, ev))
                        usage[aid] += 1
                else:
                    selected.append((aid, ev))
                    usage[aid] += 1
        
        new_roster = defaultdict(list)
        for aid, ev in selected:
            new_roster[ev].append(aid)
        return dict(new_roster)
    else:
        prob = pulp.LpProblem("Optimal_Roster", pulp.LpMaximize)
        x = {}
        for ath in my_team:
            aid = ath['athlete_id']
            for ev in events:
                if (aid, ev) in coeffs:
                    x[(aid, ev)] = pulp.LpVariable(f"x_{aid}_{ev.replace(' ', '_')}_{hash(aid)%1000}", cat='Binary')
        
        prob += pulp.lpSum(coeffs[(aid, ev)] * x[(aid, ev)] for (aid, ev) in x)
        
        # Constraints
        for ath in my_team:
            aid = ath['athlete_id']
            ath_vars = [x[(aid, ev)] for ev in events if (aid, ev) in x]
            if ath_vars:
                prob += pulp.lpSum(ath_vars) <= rules.max_events_per_athlete
        
        for ev in events:
            is_relay = 'relay' in ev.lower() or '4x' in ev.lower()
            if is_relay:
                ev_vars = [x[(aid, ev)] for ath in my_team if (ath['athlete_id'], ev) in x]
                if ev_vars:
                    prob += pulp.lpSum(ev_vars) <= 4
        
        prob.solve(pulp.PULP_CBC_CMD(msg=0))
        new_roster = defaultdict(list)
        for (aid, ev) in x:
            if pulp.value(x[(aid, ev)]) and pulp.value(x[(aid, ev)]) > 0.5:
                new_roster[ev].append(aid)
        return dict(new_roster)

def run_simulation(team_a_data, team_b_data, events, rules):
    # Initialize: A optimizes against empty B
    roster_b = {ev: [] for ev in events}
    roster_a = {ev: [] for ev in events}
    
    history = []
    
    for i in range(100): # Safety Break
        # Step 1: Team B optimizes against A
        opp_roster_for_b = {}
        for ev, aids in roster_a.items():
            opp_roster_for_b[ev] = []
            for aid in aids:
                ath = next((a for a in team_a_data if a['athlete_id'] == aid), None)
                if ath and ev in ath['best_marks']:
                    opp_roster_for_b[ev].append((parse_mark(ath['best_marks'][ev]), 'TEAM_A'))
        
        coeffs_b = calculate_net_value_matrix(team_b_data, opp_roster_for_b, rules.scoring_table)
        roster_b = solve_optimal_roster(team_b_data, events, coeffs_b, rules)
        
        # Step 2: Team A optimizes against B
        opp_roster_for_a = {}
        for ev, aids in roster_b.items():
            opp_roster_for_a[ev] = []
            for aid in aids:
                ath = next((a for a in team_b_data if a['athlete_id'] == aid), None)
                if ath and ev in ath['best_marks']:
                    opp_roster_for_a[ev].append((parse_mark(ath['best_marks'][ev]), 'TEAM_B'))
        
        coeffs_a = calculate_net_value_matrix(team_a_data, opp_roster_for_a, rules.scoring_table)
        new_roster_a = solve_optimal_roster(team_a_data, events, coeffs_a, rules)
        
        # State Hash for Cycle Detection
        state = (tuple(sorted((k, tuple(sorted(v))) for k, v in new_roster_a.items())),
                 tuple(sorted((k, tuple(sorted(v))) for k, v in roster_b.items())))
        
        if new_roster_a == roster_a:
            print(f"Convergence reached at iteration {i+1}.")
            return new_roster_a, roster_b
            
        if state in history:
            print(f"Cycle detected at iteration {i+1}.")
            return history[history.index(state):]
            
        history.append(state)
        roster_a = new_roster_a
        
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
