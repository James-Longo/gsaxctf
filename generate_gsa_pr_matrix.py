import sqlite3
import re
import csv
from collections import defaultdict

# ---------------------------------------------------------------------------
# Shared mark parsing utilities
# ---------------------------------------------------------------------------

def parse_mark(mark):
    """Convert a raw mark string to a float for comparison. Returns None if invalid."""
    if not mark or not isinstance(mark, str):
        return None
    m = mark.strip().upper()
    if any(b in m for b in ['DNF', 'DQ', 'NH', 'ND', 'SCR', 'FOUL', 'NM']):
        return None

    if any(c in m for c in ["'", '"', "-"]):
        dist_match = re.search(r"(\d+)'?\s*[-]?\s*(\d+(?:\.\d+)?)\)?\"?", m)
        if dist_match:
            return float(dist_match.group(1)) * 12 + float(dist_match.group(2))

    if ':' in m:
        parts = m.split(':')
        if len(parts) == 2:
            try:
                return float(parts[0]) * 60 + float(parts[1])
            except ValueError:
                return None

    try:
        m_clean = "".join(c for c in m if c.isdigit() or c == '.')
        if m_clean:
            return float(m_clean)
    except ValueError:
        return None

    return None


def is_better(val1, val2, event):
    """Return True if val1 is a better performance than val2 for the given event."""
    if val1 is None:
        return False
    if val2 is None:
        return True
    event_low = event.lower()
    is_time = any(x in event_low for x in [
        'dash', 'run', 'hurdles', 'mile', 'relay', '4x',
        '800', '1600', '3200', '55m', '200m', '400m', '1500'
    ])
    if any(x in event_low for x in ['jump', 'put', 'throw', 'vault']):
        is_time = False
    return val1 < val2 if is_time else val1 > val2


def beautify_meet_name(m):
    """Convert a raw meet filename slug into a human-readable column header."""
    if 'emitl' in m:
        match = re.search(r'emitl(\d+[ab]?)', m)
        if match:
            return f"EMITL {match.group(1).upper()}"
        if 'champs' in m:
            return "EMITL Championships"
    if m == 'B-Boys':
        return "Class B States (Boys)"
    if m in ('Class-B-girls-results', 'Class-B-Girls-results'):
        return "Class B States (Girls)"
    if 'classagirlsindor' in m:
        return "Class A States (Girls)"
    if 'classaboysindor' in m:
        return "Class A States (Boys)"
    return m.replace('-', ' ').replace('_', ' ').title()


# ---------------------------------------------------------------------------
# Core PR Pop logic (mirrors PRPopCalculator.jsx)
# ---------------------------------------------------------------------------

