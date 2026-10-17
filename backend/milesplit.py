"""MileSplit meet reader for meets missing from sub5 (docs/agents/missing-meets.md).

usage: python3 -m backend.milesplit list <year> <Indoor|Outdoor|XC>
       python3 -m backend.milesplit info <slug>
       python3 -m backend.milesplit write <slug> <year> <Indoor|Outdoor|XC>

<slug> is the meet's MileSplit id-name ("209365-pvc-hampden-..."). One request
at a time with a 3 s pause; pages are cached in backend/data/milesplit_cache.
`write` makes parsed_results/<year>/<season>/ms-<name>.json (parser
milesplit-manual). `list` reads the season's meet list (every page) into
backend/data/meet_listings/milesplit-<year>-<season>.json for the meet
ledger (backend/meet_ledger.py); `kind` is a first guess from the name
(hs, ms, youth, college, open) for the reader to correct.
Env: MS_STAGE=<dir> writes under <dir>/<year>/<season>/ (staging), MSHOST=ny.milesplit.com for meets hosted on another state subdomain, EXCLUDE=<result file ids> skips files (a meet page listing another meet's file), CANON=1 expands school abbreviations/mascots, MASC="Tigers=Biddeford High
School;..." maps a meet's mascots, CLASSFILES=1 tags events by class file.
Cross country (season XC) goes through parse_xc_any: Meet Manager "NAME YR TEAM MARK H#" sheets, Hy-Tek
"Event n" sheets, RaceTab, Run In A Race, tab sheets (Calais, Machias, Mount Abram, ELHS); team scores read with
scorer places, team_place filled from printed points or rebuilt from the scores; ABBR="YARM=Yarmouth High School;..."
maps team abbreviations; truncated school names are completed from the school catalog.
Also read: tab sheets that indent every row or leave empty cells between columns (SMAA Relays, Mt. Blue Relays), Place/Score/Team Name tables without a "Team Scores" title (Run In A Race, no grade column), Pine Tree / Five K Sport "TmPl" sheets with or without a gender column, Hy-Tek team blocks printed under the next header or split across pages. A second meet with the same name gets "-<date>" in its file name.
Reads Hy-Tek fixed-width, tab-delimited, RaceTab and "Last, First" layouts; a
new layout prints NO EVENTS or ROW? on stderr.
"""
import sys, re, json, html, time, subprocess, os
BASE = os.path.dirname(os.path.abspath(__file__))
SP = os.path.join(BASE, 'data', 'milesplit_cache') + '/'
os.makedirs(SP, exist_ok=True)
UA = 'Mozilla/5.0'
HOST = os.environ.get('MSHOST', 'me.milesplit.com')
UNP=[]
def note(tag,ln):
    print(tag,repr(ln),file=sys.stderr)
    if re.match(r'\s*(\d+|--+)[\s\t]',ln): UNP.append(ln.strip())
def get(url, cache):
    p = SP + cache
    if os.path.exists(p): return open(p).read()
    time.sleep(3)
    r = subprocess.run(['curl','-s','-m','40','-A',UA,'-w','\n%{http_code}',url],capture_output=True,text=True)
    body, code = r.stdout.rsplit('\n',1)
    if code != '200': raise SystemExit('HTTP %s for %s' % (code,url))
    open(p,'w').write(body); return body
def meetinfo(slug):
    h = get('https://%s/meets/%s/results' % (HOST, slug), slug+'.html')
    date = re.search(r'"startDate": "([\d-]+)"', h)
    files = re.search(r'meetResultFiles = (\[.*?\]);', h)
    title = re.search(r'<title>(.*?)</title>', h, re.S).group(1).strip()
    if not files:
        ids=sorted(set(re.findall(r'results/(\d+)/raw',h)))
        files=[{'id':int(i),'name':'Results','isMeetPro':0} for i in ids]
    return (date.group(1) if date else None), (json.loads(files.group(1)) if hasattr(files,'group') else files), html.unescape(title), h
MARK = r"[xX]?(?:\d+:)?\d+(?:\.\d+)?[a-zA-Z]?|[xXjJ]?\d+-\d+(?:\.\d+)?[a-zA-Z]?|[xX]?(?:DQ|DNF|DNS|NH|FOUL|FAIL|ND|NT|SCR|DNQ)"
STAT = {'DQ','DNF','NH','FOUL','FAIL','ND','NT','DNQ'}
def clean_mark(m):
    m = re.sub(r'^[xXjJ](?=\d)','',m)
    m = re.sub(r'(?<=\d)[FR]$', '', m)   # meet/facility record flag
    m = re.sub(r'^[xX](?=[A-Z]{2})','',m)
    if m in STAT: return m
    if re.fullmatch(r'.*\d[qQ]', m): m = m[:-1]
    return m
def norm_event(name):
    name = re.sub(r'\s+',' ',name).strip()
    name = re.sub(r'(\d)\s*[mM]\b',r'\1 Meter',name)
    name = re.sub(r'\bMeters\b','Meter',name)
    name = re.sub(r'^(Discus|Javelin)$',r'\1 Throw',name)
    name = re.sub(r'\b(Hurdles) HURDLES$',r'\1',name)
    name = re.sub(r'((?:High|Long|Triple) Jump|Pole Vault|Shot Put|(?:Discus|Javelin) Throw) Relay$',r'\1',name)  # individual marks in a relays carnival
    name = re.sub(r'\s*(Finals?|Prelims?|Final|Timed Finals)$','',name)
    return name
