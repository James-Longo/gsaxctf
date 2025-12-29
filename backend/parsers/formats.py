from enum import Enum, auto
import re

class FormatType(Enum):
    STANDARD = auto()  # Rank Name Grade School Mark
    SMAA = auto()      # Rank Name School Mark [Heat]
    UNKNOWN = auto()

class FormatDetector:
    def detect(self, text):
        """
        Scans the first chunk of text to determine the Hy-Tek column format.
        """
        lines = text.split('\n')
        # Check first 50 lines for a data row
        for line in lines[:50]:
            line = line.strip()
            # Look for a line starting with a Rank number, followed by text
            # e.g., "1  Jones, Bob  12  School  10.00"
            if not line: continue
            
            # Simple heuristic: Split by large whitespace
            parts = [p.strip() for p in re.split(r'\s{2,}', line) if p.strip()]
            
            if len(parts) >= 4 and parts[0].isdigit():
                # We have a candidate row: Rank, Col2, Col3, Col4, ...
                
                # Check 3rd column (Index 2)
                col3 = parts[2]
                
                # If Col3 looks like a grade (number 7-12, or '--'), it's STANDARD
                if col3 == '--' or (col3.isdigit() and 7 <= int(col3) <= 12):
                    return FormatType.STANDARD
                
                # If Col3 looks like a School (contains 'School', 'Academy', known acronyms, or is alphabetic text)
                # AND it doesn't look like a grade, it's likely SMAA format where Grade is missing
                # SMAA: Rank(0), Name(1), School(2), Mark(3)
                if not col3.isdigit():
                    # It's likely a school name.
                    return FormatType.SMAA
                    
        return FormatType.UNKNOWN
