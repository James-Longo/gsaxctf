from bs4 import BeautifulSoup
import re
from .base import BaseParser

class ParagraphTextParser(BaseParser):
    def parse(self, text, meet_url, season_type):
        """
        Parses results formatted as HTML paragraphs with &nbsp; spacing.
        Common in newer results (e.g. 2025).
        """
        soup = BeautifulSoup(text, 'html.parser')
        
        # Extract text preserving layout (roughly)
        # If we use get_text(), spacing might be lost or collapsed.
        # But we need to handle non-breaking spaces.
        
        # Strategy: Iterate paragraphs/pre/divs
        # Build a list of text lines, replacing &nbsp; with spaces
        lines = []
        for elem in soup.find_all(['p', 'pre', 'div']):
            # get_text with separator might be messy if internal tags exist
            # Prefer converting unicode space to space
            line = elem.get_text().replace('\xa0', ' ').replace('\u00a0', ' ')
            lines.extend(line.split('\n'))

        # Use HyTek logic on the extracted lines?
        # Usually looking for "Event X" lines still works.
        # The structure is effectively the same as HyTek text report, just wrapped in P tags.
        
        # Reuse HyTek parser logic on the plain text
        from .hytek import LegacyHyTekParser
        hytek_parser = LegacyHyTekParser(self.scraper)
        
        full_text = '\n'.join(lines)
        return hytek_parser.parse(full_text, meet_url, season_type)
