import sys
import os

# Add the parent directory to sys.path so we can import from backend
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.scraper import Sub5Scraper
from backend.generate_db_stats import generate_stats

if __name__ == "__main__":
    print("Starting Incremental Update via GitHub Actions...")
    try:
        scraper = Sub5Scraper()
        scraper.run_full_scrape(wipe=False)
        print("Incremental Update Successful!")
    except Exception as e:
        print(f"ERROR: Scraper failed with: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Always regenerate db_stats.json after a successful sync so git diff
    # gives a readable summary of what changed in the database.
    print("Generating db_stats.json...")
    generate_stats()
