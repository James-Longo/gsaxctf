import sqlite3
import re
from collections import defaultdict

class MeetRules:
    def __init__(self, max_events_per_athlete=3, max_entries_per_event=3):
        self.max_events_per_athlete = max_events_per_athlete
        self.max_entries_per_event = max_entries_per_event
        self.scoring_table = {0: 10, 1: 8, 2: 6, 3: 4, 4: 2, 5: 1}

def parse_mark(mark):
    if not mark or not isinstance(mark, str):
        return None
    m = mark.strip().upper()
    if any(b in m for b in ['DNF', 'DQ', 'NH', 'ND', 'SCR', 'FOUL']):
        return None
    # Check for distance (must contain ', ", or -)
    if any(c in m for c in ["'", '"', "-"]):
        dist_match = re.match(r"(\d+)'?\s*[-]?\s*(\d+(?:\.\d+)?)\"?", m)
        if dist_match:
            return float(dist_match.group(1)) * 12 + float(dist_match.group(2))
    if ':' in m:
        parts = m.split(':')
        if len(parts) == 2:
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

def get_event_points(marks, event, scoring_table, scoring_limit=3, average_ties=True):
    is_relay = 'relay' in event.lower() or '4x' in event.lower()
    limit = 1 if is_relay else scoring_limit
    
    # Filter out None marks
    valid_marks = [m for m in marks if m[0] is not None]
    if not valid_marks:
        return defaultdict(float)
        
    team_counts = defaultdict(int)
    team_points = defaultdict(float)
    
    sorted_marks = sorted(valid_marks, key=lambda x: x[0], reverse=not any(t in event.lower() for t in ['dash', 'run', 'hurdles', 'mile', 'relay', '4x']))
    
    scoring_idx = 0
    i = 0
    while i < len(sorted_marks) and scoring_idx < len(scoring_table):
        j = i
        while j < len(sorted_marks) and sorted_marks[j][0] == sorted_marks[i][0]:
            j += 1
        
        tied_marks = sorted_marks[i:j]
        scorable_tied_marks = [m for m in tied_marks if team_counts[m[1]] < limit]
        
        if not scorable_tied_marks:
            i = j
            continue
            
        if average_ties:
            num_to_award = min(len(scorable_tied_marks), len(scoring_table) - scoring_idx)
            total_pts = sum(scoring_table.get(scoring_idx + k, 0) for k in range(num_to_award))
            
            avg_pts = total_pts / len(scorable_tied_marks)
            for m in scorable_tied_marks:
                team_points[m[1]] += avg_pts
                team_counts[m[1]] += 1
            scoring_idx += num_to_award
        else:
            for m in scorable_tied_marks:
                if scoring_idx < len(scoring_table):
                    team_points[m[1]] += scoring_table.get(scoring_idx, 0)
                    team_counts[m[1]] += 1
                    scoring_idx += 1
                else:
                    break
        i = j
        
    return team_points

def calculate_net_value_matrix(my_team, opponent_roster, scoring_table, events_list, average_ties=True, weight_denial=1.0):
    """
    Returns:
        coeffs: {(ath_id, event): value} for individuals
        relay_coeffs: {(relay_id): value} where relay_id is an index into team's relays
    """
    coeffs = {}
    relay_coeffs = {}
    
    # Individuals
    for event in events_list:
        if 'relay' in event.lower() or '4x' in event.lower(): continue
        
        opp_marks = opponent_roster.get(event, [])
        initial_scores = get_event_points(opp_marks, event, scoring_table, average_ties=average_ties)
        opp_total_initial = sum(v for k, v in initial_scores.items() if k != 'MY_TEAM')
        
        for ath in my_team['athletes']:
            if event not in ath['best_marks']: continue
            my_mark = parse_mark(ath['best_marks'][event])
            if my_mark is None: continue
            
            new_marks = opp_marks + [(my_mark, 'MY_TEAM')]
            new_scores = get_event_points(new_marks, event, scoring_table, average_ties=average_ties)
            p_scored = new_scores.get('MY_TEAM', 0)
            opp_total_after = sum(v for k, v in new_scores.items() if k != 'MY_TEAM')
            
            # The value is what we score + what we deny the opponent (weighted)
            denial = (opp_total_initial - opp_total_after)
            coeffs[(ath['athlete_id'], event)] = p_scored + (denial * weight_denial) + (p_scored * 0.001)
            
    # Relays
    for ri, r in enumerate(my_team.get('relays', [])):
        event = r['event']
        if event not in events_list: continue
        
        opp_marks = opponent_roster.get(event, [])
        initial_scores = get_event_points(opp_marks, event, scoring_table, average_ties=average_ties)
        opp_total_initial = sum(v for k, v in initial_scores.items() if k != 'MY_TEAM')
        
        my_mark = parse_mark(r['mark'])
        if my_mark is None: continue
        
        new_marks = opp_marks + [(my_mark, 'MY_TEAM')]
        new_scores = get_event_points(new_marks, event, scoring_table, average_ties=average_ties)
        p_scored = new_scores.get('MY_TEAM', 0)
        opp_total_after = sum(v for k, v in new_scores.items() if k != 'MY_TEAM')
        
        denial = (opp_total_initial - opp_total_after)
        relay_coeffs[ri] = p_scored + (denial * weight_denial) + (p_scored * 0.001)
        
    return coeffs, relay_coeffs