def parse(text):
    lines = text.split('\n')
    events = []; rankings = []
    cur = None; sec = 'Finals'; mode = None; hdr = None; i = 0
    while i < len(lines):
        ln = lines[i]
        m = re.match(r'\s*Event\s+\d+\s+(.*?)\s*$', ln)
        if not m and i+1 < len(lines) and re.match(r'\s*=+\s*$',lines[i+1]) and re.match(r'\s*(Varsity\s+)?(Boys|Girls|Men|Women)\s+\S',ln) and 'Team Rank' not in ln and not re.match(r'\s*JV\s',ln): m = re.match(r'\s*(?:Varsity\s+)?(.*?)\s*$', ln)
        if m:
            nm = m.group(1)
            g = re.match(r'(Boys|Girls|Men|Women)\s+(.*)', nm)
            gender = {'Boys':'Boys','Men':'Boys','Girls':'Girls','Women':'Girls'}[g.group(1)] if g else ''
            ev = g.group(2) if g else nm
            ev = re.sub(r'\bRace Walk\b','Race Walk',ev)
            cur = {'event': (gender+' '+norm_event(ev)).strip(), 'gender': gender,
                   'is_relay': bool(re.search(r'Relay|Medley|Shuttle|Carousel|\dx\d',ev)), 'results': []}
            events.append(cur); sec='Finals'; hdr=None; i+=1; continue
        mts=re.match(r'\s*(Female|Male|Women|Men|Girls|Boys)\s+Team Scores',ln)
        if mts:
            g='Girls' if mts.group(1) in ('Female','Women','Girls') else 'Boys'
            teams=[]; i+=1
            while i<len(lines) and not re.match(r'\s*(Female|Male|Women|Men|Girls|Boys)\s',lines[i]):
                tm=re.match(r'\s*(\d+)\s+(.*?)\s+[A-Z&]{2,5}\s+(\d+(?:\s*\.\s*\d+)?)\s*$',lines[i])
                if tm:
                    sc=float(tm.group(3).replace(' ','')); teams.append({'rank':int(tm.group(1)),'team':tm.group(2).strip(),'score':int(sc) if sc==int(sc) else sc}); i+=1; continue
                tm=re.match(r'\s*(\d+)\s+(.+?)(?:\s{2,}[A-Z&. -]{2,12})?\s{2,}(\d+(?:\.\d+)?)\s*$',lines[i])
                if tm:
                    sc=float(tm.group(3)); teams.append({'rank':int(tm.group(1)),'team':tm.group(2).strip(),'score':int(sc) if sc==int(sc) else sc})
                i+=1
            rankings.append({'gender':g,'teams':teams}); cur=None; continue
        if re.search(r'Team Rankings', ln):
            g = 'Boys' if re.search(r'\bMen\b|Boys',ln) else ('Girls' if re.search(r'Women|Girls',ln) else '')
            teams=[]; i+=1
            while i < len(lines) and (not lines[i].strip() or re.match(r'\s*=+\s*$',lines[i]) or re.search(r'\d+\)',lines[i])):
                for mm in re.finditer(r'(\d+)\)\s+(.*?)\s+(\d+(?:\.\d+)?)(?=\s{2,}\d+\)|\s*$)', lines[i]):
                    sc=float(mm.group(3)); teams.append({'rank':int(mm.group(1)),'team':mm.group(2).strip(),'score':int(sc) if sc==int(sc) else sc})
                i+=1
            rankings.append({'gender':g,'teams':teams}); cur=None; continue
        if re.match(r'\s*Place\s+School\s+Points',ln):
            g=cur['gender'] if cur else ''
            teams=[]; i+=1
            while i<len(lines) and (not lines[i].strip() or re.match(r'\s*=+\s*$',lines[i]) or re.match(r'\s*\d+\s',lines[i])):
                tm=re.match(r'\s*(\d+)\s+(.+?)(?:\s{2,}[A-Za-z&. -]{1,12})?\s{2,}(\d+(?:\.\d+)?)\s*$',lines[i])
                if tm:
                    sc=float(tm.group(3)); teams.append({'rank':int(tm.group(1)),'team':tm.group(2).strip(),'score':int(sc) if sc==int(sc) else sc})
                i+=1
            rankings.append({'gender':g,'teams':teams}); cur=None; continue
        if cur is None: i+=1; continue
        if re.match(r'\s*=+\s*$', ln): i+=1; continue
        s = ln.strip()
        if re.fullmatch(r'(Preliminaries|Prelims?|Finals|Semi-?finals?|Final|Timed Finals.*|Section.*|Flight.*|Heat.*)', s, re.I) and not re.match(r'\s*\d',ln):
            sec = 'Prelims' if re.match(r'Prelim',s,re.I) else ('Finals' if re.match(r'(Final|Timed|Section|Flight|Heat)',s,re.I) else sec); i+=1; continue
        if re.match(r'\s*(Name|School)\s', ln) and re.search(r'Finals|Prelims|Mark|Time|Result|Points',ln):
            hdr = ln; cur['is_relay']=not re.match(r'\s*Name',ln); i+=1
            if 'Prelim' in ln and 'Finals' not in ln: sec='Prelims'
            continue
        rm = re.match(r'\s*(\d+|--)\s+(\S.*)$', ln)
        if rm and re.match(r'\s*\d{4}\s.* - \d+/\d+/\d{4}\s*$', ln): i+=1; continue  # page header "2014 Lewiston KVAC Meet 1 - 4/18/2014"
        if not rm or hdr is None: i+=1; continue
        place = None if rm.group(1)=='--' else int(rm.group(1))
        if cur['is_relay']:
            fe=max(hdr.find('Finals')+6, hdr.find('Prelims')+7, hdr.find('Time')+4)
            ms=[(mt.start(),mt.end(),mt.group(0)) for mt in re.finditer(r'(?<![\w.:-])(%s)(?![\w.:-])'%MARK, ln)]
            ms=[x for x in ms if x[0]>12]
            if not ms: note('RELAY?',ln); i+=1; continue
            best=min(ms,key=lambda x:abs(x[1]-fe))
            first=ms[0] if 'Seed' not in hdr else ms[0]
            pieces=re.split(r'\s{2,}',re.sub(r'^\s*(\d+|--)\s+','',ln).strip())
            school=re.sub(r"\s+'[A-Za-z0-9]+'\s*$",'',pieces[0]).strip()
            pre_mark=re.sub(r"\s+'[A-Za-z0-9]+'\s*$",'',re.sub(r'^\s*(\d+|--)\s+','',ln[:ms[0][0]]).strip())
            if pre_mark and len(pre_mark)>len(school): school=re.sub(r'\s+',' ',pre_mark)  # school names printed with a double space (Mt.  Desert Island)
            class _M:
                def __init__(s,t): s.t=t
                def group(s,n): return s.t
            mm=_M(best[2])
            ath=[]; j=i+1; buf=''
            while j<len(lines) and re.match(r'\s*\d\)',lines[j]): buf+=' '+lines[j]; j+=1
            for a in re.split(r'\d\)',buf)[1:]:
                a=re.sub(r'\s+(FR|SO|JR|SR|\d{1,2})\s*$','',a.strip()); 
                if a: ath.append(a)
            ex=mm.group(2).startswith(('x','X')); mk=clean_mark(mm.group(2))
            rr={'place':place if mk not in STAT else None,'school':school,'result':mk,'athletes':ath,'type':sec}
            if ex: rr['exhibition']=True
            cur['results'].append(rr)
            i=j; continue
        yc=hdr.find('Year'); sc=hdr.find('School')
        if sc<0: sc=hdr.find('Team')
        if yc<0 and hdr.find('Yr')>=0 and hdr.find('Yr')<sc: yc=hdr.find('Yr')
        if yc<0: yc=sc
        name=ln[:yc]; name=re.sub(r'^\s*(\d+|--)\s+','',name).strip()
        yr=ln[yc:sc].strip() if yc<sc else ''
        rest=ln[sc:]
        mm_=re.fullmatch(r'(?:(FR|SO|JR|SR|\d{1,2})\s+)?([A-Z])',yr)
        if mm_: yr=mm_.group(1) or ''; rest=mm_.group(2)+rest  # school column printed one character left of the header
        fe=max(hdr.find('Finals')+6, hdr.find('Prelims')+7, hdr.find('Mark')+4, hdr.find('Time')+4)
        ms=[(mt.start()+sc,mt.end()+sc,mt.group(0)) for mt in re.finditer(r'(?<![\w.:-])(%s)(?![\w.:-])'%MARK, rest)]
        if not ms: note('ROW?',ln); i+=1; continue
        best=min(ms,key=lambda x:abs(x[1]-fe))
        pieces=re.split(r'\s{2,}',rest.strip())
        school=pieces[0].strip() if len(pieces)>1 else rest[:best[0]-sc].strip()
        if best[0]-sc < len(school): school=rest[:best[0]-sc].strip()
        raw_mk=best[2]; ex=raw_mk.startswith(('x','X')); mk=clean_mark(raw_mk)
        if not re.fullmatch(r'(FR|SO|JR|SR|\d{0,2})',yr) or re.match(r'(FR|SO|JR|SR)\b',school) or len(school)<3 or school[:1].islower():
            m2=re.match(r'\s*(?:\d+|--)\s+(?:\d+\s+)?(.+?)\s+(FR|SO|JR|SR)\s+(\S.*?)\s{2,}\S',ln)   # columns shifted against the header (bib numbers)
            if m2: name,yr,school=m2.group(1).strip(),m2.group(2),m2.group(3).strip()
        r={'place':place if mk not in STAT else None,'athlete':name,'school':school,'grade':yr,'result':mk,'type':sec}
        if ex: r['exhibition']=True
        cur['results'].append(r); i+=1; continue
    return [e for e in events if e['results']], rankings
HDR = re.compile(r'^\s*(?:Event\s+\d+\s+)?(Varsity\s+|JV\s+)?(Boys|Girls|Men|Women)\s+([A-Za-z0-9 ./-]+?)\s*(?:\(.*\))?\s*$')
def hdr_gender(ln):
    ln=ln.rstrip()
    if re.search(r'Team (Rank|Scores)|Results\s*$|Scores',ln): return None
    if ln.count(chr(9))>2 or re.match(r'\s*\d',ln): return None
    m=HDR.match(ln.rstrip())
    return m
def parse_race(text):
    events=[]; rankings=[]; cur=None; skip=False; teamsec=None; teamtot=False
    for ln in text.split(chr(10)):
        if re.search(r'Team Scores',ln):
            g='Boys' if re.search(r'Boys|Men',ln) else 'Girls'; teamsec={'gender':g,'teams':[]}; rankings.append(teamsec); cur=None; continue
        m=hdr_gender(ln)
        if m:
            teamsec=None; teamtot=False
            skip=bool(m.group(1) and m.group(1).strip()=='JV')
            gender={'Boys':'Boys','Men':'Boys','Girls':'Girls','Women':'Girls'}[m.group(2)]
            ev=norm_event(m.group(3))
            cur={'event':gender+' '+ev,'gender':gender,'is_relay':bool(re.search(r'Relay|Medley|Shuttle|Carousel|\dx\d',ev)),'results':[]}
            if not skip: events.append(cur)
            continue
        if re.match(r'\s*Team\s{2,}Mark',ln): teamtot=True; continue  # team totals for a field event, not individual marks
        rm=re.match(r'\s*(\d+|--)\s+(\S.*?)\s*$',ln)
        if not rm: continue
        pieces=re.split(r'\s{2,}',rm.group(2).strip())
        if teamsec is not None:
            if len(pieces)>=2 and pieces[1].replace('.','').isdigit():
                sc=float(pieces[1]); teamsec['teams'].append({'rank':int(rm.group(1)),'team':pieces[0],'score':int(sc) if sc==int(sc) else sc})
            continue
        if cur is None or skip or teamtot: continue
        k=None
        for idx in range(1,len(pieces)):
            if re.fullmatch(r'(%s)\s+\d+\.\d+'%MARK,pieces[idx]): pieces[idx]=pieces[idx].split()[0]   # mark and a fractional points value (tie split) one space apart
            if re.fullmatch(MARK,pieces[idx]): k=idx; break
        if k is None: note('RACE?',ln); continue
        raw_mk=pieces[k]; ex=raw_mk.startswith(('x','X')); mk=clean_mark(raw_mk)
        pl=None if (rm.group(1)=='--' or mk in STAT) else int(rm.group(1))
        pre=pieces[:k]
        if cur['is_relay'] or len(pre)==1:
            r={'place':pl,'school':pre[-1],'result':mk,'athletes':[],'type':'Finals'}
        else:
            nm=pre[0]; yr=''
            ym=re.match(r'(.*?)\s+(FR|SO|JR|SR|\d{1,2})$',nm)
            if len(pre)>=3 and re.fullmatch(r'FR|SO|JR|SR|\d{1,2}',pre[1]): yr=pre[1]
            r={'place':pl,'athlete':nm,'school':pre[-1],'grade':yr,'result':mk,'type':'Finals'}
        if ex: r['exhibition']=True
        cur['results'].append(r)
    return [e for e in events if e['results']],[x for x in rankings if x['teams']]
