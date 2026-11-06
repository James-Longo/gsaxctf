from .base import BaseParser
import sys
import os

# Add parent dir to path to import parser
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from parser import Sub5ColumnParser
except ImportError:
    # Fallback for different execution contexts
    from backend.parser import Sub5ColumnParser

import re


def drop_coed_score_copies(events):
    """EMITL relay meets (2019, 2020) print the coed sprint medley once as 'Mixed ... COED Relay'
    and again as 'Boys ... Coed male' / 'Girls ... COED female' for each gender's team scores:
    the same race, so a gendered coed copy whose teams and marks equal a Mixed event's is dropped."""
    key = lambda e: [(r.get('school'), r.get('result')) for r in e.get('results', [])]
    mixed = [key(e) for e in events if e.get('gender') == 'Mixed']
    return [e for e in events if not (e.get('gender') in ('Boys', 'Girls')
            and re.search(r'\bco-?ed\b', e.get('event') or '', re.I) and key(e) in mixed)]


class ColumnStrategyParser(BaseParser):
    def __init__(self, scraper=None):
        super().__init__(scraper)

    def parse(self, text, meet_url, season_type):
        """
        Wraps Sub5ColumnParser, feeding it the in-memory text directly.
        meet_url doubles as the filename for MS-meet detection.
        """
        parser = Sub5ColumnParser(meet_url, text=text)
        raw_result = parser.parse()
        if not isinstance(raw_result, dict):
            return {"events": [], "date": None, "team_rankings": []}

        meet_name = raw_result.get("meet_name") or "Unknown Meet"
        meet_date = raw_result.get("date") or "Unknown Date"

        flat_events = []
        for ev in raw_result.get("events", []):
            flat_events.append({
                "event": ev['event'],
                "gender": ev['gender'],
                "is_relay": ev.get('is_relay', False),
                "results": ev.get('results', []),
                "date": meet_date,
                "meet_name": meet_name
            })
            if ev.get('section'):
                flat_events[-1]['section'] = ev['section']
            if ev.get('age_group'):
                flat_events[-1]['age_group'] = ev['age_group']

        flat_events = drop_coed_score_copies(flat_events)

        # Keep team_rankings so QAQC scoring can verify meets without re-parsing
        return {
            "events": flat_events,
            "date": meet_date,
            "meet_name": meet_name,
            "venue": raw_result.get("venue"),
            "team_rankings": raw_result.get("team_rankings", []),
        }
