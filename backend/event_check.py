"""Every numbered event header on a season's sub5 sheets vs the events we store: lists events printed but not stored.
    python3 -m backend.event_check Indoor"""
import json,glob,collections,re,sys,subprocess,html as H
sys.path.insert(0,'.')
from backend.event_canon import canonical_event
season=sys.argv[1] if len(sys.argv)>1 else 'Indoor'
def src_text(y,s):
    fs=glob.glob(f'backend/data/sub5_archive/{y}/{season}/{glob.escape(s)}.*')
    if not fs: return None
    p=fs[0]
    if p.lower().endswith('.pdf'):
        return subprocess.run(['pdftotext','-layout',p,'-'],capture_output=True,text=True,timeout=60).stdout
    return H.unescape(re.sub('<[^>]+>','',open(p,errors='replace').read()))
HDR=re.compile(r'^\s*(?:#\s*)?Event\s+\d+\s+(.+?)\s*$')
miss=collections.Counter(); files=collections.defaultdict(list); nfiles=0
for y in range(2003,2027):
  for f in sorted(glob.glob(f'backend/data/parsed_results/{y}/{season}/*.json')):
    s=f.split('/')[-1][:-5]
    if s.startswith('ms-'): continue
    d=json.load(open(f))
    have=set()
    for e in d.get('events',[]):
      if 'results' in e and not e['results']: continue
      if 'results' not in e and not e.get('athlete_name'): continue
      r=canonical_event(e.get('event',''),e.get('gender',''),season=season)
      if r: have.add((r[0],r[1]))
    t=src_text(y,s)
    if not t: continue
    want=set()
    for l in t.splitlines():
      m=HDR.match(l)
      if not m: continue
      ev=re.sub(r'\s*\(.*?\)\s*$','',m.group(1))
      if re.search(r'(?i)team|score',ev): continue
      g=re.match(r'(?i)(boys|girls|men|women|mixed)\b',ev)
      gender={'boys':'Boys','men':'Boys','girls':'Girls','women':'Girls','mixed':'Mixed'}.get(g.group(1).lower()) if g else ''
      r=canonical_event(ev,gender,season=season)
      if r: want.add((r[0],r[1]))
    if not want: continue
    nfiles+=1
    lost=want-have
    # tolerate gender mismatch from unlabeled
    lost={x for x in lost if not any(h[1]==x[1] for h in have if not x[0])}
    for x in lost: miss[x[1]]+=1; files[x[1]].append(f'{y} {s} {x[0]}')
print('files with numbered event headers:',nfiles)
for k,v in miss.most_common(): print(f'{v:4d}  {k}   e.g. {files[k][:3]}')
