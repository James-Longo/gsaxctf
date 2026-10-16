"""
school_consistency.py - are a meet's runners filed under the school they
run for the rest of the season?

For every (meet, team folder) group, the same runners' other results in the
same academic year are looked up by printed name (and gender). A group whose
runners are filed under one other team everywhere else is probably filed
under the wrong school: a code read as another school ("WIND" -> Windsor), a
mascot shared by two schools ("Hawks"), a middle school read as the high
school. Middle school and high school of one town, and a school and its
co-op, count as agreeing (runners move between them across seasons).

    python3 -m backend.school_consistency                  # working-tree store
    python3 -m backend.school_consistency --git HEAD       # committed store
    python3 -m backend.school_consistency --seasons Indoor,Outdoor --json out.json
"""

import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.store_diff import TEAMS, _rows_from_dir, _rows_from_git  # noqa: E402

MIN_RUNNERS = 4      # a group needs this many runners seen elsewhere
SHARE_ELSEWHERE = 0.7


def _ay(key):
    y, s = key.split('_', 1)
    return int(y) + 1 if s == 'XC' else int(y)


def _town(folder):
    """A loose school-family key: 'Orono_Middle_School' and 'Orono_High_School'
    are one town."""
    w = [t for t in re.split(r'[_\W]+', folder.lower()) if t]
    return w[0] if w else folder


def check(rows, seasons=None):
    by_runner = collections.defaultdict(collections.Counter)
    groups = collections.defaultdict(set)
    for team, key, r in rows:
        season = key.split('_', 1)[1]
        if seasons and season not in seasons:
            continue
        ev = r.get('event') or ''
        if 'Relay' in ev:
            continue
        name = (r.get('athlete_name') or '').strip().lower()
        if len(name.split()) < 2:
            continue
        g = ev.split(' ', 1)[0]
        who = (name, g, _ay(key))
        meet = (key, r.get('meet_name'))
        by_runner[who][(team, meet)] += 1
        groups[(meet, team)].add(who)
    flags = []
    n_groups = 0
    for (meet, team), who in groups.items():
        elsewhere = collections.Counter()
        seen = 0
        for w in who:
            other = collections.Counter()
            for (t, m), n in by_runner[w].items():
                if m != meet:
                    other[t] += n
            if other:
                seen += 1
                elsewhere[other.most_common(1)[0][0]] += 1
        if seen < MIN_RUNNERS:
            continue
        n_groups += 1
        same = sum(n for t, n in elsewhere.items() if t == team or _town(t) == _town(team))
        top, top_n = elsewhere.most_common(1)[0]
        if same < 0.3 * seen and top_n >= SHARE_ELSEWHERE * seen and top != team:
            flags.append(dict(key=meet[0], meet=meet[1], team=team, runners=len(who),
                              seen=seen, elsewhere=top, elsewhere_share=round(top_n / seen, 2)))
    flags.sort(key=lambda f: -f['runners'])
    return n_groups, flags


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--git', help='check the store committed at this revision')
    ap.add_argument('--dir', default=TEAMS)
    ap.add_argument('--seasons', help='comma-separated, e.g. Indoor,Outdoor')
    ap.add_argument('--json')
    ap.add_argument('--top', type=int, default=30)
    a = ap.parse_args()
    rows = _rows_from_git(a.git) if a.git else _rows_from_dir(a.dir)
    seasons = set(a.seasons.split(',')) if a.seasons else None
    n, flags = check(rows, seasons)
    print(f'{n:,} (meet, team) groups checked; {len(flags)} filed against their runners '
          f'({sum(f["runners"] for f in flags):,} runners)')
    for f in flags[:a.top]:
        print(f"  {f['key']:13s} {f['meet'][:40]:40s} {f['team'][:30]:30s} n={f['runners']:3d} "
              f"-> {f['elsewhere']} ({f['elsewhere_share']:.0%})")
    if a.json:
        with open(a.json, 'w') as fh:
            json.dump(flags, fh, indent=1)


if __name__ == '__main__':
    sys.exit(main())
