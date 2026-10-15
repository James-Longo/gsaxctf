"""
fiveksport.py - Five K Sport (5K Sports Race Management) as a second XC source.

Five K Sport times western/coastal Maine meets (WMC schools, Poland, Maine
Coast, Falmouth, Greely) and posts results on fiveksport.com as Word files
shared from the timer's personal OneDrive. sub5.com does not carry most of
these meets.

OneDrive refuses plain HTTP downloads of those files ("The request is
blocked"), and we do not work around that. A real browser opening the share
link the way a visitor does works, so the fetch step is done by an agent with
a browser tool. Everything else is code:

    python3 -m backend.fiveksport pending 2026      # files not yet archived (JSON)
    # agent: open each file in the browser, run EXTRACT_JS, save the result:
    python3 -m backend.fiveksport save < extracted.json
    python3 -m backend.fiveksport sync 2026         # parse + verify + add to the store

The full agent procedure is docs/agents/fiveksport.md.

Rules that matter:
  * fiveksport.com reuses links: the same "Girls Results" file appears under
    three different meets, and a page heading can sit above another meet's
    files. A file's identity comes from its OWN header (meet, date, gender),
    never from where the page lists it. Files are keyed by OneDrive item id.
  * Only high-school cross country is collected (no road races, youth
    leagues, Nordic or middle-school meets).
"""

import hashlib
import html
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(BASE, 'backend', 'data', 'fiveks_archive')
INDEX_PATH = os.path.join(ARCHIVE, 'index.json')
PARSED = os.path.join(BASE, 'backend', 'data', 'parsed_results')
PAGE_URL = 'https://fiveksport.com/race-results-{year}'
PREFIX = 'fiveks-'

# Meet headings on the results pages that are not high-school XC.
NOT_HS_XC = re.compile(r'nordic|running lea|middle|relays|youth|kids', re.I)
XC_HEADING = re.compile(r'cross country|\bxc\b', re.I)
# Link labels that hold results or team scores (not awards/age groups/photos).
WANT_LABEL = re.compile(r'result|team|score', re.I)
SKIP_LABEL = re.compile(r'age group|award|winner|walker', re.I)
PAGE_NOISE = re.compile(r'photo|video|drone|tatt|code|anthem|award|winner|walker|add some extra', re.I)

# Run in the browser tab AFTER the Word viewer has been loaded as the top-level
# page, with the tab's viewport emulated tall (1000x3000; see the recipe).
# Word lays pages out lazily and only as far as the viewport reaches, and its
# status bar ("Page 1 of N", "W words") stays empty while the browser pane is
# hidden, so neither is trusted. Instead this scrolls until the laid-out pages
# stop changing, then opens Word's own Document stats dialog, which counts the
# whole file (hidden or not); save() checks the text against that count.
EXTRACT_JS = r"""
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  let last = '', stable = 0, rounds = 0;
  for (; rounds < 12 && stable < 2; rounds++) {
    document.querySelectorAll('*').forEach(e => {
      if (e.scrollHeight > e.clientHeight + 50 && getComputedStyle(e).overflowY !== 'visible') e.scrollTop = e.scrollHeight;
    });
    await sleep(1500);
    const ps = [...document.querySelectorAll('div.Page')];
    const sig = ps.length + '|' + ps.map(p => p.innerText.length).join(',');
    stable = ps.length && ps.every(p => p.innerText.trim()) && sig === last ? stable + 1 : 0;
    last = sig;
  }
  const num = s => s ? Number(s.replace(/,/g, '')) : null;
  let stats = null;
  const btn = document.getElementById('ShowWordCountDialog');
  if (btn) {
    btn.click();
    for (let i = 0; i < 20 && !stats; i++) {
      await sleep(500);
      const d = [...document.querySelectorAll('[role=dialog]')].map(x => x.innerText).find(t => /Characters/.test(t));
      const c = d && d.match(/Characters\s+([\d,]+)\s+([\d,]+) without spaces/);
      if (c) stats = {chars: num(c[1]), chars_nospace: num(c[2]),
                      words: num((d.match(/Words\s+([\d,]+)/) || [])[1]),
                      paragraphs: num((d.match(/Paragraphs\s+([\d,]+)/) || [])[1])};
    }
    const ok = [...document.querySelectorAll('[role=dialog] button')].find(x => /^OK$/.test(x.innerText.trim()));
    if (ok) ok.click();
  }
  const pages = [...document.querySelectorAll('div.Page')];
  const texts = pages.map(p => (p.querySelector('.PageContent') || p).innerText);
  // normalized exactly like fiveksport.normalize(): NBSP -> space, trailing
  // spaces dropped, pages joined by a blank line
  const text = texts.map(t => t.replace(/ /g, ' ').split('\n').map(l => l.replace(/\s+$/, '')).join('\n')).join('\n\n');
  const hex = async s => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))]
                           .map(b => b.toString(16).padStart(2, '0')).join('');
  // sha256: the exact text (proves it reached save() unaltered).
  // content_sha: same document? Word renders the "Page N" header field and a
  // "Page Break" marker on some loads and not others, so those lines and
  // blank lines are left out (fiveksport.content_sha does the same).
  const sha256 = await hex(text);
  const content_sha = await hex(text.split('\n').filter(l => l.trim() && !/^\s*(Page \d+|Page Break)$/.test(l)).join('\n'));
  return {title: document.title, rendered_pages: pages.length, empty_pages: texts.filter(t => !t.trim()).length,
          settle_rounds: rounds, doc_stats: stats, sha256, content_sha, text};
})()
"""

