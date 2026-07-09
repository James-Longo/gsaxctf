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

        # Keep team_rankings so QAQC scoring can verify meets without re-parsing
        return {
            "events": flat_events,
            "date": meet_date,
            "meet_name": meet_name,
            "team_rankings": raw_result.get("team_rankings", []),
        }
