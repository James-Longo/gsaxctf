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
        Wraps Sub5ColumnParser but works on text by writing to a temporary file 
        (since Sub5ColumnParser expects a file path).
        """
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.htm', delete=False, encoding='utf-8') as tf:
            tf.write(text)
            temp_path = tf.name
            
        try:
            parser = Sub5ColumnParser(temp_path)
            raw_result = parser.parse()
            
            # Sub5ColumnParser returns: { meet_name, date, events: [ { event, gender, results: [...] } ] }
            # We need to flatten this to match the BaseParser.parse expectations: 
            # List of: { athlete_name, grade, school, event, mark, rank, points, gender, season, date, meet_name, meet_url }
            
            flat_events = []
            meet_name = raw_result.get("meet_name") or "Unknown Meet"
            meet_date = raw_result.get("date") or "Unknown Date"
            
            for ev in raw_result.get("events", []):
                # Keep the nested structure: events -> results
                flat_events.append({
                    "event": ev['event'],
                    "gender": ev['gender'],
                    "is_relay": ev.get('is_relay', False),
                    "results": ev.get('results', []),
                    "date": meet_date,
                    "meet_name": meet_name
                })
            
            # Return a dict with a "date" key at top level to help the sync logic
            return {"events": flat_events, "date": meet_date}
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
