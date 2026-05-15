from backend.scraper_v2 import Sub5ScraperV2
from backend.json_store import load_athletes, load_scrape_state

scraper = Sub5ScraperV2()
athletes = load_athletes()
scrape_state = load_scrape_state()

scrape_state['synced_meets'] = {} # force re-sync
count = scraper.sync_json_to_store(
    'backend/data/parsed_results/2023/Outdoor', 
    season='Outdoor', 
    year='2023', 
    athletes=athletes, 
    scrape_state=scrape_state
)
print("Count:", count)
