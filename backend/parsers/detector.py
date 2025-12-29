from bs4 import BeautifulSoup
import re
from .hytek import HyTekStandardParser, HyTekSMAAParser
from .formats import FormatDetector as ContentFormatDetector, FormatType

class FormatDetector:
    def __init__(self, scraper=None):
        self.scraper = scraper
        self.detector = ContentFormatDetector()

    def get_parser(self, text, url):
        """
        Analyzes content and returns format-specific parser instance.
        """
        if not text:
             return HyTekStandardParser(self.scraper)
        
        # Detect format based on content analysis
        fmt = self.detector.detect(text)
        
        if fmt == FormatType.SMAA:
            print(f"  Detected Format: SMAA (No Grade Column)")
            return HyTekSMAAParser(self.scraper)
        elif fmt == FormatType.STANDARD:
            print(f"  Detected Format: Standard Hy-Tek")
            return HyTekStandardParser(self.scraper)
        else:
            # Fallback to Standard but log warning
            print(f"  Detected Format: UNKNOWN (Defaulting to Standard)")
            return HyTekStandardParser(self.scraper)
