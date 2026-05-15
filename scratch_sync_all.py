import os
import glob
from backend.scraper_v2 import Sub5ScraperV2
from backend.json_store import load_athletes, load_scrape_state, save_athletes, save_scrape_state, rebuild_manifest

def main():
    scraper = Sub5ScraperV2()
    athletes = load_athletes()
    scrape_state = load_scrape_state()

    # We want to re-sync everything, so we'll just force clear synced_meets
    scrape_state['synced_meets'] = {}

    base_dir = os.path.dirname(os.path.abspath(__file__))
    parsed_dir = os.path.join(base_dir, 'backend', 'data', 'parsed_results')
    
    total_count = 0
    # Walk the directory to find years and seasons
    for year in os.listdir(parsed_dir):
        year_path = os.path.join(parsed_dir, year)
        if not os.path.isdir(year_path): continue
        for season in os.listdir(year_path):
            season_path = os.path.join(year_path, season)
            if not os.path.isdir(season_path): continue
            
            print(f"Syncing {year} {season}...")
            count = scraper.sync_json_to_store(
                season_path, 
                season=season, 
                year=year, 
                athletes=athletes, 
                scrape_state=scrape_state
            )
            total_count += count
            print(f"  Inserted {count} performances.")

    save_scrape_state(scrape_state)
    save_athletes(athletes)
    rebuild_manifest()
    print("Done. Total performances inserted:", total_count)

if __name__ == "__main__":
    main()