def parse_tab(text):
    events=[]; rankings=[]; cur=None; sec='Finals'
    for ln in text.split(chr(10)):
        m=re.match(r'\s*Event\s+\d+\s+(.*?)\s*$',ln)
        if m:
            nm=m.group(1).strip(); g=re.match(r'(Boys|Girls|Men|Women)\s+(.*)',nm)
            gender={'Boys':'Boys','Men':'Boys','Girls':'Girls','Women':'Girls'}[g.group(1)] if g else ''
            ev=g.group(2) if g else nm
            cur={'event':(gender+' '+norm_event(ev)).strip(),'gender':gender,'is_relay':bool(re.search(r'Relay|Medley|Shuttle|Carousel|\dx\d',ev)),'results':[]}
            events.append(cur); sec='Finals'; continue
        mh=hdr_gender(ln)
        if mh and 'Varsity'!=None:
            gender={'Boys':'Boys','Men':'Boys','Girls':'Girls','Women':'Girls'}[mh.group(2)]
            ev=norm_event(mh.group(3))
            cur={'event':gender+' '+ev,'gender':gender,'is_relay':bool(re.search(r'Relay|Medley|Shuttle|Carousel|\dx\d',ev)),'results':[]}
            if not (mh.group(1) and mh.group(1).strip()=='JV'): events.append(cur)
            sec='Finals'; continue
        if cur is None or not ln.strip(): continue
        f=[x.strip() for x in ln.split(chr(9))]
        if re.match(r'\d\)',f[0]) and cur['results'] and cur['is_relay']:   # relay legs "1) Last, First <tab> 2) ..."
            cur['results'][-1]['athletes']+=[re.sub(r'^\d\)\s*','',x) for x in f if re.match(r'\d\)',x)]; continue
        if re.match(r'(pl|place)$',f[0],re.I) or re.match(r'\d{4}$',f[0]): continue
        if len(f)<3 or (len(f)==3 and not (f[0].isdigit() or f[0] in ('---','--'))):
            if re.match(r'\s*(Prelim|Preliminaries)',ln,re.I): sec='Prelims'
            elif re.match(r'\s*Finals?\s*$',ln,re.I): sec='Finals'
            elif ln.strip(): print('TABLINE?',repr(ln),file=sys.stderr)
            continue
        pl=f[0]; 
        if not (pl.isdigit() or pl=='---' or pl=='--'): note('TABROW?',ln); continue
        place=int(pl) if pl.isdigit() else None
        f=[re.sub(r'(?<=\d)\.$','',x) for x in f]
        if any(x.split() and re.match(r'J\d',x.split()[0]) for x in f[2:]): note('TABMARK?',ln); continue
        k=None; comb=None
        for idx in range(2,len(f)):
            tk=f[idx].split()[:1]
            if tk and re.fullmatch(MARK,tk[0]): k=idx; break
            tt=f[idx].split()
            if len(tt)>=2 and re.fullmatch(MARK,tt[-1]) and not f[idx-1]: k=idx; comb=' '.join(tt[:-1]); break
        if k is None: note('TABMARK?',ln); continue
        raw_mk=f[k].split()[-1] if comb else f[k].split()[0]
        ex=raw_mk.startswith(('x','X')); mk=clean_mark(raw_mk)
        pre=[x for x in f[1:k] if x]+([comb] if comb else [])
        if len(pre)==1 or cur['is_relay']:
            r={'place':place if mk not in STAT else None,'school':pre[-1],'result':mk,'athletes':[],'type':sec}
        elif len(pre)>=2:
            nm=re.sub(r'^\d+\s+','',pre[-2])
            r={'place':place if mk not in STAT else None,'athlete':nm,'school':pre[-1],'grade':'','result':mk,'type':sec}
        else:
            note('TABPRE?',ln); continue
        if ex: r['exhibition']=True
        cur['results'].append(r)
    return [e for e in events if e['results']],rankings


# ---- cross country (individual race rows, team scores) -------------------------------------
XC_TIME = r'(?:\d+:)?\d{1,2}:\d{2}(?:\.\d+)?'
XC_STATUS = {'DNF', 'DQ', 'DNS', 'NT'}
def xc_header(ln):
    """(gender, distance, division) of a race title line ("Girls 2.9 Mile Run Junior Varsity",
    "Event 4  Boys 5k Run CC Varsity", "Boys 5k varsity", "6th Grade Boys 1 Mile Run", "boys 1.5 mile"), else None."""
    m = re.match(r'\s*(?:\.+)?(?:Event\s+\d+\s+)?(?:(\d\w*(?: (?:and|&) \d\w*)? Grade)\s+)?(Boys|Girls)\s+(\S.*?)\s*$', ln, re.I)
    if not m or re.search(r'Team|Score|Results', m.group(3)): return None
    d = re.search(r'(\d+(?:\.\d+)?)\s*(k|km|miles?|meters?|yards?|m)\b', m.group(3), re.I)
    if not d: return None
    unit = d.group(2).lower()
    if unit.startswith(('m', 'y')) and not unit.startswith('mile'): dist = '%gk' % (float(d.group(1)) / 1000)
    else: dist = d.group(1) + ('k' if unit.startswith('k') else ' Mile')
    gdiv = re.sub(r'(?<=\d)(?= (?:and|&))','th',m.group(1).replace('&','and')) if m.group(1) else None
    div = gdiv or ('JV' if re.search(r'junior varsity|\bJV\b', m.group(3), re.I) else 'Freshman' if re.search(r'freshman', m.group(3), re.I) else 'Varsity')
    return m.group(2).capitalize(), dist, div
def xc_name(n):
    n = re.sub(r'\s+', ' ', n).strip()
    m = re.match(r'^([^,]+),\s*(.+)$', n)
    if m: n = m.group(2) + ' ' + m.group(1)
    if n.isupper() or n.islower():
        n = n.title()
        n = re.sub(r"\bMc([a-z])", lambda x: 'Mc' + x.group(1).upper(), n)
    return n
def xc_finish(raw_events, raw_rankings):
    """Named events and team_rankings from [(gender, dist, div, rows)] and [(gender, div, header, teams)]."""
    merged = []   # one race split over pages (places run on) is one race
    for g, dist, div, rows in raw_events:
        prev = next((m for m in reversed(merged) if m[:3] == (g, dist, div)), None)
        if prev and rows and prev[3] and (rows[0].get('place') or 0) > (prev[3][-1].get('place') or 0):
            prev[3].extend(rows); continue
        merged.append((g, dist, div, rows))
    raw_events = merged
    divs = {}
    for g, dist, div, rows in raw_events: divs.setdefault(g, set()).add(div)
    events, labels = [], {}
    for g, dist, div, rows in raw_events:
        if not rows: continue
        lab = dist + ' Run CC' + (' ' + div if len(divs[g]) > 1 or div != 'Varsity' else '')
        labels[(g, div)] = lab
        events.append({'event': lab, 'gender': g, 'is_relay': False, 'results': rows})
    rank = []
    for g, div, hdr, teams in raw_rankings:
        if not teams: continue
        if (g, div) not in labels and len(divs.get(g, ())) == 1: div = next(iter(divs[g]))
        rank.append({'kind': 'xc', 'gender': g, 'event_header': labels.get((g, div), hdr), 'teams': teams})
    return events, rank