def solve_optimal_roster(team_data, events, coeffs, relay_coeffs, rules):
    """
    team_data: {athletes: [], relays: []}
    """
    current_roster = defaultdict(list) # event -> [ids]
    active_relays = set() # indices into team_data['relays']
    usage = defaultdict(int)
    
    def get_total_val():
        total = 0
        for (aid, ev), val in coeffs.items():
            if aid in current_roster[ev]: total += val
        for ri in active_relays:
            total += relay_coeffs.get(ri, 0)
        return total

    # Hill-Climbing
    improved = True
    while improved:
        improved = False
        current_val = get_total_val()
        
        # 1. Try adding/dropping individual events
        for (aid, ev), val in coeffs.items():
            if val <= 0: continue
            
            # If in, try dropping? (Usually doesn't help unless val < 0)
            if aid in current_roster[ev]:
                # Non-intuitive but let's stick to additions/swaps
                continue
            
            # If not in, try adding (enforce entry limit per team per individual event)
            if usage[aid] < rules.max_events_per_athlete:
                if len(current_roster[ev]) < rules.max_entries_per_event:
                    # Clear path: just add it
                    current_roster[ev].append(aid)
                    usage[aid] += 1
                    new_val = get_total_val()
                    if new_val > current_val + 0.001:
                        current_val = new_val
                        improved = True
                    else:
                        current_roster[ev].remove(aid)
                        usage[aid] -= 1
                else:
                    # Event is FULL. Can we displace a teammate for a net gain?
                    best_swap_val = -1
                    drop_aid = None
                    for raid in current_roster[ev]:
                        r_val = coeffs.get((raid, ev), 0)
                        if val > r_val + 0.001:
                            if val - r_val > best_swap_val:
                                best_swap_val = val - r_val
                                drop_aid = raid
                    
                    if drop_aid:
                        current_roster[ev].remove(drop_aid)
                        current_roster[ev].append(aid)
                        usage[drop_aid] -= 1
                        usage[aid] += 1
                        new_val = get_total_val()
                        if new_val > current_val + 0.001:
                            current_val = new_val
                            improved = True
                        else:
                            # Roll back
                            current_roster[ev].remove(aid)
                            current_roster[ev].append(drop_aid)
                            usage[aid] -= 1
                            usage[drop_aid] += 1

            elif usage[aid] >= rules.max_events_per_athlete:
                # Try swapping with current events for this athlete
                for ev_drop in [e for e, aids in current_roster.items() if aid in aids]:
                    # Need to check if target event is full
                    if len(current_roster[ev]) < rules.max_entries_per_event:
                        current_roster[ev_drop].remove(aid)
                        current_roster[ev].append(aid)
                        new_val = get_total_val()
                        if new_val > current_val + 0.001:
                            current_val = new_val
                            improved = True
                            break
                        else:
                            current_roster[ev].remove(aid)
                            current_roster[ev_drop].append(aid)
                    else:
                        # Target event is full. Try displacing a teammate AND dropping current event.
                        # This is complex, but let's try a simple version:
                        for drop_aid in current_roster[ev]:
                            r_val = coeffs.get((drop_aid, ev), 0)
                            my_old_val = coeffs.get((aid, ev_drop), 0)
                            if val > r_val + 0.001: # Potential gain from the displacement itself
                                current_roster[ev_drop].remove(aid)
                                current_roster[ev].remove(drop_aid)
                                current_roster[ev].append(aid)
                                usage[drop_aid] -= 1
                                # usage[aid] remains same
                                new_val = get_total_val()
                                if new_val > current_val + 0.001:
                                    current_val = new_val
                                    improved = True
                                    break
                                else:
                                    # Roll back
                                    current_roster[ev].remove(aid)
                                    current_roster[ev].append(drop_aid)
                                    current_roster[ev_drop].append(aid)
                                    usage[drop_aid] += 1
                        if improved: break
                if improved: break
        
        if improved: continue

        # 2. Try adding/dropping relays
        for ri, val in relay_coeffs.items():
            if val <= 0: continue
            if ri in active_relays: continue
            
            r = team_data['relays'][ri]
            ev = r['event']
            
            # Rule: Only one relay per team per event (A-team only)
            if any(team_data['relays'][other_ri]['event'] == ev for other_ri in active_relays):
                continue
                
            mids = r['member_ids']
            if not mids or len(mids) < 4: continue
            
            # Can we afford 4 slots?
            # We might need to drop individual events to make room
            needed_drops = []
            possible = True
            for mid in mids:
                if usage[mid] >= rules.max_events_per_athlete:
                    # Find weakest event to drop
                    best_ev_to_drop = None
                    min_val = 999
                    for ev_d in [e for e, aids in current_roster.items() if mid in aids]:
                        v = coeffs.get((mid, ev_d), 0)
                        if v < min_val:
                            min_val = v
                            best_ev_to_drop = ev_d
                    
                    if best_ev_to_drop:
                        needed_drops.append((mid, best_ev_to_drop, min_val))
                    else:
                        possible = False
                        break
            
            if possible:
                # Check if gain > cost
                cost = sum(d[2] for d in needed_drops)
                if val > cost + 0.001:
                    # Perform surgical swap
                    for mid, ev_d, _ in needed_drops:
                        current_roster[ev_d].remove(mid)
                        usage[mid] -= 1
                    active_relays.add(ri)
                    for mid in mids:
                        usage[mid] += 1
                    improved = True # Value increased
                    break
        
    # Convert to standard roster format
    final_roster = defaultdict(list)
    for ev, aids in current_roster.items():
        final_roster[ev].extend(aids)
    for ri in active_relays:
        r = team_data['relays'][ri]
        final_roster[r['event']] = r['member_ids']
    
    return dict(final_roster)

