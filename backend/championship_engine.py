import copy
from collections import defaultdict
from nash_engine import (
    calculate_net_value_matrix, 
    solve_optimal_roster, 
    get_event_points, 
    parse_mark
)

class ChampionshipEngine:
    def __init__(self, teams_data, events, rules):
        self.teams_data_list = teams_data  # List of team dicts
        self.teams_dict = {t['team_name']: t for t in teams_data}
        self.events = events
        self.rules = rules
        
        # Initial rosters (Greedy)
        self.current_rosters = {}
        for t_name, t_data in self.teams_dict.items():
            self.current_rosters[t_name] = self._get_greedy_roster(t_data)

    def _get_greedy_roster(self, team_data):
        """Standard greedy best-3 strategy."""
        roster = {ev: [] for ev in self.events}
        
        # Collect all possible performances
        ath_perfs = defaultdict(list)
        for a in team_data['athletes']:
            for ev, mark in a['best_marks'].items():
                if ev in self.events:
                    ath_perfs[a['athlete_id']].append({
                        'event': ev,
                        'mark': mark,
                        'athlete_id': a['athlete_id']
                    })
        
        # Simple greedy: for each athlete, take their 3 best events (simplified)
        # In reality, we just want A roster. The Nash loop will improve it.
        for aid, perfs in ath_perfs.items():
            # Sort by points (approximate using 10.0 for all for now, or just take first 3)
            # Better: just take first 3 available events to fill slots
            for p in perfs[:3]:
                roster[p['event']].append(aid)

        # Relays: If they have relays, add them
        for r in team_data.get('relays', []):
            if r['event'] in self.events:
                # Greedy relay: if we have 4 members, just put it in
                if len(r['member_ids']) == 4:
                    roster[r['event']] = r['member_ids']
                    
        return roster

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
                            
            points = get_event_points(all_marks, ev, self.rules.scoring_table)
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
        """Iterative Nash loop between two teams, Treating others as static."""
        challenger_data = self.teams_dict[challenger_name]
        defender_data = self.teams_dict[defender_name]
        
        static_background = self.get_static_field_marks([challenger_name, defender_name])
        
        roster_c = self.current_rosters[challenger_name]
        roster_d = self.current_rosters[defender_name]
        
        for i in range(10):
            # 1. Challenger Optimizes
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
                challenger_data, opp_marks_for_c, self.rules.scoring_table, self.events
            )
            new_roster_c = solve_optimal_roster(
                challenger_data, self.events, coeffs_c, r_coeffs_c, self.rules
            )
            c_changed = (new_roster_c != roster_c)
            roster_c = new_roster_c
            
            # 2. Defender Optimizes
            opp_marks_for_d = copy.deepcopy(static_background)
            for ev, aids in roster_c.items():
                found_relay = False
                for r in challenger_data.get('relays', []):
                    if r['event'] == ev and set(aids) == set(r['member_ids']):
                        opp_marks_for_d[ev].append((parse_mark(r['mark']), 'CHALLENGER'))
                        found_relay = True
                        break
                if not found_relay:
                    for aid in aids:
                        ath = next((a for a in challenger_data['athletes'] if a['athlete_id'] == aid), None)
                        if ath and ev in ath['best_marks']:
                            opp_marks_for_d[ev].append((parse_mark(ath['best_marks'][ev]), 'CHALLENGER'))
                        
            coeffs_d, r_coeffs_d = calculate_net_value_matrix(
                defender_data, opp_marks_for_d, self.rules.scoring_table, self.events
            )
            new_roster_d = solve_optimal_roster(
                defender_data, self.events, coeffs_d, r_coeffs_d, self.rules
            )
            d_changed = (new_roster_d != roster_d)
            roster_d = new_roster_d
            
            if not c_changed and not d_changed:
                break
                
        self.current_rosters[challenger_name] = roster_c
        self.current_rosters[defender_name] = roster_d

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
