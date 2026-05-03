import sys
import os

# Add the parent directory to sys.path so we can import from backend
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.scraper_v2 import Sub5ScraperV2

if __name__ == "__main__":
    print("Starting Incremental Update via GitHub Actions (JSON-only)...")
    try:
        scraper = Sub5ScraperV2()
        count = scraper.run_full_scrape()
        print(f"Incremental Update Successful! {count} new performances added.")
    except Exception as e:
        print(f"ERROR: Scraper failed with: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