def run_simulation(team_a_data, team_b_data, events, rules):
    name_a = team_a_data.get('team_name', 'Team A')
    name_b = team_b_data.get('team_name', 'Team B')
    roster_a = {ev: [] for ev in events}
    roster_b = {ev: [] for ev in events}
    
    history = []
    
    def print_current_balance(r_a, r_b, step_label):
        pts_a = 0
        pts_b = 0
        for ev in events:
            marks = []
            for aid in r_a.get(ev, []):
                ath = next((a for a in team_a_data['athletes'] if a['athlete_id'] == aid), None)
                if ath and ev in ath['best_marks']:
                    marks.append((parse_mark(ath['best_marks'][ev]), 'A'))
                else:
                    for r in team_a_data['relays']:
                        if r['event'] == ev and set(r_a[ev]) == set(r['member_ids']):
                            marks.append((parse_mark(r['mark']), 'A'))
                            break
            for aid in r_b.get(ev, []):
                ath = next((a for a in team_b_data['athletes'] if a['athlete_id'] == aid), None)
                if ath and ev in ath['best_marks']:
                    marks.append((parse_mark(ath['best_marks'][ev]), 'B'))
                else:
                    for r in team_b_data['relays']:
                        if r['event'] == ev and set(r_b[ev]) == set(r['member_ids']):
                            marks.append((parse_mark(r['mark']), 'B'))
                            break
            if marks:
                res = get_event_points(marks, ev, rules.scoring_table)
                pts_a += res.get('A', 0)
                pts_b += res.get('B', 0)
        print(f"  [{step_label}] Score: {name_a} {pts_a:.1f} | {name_b} {pts_b:.1f}")

    print(f"Starting tactical iteration between {name_a} and {name_b}...")
    for i in range(20):
        # Step 1: Team B optimizes against A
        opp_marks_for_b = defaultdict(list)
        for ev, aids in roster_a.items():
            for aid in aids:
                # Find athlete in A's data (individuals or relay members)
                ath = next((a for a in team_a_data['athletes'] if a['athlete_id'] == aid), None)
                if ath and ev in ath['best_marks']:
                    opp_marks_for_b[ev].append((parse_mark(ath['best_marks'][ev]), 'TEAM_A'))
                else:
                    # Check relays
                    for r in team_a_data['relays']:
                        if r['event'] == ev and set(aids) == set(r['member_ids']):
                            opp_marks_for_b[ev].append((parse_mark(r['mark']), 'TEAM_A'))
                            break
        
        coeffs_b, r_coeffs_b = calculate_net_value_matrix(team_b_data, opp_marks_for_b, rules.scoring_table, events)
        new_roster_b = solve_optimal_roster(team_b_data, events, coeffs_b, r_coeffs_b, rules)
        
        if new_roster_b != roster_b:
            print_current_balance(roster_a, new_roster_b, f"Turn {i+1} - {name_b} Adjusts")
        
        # Step 2: Team A optimizes against B
        opp_marks_for_a = defaultdict(list)
        for ev, aids in new_roster_b.items():
            for aid in aids:
                ath = next((a for a in team_b_data['athletes'] if a['athlete_id'] == aid), None)
                if ath and ev in ath['best_marks']:
                    opp_marks_for_a[ev].append((parse_mark(ath['best_marks'][ev]), 'TEAM_B'))
                else:
                    for r in team_b_data['relays']:
                        if r['event'] == ev and set(aids) == set(r['member_ids']):
                            opp_marks_for_a[ev].append((parse_mark(r['mark']), 'TEAM_B'))
                            break
        
        coeffs_a, r_coeffs_a = calculate_net_value_matrix(team_a_data, opp_marks_for_a, rules.scoring_table, events)
        new_roster_a = solve_optimal_roster(team_a_data, events, coeffs_a, r_coeffs_a, rules)

        if new_roster_a != roster_a:
            print_current_balance(new_roster_a, new_roster_b, f"Turn {i+1} - {name_a} Adjusts")

        state = (tuple(sorted((k, tuple(sorted(v))) for k, v in new_roster_a.items())),
                 tuple(sorted((k, tuple(sorted(v))) for k, v in new_roster_b.items())))
        
        if new_roster_a == roster_a and new_roster_b == roster_b:
            print(f"Convergence reached at iteration {i+1}.")
            return new_roster_a, new_roster_b
            
        if state in history:
            print(f"Cycle detected at iteration {i+1}.")
            return history[history.index(state):]
            
        history.append(state)
        roster_a, roster_b = new_roster_a, new_roster_b
        
    return roster_a, roster_b

