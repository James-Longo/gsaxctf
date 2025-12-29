from abc import ABC, abstractmethod
import re

class BaseParser(ABC):
    def __init__(self, scraper=None):
        self.scraper = scraper

    @abstractmethod
    def parse(self, text, meet_url, season_type):
        """
        Parses the text content of a meet result page.
        Returns a list of result dictionaries.
        """
        pass

    def clean_event_name(self, event):
        """
        Cleans up event names by removing suffixes like 'Meet A', 'Division I', etc.
        """
        # Remove "Event X" prefix if it leaked in (though regex usually handles this)
        event = re.sub(r'^Event\s+\d+\s+', '', event, flags=re.IGNORECASE)
        
        # Remove gender if it's duplicated at start (e.g. "Girls Girls 55m")
        # (Parser usually constructs "Gender Event", so this might be redundant but safe)
        
        suffixes = [
            r'\s+Meet\s+[A-Z].*', r'\s+Small\s+School.*', r'\s+Large\s+School.*',
            r'\s+Open\s+Division.*', r'\s+OPEN\s+DIVISION.*', r'\s+Division\s+[1-4].*',
            r'\s+CLASS\s+[A-C].*', r'\s+JR\s+DIV.*', r'\s+INT\s+DIV.*',
            r'\s+SR\s+DIV.*', r'\s+Jr\.\s+Division.*', r'\s+Sr\.\s+Division.*',
            r'\s+Junior\s+Div.*', r'\s+Senior\s+Div.*', r'\s+Team\s+Scores.*',
            r'\s+OPEN\s+DIV.*', r'\s+sionon.*', r'\s+idual.*', r'\s+chool.*',
            r'\s+hool.*', r'\s+-\s*IN$', r'\s+IN$', r'\s+Relay\s+Relay'
        ]
        for s in suffixes:
            event = re.sub(s, '', event, flags=re.IGNORECASE).strip()
        event = re.sub(r'\s+[A-Z]School$', '', event).strip()
        return event

    def get_meet_details(self, text):
        """
        Extracts meet name (header) and date from text.
        """
        # Remove HTML comments
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        header = "Unknown Meet"
        
        # Look for a candidate in the first few lines
        candidate_lines = lines[:10]
        base_header = ""
        specific_detail = ""
        
        for i, l in enumerate(candidate_lines):
            if '<' in l or '>' in l: continue
            if any(x in l.lower() for x in ["license", "contractor", "timing", "hy-tek", "page"]): continue
            
            clean_l = re.sub(r'<[^>]+>', '', l).strip()
            if len(clean_l) <= 3: continue
            
            # Normalize common leagues
            if "PVC-Eastern Maine Indoor Track League" in clean_l:
                clean_l = clean_l.replace("PVC-Eastern Maine Indoor Track League", "EMITL")
            
            # If we don't have a base header yet, pick this one
            if not base_header:
                # Remove date from header if present
                clean_l = re.sub(r'-\s*\d{1,2}/\d{1,2}/\d{2,4}.*', '', clean_l).strip()
                base_header = clean_l
            
            # Look for specific meet identifiers in this or subsequent lines
            # Pattern: "Meet 1A", "Meet 2B", "Meet 3" etc.
            meet_match = re.search(r'(Meet\s+\d+[A-Z]?)', l, re.I)
            if meet_match:
                specific_detail = meet_match.group(1)
                break # We found the specific detail, we're done
        
        if base_header:
            if specific_detail and specific_detail not in base_header:
                header = f"{base_header} {specific_detail}"
            else:
                header = base_header
        
        if '<HTML>' in header:
             print(f"!!! BAD HEADER DETECTED IN get_meet_details: '{header}'")
             
        # Try to find date
        date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', text)
        meet_date = date_match.group(1) if date_match else "Unknown"
        return header, meet_date

    def get_season_year(self, text, meet_url, season_type):
        """
        Determines the season year (e.g. '2026') focusing on current season logic.
        """
        # Search for a date in text: MM/DD/YYYY or MM/DD/YY
        match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', text)
        if match:
            month, day, year = match.groups()
            if len(year) == 2: year = "20" + year
            month = int(month)
            year = int(year)
            
            # 2025-2026 Indoor Season: 
            # Dec 2025 -> 2026 Indoor
            # Jan-Feb 2026 -> 2026 Indoor
            if season_type == "Indoor":
                if month >= 11: # Starting Nov/Dec
                    return str(year + 1)
                return str(year)
            return str(year)

        # Fallback to URL year
        match = re.search(r'20\d{2}', meet_url)
        if match:
            year = int(match.group(0))
            if "indoor" in meet_url.lower() and ("dec" in meet_url.lower() or "nov" in meet_url.lower()):
                 return str(year + 1)
            return str(year)

        return "2026" # Default for current year focus