# Run on the OneDrive share page (onedrive.live.com) once it has loaded: it
# re-targets the viewer's own form so the Word viewer becomes the whole tab
# (its text is then readable; inside the cross-site frame it is not).
OPEN_VIEWER_JS = r"""
(() => {
  const f = document.querySelector('form');
  if (!f) return {ok: false, title: document.title};
  const name = (f.querySelector('input[name=filename]') || {}).value;
  f.target = '_self';
  f.submit();
  return {ok: true, filename: name};
})()
"""


# ---------------------------------------------------------------------------
# Inventory of the results pages
# ---------------------------------------------------------------------------

def _get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'gsaxctf results archive (fiveksport inventory)'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace')


def file_id(url):
    m = re.search(r'1drv\.ms/\w/c/[0-9a-f]+/([^?]+)', url)
    return m.group(1) if m else url


def inventory(year):
    """High-school XC result and team-score files listed on one season page.

    The page lists each meet as a heading, its location/date lines, then a
    run of file links. Returned rows keep the page's meet label only as a
    hint; save() names the file from its own header.
    """
    s = _get(PAGE_URL.format(year=year))
    s = re.sub(r'<script.*?</script>|<style.*?</style>', '', s, flags=re.S)
    s = re.sub(r'<a[^>]+href="(https://1drv[^"]+)"[^>]*>(.*?)</a>',
               lambda m: '\n[[LINK|%s|%s]]\n' % (re.sub('<[^>]+>', '', m.group(2)).strip(), m.group(1)),
               s, flags=re.S)
    lines = [l.strip() for l in html.unescape(re.sub(r'<[^>]+>', '\n', s)).split('\n') if l.strip()]
    rows, seen = [], set()
    for i, l in enumerate(lines):
        if l.startswith('[[') or len(l) > 90 or not XC_HEADING.search(l) or NOT_HS_XC.search(l):
            continue
        info, j = [], i + 1
        while j < len(lines) and not lines[j].startswith('[[') and len(info) < 3:
            info.append(lines[j])
            j += 1
        while j < len(lines):
            x = lines[j]
            if x.startswith('[[LINK|'):
                _, label, url = x.strip('[]').split('|', 2)
                if WANT_LABEL.search(label) and not SKIP_LABEL.search(label):
                    fid = file_id(url)
                    if fid not in seen:
                        seen.add(fid)
                        rows.append(dict(year=int(year), page_meet=l, page_info=' '.join(info),
                                         label=label.replace('\xa0', ' ').strip(), url=url, file_id=fid))
            elif not PAGE_NOISE.search(x):
                break
            j += 1
    return rows