def get_team_dataset(db_path, team_name, season, year):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # Get all athletes first to build name-to-id map
    raw_athletes = cursor.execute("SELECT id, name FROM athletes").fetchall()
    name_to_id = {r['name']: r['id'] for r in raw_athletes}
    
    # Get all athletes for this team regardless of whether they have individual performances
    query_all_aths = """
        SELECT DISTINCT a.id, a.name, p.event, p.mark
        FROM athletes a
        JOIN performances p ON a.id = p.athlete_id
        WHERE p.team = ? AND p.season = ? AND p.year = ?
    """
    rows = cursor.execute(query_all_aths, (team_name, season, year)).fetchall()
    conn.close()
    
    athletes_dict = {}
    relays = []
    
    for r in rows:
        aid, name, ev, mark = r['id'], r['name'], r['event'], r['mark']
        ev_low = ev.lower()
        is_boys_event = 'boys' in ev_low
        is_girls_event = 'girls' in ev_low
        
        if ',' in name:
            # Relay
            members = [n.strip() for n in name.split(',')]
            mids = [name_to_id.get(n) for n in members if name_to_id.get(n)]
            if len(mids) == 4:
                relays.append({'event': ev, 'mark': mark, 'member_ids': mids, 'gender': 'boys' if is_boys_event else 'girls'})
        else:
            # Individual
            if aid not in athletes_dict:
                athletes_dict[aid] = {'athlete_id': aid, 'athlete_name': name, 'best_marks': {}, 'gender': 'boys' if is_boys_event else 'girls'}
            
            # Update gender if we see a more specific event (sometimes 'boys'/'girls' is missing in first event)
            if is_boys_event: athletes_dict[aid]['gender'] = 'boys'
            if is_girls_event: athletes_dict[aid]['gender'] = 'girls'

            m = parse_mark(mark)
            if m is not None:
                existing = parse_mark(athletes_dict[aid]['best_marks'].get(ev))
                if existing is None or is_better(m, existing, ev):
                    athletes_dict[aid]['best_marks'][ev] = mark
                    
    return {'athletes': list(athletes_dict.values()), 'relays': relays, 'team_name': team_name}