def xc_team_places(events, rankings):
    """Team-score places (what Hy-Tek prints in its Points column) for rows of files that do not print them:
    runners of the teams in the printed team scores count in finishing order; kept only if the first five of
    each team add up to the printed score."""
    for r in rankings:
        ev = next((e for e in events if e['gender'] == r['gender'] and e['event'] == r['event_header']), None)
        if not ev or any('team_place' in x for x in ev['results']): continue
        names = {t['team'] for t in r['teams']}
        tp = 0; got = {}; per = {}
        for x in ev['results']:
            if x['school'] in names and x.get('place') and len(per.get(x['school'], [])) < 7:
                tp += 1; got[id(x)] = tp; per.setdefault(x['school'], []).append(tp)
        ok = all(sum(per.get(t['team'], [])[:5]) == t['score'] for t in r['teams'] if len(per.get(t['team'], [])) >= 5)
        if ok and got:
            for x in ev['results']:
                if id(x) in got: x['team_place'] = got[id(x)]
        else:
            print('XC team places not reproduced for', r['event_header'], r['gender'], file=sys.stderr)
        for t in r['teams']:
            if 'places' not in t:
                t['places'] = [x['place'] for x in ev['results'] if x['school'] == t['team'] and x.get('place')][:7]
def parse_xc(text):
    """Fixed-width XC sheets: "NAME YR TEAM MARK H# WIND" (Meet Manager exports) and Hy-Tek "Event n" sheets
    (Name Year School [Avg Mile] Finals Points). Team scores follow the races."""
    raw_events = []; raw_rank = []; cur = None; heat = False; pend = None; teamsec = None; bib = False
    lines = text.replace('\t', '  ').split('\n')
    def _teamrow(i_):   # a team-score row (rank, team, score, places) followed by its "Total Time:" line
        return i_ + 1 < len(lines) and re.match(r'\s*\d+\s+\S.*?\s{2,}\d+(?:\.\d+)?(?:\s+\d+)+\s*$', lines[i_]) and re.match(r'\s*Total Time', lines[i_ + 1])
    for li, ln in enumerate(lines):
        mrw = re.match(r'\s*Results - (Men|Women)\s*$', ln)
        hh = xc_header(ln)
        if (mrw or hh) and _teamrow(li + 1) and not any('Team Scores' in x for x in lines[max(0, li - 6):li]):   # Hy-Tek prints the team block under the next header with no "Team Scores" title
            g_ = {'Men': 'Boys', 'Women': 'Girls'}[mrw.group(1)] if mrw else hh[0]
            fr = int(re.match(r'\s*(\d+)', lines[li + 1]).group(1))
            prev_ = [b for b in raw_rank if b[0] == g_ and b[3] and b[3][-1]['rank'] == fr - 1]
            if prev_ and raw_rank[-1] is prev_[0]:   # same block continued after a page break
                teamsec = {'g': g_, 'div': prev_[0][1], 'hdr': 'Team Scores', 'teams': prev_[0][3]}
            else:
                teamsec = {'g': g_, 'div': hh[2] if hh else 'Varsity', 'hdr': 'Team Scores', 'teams': []}
                raw_rank.append((g_, teamsec['div'], 'Team Scores', teamsec['teams']))
            cur = None; continue
        if re.match(r'\s*(Girls|Boys|[MF])?\s*(Varsity|Junior Varsity|JV)?\s*(Girls|Boys)?\s*Team Scores', ln):
            g = re.search(r'Girls|Boys', ln)
            mf = re.match(r'\s*([MF])\s+Team Scores', ln)
            if mf and not g: g = re.match(r'(Boys|Girls)', {'M': 'Boys', 'F': 'Girls'}[mf.group(1)])
            dv = 'JV' if re.search(r'Junior Varsity|JV', ln) else 'Varsity'
            teamsec = {'g': g.group(0) if g else (cur[0] if cur else None), 'div': dv if g else (cur[2] if cur else 'Varsity'), 'hdr': 'Team Scores', 'teams': []}
            raw_rank.append((teamsec['g'], teamsec['div'], 'Team Scores', teamsec['teams'])); cur = None; continue
        h = xc_header(ln)
        if h:
            if cur and tuple(cur[:3]) == h and (ln.strip().startswith('.') or not teamsec):
                teamsec = None; continue   # "....Event 2 Boys 3k Run CC": the race continued on the next page
            cur = [h[0], h[1], h[2], []]; raw_events.append(tuple(cur[:3]) + (cur[3],)); teamsec = None; heat = False; continue
        if re.match(r'\s*NAME\s+YR\s+TEAM', ln): heat = True; continue
        if re.match(r'\s*Name\s+Year\s+School.*\bH#', ln): heat = True; continue   # Hy-Tek with a heat column: the last number is not points
        if re.match(r'\s*#\s+Athlete\s+Yr\s+Team', ln): heat = True; bib = True; continue
        if teamsec is not None:
            mr = re.match(r'\s*Results - (Men|Women)', ln)
            if mr and teamsec['g'] is None:
                teamsec['g'] = 'Boys' if mr.group(1) == 'Men' else 'Girls'
                raw_rank[-1] = (teamsec['g'], teamsec['div'], ln.strip(), teamsec['teams'])
            tm = re.match(r'\s*(\d+)\s+(\S.*?)\s{2,}(\d+(?:\.\d+)?)((?:\s+\d+)*)\s*$', ln)
            if tm:
                if teamsec['teams'] and int(tm.group(1)) < teamsec['teams'][-1]['rank']:   # page break lost the other race's title: ranks restart; continue the other gender's block
                    og = 'Boys' if teamsec['g'] == 'Girls' else 'Girls'
                    nxt = [b for b in raw_rank if b[0] == og and b[3] and b[3][-1]['rank'] == int(tm.group(1)) - 1]
                    if nxt: teamsec = {'g': og, 'div': teamsec['div'], 'hdr': 'Team Scores', 'teams': nxt[0][3]}
                sc = float(tm.group(3)); t = {'rank': int(tm.group(1)), 'team': tm.group(2).strip(), 'score': int(sc) if sc == int(sc) else sc}
                pl = [int(x) for x in tm.group(4).split()]
                while len(pl) > 1 and pl[-1] < pl[-2]: pl.pop()   # last number clipped at the line end ("24 2" for 24 25)
                if pl: t['places'] = pl
                teamsec['teams'].append(t)
            continue
        if cur is None: continue
        rm = re.match(r'\s*(\d+|--)\.?\s+(\S.*?)\s*$', ln)
        if not rm: continue
        f = re.split(r'\s{2,}', re.sub(r'^\d+\s+', '', rm.group(2)) if bib else re.sub(r'^#\s+\d*\s*', '', rm.group(2)))   # "1 #  486 Mathews, Ophelia": bib number before the name
        pts = None
        while len(f) > 2 and re.fullmatch(r'\d{1,3}', f[-1]):
            v = f.pop()
            if pts is None and not heat: pts = int(v)
        mk = f.pop().strip()
        if not (re.fullmatch(XC_TIME, mk) or mk in XC_STATUS): note('XCROW?', ln); continue
        if f and re.fullmatch(XC_TIME, f[-1]) and len(f) > 2: f.pop()   # average mile column
        if len(f) < 2: note('XCROW?', ln); continue
        if len(f) == 2:   # "Name      12 School": year and school one space apart
            my = re.match(r'(\d{1,2}|FR|SO|JR|SR)\s+(\S.*)$', f[1])
            if my: f = [f[0], my.group(1), my.group(2)]
        name, grade = f[0], ''
        if len(f) >= 3 and re.fullmatch(r'\d{1,2}|FR|SO|JR|SR', f[1]): grade = f[1]; school = f[2]
        else: school = f[-1]
        r = {'place': int(rm.group(1)) if rm.group(1) != '--' and mk not in XC_STATUS else None,
             'athlete': xc_name(name), 'school': school, 'grade': grade, 'result': mk, 'type': 'Finals'}
        if pts is not None: r['team_place'] = pts
        cur[3].append(r)
    ev, rk = xc_finish([e for e in raw_events], [(a, b, c, d) for a, b, c, d in raw_rank])
    return ev, rk
