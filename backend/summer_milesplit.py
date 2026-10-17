"""MileSplit side of summer track: fetch the Youth Summer Series meets' raw result text.

The meets come from backend/data/summer/milesplit_series.json (MileSplit's youth-level
outdoor list, filtered to the series: Group A-D meets, qualifiers, the 14 & under
state meet). Each meet's raw result files go through milesplit.get (cached, one
request every 3 s, no paywalled files) into backend/data/summer/raw/ms-<meet id>.txt,
headed by a '#meet' line like the athletic.net captures; summer_track.parse reads both.

usage: python3 -m backend.summer_milesplit fetch [--years 2024 2025]
"""
import argparse
import html
import json
import os
import re

from backend import milesplit as ms

BASE = os.path.dirname(os.path.abspath(__file__))
LIST = os.path.join(BASE, 'data', 'summer', 'milesplit_series.json')
RAW = os.path.join(BASE, 'data', 'summer', 'raw')


def fetch(years=None):
    os.makedirs(RAW, exist_ok=True)
    meets = json.load(open(LIST))
    for m in meets:
        if years and m['year'] not in years:
            continue
        dest = os.path.join(RAW, f"ms-{m['id']}.txt")
        if os.path.exists(dest):
            continue
        slug = re.search(r'/meets/([^/?#]+)', m['url']).group(1)
        try:
            date, files, title, page = ms.meetinfo(slug)
        except SystemExit as e:
            print('  ERR', m['name'], e, flush=True)
            continue
        venue = re.search(r'<span class="meet-venue">\s*([^<]+)', page) or re.search(r'"location":\s*\{[^}]*"name":\s*"([^"]+)"', page)
        texts, skipped = [], []
        for f in files:
            if f.get('isMeetPro'):
                skipped.append(f['name'])
                continue
            raw = ms.get(f'https://{ms.HOST}/meets/{slug}/results/{f["id"]}/raw', f'{slug}-{f["id"]}.html')
            pre = re.findall(r'<pre[^>]*>(.*?)</pre>', raw, re.S)
            if pre:
                texts.append(f'#file\t{f["name"]}\t{f["id"]}\n' + html.unescape(re.sub(r'<[^>]+>', '', pre[0])))
            else:
                skipped.append(f['name'] + ' (no text)')
        head = '\t'.join(['#meet', m['name'], date or '', html.unescape(venue.group(1)).strip() if venue else '',
                          f'https://{ms.HOST}/meets/{slug}/results'])
        open(dest, 'w', encoding='utf-8').write(head + '\n' + '\n'.join(texts))
        print(f"  {m['year']} {m['name'][:50]}: {len(texts)} files" + (f', skipped {skipped}' if skipped else ''), flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['fetch'])
    ap.add_argument('--years', nargs='*', type=int)
    a = ap.parse_args()
    fetch(a.years)
