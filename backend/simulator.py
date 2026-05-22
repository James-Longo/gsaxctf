import sqlite3
import re
import random
import os
import json
from datetime import datetime

class TrackSimulator:
    def __init__(self, db_path):
        self.db_path = db_path
        self.scoring_rules = [10, 8, 6, 4, 2, 1]
        self.event_limit = 3 # Indoor limit as corrected by user

    def parse_mark(self, mark):
        """Converts any track/field mark into a comparable float score."""
        if not mark or not isinstance(mark, str):
            return -1.0
        
        m = mark.strip()
        # Time (mm:ss.hh or ss.hh)
        if ':' in m or ('.' in m and any(c.isdigit() for c in m)):
            try:
                if ':' in m:
                    parts = m.split(':')
                    minutes = float(parts[0])
                    seconds = float(parts[1])
                    return (minutes * 60) + seconds
                else:
                    return float(m)
            except:
                pass
        
        # Distance (ft-in.hh or ft' in")
        # e.g. 12-06.50 or 44' 2"
        dist_match = re.match(r"(\d+)'?\s*[-]?\s*(\d+(?:\.\d+)?)\"?", m)
        if dist_match:
            try:
                feet = float(dist_match.group(1))
                inches = float(dist_match.group(2))
                return feet * 12 + inches
            except:
                pass
        
        # Fallback for simple numeric (like shot put might just be "44.2")
        try:
            return float(m)
        except:
            return -1.0

    def is_better(self, mark1, mark2, event):
        """Decides if score1 is better than score2 for a given event."""
        s1 = self.parse_mark(mark1)
        s2 = self.parse_mark(mark2)
        
        if s1 < 0: return False
        if s2 < 0: return True
        
        event_low = event.lower()
        # Running events: Lower is better
        is_time = any(x in event_low for x in ['dash', 'run', 'hurdles', 'mile', 'relay', '4x'])
        if is_time:
            return s1 < s2
        # Field events: Higher is better
        return s1 > s2

    def get_pvc_data(self, season, year, gender=None):
        """Fetches all top performances for PVC schools in target season, optionally filtered by gender."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        pvc_teams = [
            "Bangor Christian Schools", "Bucksport High School", "Central High School",
            "Dexter Regional High School", "George Stevens Academy",
            "Mattanawcook Academy", "Orono High School", "Piscataquis Community High School",
            "Penquis Valley High School", "Searsport District High School", "Sumner/Narragaugus"
        ]
        
        placeholders = ','.join(['?'] * len(pvc_teams))
        query = f'''
            SELECT performances.*, athletes.name as athlete_name, athletes.id as athlete_uuid
            FROM performances 
            JOIN athletes ON performances.athlete_id = athletes.id 
            WHERE team IN ({placeholders})
            AND season LIKE ? 
            {f"AND year = '{year}'" if year else ""}
        '''
        params = pvc_teams + [f"%{season}"]
        
        if gender:
            query += f" AND event LIKE '{gender.capitalize()}%'"
        
        rows = cursor.execute(query, params).fetchall()
        conn.close()
        
        # Group by [Athlete/Team, Event] to find best marks
        # { (athlete_uuid, event): best_perf_dict }
        best_perfs = {}
        for row in rows:
            p = dict(row)
            is_relay = 'relay' in p['event'].lower() or '4x' in p['event'].lower()
            key = (p['team'], p['event']) if is_relay else (p['athlete_uuid'], p['event'])
            
            if key not in best_perfs or self.is_better(p['mark'], best_perfs[key]['mark'], p['event']):
                best_perfs[key] = p
                
        return list(best_perfs.values())

    def simulate_meet(self, team_entries):
        """
        Runs a single meet simulation.
        team_entries: { team_name: [list of entries] }
        Returns { team_name: score }
        """
        # Group by event
        event_groups = {}
        for team, entries in team_entries.items():
            for entry in entries:
                ev = entry['event']
                if ev not in event_groups: event_groups[ev] = []
                event_groups[ev].append({**entry, 'source_team': team})
        
        scores = {}
        for ev, entries in event_groups.items():
            # Sort entries
            entries.sort(key=lambda x: self.parse_mark(x['mark']), reverse=not any(t in ev.lower() for t in ['dash', 'run', 'hurdles', 'mile', 'relay', '4x']))
            
            # Apply points
            rank = 1
            for i, e in enumerate(entries[:len(self.scoring_rules)]):
                # Tie logic simplified for first pass
                pts = self.scoring_rules[i]
                team = e['source_team']
                scores[team] = scores.get(team, 0) + pts
                
        return scores

    def get_athlete_pools(self, performances):
        """Groups performances by team and then by athlete."""
        pools = {} # { team: { athlete_id: [perfs] } }
        for p in performances:
            team = p['team']
            if team not in pools: pools[team] = {}
            
            is_relay = 'relay' in p['event'].lower() or '4x' in p['event'].lower()
            if is_relay:
                ath_id = f"relay_{team}_{p['event']}"
            else:
                ath_id = p['athlete_uuid']
                
            if ath_id not in pools[team]: pools[team][ath_id] = []
            pools[team][ath_id].append(p)
        return pools

    def get_greedy_entries(self, athlete_pool):
        """Standard 'Best 3' strategy for a team, handling mixed time/distance events."""
        entries = []
        for ath_id, perfs in athlete_pool.items():
            if not perfs: continue
            
            # To pick the "best" events across mixed types (time vs distance),
            # we need a normalized way to compare them.
            # But the requirement is likely just "standard best 3".
            # Let's just ensure we sort each type correctly and then maybe pick the ones 
            # that score the most points (heuristic).
            
            # For simplicity in 'greedy', let's just ensure we don't use a single is_time flag for the pool.
            # We'll use the 'is_better' logic for rankings.
            
            # Sorting mixed events is hard without points. Let's just pick the ones
            # that are highest in their respective events.
            # Actually, the user's online version uses the optimizer.
            
            # For this simulator's greedy mode, let's just sort by a normalized score if possible,
            # or just be more careful with the sort.
            
            def sort_key(p):
                val = self.parse_mark(p['mark'])
                is_time = any(t in p['event'].lower() for t in ['dash', 'run', 'hurdles', 'mile', 'relay', '4x'])
                # Return a value where HIGHER is always BETTER
                if is_time:
                    return -val if val > 0 else -999999
                return val

            perfs.sort(key=sort_key, reverse=True)
            entries.extend(perfs[:self.event_limit])
        return entries

    def optimize_team(self, target_team, season, year, gender=None, iterations=100, scenarios=10):
        all_perfs = self.get_pvc_data(season, year, gender=gender)
        pools = self.get_athlete_pools(all_perfs)
        
        target_pool = pools.pop(target_team, {})
        opponent_pools = pools
        
        # 1. Generate Opponent Scenarios (Monte Carlo)
        # Each scenario is a fixed set of entries for all other teams
        opponent_scenarios = []
        for _ in range(scenarios):
            scenario_entries = {}
            for team, pool in opponent_pools.items():
                scenario_entries[team] = self.get_greedy_entries(pool)
            opponent_scenarios.append(scenario_entries)
            
        # 2. Genetic Algorithm for Target Team
        # Genome: List of (athlete_id, event_index) pairings
        # But easier: A list of indices into each athlete's available events.
        athletes = list(target_pool.keys())
        # Flatten target_pool for easy access: [(ath_id, perf_dict), ...]
        all_possible_target_entries = []
        for aid in athletes:
            for p in target_pool[aid]:
                all_possible_target_entries.append(p)
                
        def get_members(p):
            name = p.get('athlete_name', '')
            if ',' in name or ' & ' in name or 'Relay' in name:
                # Basic split, could be smarter
                return [m.strip() for m in re.split(r',|&', name) if m.strip() and 'Relay' not in m]
            return [name]

        def evaluate(individual_indices):
            # Enforce 3-event limit
            usage = {}
            selected = []
            for idx in individual_indices:
                p = all_possible_target_entries[idx]
                members = get_members(p)
                
                can_add = True
                for m in members:
                    if usage.get(m, 0) >= self.event_limit:
                        can_add = False
                        break
                
                if can_add:
                    selected.append(p)
                    for m in members:
                        usage[m] = usage.get(m, 0) + 1
            
            total_score = 0
            for scenario in opponent_scenarios:
                full_meet = {**scenario, target_team: selected}
                results = self.simulate_meet(full_meet)
                total_score += results.get(target_team, 0)
            
            return total_score / scenarios # Robust score (average across scenarios)

        # Simple GA implementation
        pop_size = 20
        # Population: list of random entry sets (each a list of indices)
        # Number of entries can vary, but let's say we pick random subset of all possible.
        population = []
        for _ in range(pop_size):
            size = min(len(all_possible_target_entries), len(athletes) * self.event_limit)
            population.append(random.sample(range(len(all_possible_target_entries)), min(size, len(all_possible_target_entries))))

        for _ in range(iterations):
            # Rank
            population.sort(key=evaluate, reverse=True)
            # Breed (Top 5)
            new_pop = population[:5]
            while len(new_pop) < pop_size:
                p1, p2 = random.sample(population[:10], 2)
                # Crossover
                split = random.randint(0, min(len(p1), len(p2)))
                child = list(set(p1[:split] + p2[split:])) # set to avoid duplicate events for SAME athlete (handled in evaluate but better here)
                # Mutation
                if random.random() < 0.2:
                    if random.random() < 0.5 and len(child) > 0:
                        child.pop(random.randint(0, len(child)-1))
                    else:
                        child.append(random.randint(0, len(all_possible_target_entries)-1))
                new_pop.append(list(set(child)))
            population = new_pop
            
        # Best result
        population.sort(key=evaluate, reverse=True)
        best_indices = population[0]
        
        # Resolve to actual entries
        usage = {}
        final_best = []
        for idx in best_indices:
            p = all_possible_target_entries[idx]
            members = get_members(p)
            
            can_add = True
            for m in members:
                if usage.get(m, 0) >= self.event_limit:
                    can_add = False
                    break
            
            if can_add:
                final_best.append(p)
                for m in members:
                    usage[m] = usage.get(m, 0) + 1
                
        return {
            "entries": final_best,
            "avg_score": evaluate(best_indices),
            "opponent_count": len(opponent_pools)
        }