def parse_xc_tab(text):
    """Tab sheets: Calais "Place Bib First name Last name Team Category Time Team_Points" and Machias
    "Place Name Team Time" with "Boys Team Scores:" lines ("Calais 30 Places 1,3,4,9,13")."""
    raw_events = []; raw_rank = []; cur = None; cols = None; teamsec = None; squeeze = False
    for ln in text.split('\n'):
        if ln.startswith('\t'): ln = ln[1:]   # sheets that indent every row ("\tPlace\tName\tTeam\tTime")
        ln = re.sub(r'(?<=[a-z])(Mt\. [A-Z][a-z]+)\t', r'\t\t\1\t', ln)   # school glued to the name ("RodriguezMt. Blue")
        f = [x.strip() for x in ln.split('\t')]
        h = xc_header(f[0]) if f[0] and len([x for x in f if x]) == 1 else None
        if h:
            cur = [h[0], h[1], h[2], []]; raw_events.append(cur); teamsec = None; continue
        if f[0].lower() == 'place':
            cols = [x.lower() for x in f]; squeeze = '' in cols[1:-1] or cols[-1] == ''
            if squeeze: cols = [x for x in cols if x]
            continue
        if f[0] == 'Team Scores' or f[0].startswith('AWARDS'):   # relay-style score tables ("1 Mt. Blue A 1:00:16"): not individual rows
            cur = None; teamsec = {'g': None, 'teams': []}; continue
        mt = re.match(r'(Boys|Girls)\s+.*?Team Scores', f[0])
        if mt:
            teamsec = {'g': mt.group(1), 'teams': []}
            raw_rank.append((mt.group(1), 'Varsity', 'Team Scores', teamsec['teams'])); cur = None; continue
        if teamsec is not None:
            if f[0].isdigit() and len(f) > 4 and f[3].isdigit():   # "1 <tab> <tab> Team <tab> Pts <tab> 2 <tab> 3 ... <tab> (22)"
                pl = []
                for x in f[4:]:
                    mp = re.fullmatch(r'\(?(\d+)\)?', x)
                    if not mp: break
                    pl.append(int(mp.group(1)))
                teamsec['teams'].append({'rank': int(f[0]), 'team': f[2], 'score': int(f[3]), 'places': pl}); continue
            tm = re.match(r'(.+?)\s+(\d+)\s+Places\s+([\d,\s]+)', f[0])
            if tm:
                pl = [int(x) for x in re.findall(r'\d+', tm.group(3))]
                teamsec['teams'].append({'rank': len(teamsec['teams']) + 1, 'team': tm.group(1).strip(), 'score': int(tm.group(2)), 'places': pl})
            continue
        if cur is None or cols is None or not f[0].isdigit(): continue
        if squeeze: f = [f[0]] + [x for x in f[1:] if x]
        row = dict(zip(cols, f))
        if 'athlete' in row: name = row['athlete']
        elif 'first name' in row: name = row['first name'] + ' ' + row['last name']
        else: name = row.get('name', '')
        name = re.sub(r'\s*-\s+', '-', name)
        gr = ''
        mg = re.match(r'^(.*\S)\s+(FR|SO|JR|SR)$', name)
        if row.get('grade', '').isdigit(): gr = row['grade']
        if mg: name = mg.group(1); gr = {'FR': '9', 'SO': '10', 'JR': '11', 'SR': '12'}[mg.group(2)]
        tm_ = row.get('time') or row.get('mark') or row.get('finals', '')
        mm = re.fullmatch(r'(\d+:\d{2}(?:\.\d+)?):00', tm_)   # "28:05:00" printed for 28:05
        if mm: tm_ = mm.group(1)
        if not (re.fullmatch(XC_TIME, tm_) or tm_ in XC_STATUS): note('XCTAB?', ln); continue
        if (row.get('team') or row.get('school', '')) in ('??', ''): note('XCTAB?', ln); continue   # school unknown in the source
        r = {'place': int(f[0]), 'athlete': xc_name(name), 'school': row.get('team') or row.get('school', ''), 'grade': gr, 'result': tm_, 'type': 'Finals'}
        for k_ in ('team_points', 'points', 'score'):
            if row.get(k_, '').isdigit(): r['team_place'] = int(row[k_])
        cur[3].append(r)
    return xc_finish([tuple(e) for e in raw_events], raw_rank)
def parse_xc_ria(text):
    """Run In A Race sheets: "Place Bib # Name Time Pace Grade Team Name", then "Team Scores / Place Score Team Name"."""
    evs = []; rk = []; cur = None; ts = None
    for ln in text.split('\n'):
        h = xc_header(ln)
        if h: cur = (h[0], h[1], h[2], []); evs.append(cur); ts = None; continue
        if (re.match(r'\s*Team Scores', ln) or re.match(r'\s*Place\s+Score\s+Team Name', ln)) and cur:
            ts = []; rk.append((cur[0], cur[2], 'Team Scores', ts)); continue
        if ts is not None:
            m = re.match(r'\s*(\d+)\s+(\d+)\s+(\S.*?)\s*$', ln)
            if m: ts.append({'rank': int(m.group(1)), 'team': m.group(3), 'score': int(m.group(2))})
            continue
        m = re.match(r'\s*(\d+)\s+\d+\s+(\S.*?)\s+(%s)\s+\d+:\d\d\s+(?:(\d{1,2})\s+)?(\S.*?)\s*$' % XC_TIME, ln)
        if m and cur: cur[3].append({'place': int(m.group(1)), 'athlete': xc_name(m.group(2)), 'school': m.group(5), 'grade': m.group(4) or '', 'result': m.group(3), 'type': 'Finals'})
    return xc_finish(evs, rk)
def parse_xc_any(t):
    if re.search(r'Pace\s+(?:Grade\s+)?Team Name', t): return parse_xc_ria(t)
    if '\tFirst name\t' in t or t.count('\t') > 5: return parse_xc_tab(t)
    if re.search(r'^=+ =+ =+', t, re.M) and 'TmPl' in t:
        import backend.fiveksport as fk
        g = None; evs = []; rk = []
        parts = re.split(r'\n(?=(?:\d\w*(?: (?:and|&) \d\w*)? Grade )?(?:Girls|Boys|girls|boys) (?:(?:Varsity|JV|Junior Varsity) )?\d)', '\n' + t)
        for part in parts:
            h = xc_header(part.strip().split('\n')[0]) if part.strip() else None
            if not h: continue
            rows = []
            for ln in part.split('\n'):
                m = re.match(r'\s*(\d+)\s+(?:(\d+)\s+)?(\d+)\s+(\S.*?)\s+[MFmf]\s+(\S.*?)\s+(%s)\s*$' % XC_TIME, ln)
                if not m:   # no gender column (Poland): name, optional year, school, time split by runs of spaces
                    m2 = re.match(r'\s*(\d+)\s+(?:(\d+)\s+)?(\d+)\s+(\S.*?)\s{2,}(?:\d{1,2}\s+)?([A-Za-z]\S*(?: \S+)*?)\s{2,}(%s)\s*$' % XC_TIME, ln)
                    m = m2
                if m:
                    r = {'place': int(m.group(1)), 'athlete': xc_name(m.group(4)), 'school': m.group(5), 'grade': '', 'result': m.group(6), 'type': 'Finals'}
                    if m.group(2): r['team_place'] = int(m.group(2))
                    rows.append(r)
            evs.append((h[0], h[1], h[2], rows))
            tb = fk.read_team_scores(part, h[0])
            if tb:
                for t in tb['teams']: t['score'] = int(t['score']) if t['score'] == int(t['score']) else t['score']
                rk.append((h[0], h[2], 'Team Score', tb['teams']))
        return xc_finish(evs, rk)
    return parse_xc(t)

_XCCAT = {}
def xc_untruncate(sn):
    """A school the sheet cut short ("Camden Hills Regional High Sch", "Ellsworth Hi") -> the catalog's full name."""
    if sn in _XCCAT: return _XCCAT[sn]
    out = sn
    try:
        sys.path.insert(0, os.path.dirname(BASE))
        from backend import school_catalog as sc
        sid = sc.resolve(sn, year=2026, season='XC')
        full = (sc.info(sid) or {}).get('name') if sid else None
        if full and full != sn and len(sn) >= 6 and full.lower().startswith(sn.lower().rstrip('.')): out = full
    except Exception as ex:
        print('catalog?', ex, file=sys.stderr)
    _XCCAT[sn] = out
    return out
ABBR=dict(x.split('=') for x in os.environ.get('ABBR','').split(';') if x)
def _evname(t):
    t=re.sub(r'\s+',' ',t).strip()
    t=' '.join(w[:1].upper()+w[1:] if w[:1].isalpha() else w for w in t.split(' ')).replace('4X','4x')
    return norm_event(t)
