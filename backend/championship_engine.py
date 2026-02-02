import copy
from collections import defaultdict
from nash_engine import (
    calculate_net_value_matrix, 
    solve_optimal_roster, 
    get_event_points, 
    parse_mark
)

class ChampionshipEngine:
    def __init__(self, teams_data, events, rules, average_ties=True):
        self.teams_data_list = teams_data  # List of team dicts
        self.teams_dict = {t['team_name']: t for t in teams_data}
        self.events = events
        self.rules = rules
        self.average_ties = average_ties
        
        # Initial rosters
        self.current_rosters = {}
        self.initialize_greedy_rosters()

    def initialize_greedy_rosters(self):
        """Initializes all teams to their point-maximizing configurations."""
        for t_name, t_data in self.teams_dict.items():
            static_marks = self.get_static_field_marks([t_name])
            coeffs, r_coeffs = calculate_net_value_matrix(
                t_data, static_marks, self.rules.scoring_table, self.events, 
                average_ties=self.average_ties, weight_denial=0.0
            )
            self.current_rosters[t_name] = solve_optimal_roster(
                t_data, self.events, coeffs, r_coeffs, self.rules
            )

    def optimize_team_greedy(self, team_name):
        """Optimize a single team based purely on raw point yield against the current field."""
        t_data = self.teams_dict[team_name]
        static_marks = self.get_static_field_marks([team_name])
        coeffs, r_coeffs = calculate_net_value_matrix(
            t_data, static_marks, self.rules.scoring_table, self.events, 
            average_ties=self.average_ties, weight_denial=0.0
        )
        self.current_rosters[team_name] = solve_optimal_roster(
            t_data, self.events, coeffs, r_coeffs, self.rules
        )

    def get_full_standings(self):
        """Calculates points for the entire field based on current rosters."""
        scores = defaultdict(float)
        
        for ev in self.events:
            all_marks = []
            for t_name, roster in self.current_rosters.items():
                active_ids = roster.get(ev, [])
                t_data = self.teams_dict[t_name]
                
                # Relays first
                found_relay = False
                for r in t_data.get('relays', []):
                    if r['event'] == ev and set(active_ids) == set(r['member_ids']):
                        all_marks.append((parse_mark(r['mark']), t_name))
                        found_relay = True
                        break
                
                if not found_relay:
                    for aid in active_ids:
                        ath = next((a for a in t_data['athletes'] if a['athlete_id'] == aid), None)
                        if ath and ev in ath['best_marks']:
                            mark = parse_mark(ath['best_marks'][ev])
                            all_marks.append((mark, t_name))
                            
            points = get_event_points(all_marks, ev, self.rules.scoring_table, average_ties=self.average_ties)
            for team, pts in points.items():
                scores[team] += pts
                
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    def get_static_field_marks(self, exclude_team_names):
        """Returns background noise from teams not in the current battle."""
        static_marks = defaultdict(list)
        for t_name, roster in self.current_rosters.items():
            if t_name in exclude_team_names:
                continue
            
            t_data = self.teams_dict[t_name]
            for ev, active_ids in roster.items():
                # Relays
                found_relay = False
                for r in t_data.get('relays', []):
                    if r['event'] == ev and set(active_ids) == set(r['member_ids']):
                        static_marks[ev].append((parse_mark(r['mark']), t_name))
                        found_relay = True
                        break
                
                if not found_relay:
                    for aid in active_ids:
                        ath = next((a for a in t_data['athletes'] if a['athlete_id'] == aid), None)
                        if ath and ev in ath['best_marks']:
                            m = parse_mark(ath['best_marks'][ev])
                            if m is not None:
                                static_marks[ev].append((m, t_name))
        return static_marks

    def run_battle(self, challenger_name, defender_name, label="BATTLE"):
        """
        One-way Nash step: Challenger optimizes tactically against Defender.
        Defender optimizes purely greedily (doesn't 'fight down' unless it gains points).
        """
        challenger_data = self.teams_dict[challenger_name]
        defender_data = self.teams_dict[defender_name]
        
        static_background = self.get_static_field_marks([challenger_name, defender_name])
        
        for i in range(5): # Fewer iterations needed for cascading stability
            # 1. Defender Optimizes GREEDILY (No defensive blocking)
            self.optimize_team_greedy(defender_name)
            
            # 2. Challenger Optimizes TACTICALLY against Defender
            roster_d = self.current_rosters[defender_name]
            opp_marks_for_c = copy.deepcopy(static_background)
            for ev, aids in roster_d.items():
                found_relay = False
                for r in defender_data.get('relays', []):
                    if r['event'] == ev and set(aids) == set(r['member_ids']):
                        opp_marks_for_c[ev].append((parse_mark(r['mark']), 'DEFENDER'))
                        found_relay = True
                        break
                if not found_relay:
                    for aid in aids:
                        ath = next((a for a in defender_data['athletes'] if a['athlete_id'] == aid), None)
                        if ath and ev in ath['best_marks']:
                            opp_marks_for_c[ev].append((parse_mark(ath['best_marks'][ev]), 'DEFENDER'))
            
            coeffs_c, r_coeffs_c = calculate_net_value_matrix(
                challenger_data, opp_marks_for_c, self.rules.scoring_table, self.events, 
                average_ties=self.average_ties, weight_denial=1.0 # Challenger is tactical
            )
            self.current_rosters[challenger_name] = solve_optimal_roster(
                challenger_data, self.events, coeffs_c, r_coeffs_c, self.rules
            )

    def solve_championship(self, label="GENDER"):
        stability_counter = 0
        while stability_counter < 10:
            standings = self.get_full_standings()
            initial_order = [t for t, s in standings]
            rosters_before = copy.deepcopy(self.current_rosters)
            
            ranking_changed = False
            for i in range(len(standings) - 1):
                defender_name = standings[i][0]
                challenger_name = standings[i+1][0]
                
                self.run_battle(challenger_name, defender_name, label=label)
                
                new_standings = self.get_full_standings()
                new_order = [t for t, s in new_standings]
                
                if new_order != initial_order:
                    print(f"[{label}] !!! RANKING CHANGE DETECTED !!! {challenger_name} vs {defender_name}")
                    ranking_changed = True
                    break
            
            if ranking_changed:
                stability_counter += 1
                continue
            
            if self.current_rosters == rosters_before:
                return self.current_rosters
            
            stability_counter += 1
        return self.current_rosters

    def get_strategic_insights(self, team_name):
        """Generates a report of tactical dilemmas and untapped potential for a team."""
        t_data = self.teams_dict[team_name]
        roster = self.current_rosters[team_name]
        usage = defaultdict(int)
        
        # Pre-calculate points for every event the team is in
        current_event_points = {}
        for ev in self.events:
            all_marks = []
            for t_n, r in self.current_rosters.items():
                aids = r.get(ev, [])
                t_d = self.teams_dict[t_n]
                for aid in aids:
                    ath = next((a for a in t_d['athletes'] if a['athlete_id'] == aid), None)
                    if ath and ev in ath['best_marks']:
                        mark = parse_mark(ath['best_marks'][ev])
                        if mark is not None:
                            all_marks.append((mark, t_n, aid))
                # Add relays
                for r_obj in t_d.get('relays', []):
                    if r_obj['event'] == ev and set(aids) == set(r_obj['member_ids']):
                        mark = parse_mark(r_obj['mark'])
                        if mark is not None:
                            all_marks.append((mark, t_n, "RELAY"))
            
            # Use scoring engine to see who actually gets points
            if all_marks:
                is_time = any(x in ev.lower() for x in ['dash', 'run', 'hurdles', 'mile', 'relay', '4x'])
                sorted_all = sorted(all_marks, key=lambda x: x[0], reverse=not is_time)
                
                # Simplified point awarding to check who's in top 6
                # (Actual scoring rules might limit per team, but this is for insight)
                scoring_idx = 0
                team_limit_counts = defaultdict(int)
                pts_map = {} # aid -> points
                
                # Use standard logic
                for m, t_n, aid in sorted_all:
                    if scoring_idx >= len(self.rules.scoring_table): break
                    limit = 1 if aid == "RELAY" else 3
                    if team_limit_counts[t_n] < limit:
                        if t_n == team_name:
                            pts = self.rules.scoring_table[scoring_idx]
                            if aid == "RELAY":
                                # Award points to all athletes currently in this relay for our team
                                for member_id in roster.get(ev, []):
                                    pts_map[member_id] = pts
                            else:
                                pts_map[aid] = pts
                        scoring_idx += 1
                        team_limit_counts[t_n] += 1
                current_event_points[ev] = pts_map

        # Track usage and athlete's specific current scores
        athlete_current_scores = defaultdict(dict) # aid -> {ev: pts}
        for ev, aids in roster.items():
            pts_map = current_event_points.get(ev, {})
            for aid in aids:
                usage[aid] += 1
                athlete_current_scores[aid][ev] = pts_map.get(aid, 0)
        
        insights = {
            'team_name': team_name,
            'congested_athletes': [], 
            'relay_bottlenecks': [],
            'no_brainer_swaps': []
        }
        
        # 1. Athlete Congestion & No-Brainers
        field_marks = self.get_static_field_marks([team_name])
        for a in t_data['athletes']:
            aid = a['athlete_id']
            a_name = a['athlete_name']
            
            # Check for "Dead Weight" - athlete is maxed but scoring 0 in an event
            dead_weight_events = [ev for ev, pts in athlete_current_scores[aid].items() if pts == 0]
            
            for ev, mark_str in a['best_marks'].items():
                if ev not in self.events: continue
                if aid in roster.get(ev, []): continue
                
                my_mark = parse_mark(mark_str)
                if my_mark is None: continue
                
                opp_marks = field_marks.get(ev, [])
                test_marks = opp_marks + [(my_mark, team_name)]
                pts_result = get_event_points(test_marks, ev, self.rules.scoring_table, average_ties=self.average_ties)
                potential_val = pts_result.get(team_name, 0)
                
                if potential_val > 0:
                    if usage[aid] < self.rules.max_events_per_athlete:
                        # Open slot!
                        insights['no_brainer_swaps'].append({
                            'athlete_name': a_name,
                            'event': ev,
                            'gain': potential_val,
                            'reason': "Empty event slot available"
                        })
                    elif dead_weight_events:
                        # Swap from 0 to >0
                        insights['no_brainer_swaps'].append({
                            'athlete_name': a_name,
                            'from_event': dead_weight_events[0],
                            'to_event': ev,
                            'gain': potential_val,
                            'reason': f"Replacing 0-point {dead_weight_events[0]}"
                        })
                    else:
                        # Truly congested (all events are scoring)
                        insights['congested_athletes'].append({
                            'athlete_name': a_name,
                            'event': ev,
                            'potential_points': potential_val,
                            'current_usage': usage[aid],
                            'lowest_scoring_active': min(athlete_current_scores[aid].values()) if athlete_current_scores[aid] else 0
                        })

        # 2. Relay Criticality
        seen_relay_events = set()
        for r in t_data.get('relays', []):
            ev = r['event']
            if ev not in self.events: continue
            
            # If we are already running this event, don't flag other versions as bottlenecks
            if ev in roster: continue
            if ev in seen_relay_events: continue
            seen_relay_events.add(ev)
            
            maxed_and_scoring = [] # list of {name, events: {ev: pts}}
            maxed_but_free = []
            
            for mid in r['member_ids']:
                # They only "block" if they aren't in THIS event and are maxed out elsewhere
                if mid not in roster.get(ev, []) and usage[mid] >= self.rules.max_events_per_athlete:
                    ath = next((a for a in t_data['athletes'] if a['athlete_id'] == mid), None)
                    name = ath['athlete_name'] if ath else "Unknown"
                    
                    ath_scores = athlete_current_scores[mid]
                    scoring_events = {ev: pts for ev, pts in ath_scores.items() if pts > 0}
                    zero_events = {ev: pts for ev, pts in ath_scores.items() if pts == 0}
                    
                    info = {
                        'name': name,
                        'scoring_events': scoring_events,
                        'zero_events': list(zero_events.keys())
                    }
                    
                    if scoring_events:
                        maxed_and_scoring.append(info)
                    else:
                        maxed_but_free.append(info)
            
            if maxed_and_scoring or maxed_but_free:
                insights['relay_bottlenecks'].append({
                    'event': ev,
                    'maxed_and_scoring': maxed_and_scoring,
                    'maxed_but_free': maxed_but_free
                })

        return insights

    def get_entry_decisions(self, team_name):
        """
        Categorizes athletes based on potential scoring events (>3 vs <=3).
        Calculates simple rankings based on best season marks.
        """
        t_data = self.teams_dict[team_name]
        
        # 1. Gather "best of the best" marks globally for comparison
        # (This is a "simple simulation" - just ranking season bests)
        global_bests = defaultdict(list) # event -> [(mark, team_name)]
        for t_n, t_d in self.teams_dict.items():
            # Individuals
            for a in t_d['athletes']:
                for ev, mark_str in a['best_marks'].items():
                    m = parse_mark(mark_str)
                    if m is not None:
                        global_bests[ev].append((m, t_n))
            # Relays (optional, but let's focus on individual for "entry decisions")
            for r in t_d.get('relays', []):
                m = parse_mark(r['mark'])
                if m is not None:
                    global_bests[ev].append((m, t_n))

        # Sort global rankings
        rankings = {}
        for ev, marks in global_bests.items():
            is_time = any(x in ev.lower() for x in ['dash', 'run', 'hurdles', 'mile', 'relay', '4x'])
            rankings[ev] = sorted(marks, key=lambda x: x[0], reverse=not is_time)

        decision_athletes = []
        straightforward_athletes = []

        for a in t_data['athletes']:
            a_name = a['athlete_name']
            potential_scoring_events = []
            
            for ev, mark_str in a['best_marks'].items():
                if ev not in self.events: continue
                my_mark = parse_mark(mark_str)
                if my_mark is None: continue
                
                # Find rank in global list (simple ranking)
                event_ranks = rankings.get(ev, [])
                # To be fair, only count 3 per team in the ranking
                team_counts = defaultdict(int)
                rank_pos = 0
                my_rank = None
                
                for m, t_n in event_ranks:
                    # If this is me, record rank
                    if t_n == team_name and m == my_mark:
                        # Avoid double counting same mark
                        my_rank = rank_pos + 1
                        break
                    
                    # Otherwise, increment rank if it counts towards scoring (top 3 per team)
                    if team_counts[t_n] < 3:
                        rank_pos += 1
                        team_counts[t_n] += 1
                
                if my_rank is not None and my_rank <= len(self.rules.scoring_table):
                    potential_scoring_events.append({
                        'event': ev,
                        'rank': my_rank,
                        'mark': mark_str
                    })

            # Sort events by rank
            potential_scoring_events.sort(key=lambda x: x['rank'])
            
            athlete_info = {
                'name': a_name,
                'scoring_events': potential_scoring_events
            }
            
            if len(potential_scoring_events) > 3:
                decision_athletes.append(athlete_info)
            elif potential_scoring_events:
                straightforward_athletes.append(athlete_info)

        return {
            'decision_athletes': decision_athletes,
            'straightforward_athletes': straightforward_athletes
        }
