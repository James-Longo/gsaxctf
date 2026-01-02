from scraper import Sub5Scraper
import os

if __name__ == "__main__":
    scraper = Sub5Scraper()
    # Wipe and re-sync from existing JSON files
    scraper.initialize_db(wipe=True)
    
    base_dir = os.path.dirname(os.path.dirname(__file__))
    years = ["2023", "2024", "2025", "2026"]
    
    for year in years:
        json_dir = os.path.join(base_dir, f'backend/data/parsed_results/{year}')
        if os.path.exists(json_dir):
            scraper.sync_json_to_db(json_dir, season="Indoor", year=year)
            
    print("Sync complete.")