def parse_tab5(text):
    """Hand-typed coach sheets: an event title line (or none), a 'Place Athlete Team Event time Points'
    header, rows 'pl <tab> Last, First <tab> Team <tab> event label <tab> mark <tab> points' (the label
    is sometimes missing; points sometimes glued to the mark: 11.9:10). Teams are abbreviations, mapped
    with ABBR="Lis=Lisbon High School;...". Gender is inherited from the previous title."""
    events=[]; cur=None; gender='Boys'; pend=False
    def newev(title):
        nonlocal gender,cur
        g=re.match(r'(boys|girls|men|women)\s+(.*)',title.strip(),re.I)
        if g: gender={'boys':'Boys','men':'Boys','girls':'Girls','women':'Girls'}[g.group(1).lower()]; title=g.group(2)
        ev=_evname(title)
        cur={'event':gender+' '+ev,'gender':gender,'is_relay':bool(re.search(r'Relay|\dx\d',ev)),'results':[]}
        events.append(cur)
    for ln in text.split(chr(10)):
        f=[x.strip() for x in ln.split(chr(9))]
        if not any(f): pend=True; continue
        if re.match(r'(pl|place)$',f[0],re.I):
            if pend: cur=None
            pend=False; continue
        if not f[0].isdigit():
            if len([x for x in f if x])==1 and f[0].lower()!='<pre>': newev(f[0]); pend=False; continue
            note('TAB5?',ln); continue
        pl=int(f[0]); rest=[x for x in f[1:]]
        if cur and cur['is_relay']:
            team=next((x for x in rest[:2] if x),''); tail=rest[2:] if rest[0] else rest[1:]
            tail=[x for x in rest[1:] if x and x!=team] if True else tail
            name=None
        else:
            name=rest[0]; team=rest[1]; tail=[x for x in rest[2:] if x]
        if cur is None:   # untitled event: its name is the label column
            lab=[x for x in tail if re.search(r'[A-Za-z]{3}',x)]
            newev(lab[0] if lab else 'Event')
        if tail and re.search(r'[A-Za-z]{3}',tail[0]): tail=tail[1:]
        mk=None
        if cur['is_relay'] and len(tail)>=2 and re.fullmatch(r'\d',tail[0]) and re.fullmatch(r'\d{1,2}\.\d',tail[1]):
            mk='%s:%s'%(tail[0],tail[1].zfill(4)); print('RELAYFIX',repr(ln),file=sys.stderr)
        elif tail:
            t=tail[0]; m=re.fullmatch(MARK,t)
            if not m:
                g=re.match(r'(\d+:\d+\.\d+|\d+\.\d+)(?=:\d+$)',t)
                if g: mk=g.group(1)
            else: mk=clean_mark(t)
            if mk is None and m: mk=clean_mark(t)
        if not mk: note('TAB5MARK?',ln); continue
        sc=ABBR.get(team,team)
        if cur['is_relay']: r={'place':pl,'school':sc,'result':mk,'athletes':[],'type':'Finals'}
        else: r={'place':pl,'athlete':name,'school':sc,'grade':'','result':mk,'type':'Finals'}
        cur['results'].append(r)
    return [e for e in events if e['results']],[]
CANON=[ # school-name expansions; every rule anchored to the start of the name
    (r'^upper kennebec','Upper Kennebec Valley High School'),(r'^me acad','Maine Academy of Natural Sciences'),(r'^med$','Medomak Valley High School'),(r'^elgo$','Edward Little High School'),
    (r'^hwood$','Marshwood High School'),(r'^br14$|^brhs$|^brun$|^brunswick','Brunswick High School'),(r'^gtr\.? houlton','Houlton High School'),(r'^maine cen','Maine Central Institute'),
    (r'^no\.? ?yarm|^northyarm','North Yarmouth Academy'),(r'^sp red','South Portland High School'),(r'^valley$','Mountain Valley High School'),(r'^saints$','St. Dominic Academy'),
    (r'^poland','Poland Regional High School'),(r'^bangor chr','Bangor Christian School'),(r'^bangor( high|^ h\.?s\.?)?$|^ban$','Bangor High School'),(r'^dexter|^dex$','Dexter Regional High School'),
    (r'^calais','Calais High School'),(r'^old town|^ot$','Old Town High School'),(r'^piscataquis|^pchs$','Piscataquis Community High School'),(r'^penquis|^pen$','Penquis Valley High School'),
    (r'^searsport|^srpt$','Searsport District High School'),(r'^wash(ington)?\.? acad','Washington Academy'),(r'^jonesport','Jonesport-Beals High School'),(r'^f(or)?t\.? ?fairfield|^ffd$','Fort Fairfield High School'),
    (r'^(grtr|^greater)\.? houlton|^houlton','Houlton High School'),(r'^washburn','Washburn District High School'),(r'^katahdin','Katahdin High School'),(r'^f(or)?t\.? ?kent|^ftk$','Fort Kent Community High School'),
    (r'^foxcroft|^fox$','Foxcroft Academy'),(r'^john bapst|^jb$','John Bapst Memorial High School'),(r'^mattanawcook|^mat$','Mattanawcook Academy'),(r'^central( high|^ h\.?s\.?)?$|^cent?$','Central High School'),
    (r'^greenville|^grn$','Greenville High School'),(r'^narraguagus|^nar$','Narraguagus High School'),(r'^caribou|^car$','Caribou High School'),(r'^presque isle|^pi$','Presque Isle High School'),
    (r'^sumner|^sum$','Sumner Memorial High School'),(r'^ellsworth|^ell$','Ellsworth High School'),(r'^bucksport|^buc$','Bucksport High School'),(r'^cal$','Calais High School'),
    (r'^hampden','Hampden Academy'),(r'^orono','Orono High School'),(r'^hermon','Hermon High School'),(r'^bucksport','Bucksport High School'),
    (r'^bangor christian','Bangor Christian School'),(r'^gng$|^gray.?new','Gray-New Gloucester High School'),(r'^khs|^kennebunk','Kennebunk High School'),(r'^madison','Madison High School'),
    (r'^gould','Gould Academy'),(r'^wiscasset','Wiscasset High School'),(r'^nya$|^north yarmouth','North Yarmouth Academy'),(r'^(mount|^mt\.?) abram','Mount Abram High School'),
    (r'^(st\.?|^saint) dom','St. Dominic Academy'),(r'^sacopee','Sacopee Valley High School'),(r'^wells','Wells High School'),(r'^traip','Traip Academy'),
    (r'^york','York High School'),(r'^hebron','Hebron Academy'),(r'^carrabec','Carrabec High School'),(r'^old orchard|^oob$','Old Orchard Beach High School'),
    (r'^prhs$|^poland','Poland Regional High School'),(r'^frpt$|^freeport','Freeport High School'),(r'^dragons$|^brunswick','Brunswick High School'),(r'^lac$','Lincoln Academy'),
    (r'^mess','Messalonskee High School'),(r'^medomak','Medomak Valley High School'),(r'^mcs$','Maranacook Community School'),(r'^kh$','Kents Hill School'),
    (r'^bidd','Biddeford High School'),(r'^bonny|^be$','Bonny Eagle High School'),(r'^chev','Cheverus High School'),(r'^deering|^deer$','Deering High School'),
    (r'^gorh|^gorham','Gorham High School'),(r'^marsh|^mswd|^hawks$','Marshwood High School'),(r'^massab|^mass$','Massabesic High School'),(r'^noble|^nobl','Noble High School'),
    (r'^portland|^ptld','Portland High School'),(r'^scarb|^scar$','Scarborough High School'),(r'^sanf','Sanford High School'),(r'^so(uth)?\.? ?port|^sp$','South Portland High School'),
    (r'^thorn|^ta$','Thornton Academy'),(r'^westb|^west$','Westbrook High School'),(r'^wind','Windham High School'),(r'^mcau','Catherine McAuley High School'),
    (r'^mdi$|^mt\.? desert|^mount desert','Mount Desert Island High School'),(r'^sumner','Sumner Memorial High School'),(r'^george stevens|^gsa$','George Stevens Academy'),(r'^mtb$|^mt\.? blue|^mount blue','Mount Blue High School'),
    (r'^mta|^mt\.? ararat|^mount ararat','Mount Ararat High School'),(r'^gahs$|^gardiner','Gardiner Area High School'),(r'^oshs$|^oceanside','Oceanside High School'),(r'^leavitt','Leavitt Area High School'),
    (r'^edward little|^el$|^elhs','Edward Little High School'),(r'^lawrence','Lawrence High School'),(r'^waterville|^wtvl','Waterville High School'),(r'^mci$|^maine central inst','Maine Central Institute'),
    (r'^lewiston|^lhs$','Lewiston High School'),(r'^oxford hills|^oxhl|^ohhs|^ohs$','Oxford Hills High School'),(r'^morse','Morse High School'),(r'^lisbon','Lisbon High School'),
    (r'^cony','Cony High School'),(r'^skowhegan','Skowhegan Area High School'),(r'^nokomis','Nokomis Regional High School'),(r'^belfast','Belfast Area High School'),
    (r'^mt\.? ?(view|^v)$|^mount view|^mvhs$','Mount View High School'),(r'^winslow|^win$','Winslow High School'),(r'^spruce','Spruce Mountain High School'),(r'^monmouth|^mon$','Monmouth Academy'),
    (r'^hall[- ]?dale','Hall-Dale High School'),(r'^camden','Camden Hills Regional High School'),(r'^erskine','Erskine Academy'),(r'^brewer','Brewer High School'),
    (r'^kents hill','Kents Hill School'),(r'^maranacook|^marancook','Maranacook Community School'),(r'^waterville|^wtvl','Waterville Senior High School'),(r'^north haven','North Haven Community School'),
    (r'^winthrop','Winthrop High School'),(r'^telstar','Telstar High School'),(r'^richmond','Richmond High School'),(r'^oak hill','Oak Hill High School'),
    (r'^st\.? dom','St. Dominic Academy'),(r'^boothbay','Boothbay Region High School'),(r'^dirigo','Dirigo High School'),(r'^mt\.? valley|^mountain valley','Mountain Valley High School'),
    (r'^falmouth','Falmouth High School'),(r'^greely','Greely High School'),(r'^yarmouth','Yarmouth High School'),(r'^cape','Cape Elizabeth High School'),
    (r'^seacoast','Seacoast Christian School'),(r'^lake region','Lake Region High School'),(r'^fryeburg','Fryeburg Academy'),(r'^waynflete','Waynflete School'),
    (r'^sacopee','Sacopee Valley High School'),(r'^nya$|^north yarmouth','North Yarmouth Academy'),(r'^gng$|^gray','Gray-New Gloucester High School'),(r'^york','York High School'),
    (r'^oob|^old orchard','Old Orchard Beach High School'),(r'^wells','Wells High School'),(r'^traip','Traip Academy'),(r'^sacopee','Sacopee Valley High School'),
    (r'^kennebunk','Kennebunk High School'),
]
def canon(sn):
    k=sn.lower().strip()
    # never turn a middle school, elementary or junior high into its high school
    if re.search(r'middle|\bm\.?s\.?$|\bms\b|\bj\.?h\.?$|jr\.? ?high|junior|elementary|\bgrade|\bcs\b|community school|\bk-?8\b', k): return sn
    for pat,nm in CANON:
        if re.search(pat,k): return nm
    return sn
