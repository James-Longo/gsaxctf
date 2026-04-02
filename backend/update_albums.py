import os
import json
import requests
from bs4 import BeautifulSoup
import sys

ALBUMS_FILE = 'albums.txt'
UI_JSON_PATH = os.path.join('ui', 'public', 'albums.json')

def fetch_album_metadata(url):
    print(f"Fetching metadata for: {url}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url.strip(), headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get Title
        title = "Unknown Album"
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.text.replace(' - Google Photos', '').strip()
        elif soup.find('meta', property='og:title'):
            title = soup.find('meta', property='og:title').get('content', '').replace(' - Google Photos', '').strip()
            
        # Get Image
        image_url = ""
        og_image = soup.find('meta', property='og:image')
        if og_image:
            image_url = og_image.get('content', '')
            
        return {
            "id": url.split('/')[-1] if '/' in url else url,
            "title": title,
            "description": "Shared Google Photos Album. Click to view or upload footage.",
            "url": url.strip(),
            "coverImage": image_url
        }
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return {
            "id": url.split('/')[-1] if '/' in url else url,
            "title": "New Album",
            "description": "Shared Google Photos Album. Click to view or upload footage.",
            "url": url.strip(),
            "coverImage": ""
        }

def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    albums_txt_path = os.path.join(root_dir, ALBUMS_FILE)
    output_json_path = os.path.join(root_dir, UI_JSON_PATH)

    if not os.path.exists(albums_txt_path):
        print(f"Could not find {ALBUMS_FILE}. Creating a template...")
        with open(albums_txt_path, 'w') as f:
            f.write("https://photos.app.goo.gl/sWhLQfB6rP6bGm3b8\n")
            
    with open(albums_txt_path, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]
        
    print(f"Found {len(urls)} URLs. Processing...")
    
    albums_data = []
    for url in urls:
        metadata = fetch_album_metadata(url)
        if metadata:
            albums_data.append(metadata)
            
    # Ensure public dir exists
    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
    
    with open(output_json_path, 'w') as f:
        json.dump(albums_data, f, indent=4)
        
    print(f"\nSuccessfully updated {output_json_path} with {len(albums_data)} albums.")

if __name__ == '__main__':
    main()