def calculate_pr_pops_for_meet(athlete_id, meet_year, meet_name, meet_date_prefix, cursor):
    """
    Return the number of PR Pops an athlete achieved at a specific meet.

    A PR Pop is a mark that strictly improves upon the athlete's career best in
    that event PRIOR to the day of the meet.  First-time marks do not count.
    This mirrors the logic in ui/src/PRPopCalculator.jsx exactly.
    """
    cursor.execute("""
        SELECT event, mark
        FROM performances
        WHERE athlete_id = ? AND year = ? AND meet_name = ?
    """, (athlete_id, meet_year, meet_name))

    meet_perfs = cursor.fetchall()
    if not meet_perfs:
        return 0

    # Best mark per event at this meet
    best_at_meet = {}
    for perf in meet_perfs:
        val = parse_mark(perf['mark'])
        if val is None:
            continue
        ev = perf['event']
        if ev not in best_at_meet or is_better(val, best_at_meet[ev], ev):
            best_at_meet[ev] = val

    pr_count = 0
    for event, meet_best in best_at_meet.items():
        cursor.execute("""
            SELECT mark
            FROM performances
            WHERE athlete_id = ? AND event = ? AND date < ?
        """, (athlete_id, event, f"{meet_date_prefix}T00:00:00"))

        prior_perfs = cursor.fetchall()
        if not prior_perfs:
            continue  # First time in event — not a pop

        prior_best = None
        for p in prior_perfs:
            pv = parse_mark(p['mark'])
            if pv is None:
                continue
            if prior_best is None or is_better(pv, prior_best, event):
                prior_best = pv

        if prior_best is not None and is_better(meet_best, prior_best, event):
            pr_count += 1

    return pr_count


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_team_season_prs(team_pattern, year, season, cursor):
    """
    Calculate total PR Pops per athlete for every meet in a given team/season.

    Returns a dict: { athlete_name: { meet_name: pop_count, ... }, ... }
    and the ordered list of meet names (column order).

    Uses the same PR Pop definition as calculate_pr_pops_for_meet — i.e. the
    PR Pop Calculator logic from the UI.

    Parameters
    ----------
    team_pattern : str   SQL LIKE pattern, e.g. 'George Stevens%'
    year         : str   e.g. '2026'
    season       : str   e.g. 'Indoor'
    cursor       : sqlite3 cursor (row_factory = sqlite3.Row expected)
    """
    # Ordered list of ALL meet instances (globally) so prior-best lookups are correct
    cursor.execute("""
        SELECT DISTINCT year, meet_name, MIN(date) AS date, season
        FROM performances
        GROUP BY year, meet_name
        ORDER BY MIN(date) ASC
    """)
    all_meets_rows = cursor.fetchall()

    # Target meets: where the team competed in this year/season
    cursor.execute("""
        SELECT DISTINCT year, meet_name, MIN(date) AS date
        FROM performances
        WHERE team LIKE ? AND year = ? AND season = ?
        GROUP BY year, meet_name
        ORDER BY MIN(date) ASC
    """, (team_pattern, year, season))
    target_set = {(row['year'], row['meet_name']): row['date'] for row in cursor.fetchall()}

    # Ordered unique instances
    seen = set()
    ordered_instances = []
    for row in all_meets_rows:
        key = (row['year'], row['meet_name'])
        if key in seen:
            continue
        seen.add(key)
        date_prefix = row['date'].split('T')[0] if row['date'] else '9999-12-31'
        ordered_instances.append({
            'year': row['year'],
            'name': row['meet_name'],
            'date_prefix': date_prefix,
            'is_target': key in target_set,
        })

    ordered_column_meets = [m['name'] for m in ordered_instances if m['is_target']]

    # Athletes on this team this season (exclude relay entries)
    cursor.execute("""
        SELECT DISTINCT a.id, a.name
        FROM athletes a
        JOIN performances p ON a.id = p.athlete_id
        WHERE p.team LIKE ? AND p.year = ? AND p.season = ?
          AND a.name NOT LIKE '%,%'
    """, (team_pattern, year, season))
    athletes = {row['id']: row['name'] for row in cursor.fetchall()}

    matrix = defaultdict(lambda: defaultdict(int))
    for aid, name in athletes.items():
        for meet in ordered_instances:
            if not meet['is_target']:
                continue
            pops = calculate_pr_pops_for_meet(aid, meet['year'], meet['name'], meet['date_prefix'], cursor)
            matrix[name][meet['name']] = pops

    return matrix, ordered_column_meets, athletes


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def write_pr_matrix_csv(matrix, ordered_column_meets, athletes, output_file):
    """Write the per-meet PR Pop matrix to a CSV file."""
    beautified = [beautify_meet_name(m) for m in ordered_column_meets]
    col_map = dict(zip(ordered_column_meets, beautified))

    active = [
        n for n in athletes.values()
        if any(matrix[n][m] > 0 for m in ordered_column_meets)
    ]
    active.sort(key=lambda n: sum(matrix[n][m] for m in ordered_column_meets), reverse=True)

    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Athlete'] + beautified + ['Total PRs'])
        writer.writeheader()
        for name in active:
            row = {'Athlete': name}
            total = 0
            for meet in ordered_column_meets:
                count = matrix[name].get(meet, 0)
                row[col_map[meet]] = count
                total += count
            row['Total PRs'] = total
            writer.writerow(row)

    return active


def write_pr_totals_csv(matrix, ordered_column_meets, athletes, output_file):
    """Write a simple athlete -> total PR Pops summary CSV."""
    totals = [
        {'Athlete': n, 'PRs This Season': sum(matrix[n][m] for m in ordered_column_meets)}
        for n in athletes.values()
        if sum(matrix[n][m] for m in ordered_column_meets) > 0
    ]
    totals.sort(key=lambda x: x['PRs This Season'], reverse=True)

    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Athlete', 'PRs This Season'])
        writer.writeheader()
        writer.writerows(totals)

    return totals


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    db_path = 'track_app.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    TEAM = 'George Stevens%'
    YEAR = '2026'
    SEASON = 'Indoor'

    matrix, ordered_column_meets, athletes = calculate_team_season_prs(TEAM, YEAR, SEASON, cursor)

    active = write_pr_matrix_csv(matrix, ordered_column_meets, athletes, 'gsa_pr_matrix_2026.csv')
    print(f"Generated gsa_pr_matrix_2026.csv — {len(active)} athletes, {len(ordered_column_meets)} meets.")

    totals = write_pr_totals_csv(matrix, ordered_column_meets, athletes, 'gsa_prs_2026.csv')
    print(f"Generated gsa_prs_2026.csv — {len(totals)} athletes.")

    conn.close()
