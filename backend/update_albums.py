"""Refresh ui/public/albums.json (the Footage tab) from the album links in albums.txt.

Each album's title and cover come from its shared page (og:title / og:image).
If a page can't be fetched, or has no cover (an empty album), the album keeps
what albums.json already had for it.
"""
import json
import os

import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALBUMS_TXT = os.path.join(ROOT, 'albums.txt')
ALBUMS_JSON = os.path.join(ROOT, 'ui', 'public', 'albums.json')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                         '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'}


def fetch_album(url, old):
    album = {
        'id': url.rstrip('/').split('/')[-1],
        'title': old.get('title', 'New Album'),
        'description': 'Shared Google Photos Album. Click to view or upload footage.',
        'url': url,
        'coverImage': old.get('coverImage', ''),
    }
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f'  fetch failed, keeping previous entry: {e}')
        return album
    soup = BeautifulSoup(response.text, 'html.parser')
    if soup.title and soup.title.text.strip():
        album['title'] = soup.title.text.replace(' - Google Photos', '').strip()
    og_image = soup.find('meta', property='og:image')
    if og_image and og_image.get('content'):
        album['coverImage'] = og_image['content']
    else:
        print('  no cover on the page (album empty?)')
    return album


def main():
    with open(ALBUMS_TXT) as f:
        urls = [line.strip() for line in f if line.strip()]
    old = {}
    if os.path.exists(ALBUMS_JSON):
        with open(ALBUMS_JSON) as f:
            old = {a['url']: a for a in json.load(f)}
    albums = []
    for url in urls:
        print(f'Fetching {url}')
        albums.append(fetch_album(url, old.get(url, {})))
    with open(ALBUMS_JSON, 'w') as f:
        json.dump(albums, f, indent=4)
    missing = [a['title'] for a in albums if not a['coverImage']]
    print(f'Wrote {len(albums)} albums to {ALBUMS_JSON}; without a cover: {missing or "none"}')


if __name__ == '__main__':
    main()
