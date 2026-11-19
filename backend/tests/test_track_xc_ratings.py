"""XC ratings in the track store: course-table names joined to observations (no store).

Run:  python3 backend/tests/test_track_xc_ratings.py      (or pytest, if installed)
"""
import gzip
import json
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend import track_postseason as tp  # noqa: E402
from backend import xc_course_model as cm  # noqa: E402


def _ratings(courses, obs):
    old_dir, old_clean = tp.js.DATA_DIR, cm.clean_observations
    with tempfile.TemporaryDirectory() as d:
        with gzip.open(os.path.join(d, 'xc_courses.json.gz'), 'wt') as f:
            json.dump({'courses': courses}, f)
        tp.js.DATA_DIR, cm.clean_observations = d, lambda team_filter=True: obs
        try:
            return tp._xc_ratings()
        finally:
            tp.js.DATA_DIR, cm.clean_observations = old_dir, old_clean


def test_observations_join_the_course_table_by_label_and_era():
    courses = [
        {'course': 'Belfast (5K)', 'venue': 'Belfast', 'distance': '5K', 'factor': 1.0, 'years': ['2026']},
        {'course': 'Orono High School (4K)', 'venue': 'Orono High School', 'distance': '4K',
         'factor': 0.81, 'years': ['2018', '2026']},
        {'course': 'Orono High School (4K, 2013-2016)', 'venue': 'Orono High School', 'distance': '4K',
         'factor': 0.80, 'years': ['2013', '2014', '2016']},
    ]
    t = math.log(1200)
    obs = [('a', '2026', ('Belfast', 5000), t, 'm', '2026-10-03'),
           ('b', '2026', ('Orono High School', 4000), t, 'm', '2026-10-10'),
           ('c', '2014', ('Orono High School~2013-2016', 4000), t, 'm', '2014-10-10'),
           # an era span the table drew differently: matched by year
           ('d', '2016', ('Orono High School~2014-2016', 4000), t, 'm', '2016-10-10'),
           ('e', '2026', ('Nowhere', 5000), t, 'm', '2026-10-10')]
    got = {a: (ay, d, round(math.exp(x))) for a, ay, d, x in _ratings(courses, obs)}
    assert got['a'] == (2027, '2026-10-03', 1200)
    assert got['b'][2] == round(1200 / 0.81)
    assert got['c'][2] == got['d'][2] == round(1200 / 0.80)
    assert 'e' not in got


if __name__ == '__main__':
    test_observations_join_the_course_table_by_label_and_era()
    print('ok')
