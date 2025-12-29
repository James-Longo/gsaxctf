import requests
from bs4 import BeautifulSoup
import re
import os

def extract_links_with_dates(url):
    print(f"Fetching {url}...")
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(r.text, 'html.parser')
    
    mapping = {}
    
    # Tables on sub5 often look like:
    # <tr>
    #   <td>Date</td>
    #   <td><a href="results.htm">Meet Name</a></td>
    # </tr>
    
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        current_date = None
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if not cells: continue
            
            # Try to find a date in any cell
            row_text = row.get_text()
            # Month DD, YYYY or Month DD-DD, YYYY
            date_match = re.search(r'([A-Z][a-z]+ \d{1,2}(?:-\d{1,2})?, \d{4})', row_text)
            if date_match:
                current_date = date_match.group(1)
            
            # Find links in this row
            links = row.find_all('a', href=True)
            for a in links:
                href = a['href']
                filename = os.path.basename(href)
                if filename.endswith(('.htm', '.html')):
                    if current_date:
                        mapping[filename] = current_date

    return mapping

if __name__ == "__main__":
    urls = [
        "https://sub5.com/youth-pages/indoor-track/2026-indoor-results/",
        "https://sub5.com/youth-pages/indoor-track/2025-indoor-results/",
        "https://sub5.com/youth-pages/indoor-track/2024-indoor-results/",
        "https://sub5.com/youth-pages/indoor-track/2023-indoor-results/"
    ]
    
    all_mappings = {}
    for url in urls:
        all_mappings.update(extract_links_with_dates(url))
    
    import json
    with open('backend/web_date_mapping.json', 'w') as f:
        json.dump(all_mappings, f, indent=4)
    print(f"Saved {len(all_mappings)} mappings to backend/web_date_mapping.json")
