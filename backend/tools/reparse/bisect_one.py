import sys, os, json, collections
root, src, out = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, root); sys.path.insert(0, os.path.join(root, 'backend'))
os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))       # archive paths and data files
from backend import scraper_v2 as sv
assert sv.__file__.startswith(root), sv.__file__
sv._parse_one_file((src, out, src.split('/')[-2]))
d = json.load(open(out))
print([e['event'] for e in d['events'] if e.get('is_relay')][:4])