def load_index():
    try:
        with open(INDEX_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def pending(year):
    """Inventory rows still to fetch: status 'new' (not archived) or
    'recheck' (archived without a completeness check)."""
    idx = load_index()
    out = []
    for r in inventory(year):
        e = idx.get(r['file_id'])
        if e is None:
            out.append(dict(r, status='new'))
        elif 'path' in e and 'doc_stats' not in e:
            # archived before the completeness check existed: re-check it.
            # If the browser's content_sha equals this, save without text.
            out.append(dict(r, status='recheck', archived_content_sha=entry_content_sha(e)))
    return out


# Calibration on the 16 files archived by 2026-10-15: Word's "characters
# (no spaces)" equals the extracted text's non-whitespace count exactly, or
# exceeds it by 5 when the viewer did not render the "Page 1" header field on
# that load. So the text may fall short by at most one "Page N" field per page
# (<= 6 characters each) and may never exceed Word's count. A lost result line
# is 25+ characters.
PAGE_FIELD_CHARS = 6


def text_chars(text):
    """Non-whitespace characters, without the viewer's 'Page Break' marker
    (rendered text, not document content)."""
    return len(re.sub(r'\s', '', text.replace('Page Break', '')))


def check_complete(text, payload, pages=None):
    """Refuse text that does not account for every character Word counts."""
    st = payload.get('doc_stats') or {}
    if st.get('chars_nospace') is None:
        raise ValueError('no doc_stats: extract with the current EXTRACT_JS (it reads Word\'s Document stats)')
    got = text_chars(text)
    short = st['chars_nospace'] - got
    pages = max(1, pages or payload.get('rendered_pages') or 1)
    if not 0 <= short <= PAGE_FIELD_CHARS * pages:
        raise ValueError(f"incomplete extraction: text has {got} characters, Word counts {st['chars_nospace']} "
                         '-- reload the document (tall viewport) and extract again')
    return st


# ---------------------------------------------------------------------------
# Saving extracted documents
# ---------------------------------------------------------------------------

MONTHS = {m: i for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july',
                                       'august', 'september', 'october', 'november', 'december'], 1)}


