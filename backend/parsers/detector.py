from bs4 import BeautifulSoup
import re
from .hytek import HyTekStandardParser, HyTekSMAAParser
from .column import ColumnStrategyParser
from .formats import FormatDetector as ContentFormatDetector, FormatType

class FormatDetector:
    def __init__(self, scraper=None, verbose=False):
        self.scraper = scraper
        self.verbose = verbose
        self.detector = ContentFormatDetector()

    def get_parser(self, text, url):
        """
        Analyzes content and returns format-specific parser instance.
        """
        if not text:
             return HyTekStandardParser(self.scraper)

        # Detect format based on content analysis
        fmt = self.detector.detect(text)

        # Check for MS keywords to force ColumnStrategy (which has better MS support)
        ms_keywords = ["ms ", "-ms-", "middle school", "junior high", " jh ", "elementary"]
        if any(x in url.lower() for x in ms_keywords) or any(x in text[:1000].lower() for x in ms_keywords):
            if self.verbose: print("  Detected Format: Middle School / Junior High (Forcing ColumnStrategy)")
            return ColumnStrategyParser(self.scraper)

        if fmt == FormatType.SMAA:
            if self.verbose: print("  Detected Format: SMAA (No Grade Column)")
            return HyTekSMAAParser(self.scraper)
        elif fmt == FormatType.STANDARD:
            if self.verbose: print("  Detected Format: Standard Hy-Tek")
            return HyTekStandardParser(self.scraper)
        else:
            # Fallback to the robust ColumnStrategyParser (Sub5ColumnParser)
            if self.verbose: print("  Detected Format: UNKNOWN (Attempting ColumnStrategy fallback)")
            return ColumnStrategyParser(self.scraper)