CLASSFILES=bool(os.environ.get('CLASSFILES'))
MS_SEASON = {'Indoor': 'indoor', 'Outdoor': 'outdoor', 'XC': 'cc'}
def kind_of(name):
    n = name.lower()
    if re.search(r'middle|\bms\b|jr\.? high|junior high|grade|\b[5-8]th\b|elementary', n): return 'ms'
    if re.search(r'usatf|youth|junior olympic|\bjo\b|group [a-d]\b|age group', n): return 'youth'
    if re.search(r'college|collegiate|university|ncaa|\barmy\b|\bnavy\b|\bair force\b|nescac|\bcolby\b|bates|bowdoin(?! relays)|\bumaine\b|husson|\bume\b|usm\b', n): return 'college'
    if re.search(r'twilight|road race|\b5k\b|masters|open\b', n): return 'open'
    return 'hs'
def listing(year, season):
    meets = []; seen = set()
    for page in range(1, 30):
        url = 'https://me.milesplit.com/results?year=%s&season=%s&page=%d' % (year, MS_SEASON[season], page)
        h = get(url, 'list-%s-%s-%d.html' % (year, season, page))
        rows = re.findall(r'<li class="meet-row"\s+data-meet-id="(\d+)".*?meet-row__day">([^<]+)<.*?<a class="meet-row__name" href="([^"]+)">([^<]+)</a>(?:\s*<span class="meet-row__venue">([^<]*)</span>)?', h, re.S)
        new = [r for r in rows if r[0] not in seen]
        if not new: break
        for mid, day, href, name, venue in new:
            seen.add(mid)
            name = html.unescape(name).strip()
            try:
                date = time.strftime('%Y-%m-%d', time.strptime('%s %s' % (day.strip().split('-')[0].strip(), year), '%b %d %Y'))
            except ValueError:
                date = None
            meets.append({'id': mid, 'name': name, 'date': date, 'venue': html.unescape(venue or '').strip(),
                          'url': href.replace('/results', ''), 'kind': kind_of(name)})
    out = os.path.join(BASE, 'data', 'meet_listings', 'milesplit-%s-%s.json' % (year, season))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out):   # keep readers' verdicts (match, kind, note) across re-listing
        old = {m['id']: m for m in json.load(open(out))['meets']}
        for m in meets:
            for k in ('match', 'note'):
                if k in old.get(m['id'], {}): m[k] = old[m['id']][k]
            if old.get(m['id'], {}).get('kind_checked'): m['kind'] = old[m['id']]['kind']; m['kind_checked'] = True
    json.dump({'site': 'milesplit', 'year': int(year), 'season': season,
               'listed': 'https://me.milesplit.com/results?year=%s&season=%s' % (year, MS_SEASON[season]),
               'meets': meets}, open(out, 'w'), indent=1)
    print('LISTED', len(meets), 'meets ->', out)