def header_identity(text):
    """(meet title, iso date or None, gender or None, is_team_scores) from the
    document's own header lines."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    head = [l for l in lines[:12] if not re.match(r'^page \d+$', l, re.I)]
    title = next((l for l in head if XC_HEADING.search(l) or re.search(r'meet|invitational|championship', l, re.I)),
                 head[0] if head else '')
    when = None
    for l in head:
        m = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s+(\d{4})', l, re.I)
        if m:
            when = date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))).isoformat()
            break
        m = re.search(r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b', l)
        if m:
            y = int(m.group(3)); y += 2000 if y < 100 else 0
            when = date(y, int(m.group(1)), int(m.group(2))).isoformat()
            break
    blob = ' '.join(head[:6]).lower()
    gender = 'Girls' if re.search(r'\bgirls?\b|\bwomen\b', blob) else 'Boys' if re.search(r'\bboys?\b|\bmen\b', blob) else None
    team = bool(re.search(r'team\s+(scores?|results|standings)', ' '.join(head).lower()))
    return title, when, gender, team


def _slug(s):
    s = re.sub(r'\b(girls?|boys?|women|men)\b', ' ', s.lower())
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:60]


TEAM_SCORE_HEAD = re.compile(r'\*+\s*TEAM SCORES?\s*\*+', re.I)


def team_score_names(text):
    """Runner names listed under each team on a team-score sheet."""
    names, buf = [], []
    for l in text.splitlines():
        if re.match(r'^\s*\d+\.\s+\S', l) or re.search(r'=\s*\d+\s*$', l) or not l.strip():
            if buf:
                names += [n.strip() for n in ' '.join(buf).split(',') if n.strip()]
                buf = []
            continue
        if not TEAM_SCORE_HEAD.search(l) and 'Page Break' not in l:
            buf.append(l.strip())
    if buf:
        names += [n.strip() for n in ' '.join(buf).split(',') if n.strip()]
    return names


def pair_team_scores(text, year):
    """(title, date, gender) of the one archived results file in `year` whose
    finish list contains the runners on this team-score sheet. Results show
    names cut to the column width, so match on the first 14 characters."""
    names = [n[:14] for n in team_score_names(text) if len(n) >= 6]
    if len(names) < 3:
        raise ValueError('team-score sheet lists too few runners to pair')
    hits = []
    for fid, e in load_index().items():
        if e.get('kind') != 'results' or not e.get('date', '').startswith(str(year)):
            continue
        try:
            body = open(os.path.join(BASE, e['path']), encoding='utf-8').read()
        except OSError:
            continue
        found = sum(1 for n in names if n in body)
        if found >= 0.8 * len(names):
            hits.append((found, e))
    if len(hits) != 1:
        raise ValueError(f'team-score sheet matches {len(hits)} archived results files in {year}; '
                         'save its results file first (exactly one must contain its runners)')
    e = hits[0][1]
    return e['header_title'], e['date'], e['gender']


def normalize(text):
    """The text form both the browser and save() hash: NBSP -> space,
    trailing whitespace dropped per line."""
    return '\n'.join(l.rstrip() for l in text.replace(' ', ' ').split('\n'))


MARKER_LINE = re.compile(r'^\s*(Page \d+|Page Break)$')


def content_sha(text):
    """Identity of a document's content, stable across viewer loads (see
    EXTRACT_JS): non-blank lines other than page-number/page-break markers."""
    lines = [l for l in normalize(text).split('\n') if l.strip() and not MARKER_LINE.match(l)]
    return hashlib.sha256('\n'.join(lines).encode('utf-8')).hexdigest()


def entry_content_sha(e):
    if e.get('content_sha'):
        return e['content_sha']
    if 'path' in e:
        try:
            return content_sha(open(os.path.join(BASE, e['path']), encoding='utf-8').read())
        except OSError:
            return None
    return None


def _write_index(idx):
    os.makedirs(ARCHIVE, exist_ok=True)
    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(idx, f, indent=1, sort_keys=True)


def save(payload):
    """Archive one extracted document.

    payload: {file_id, url, label, year, text, rendered_pages, doc_stats,
              empty_pages, title}. Refuses incomplete extractions.
    """
    if payload.get('skip'):
        # Seen and deliberately not archived (middle-school race, a team sheet
        # whose results were overwritten). The hash still lets a later run
        # notice if the timer replaces the file with something new.
        idx0 = load_index()
        idx0[payload['file_id']] = dict(skipped=payload['skip'], url=payload['url'],
                                        label=payload.get('label', ''), page_meet=payload.get('page_meet'),
                                        sha256=payload.get('sha256'), content_sha=payload.get('content_sha'),
                                        head=payload.get('head', '')[:200],
                                        fetched=datetime.now().isoformat(timespec='seconds'))
        _write_index(idx0)
        return f"skipped: {payload['skip']}"
    idx0 = load_index()
    if 'text' not in payload:
        # Hash-only save: no text copied, so the browser's content_sha must
        # name a document we already hold.
        csha = payload.get('content_sha')
        same = idx0.get(payload['file_id'], {})
        if csha and 'path' in same and entry_content_sha(same) == csha:
            # Re-check of this link's document, unchanged: confirm the
            # archived text against Word's count.
            body = open(os.path.join(BASE, same['path']), encoding='utf-8').read()
            st = check_complete(body, payload, same.get('pages'))
            same.update(doc_stats=st, content_sha=csha)
            _write_index(idx0)
            return f"unchanged, complete ({st['chars_nospace']} chars): {same['path']}"
        dup = next((fid for fid, e in idx0.items()
                    if 'path' in e and fid != payload['file_id'] and csha and entry_content_sha(e) == csha), None)
        if not dup:
            raise ValueError('no text given and content_sha matches nothing archived: include the text')
        text, digest = None, payload.get('sha256')
    else:
        text = normalize(payload['text'])
        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
        if payload.get('sha256') and payload['sha256'] != digest:
            raise ValueError('text does not match the hash computed in the browser: it was altered in '
                             'transit (copy it again verbatim, or pass the browser output through a file)')
        csha = content_sha(text)
        # Same document behind a different link (the timer reuses Word files:
        # the 2025 Poland link now holds the 2026 race). Record the alias so
        # the link is not fetched again; keep one copy.
        dup = next((fid for fid, e in idx0.items()
                    if 'path' in e and fid != payload['file_id'] and entry_content_sha(e) == csha), None)
    if dup:
        idx0[payload['file_id']] = dict(duplicate_of=dup, url=payload['url'], label=payload.get('label', ''),
                                        page_meet=payload.get('page_meet'), content_sha=csha,
                                        fetched=datetime.now().isoformat(timespec='seconds'))
        _write_index(idx0)
        return f"duplicate of {dup}: {idx0[dup]['path']}"
    if payload.get('empty_pages'):
        raise ValueError(f"incomplete extraction: {payload['empty_pages']} empty pages -- extract again")
    # Page counts alone were fooled once (the viewer reported "Page 1 of 1"
    # for a 2-page file before laying out page 2). Word's own count is the check.
    st = check_complete(text, payload)
    title, when, gender, team = header_identity(text)
    label = payload.get('label', '')
    unpaired = False
    if TEAM_SCORE_HEAD.search(text):
        # Team-score sheets carry no header at all. They belong to the results
        # file whose runners they list; pair by content, never by the page.
        # A sheet whose runners are in no archived results file (the page
        # links a middle-school sheet under a high-school meet, say) is kept
        # as unpaired so it is not fetched again, and never synced.
        team = True
        try:
            title, when, gender = pair_team_scores(text, int(payload['year']))
        except ValueError:
            unpaired = True
            title, when = 'unpaired team scores', None
    year = int(when[:4]) if when else int(payload['year'])
    if gender is None:
        gender = 'Girls' if re.search(r'girl', label, re.I) else 'Boys' if re.search(r'boy', label, re.I) else 'Mixed'
    kind = 'teamscores' if team or re.search(r'team', label, re.I) else 'results'
    # The page lists some middle-school races under high-school headings;
    # the document's own title decides. Archived (so it is not refetched)
    # but never synced as high-school racing.
    level = 'ms' if re.search(r'middle\s*school|junior\s*high|\bms\b', title, re.I) else 'hs'
    if unpaired:
        level = 'unpaired'
    stem = (f"{PREFIX}unpaired-{payload['file_id'][:12]}" if unpaired else
            f"{PREFIX}{_slug(title)}-{when or 'undated'}-{gender.lower()}-{kind}")
    d = os.path.join(ARCHIVE, str(year), 'XC')
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, stem + '.txt')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    idx = load_index()
    prev = idx.get(payload['file_id'])
    if prev and 'path' in prev and (prev.get('date'), prev.get('gender'), prev.get('kind')) != (when, gender, kind):
        # The timer reuses Word files across seasons: this link now holds a
        # different race. Keep the earlier document under its own key.
        idx[f"{payload['file_id']}@{prev.get('date')}"] = prev
    elif prev and 'path' in prev and prev['path'] != os.path.relpath(path, BASE):
        try:
            os.remove(os.path.join(BASE, prev['path']))
        except OSError:
            pass
    idx[payload['file_id']] = dict(path=os.path.relpath(path, BASE), url=payload['url'], label=label,
                                   page_meet=payload.get('page_meet'), header_title=title, date=when,
                                   gender=gender, kind=kind, level=level, pages=payload.get('rendered_pages'),
                                   doc_stats=st, sha256=digest, content_sha=csha,
                                   fetched=datetime.now().isoformat(timespec='seconds'))
    os.makedirs(ARCHIVE, exist_ok=True)
    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(idx, f, indent=1, sort_keys=True)
    return path


# ---------------------------------------------------------------------------
# Parse, verify, sync
# ---------------------------------------------------------------------------

RULER = re.compile(r'^=+(\s+=+)+\s*$')


def read_results(text):
    """Finish list from a Five K Sport results sheet, cut by the ===== ruler.

    The header row (Place TmPl No. Name Yr School Time) sits right above the
    ruler; each ruler segment is one column. Cutting by position keeps a
    blank team-place or year cell blank instead of letting the bib slide in.
    """
    lines = text.splitlines()
    out, cols = [], None
    for i, l in enumerate(lines):
        if RULER.match(l):
            hdr = next((lines[j] for j in range(i - 1, max(i - 4, -1), -1) if lines[j].strip()), '')
            spans = [(m.start(), m.end()) for m in re.finditer(r'=+', l)]
            names = []
            for a, b in spans:
                names.append(hdr[a:b + 1].strip().lower() if len(hdr) > a else '')
            cols = list(zip(names, spans))
            continue
        if cols is None or not l.strip():
            continue
        row = {}
        for k, (name, (a, b)) in enumerate(cols):
            # last column runs to the end of the line; others to the next column
            end = cols[k + 1][1][0] if k + 1 < len(cols) else len(l)
            row[name] = l[a:end].strip()
        place = row.get('place', '')
        # Multi-page sheets repeat the header block on every page; its lines
        # (the timer's phone number, say) can slice into digit-looking cells.
        # A finisher row has a real finish time.
        if not place.isdigit() or not re.fullmatch(r'(\d+:)?\d{1,2}:\d{2}(\.\d+)?', row.get('time', '')):
            continue
        out.append(dict(place=int(place), team_place=int(row['tmpl']) if row.get('tmpl', '').isdigit() else None,
                        bib=row.get('no.') or row.get('no'), athlete=row.get('name', ''),
                        grade=row.get('yr', ''), school=row.get('school', ''), result=row['time'],
                        type='Finals'))
    return out


def read_team_scores(text, gender):
    """Team-score sheet -> team_rankings block (team places, displacers in
    parentheses count as places but not toward the score)."""
    teams = []
    lines = text.splitlines()
    for i, l in enumerate(lines):
        m = re.match(r'^\s*(\d+)\.\s+(.+?)\s*$', l)
        if not m:
            continue
        for l2 in lines[i + 1:i + 4]:
            m2 = re.search(r'^\s*([\d\s()]+?)\s*=\s*(\d+)\s*$', l2)
            if m2:
                places = [int(x) for x in re.findall(r'\d+', m2.group(1))]
                teams.append(dict(rank=int(m.group(1)), team=m.group(2), score=float(m2.group(2)),
                                  places=places))
                break
    return dict(kind='xc', gender=gender, event_header='Team Score', teams=teams) if teams else None


def _venue(text):
    for l in text.splitlines()[:12]:
        m = re.match(r'^\s*([A-Z][A-Za-z .\'-]+?),\s*(Maine|ME)\b', l)
        if m:
            return m.group(1).strip()
    return None


def parse(year):
    """Archived Five K Sport sheets -> parsed_results/{year}/XC/fiveks-*.json,
    one file per results sheet with its paired team scores attached, in the
    same schema the sub5 parsers write. Returns [(file, rows, problem)]."""
    idx = load_index()
    out_dir = os.path.join(PARSED, str(year), 'XC')
    os.makedirs(out_dir, exist_ok=True)
    teams_for = {}
    for fid, e in idx.items():
        if e.get('kind') == 'teamscores':
            teams_for[(e['date'], e['gender'], e['header_title'])] = e
    res, changed = [], []
    for fid, e in sorted(idx.items(), key=lambda kv: kv[1].get('path', '')):
        if e.get('kind') != 'results' or not (e.get('date') or '').startswith(str(year)):
            continue
        if e.get('level') == 'ms':
            res.append((os.path.basename(e['path']), 0, 'middle school: archived, not synced'))
            continue
        text = open(os.path.join(BASE, e['path']), encoding='utf-8').read()
        rows = read_results(text)
        rankings = []
        t = teams_for.get((e['date'], e['gender'], e['header_title']))
        if t:
            blk = read_team_scores(open(os.path.join(BASE, t['path']), encoding='utf-8').read(), e['gender'])
            if blk:
                rankings.append(blk)
        stem = os.path.basename(e['path'])
        doc = dict(events=[dict(event=f"{e['gender']} Run CC", gender=e['gender'], is_relay=False,
                                results=rows)],
                   date=e['date'], meet_name=e['header_title'], venue=_venue(text),
                   team_rankings=rankings, meet_level='hs', parser='fiveksport',
                   source=dict(site='fiveksport.com', url=e['url'], sha256=e['sha256']))
        out_path = os.path.join(out_dir, stem + '.json')
        try:
            with open(out_path, encoding='utf-8') as f:
                before = json.load(f)
        except (OSError, ValueError):
            before = None
        if before is not None and before.get('events') != doc['events']:
            # A re-extraction changed the rows (a truncated file completed).
            # The store skips meets it has synced, so un-mark this one; the
            # next sync adds the new rows (ids are deterministic, so rows
            # already stored are not duplicated).
            changed.append(stem)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=1)
        problem = None
        if not rows:
            problem = 'no rows read'
        elif [r['place'] for r in rows] != list(range(1, len(rows) + 1)):
            problem = 'places not 1..N'
        res.append((stem, len(rows), problem))
    if changed:
        from backend.scraper_v2 import load_scrape_state, save_scrape_state
        state = load_scrape_state()
        for stem in changed:
            state.get('synced_meets', {}).pop(f'{year}_XC_{stem}', None)
        save_scrape_state(state)
    return res


def verify(year):
    """Team-score verification of this season's Five K Sport files."""
    sys.path.insert(0, os.path.join(BASE, 'backend'))
    import qaqc
    out = os.path.join(PARSED, str(year), 'XC')
    res = {}
    for fn in sorted(os.listdir(out)) if os.path.isdir(out) else []:
        if fn.startswith(PREFIX):
            v = qaqc.xc_verify_file(os.path.join(out, fn))
            if v:
                res[fn] = v.get('status')
    return res


def sync(year):
    """Parse, verify, and add the season's Five K Sport meets to the store
    through the same sync as sub5 (school catalog, double-ingest guard)."""
    from backend.scraper_v2 import Sub5ScraperV2, SEASONS
    parsed = parse(year)
    ver = verify(year)
    s = Sub5ScraperV2(progress_callback=lambda *a, **k: None)
    n = s.run_full_scrape(wipe=False, seasons=[x for x in SEASONS if x['season'] == 'XC' and x['year'] == str(year)],
                          download=False, parse=False)
    return dict(parsed=parsed, verification=ver, synced=n)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'pending':
        print(json.dumps(pending(sys.argv[2]), indent=1))
    elif cmd == 'inventory':
        print(json.dumps(inventory(sys.argv[2]), indent=1))
    elif cmd == 'save':
        print(save(json.load(sys.stdin)))
    elif cmd == 'parse':
        for r in parse(sys.argv[2]):
            print(r)
    elif cmd == 'verify':
        print(json.dumps(verify(sys.argv[2]), indent=1))
    elif cmd == 'sync':
        print(json.dumps(sync(sys.argv[2]), indent=1, default=str))
    else:
        print(__doc__)
