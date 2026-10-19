import json, sys, os, shutil, glob, collections
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO); os.chdir(REPO)
from backend import scraper_v2 as sv
from backend.event_canon import canonical_event
R = sys.argv[1]
changed = json.load(open(f'{R}/changed2.json'))

def kept(path, season):
    if not os.path.exists(path):
        return collections.Counter()
    d = json.load(open(path)); evs = d.get('events', []) if isinstance(d, dict) else d
    c = collections.Counter()
    for e in evs:
        if isinstance(e, dict):
            g = e.get('gender') or 'Boys'
            ce = canonical_event(e.get('event', ''), {'Women': 'Girls', 'Men': 'Boys'}.get(g, g), season=season)
            if ce:
                c[ce] += len(e.get('results') or [])
    return c

direct, special = [], []
for c in changed:
    rel = c['rel']; st = f'backend/data/parsed_results/{rel}'
    (direct if os.path.exists(st) and open(f'{R}/before/{rel}').read() == open(st).read() else special).append(rel)
for rel in direct:
    shutil.copyfile(f'{R}/after3/{rel}', f'backend/data/parsed_results/{rel}')
print(len(direct), 'written directly')
# the rest: parse each source to its real output name, compare with the stored parse
os.makedirs(f'{R}/special', exist_ok=True)
for rel in special:
    y, s, name = rel.split('/'); stem = name[:-5]
    srcs = [f for f in glob.glob(f'backend/data/sub5_archive/{y}/{s}/{glob.escape(stem)}.*')
            if f.lower().endswith(('.htm', '.html', '.pdf'))]
    for src in srcs:
        out_stem = stem if len(srcs) == 1 or src.lower().endswith('.htm') else stem + '_' + src.rsplit('.', 1)[1].lower()
        out = f'backend/data/parsed_results/{y}/{s}/{out_stem}.json'
        tmp = f'{R}/special/{y}_{s}_{out_stem}.json'
        sv._parse_one_file((src, tmp, s))
        a, b = kept(out, s), kept(tmp, s)
        loss = {str(k): (a[k], b.get(k, 0)) for k in a if b.get(k, 0) < a[k]}
        same = os.path.exists(out) and open(out).read() == open(tmp).read()
        verdict = 'same' if same else ('WRITE' if not loss else 'KEEP stored')
        if verdict == 'WRITE':
            shutil.copyfile(tmp, out)
        print(f'  {verdict:11} {y}/{s}/{out_stem}: kept {sum(a.values())} -> {sum(b.values())}', dict(list(loss.items())[:3]))