def main():
    cmd, slug = sys.argv[1], sys.argv[2]
    if cmd == 'list':
        listing(sys.argv[2], sys.argv[3]); return
    # MS_STAGE=<dir>: write to <dir>/<year>/<season>/ instead of parsed_results (backend/milesplit_bulk.py)
    OUT = os.path.join(os.environ.get('MS_STAGE') or os.path.join(BASE, 'data', 'parsed_results'), sys.argv[3], sys.argv[4]) + '/' if cmd == 'write' else ''
    if OUT: os.makedirs(OUT, exist_ok=True)
    date, files, title, h = meetinfo(slug)
    if cmd=='info':
        print(slug, date, title[:80], [(f['name'],f['id'],f['isMeetPro']) for f in files]); return
    events=[]; rank=[]; urls=[]; paywalled=[]; head=['','']
    for f in files:
        if str(f['id']) in os.environ.get('EXCLUDE','').split(','): continue
        if f['isMeetPro']: paywalled.append(f['name']); continue
        u='https://%s/meets/%s/results/%s/raw'%(HOST,slug,f['id'])
        raw=get(u,'%s-%s.html'%(slug,f['id']))
        pre=re.findall(r'<pre[^>]*>(.*?)</pre>',raw,re.S)
        if not pre: print('no <pre> for',f['name']); paywalled.append(f['name']+' (no text)'); continue
        t=html.unescape(re.sub(r'<[^>]+>','',pre[0]))
        t=re.sub(r"(?<=[\w.)])((?:Mt\. )?[A-Z][\w.]*(?: [A-Z][\w.]*)* Track Hy-Tek's MEET MANAGER\t)",r'\n\1',t)   # page header glued to the last row/leg before the page break
        e,r=(parse_xc_any(t) if sys.argv[4]=='XC' else parse_tab5(t) if '\tEvent\t' in t else parse_tab(t) if t.count('\t')>5 else (parse_race(t) if 'RaceTab' in t[:200] else parse(t))); 
        if sys.argv[4]=='XC': xc_team_places(e,r)
        events+=e; rank+=r; urls.append(u)
        cm=re.search(r'Class ([ABC])\b',f['name'])
        if cm and CLASSFILES:
            for x in e: x['event']+=' Class '+cm.group(1)
            for x in r: x['division']='Class '+cm.group(1)
        gs=[x['gender'] for x in e]
        for x in r:
            if not x['gender'] and gs: x['gender']=max(set(gs),key=gs.count)
        head=[x.strip() for x in t.strip().split('\n') if x.strip() and not re.match(r'(Licensed to|RaceTab|Results\s*$|Brewer High School - ME)',x.strip())][:2]
    names=set(re.sub(r'^Mt\.? ','Mount ',t['team']) for x in rank for t in x['teams'])|set(re.sub(r'^Mt\.? ','Mount ',r['school']) for e in events for r in e['results'])
    names=set(n for n in names if n)
    CODES={'BAN':'Bangor','OT':'Old Town','BRW':'Brewer','PEN':'Penquis','PCHS':'Piscataquis','NAR':'Narraguagus','MDI':'Mount Desert Island','MDIHS':'Mount Desert Island','HAM':'Hampden','CAL':'Calais','SUM':'Sumner','ELL':'Ellsworth','HOUL':'Houlton','GRNV':'Greenville','CAR':'Caribou','PI':'Presque Isle','FK':'Fort Kent','LIM':'Limestone','WSBN':'Woodland','HER':'Hermon','JB':'John Bapst','DEX':'Dexter','CEN':'Central','ORO':'Orono','FOX':'Foxcroft','GSA':'George Stevens','BUC':'Bucksport','MAT':'Mattanawcook','WA':'Washington Academy'}
    MASC=dict(x.split('=') for x in os.environ.get('MASC','').split(';') if x)
    def full(sc):
        sc=re.sub(r'^Mt\.? ','Mount ',sc)
        stem=CODES.get(sc) if sc.isupper() or sc in ('Mt',) else None
        if sc=='MDI': stem='Mount Desert Island'
        if stem:
            c=sorted([t for t in names if t.lower().startswith(stem.lower()) and len(t)>len(stem)],key=len)
            return c[-1] if c else sc
        c=sorted([t for t in names if t.lower().startswith(sc.lower()) and t.lower()!=sc.lower() and len(t)>len(sc)],key=len)
        fam=set(re.sub(r'\s*(High School|HS|Academy|Memorial|Area)\s*$','',x) for x in c)
        return c[-1] if c and len(fam)==1 else sc
    MSRE=r'middl|\bm\.?s\.?$|\bj\.?h\.?$|junior|jr\.? ?high|elementary|community school|\bcs\b|\bk-?8\b|\(middle'
    allnames=[n for n in names if n]
    MSMODE=bool(os.environ.get('MSMODE')) or (bool(os.environ.get('CANON')) and sys.argv[4]=='XC' and allnames and sum(1 for n in allnames if re.search(MSRE,n,re.I))>=0.4*len(allnames))
    MSBARE={'presque isle':'Presque Isle Middle School','boothbay':'Boothbay Region Elementary School (middle grades)','deer isle':'Deer Isle-Stonington Elementary School','dedham':'Dedham School','brewer cs':'Brewer Community School','berwick academy':'Berwick Academy (middle grades)','berwick acad':'Berwick Academy (middle grades)','mcwm':'Maine Coast Waldorf MS','friends scho':'Friends School of Portland',"st. john's c":"St. John's Catholic School",'mountain view':'Mountain View School','beech hill':'Beech Hill School','cave hill':'Cave Hill School','north haven community':'North Haven Community School','lyman moore':'Lyman Moore Middle School','loranger':'Loranger Memorial School','loranger old orchard beach':'Loranger Memorial School','maine coast waldorf':'Maine Coast Waldorf MS','molly ockett':'Molly Ockett Middle School','gray new glo':'Gray New Gloucester MS','south portla':'South Portland Middle School','bonny eagle':'Bonny Eagle MS','southern mai':'Southern Maine Catholic (combined MS team)','southern maine catholic':'Southern Maine Catholic (combined MS team)','surry elementary':'Surry Elementary School'}
    def msname(x):   # middle-school meets: never a high school name; expand only what the sheet cut short
        sn=re.sub(r'\s+',' ',x).strip()
        if sn.isupper() and len(sn)>5: sn=sn.title()
        if '(' in sn and ')' not in sn: sn=sn[:sn.index('(')].strip()   # cut-off parenthetical
        sn=re.sub(r'\bMs\b','MS',sn); sn=re.sub(r'\bJh\b','JH',sn); sn=re.sub(r'\bCs\b','CS',sn)
        if sn in ABBR: return ABBR[sn]
        def fin(t):
            if '(' in t and ')' not in t: t=t[:t.index('(')].strip()
            t=re.sub(r'\bOf\b','of',t)
            m=re.match(r'^(.*?\S)\s+(?:M|Mi|Mid|Midd|Middl|Middle|Middle S|Middle Sc|Middle Sch|Middle Scho|Middle Schoo)$',t)
            return m.group(1)+' Middle School' if m and not re.search(r'(?i)middle school',t) else t
        sn=fin(sn)
        c=full(sn)
        if c!=sn and re.search(MSRE,c,re.I): sn=fin(c)
        if sn.lower() in MSBARE: return MSBARE[sn.lower()]
        if not re.search(MSRE,sn,re.I):   # a name the sheet cut short: complete it from the catalog, but only to a middle school
            u=xc_untruncate(sn)
            if u!=sn and re.search(MSRE,u,re.I): sn=u
        return sn
    def nsch(x):
        if MSMODE: return MASC.get(msname(x),msname(x))
        sn=full(x); sn=re.sub(r'\s+',' ',sn).strip()
        if sn.isupper() and len(sn)>5: sn=sn.title()
        sn=re.sub(r'High School$','High School',sn,flags=re.I)
        if os.environ.get('CANON'): sn=canon(sn)
        if sys.argv[4]=='XC': sn=xc_untruncate(ABBR.get(sn,sn))
        return MASC.get(sn,sn)
    if MSMODE: print('MS-MODE names (no high-school expansion)',file=sys.stderr)
    for x in rank:
        for t in x['teams']: t['team']=nsch(t['team'])
    for e in events:
        for r in e['results']:
            r['school']=nsch(r['school'])
            if 'athlete' in r: r['athlete']=re.sub(r'^\d+\s+','',r['athlete'])
            gm = re.match(r'^(\S+(?: \S+)?)\s{2,}(\d{1,2})\s+(\S.*)$', r.get('athlete') or '')
            if gm:   # "Erin      17 Martin": a layout that prints the grade between the names
                r['athlete'] = gm.group(1) + ' ' + gm.group(3)
                r.setdefault('grade', gm.group(2)) if r.get('grade') else r.__setitem__('grade', gm.group(2))
            if 'athletes' in r:
                r['athletes']=[re.sub(r'^\d+\s+','',a) for a in r['athletes']]
                r['athletes']=[(lambda mm: mm.group(2)+' '+mm.group(1) if mm else a)(re.match(r'^([^,]+),\s+(.+)$',a)) for a in r['athletes']]
            nm=re.match(r'^([^,]+),\s+(.+)$',r.get('athlete',''))
            if nm: r['athlete']=nm.group(2)+' '+nm.group(1)
            for k_ in ('athlete',):
                if k_ in r: r[k_]=r[k_].replace('_','-')
            if 'athletes' in r: r['athletes']=[a.replace('_','-') for a in r['athletes']]
    if sys.argv[4]=='XC':   # one race printed in two files ("Complete" and "updated results"): keep the fuller list
        keep={}
        for i_,e in enumerate(events):
            k_=(e['gender'],e['event'])
            if k_ not in keep or len(e['results'])>=len(events[keep[k_]]['results']): keep[k_]=i_
        events=[e for i_,e in enumerate(events) if keep[(e['gender'],e['event'])]==i_]
    if sys.argv[4]=='XC':   # the same race's team scores printed in two files: the later file's block wins
        last_={}
        for i_,x in enumerate(rank): last_[(x['gender'],x.get('event_header'))]=i_
        rank=[x for i_,x in enumerate(rank) if last_[(x['gender'],x.get('event_header'))]==i_]
    if sys.argv[4]=='XC':   # pair each team block with its race (the QAQC verifier reads event_idx)
        for x in rank:
            ix=[i_ for i_,e in enumerate(events) if e['gender']==x['gender'] and e['event']==x.get('event_header')]
            if len(ix)==1: x['event_idx']=ix[0]
    n=sum(len(e['results']) for e in events)
    mname=re.sub(r'\s+Meet Manager\s*$','',title).strip()
    hd=[x for x in head if not re.search(r'MANAGER|Manager|Licensed',x)]
    edate=None; dnote=''
    for x in hd:
        dm=re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})',x)
        if dm: edate='%s-%02d-%02d'%(dm.group(3),int(dm.group(1)),int(dm.group(2))); break
    if edate and edate!=date and date and edate[:4]==date[:4] and abs((time.mktime(time.strptime(edate,'%Y-%m-%d'))-time.mktime(time.strptime(date,'%Y-%m-%d')))/86400)<=3: dnote=' Date taken from the results header (%s); MileSplit lists %s.'%(edate,date); date=edate
    venue=''
    vm=re.search(r'"location": \{\s*"@type": "Place",\s*"name": "([^"]+)"',h)
    if vm and sys.argv[4]=='XC': venue=html.unescape(vm.group(1))
    if sys.argv[4]!='XC' and (head and re.search(r'HY-TEK|Hy-Tek|Meet Manager',' '.join(head)) or (len(head)>1 and re.search(r' - \d+/\d+/\d{4}',head[0]))): venue=head[1] if len(head)>1 else ''
    out={'meet_name':mname,'date':date,'venue':venue,
         'meet_level':'hs','parser':'milesplit-manual','source':{'site':'milesplit','url':urls},
         'events':events,'team_rankings':[x for i_,x in enumerate(rank) if x['teams'] and x not in rank[:i_]],
         'notes':'Transcribed from MileSplit raw result text (me.milesplit.com). Schools kept as MileSplit prints them. Prelim/final/heat rows as printed; points column not copied; exhibition marks (x) flagged.'+dnote+(' Result file(s) %s skipped: duplicate of another meet\'s results.'%os.environ['EXCLUDE'] if os.environ.get('EXCLUDE') else '')+(' Abbreviated or mascot school names (LAC, MTB, Dragons ...) expanded to full names.' if os.environ.get('CANON') else '')+(' Schools printed as mascots in the source mapped: %s.'%os.environ['MASC'] if MASC else '')+(' '+os.environ['NOTES'] if os.environ.get('NOTES') else '')+(' Not available (Pro/no text): %s.'%paywalled if paywalled else '')+(' Rows not transcribed (unreadable mark or status): %s.'%'; '.join(UNP) if UNP else '')}
    if not events: print('NO EVENTS', paywalled); return
    path=OUT+'ms-%s.json'%re.sub(r'^\d+-','',slug)
    if os.path.exists(path):   # same meet name on another date (two "Portland High School" home meets): keep both
        try: prev=json.load(open(path))['source']['url']
        except Exception: prev=urls
        if prev!=urls: path=path[:-5]+'-%s.json'%date
    json.dump(out,open(path,'w'),indent=1)
    print('WROTE',path,n,'rows',len(events),'events', 'paywalled:',paywalled, 'rankings:',[(x['gender'],len(x['teams'])) for x in rank])
if __name__ == '__main__':
    main()
