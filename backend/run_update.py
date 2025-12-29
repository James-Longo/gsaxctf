import sys
import os

# Add the parent directory to sys.path so we can import from backend
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.scraper import Sub5Scraper

if __name__ == "__main__":
    print("Starting Incremental Update via GitHub Actions...")
    scraper = Sub5Scraper()
    scraper.run_full_scrape(wipe=False)
