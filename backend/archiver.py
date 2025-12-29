import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import time
import re

class Sub5Archiver:
    def __init__(self, base_dir="backend/data/sub5_archive"):
        self.base_dir = base_dir
        self.headers = {'User-Agent': 'Mozilla/5.0'}
        self.scraped_urls = set()
        self.manifest_path = os.path.join(self.base_dir, "manifest.json")
        self.manifest = self.load_manifest()
        
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)

    def load_manifest(self):
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_manifest(self):
        with open(self.manifest_path, 'w') as f:
            json.dump(self.manifest, f, indent=4)

    def get_year_from_url(self, url, text=""):
        # This is now only used for the start URLs or explicit year links
        match = re.search(r'/(20\d{2})', url)
        if match:
            return match.group(1)
        match = re.search(r'(20\d{2})', text)
        if match:
            return match.group(1)
        return "unknown"

    def download_file(self, url, year_dir):
        # We allow re-downloading/moving if we now have a better year_dir
        # But for now, let's just use the strict year_dir provided by the parent page
        
        filename = os.path.basename(urlparse(url).path)
        if not filename:
            filename = "index.html"
        
        year_path = os.path.join(self.base_dir, year_dir)
        if not os.path.exists(year_path):
            os.makedirs(year_path)
            
        local_path = os.path.join(year_path, filename)
        
        # If already exists in manifest, check if it's in the same year
        if url in self.manifest:
            old_year = self.manifest[url].get('year')
            if old_year == year_dir:
                return False
            # If it's different, we might want to move it, but let's just download to new location if it doesn't exist
            if os.path.exists(local_path):
                # Update manifest and return
                self.manifest[url]['year'] = year_dir
                self.manifest[url]['local_path'] = os.path.relpath(local_path, self.base_dir)
                return False

        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            self.manifest[url] = {
                "local_path": os.path.relpath(local_path, self.base_dir),
                "timestamp": time.time(),
                "year": year_dir
            }
            return True
        except Exception as e:
            print(f"Error downloading {url}: {e}")
            return False

    def crawl_year_results(self, url, current_year, depth=0, max_depth=2):
        if url in self.scraped_urls:
            return
        
        self.scraped_urls.add(url)
        print(f"Processing Year {current_year}: {url} (Depth: {depth})")
        
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. Look for result files
            for a in soup.find_all('a', href=True):
                href = urljoin(url, a['href'])
                url_lower = href.lower()
                
                if any(url_lower.endswith(ext) for ext in ['.htm', '.html', '.pdf', '.txt', '.csv']):
                    # Result detection
                    if 'wp-content' in href or 'results' in url_lower or 'scores' in url_lower or depth > 0:
                        if self.download_file(href, current_year):
                            print(f"  Saved to {current_year}: {href}")

            # 2. Look for frames (staying in the same year)
            for frame in soup.find_all(['frame', 'iframe'], src=True):
                frame_url = urljoin(url, frame['src'])
                self.crawl_year_results(frame_url, current_year, depth + 1, max_depth)

            # 3. If depth is 0, find links to other years
            if depth == 0:
                for a in soup.find_all('a', href=True):
                    href = urljoin(url, a['href'])
                    text = a.text.strip()
                    
                    # Look for "20XX" in text or link specifically in the "Results Archive" section
                    # Sub5 has a specific list like "2025 - 2024 - 2023..."
                    if re.match(r'^20\d{2}$', text) or (current_year == "2026" and "indoor-results" in href.lower() and "20" in text):
                        year_match = re.search(r'20\d{2}', text)
                        if year_match:
                            next_year = year_match.group(0)
                            if next_year != current_year:
                                self.crawl_year_results(href, next_year, 0, max_depth)

        except Exception as e:
            print(f"Error crawling {url}: {e}")

    def run(self, start_url):
        print(f"Starting archival mission from: {start_url}")
        # Determine initial year
        start_year = self.get_year_from_url(start_url)
        self.crawl_year_results(start_url, start_year)
        self.save_manifest()
        print("Archival mission complete.")

if __name__ == "__main__":
    archiver = Sub5Archiver()
    # Start with the 2026 indoor results
    archiver.run("https://sub5.com/youth-pages/indoor-track/2026-indoor-results/")
