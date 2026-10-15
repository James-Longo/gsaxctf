import re
from bs4 import BeautifulSoup
import json
import os
import sys
import subprocess
import tempfile

_GRADE_MAP = {
    'Fr': 'FR', 'fr': 'FR', 'FRESHMAN': 'FR',
    'So': 'SO', 'so': 'SO', 'SOPH': 'SO', 'SOPHOMORE': 'SO',
    'Jr': 'JR', 'jr': 'JR', 'JUNIOR': 'JR',
    'Sr': 'SR', 'sr': 'SR', 'SENIOR': 'SR',
}

def normalize_grade(g):
    """Return a clean grade string (5-12, FR/SO/JR/SR, or MS) or '' for junk.
    Middle-school grades 5-7 are kept: they are how a junior-high race that
    sub5 posts beside the high-school results is told apart."""
    if not g:
        return ''
    g = g.strip()
    if not g or g in ('--', '0', '22'):
        return ''
    if g in ('5', '6', '7', '8', '9', '10', '11', '12', 'MS', 'FR', 'SO', 'JR', 'SR'):
        return g
    if g in _GRADE_MAP:
        return _GRADE_MAP[g]
    # "9 H", "11 B", "12 Finals", "8th", "8t" — extract the leading grade number
    m = re.match(r'^([5-9]|10|11|12)(?:\b|st|nd|rd|th|t\b)', g)
    if m:
        return m.group(1)
    return ''


# "CLASS A Results" / "Division II Results": per-class sections of one race
# ("Class A Results - Women" also splits a Mixed race by gender)
# ("Division 2,3, JC Results 5000 Run": a label of several words, then the race)
_SECTION_RE = re.compile(r'^(Class|Division|Section)\s+(\w{1,4}(?:\s*,\s*\w{1,4})*)\s+Results'
                         r'(?:\s*-\s*(Women|Men|Girls|Boys))?(?:\s+\d+\s*\w*\s*Run)?$', re.I)
_SECTION_GENDER = {'women': 'Girls', 'girls': 'Girls', 'men': 'Boys', 'boys': 'Boys'}
_XC_SCORES_LINE = re.compile(r'^(?:\S+\s+){0,3}Team\s+Scores?$', re.I)


_NUMBER_WORDS = {'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5', 'six': '6'}


def _number_words(label):
    """'Three Mile Run' -> '3 Mile Run': distance words become digits so the
    event canonicaliser reads the distance."""
    return re.sub(r'\b(one|two|three|four|five|six)(?=\s+(?:mile|k\b|kilometer))',
                  lambda m: _NUMBER_WORDS[m.group(1).lower()], label, flags=re.I)


def _is_xc_event(name):
    """A cross-country race label: "5k Run CC", "3.1 Mile Run VARSITY Class C",
    "2.4 Mile Run" - CC/XC/cross, a k-distance run, or a run over 2 miles
    (track runs stop at 2 miles)."""
    if re.search(r'\bCC\b|cross|\bXC\b', name, re.I):
        return True
    if re.search(r'\d\s*(?:k|km)\s+run', name, re.I):
        return True
    m = re.search(r'(\d+(?:\.\d+)?)\s*miles?\s+run', name, re.I)
    return bool(m and float(m.group(1)) > 2)


class Sub5ColumnParser:
    def __init__(self, file_path, text=None):
        """Parse from a file path, or directly from `text` (html or plain)
        to avoid the temp-file round trip when the caller already has the
        content in memory."""
        self.file_path = file_path
        self.text = text
        self.headers = {'User-Agent': 'Mozilla/5.0'}
        self.standard_events = [
            # IMPORTANT: More-specific entries must precede their substrings.
            # Race Walk events must come before plain Run events to avoid
            # "1600 Meter Race Walk" being misidentified as "1600 Meter Run".
            "1600 Meter Race Walk", "800 Meter Race Walk",
            # Relays before bare distance events
            "4x200 Meter Relay", "4x400 Meter Relay", "4x800 Meter Relay",
            "4x100 Meter Relay",
            # Running events
            "55 Meter Dash", "100 Meter Dash", "200 Meter Dash", "400 Meter Dash",
            "600 Meter Run", "800 Meter Run", "1000 Meter Run",
            "1600 Meter Run", "3200 Meter Run",
            "1 Mile Run", "2 Mile Run",
            # Hurdles
            "55 Meter Hurdles", "55 Yard Hurdles",
            "100 Meter Hurdles", "110 Meter Hurdles",
            "300 Meter Hurdles", "400 Meter Hurdles",
            # Field events
            "High Jump", "Long Jump", "Triple Jump", "Pole Vault",
            "Shot Put", "Discus", "Javelin",
            # Misc
            "Indoor Pentathlon",
        ]

    def normalize_event_name(self, event_name):
        """
        Normalizes event names by matching against a list of standard events.
        If a standard event is a substring of the input, use the standard version.
        Prioritizes the longest match to ensure more-specific events (e.g.
        "1600 Meter Race Walk") win over less-specific ones ("1600 Meter Run").
        """
        best_match = event_name
        max_len = 0
        low = event_name.lower()

        for std in self.standard_events:
            # whole-number boundary: "2.1 Mile Run CC" is not "1 Mile Run",
            # nor "3.2 Mile Run" a "2 Mile Run"
            if re.search(r'(?<![\d.])' + re.escape(std.lower()), low):
                if len(std) > max_len:
                    best_match = std
                    max_len = len(std)

        return best_match
        
    @staticmethod
    def pdf_to_text(pdf_path):
        """Convert a PDF file to plain text using pdftotext (poppler).
        Returns the extracted text string, or None if pdftotext is unavailable."""
        try:
            result = subprocess.run(
                ['pdftotext', '-layout', pdf_path, '-'],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                return result.stdout
            else:
                print(f"pdftotext error for {pdf_path}: {result.stderr.strip()}")
                return None
        except FileNotFoundError:
            print("pdftotext not found. Install poppler-utils to parse PDF results.")
            return None
        except Exception as e:
            print(f"Error converting PDF {pdf_path}: {e}")
            return None

    @staticmethod
    def pdf_words_to_text(pdf_path):
        """Rebuild a PDF's text from word coordinates (PyMuPDF).

        pdftotext -layout scrambles spreadsheet-style exports whose cells
        aren't in reading order; regrouping words by y-position and spacing
        them by x-position recovers a usable fixed-width layout. Returns
        None if PyMuPDF is unavailable."""
        try:
            import fitz
        except ImportError:
            return None
        try:
            doc = fitz.open(pdf_path)
        except Exception:
            return None
        out_lines = []
        for page in doc:
            rows = {}
            for w in page.get_text('words'):
                y = round(w[1] / 4)  # 4pt row tolerance
                rows.setdefault(y, []).append(w)
            for y in sorted(rows):
                ws = sorted(rows[y], key=lambda w: w[0])
                line = ''
                for w in ws:
                    col = int(w[0] / 3.5)  # ~average char width in points
                    if len(line) < col:
                        line += ' ' * (col - len(line))
                    elif line and not line.endswith(' '):
                        line += ' '
                    line += w[4]
                out_lines.append(line)
            out_lines.append('')
        return '\n'.join(out_lines)

    @staticmethod
    def pdf_ocr_text(pdf_path, timeout=180):
        """OCR an image-only PDF via pdftoppm + tesseract. Returns text or None."""
        import shutil as _shutil
        if not _shutil.which('tesseract') or not _shutil.which('pdftoppm'):
            return None
        import tempfile as _tf
        out = []
        try:
            with _tf.TemporaryDirectory() as td:
                subprocess.run(['pdftoppm', '-r', '300', '-png', pdf_path,
                                os.path.join(td, 'pg')],
                               capture_output=True, timeout=timeout)
                pages = sorted(f for f in os.listdir(td) if f.endswith('.png'))
                for pg in pages:
                    r = subprocess.run(['tesseract', os.path.join(td, pg), '-'],
                                       capture_output=True, text=True, timeout=timeout)
                    if r.returncode == 0:
                        out.append(r.stdout)
        except Exception:
            return None
        return '\n'.join(out) if out else None

    @staticmethod
    def pdf_column_text(pdf_path):
        """Column-aware PDF text: detect vertical whitespace gaps in the word
        x-positions and emit each column's text sequentially. Handles
        hand-made dual-meet sheets laid out as 2-3 columns of event blocks."""
        try:
            import fitz
        except ImportError:
            return None
        try:
            doc = fitz.open(pdf_path)
        except Exception:
            return None
        out = []
        for page in doc:
            words = page.get_text('words')
            if not words:
                continue
            spans = sorted((w[0], w[2]) for w in words)
            merged = []
            for a, b in spans:
                if merged and a <= merged[-1][1] + 25:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], b))
                else:
                    merged.append((a, b))
            for cx0, cx1 in merged:
                colwords = [w for w in words if cx0 - 1 <= w[0] < cx1 + 1]
                rows = {}
                for w in colwords:
                    y = round(w[1] / 4)
                    rows.setdefault(y, []).append(w)
                for y in sorted(rows):
                    ws = sorted(rows[y], key=lambda w: w[0])
                    out.append(' '.join(w[4] for w in ws))
                out.append('')
        return '\n'.join(out)

    @staticmethod
    def split_pdf_columns(page_text):
        """Detect side-by-side event columns in pdftotext -layout output and
        re-emit them sequentially (column 1's lines, then column 2's, ...).

        Multi-column pages repeat the 'Name ... Finals' header at distinct x
        positions; without splitting, one line splices rows from 2-3
        different events together."""
        lines = page_text.splitlines()
        positions = []
        for l in lines:
            for m in re.finditer(r'\bName\b', l):
                # "First Name  Last Name" is one table's two name cells
                if re.search(r'\b(Last|Team|School)\s+$', l[:m.start()]):
                    continue
                positions.append(m.start())
        if not positions:
            return page_text
        # cluster x-positions (within 3 chars)
        clusters = []
        for p in sorted(positions):
            for c in clusters:
                if abs(c[0] - p) <= 3:
                    c.append(p)
                    break
            else:
                clusters.append([p])
        starts = sorted(min(c) for c in clusters if len(c) >= 1)
        if len(starts) < 2:
            return page_text
        # column boundaries: a bit left of each 'Name' header (rank numbers
        # sit ~4-6 chars before it) - or at the column's own "Place" header
        # when one precedes the name ("Place Score Name ...  Place Score Name")
        def _gutter(x):
            # nearest column at/left of x that is blank on every data line
            data = [l for l in lines if re.match(r'\s*\d+\s', l)]
            for c in sorted(range(max(1, x - 12), x + 5), key=lambda c: (abs(c - x), c)):
                if all(len(l) <= c or not l[c - 1:c + 1].strip() for l in data):
                    return c
            return x

        def _bound(x):
            for l in lines:
                if l[x:x + 4] == 'Name':
                    pm = list(re.finditer(r'\b(?:Place|PLACE|Pl|PL|Plc)\b', l[max(0, x - 24):x]))
                    if pm:
                        return _gutter(max(0, x - 24) + pm[-1].start())
            return max(0, x - 6)
        bounds = [0] + [_bound(s) for s in starts[1:]] + [10 ** 6]
        columns = [[] for _ in range(len(bounds) - 1)]
        for l in lines:
            for i in range(len(bounds) - 1):
                seg = l[bounds[i]:bounds[i + 1]].rstrip()
                columns[i].append(seg)
        return '\n'.join('\n'.join(col) for col in columns)

    @staticmethod
    def clean_pdf_text(text):
        """Strip PDF-specific artifacts so the column parser works normally.

        Artifacts handled:
        - Form-feed page breaks with multi-line header blocks
        - Continuation event headers like ....Event N Girls ...
        - Indent normalization: result rows must all have exactly 2 leading
          spaces before the rank number so columns align with the header row.
          pdftotext produces:
            page 1:  "  1 Name ..."  (2 spaces before 1-digit rank)
            page 1:  "  9 Name ..."  (2 spaces before 1-digit rank)
            page 1:  " 10 Name ..."  (1 space before 2-digit rank)
            page 2:  " 8 Name ..."   (1 space before 1-digit rank -- needs +1)
            page 2:  "19 Name ..."   (0 spaces before 2-digit rank -- needs +2)
          After normalization all single-digit ranks have 2 leading spaces.
        - The meet date in the Hy-Tek header is extracted and prepended.
        """
        # (a lone carriage return inside a row - "Serena\t\r Blasios" -
        # is no line break)
        text = re.sub(r'\t?\r(?!\n)', ' ', text)
        text = re.sub(r'(?<=\S)( *)\t\n[ \xa0\t]*(?=\S)', lambda m: m.group(1) or ' ', text)   # (already split: "Serena\t" / " \xa0 Blasios")
        # Split multi-column pages before joining (page by page, since
        # column boundaries can differ between pages)
        pages = text.split("\x0c")
        text = "\n".join(Sub5ColumnParser.split_pdf_columns(p) for p in pages)

        import re as _re

        injected_date_line = None
        m_date = _re.search(r"Hy-Tek's MEET MANAGER.*?(\d{1,2}/\d{1,2}/\d{4})", text)
        if m_date:
            injected_date_line = f"Meet Date: {m_date.group(1)}"

        cleaned_lines = []
        if injected_date_line:
            cleaned_lines.append(injected_date_line)

        skip_remaining = 0
        for line in text.splitlines():
            stripped = line.strip()

            if skip_remaining > 0:
                skip_remaining -= 1
                continue

            if _re.search(r"Hy-Tek's MEET MANAGER", line):
                skip_remaining = 3
                continue

            if _re.match(r"^\.+Event\s+\d+\s+", stripped, _re.IGNORECASE):
                continue

            # Normalize result-row indentation so all ranks are preceded by
            # exactly 2 spaces (matching the page-1 header column positions).
            # Single-digit rank with 1 leading space: " N " -> "  N "
            if _re.match(r"^ \d ", line):
                line = " " + line
            # Two-digit rank with no leading space: "NN " -> "  NN "
            elif _re.match(r"^\d{2} ", line):
                line = "  " + line

            cleaned_lines.append(line)

        return "\n".join(cleaned_lines)

    def parse(self):
        if self.text is None and not os.path.exists(self.file_path):
            return []

        # --- PDF handling ---
        if self.text is None and self.file_path.lower().endswith('.pdf'):
            raw_text = self.pdf_to_text(self.file_path)
            if raw_text is None:
                print(f"Cannot parse PDF (pdftotext unavailable): {self.file_path}")
                return []
            text = self.clean_pdf_text(raw_text)
            lines = text.splitlines()
        else:
            if self.text is not None:
                html_content = self.text
            else:
                with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    html_content = f.read()

            soup = BeautifulSoup(html_content, 'html.parser')

            # Try to find <pre> specifically if possible.
            # Older files (2003-2013) split one meet across several <pre>
            # blocks, so join them all rather than taking just the first.
            pres = soup.find_all('pre')
            # Word "Save as Web Page" exports hold one Hy-Tek line per <p>,
            # wrapped at arbitrary points in the source; those newlines are
            # just HTML whitespace (the alignment lives in &nbsp; runs). Any
            # <pre> blocks in such files are stray fragments.
            word_html = 'schemas-microsoft-com:office' in html_content[:5000]
            word_lines = []
            if word_html:
                word_lines = [re.sub(r'[ \t\r\n]+', ' ', t.get_text()).replace('\xa0', ' ')
                              for t in soup.find_all('p')]
            if pres:
                text = "\n".join(p.get_text() for p in pres)
                lines = text.splitlines()
                row = re.compile(r'^\s*\d+\s+\S.*\d:\d\d')
                if word_lines and sum(1 for l in word_lines if row.match(l)) > \
                        sum(1 for l in lines if row.match(l)):
                    lines = word_lines
                # a <pre> holding only the page header, the results loose
                # in the body (&nbsp;-padded lines broken by <br>)
                # (or the results run on past the <pre> in &nbsp;-padded
                # paragraphs: scarborough17sept04.htm's boys races)
                body = re.sub(r'<br\s*/?>', '\n', html_content, flags=re.I)
                body_lines = [l.replace('\xa0', ' ') for l in
                              BeautifulSoup(body, 'html.parser').get_text().splitlines()]
                n_pre = sum(1 for l in lines if row.match(l))
                n_body = sum(1 for l in body_lines if row.match(l))
                if n_pre == 0 and n_body >= 3:
                    lines = body_lines
                elif n_pre and n_body >= 1.3 * n_pre + 5:
                    lines = [l for l in body_lines if l.strip()]   # (paragraph gaps)
            elif word_lines:
                lines = word_lines
            elif soup.find('tr') is not None and not soup.find(['p', 'div']) and \
                    any(re.match(r'^\s*\d+\s+\S.*\d:\d\d', tr.get_text(' ')) for tr in soup.find_all('tr')[:400]):
                # Hy-Tek "HTML table" export: one text row per <tr>
                lines = [' '.join(td.get_text() for td in tr.find_all(['td', 'th'])).replace('\xa0', ' ')
                         for tr in soup.find_all('tr')]
            else:
                # If no <pre>, extract from <p> or <div> tags
                lines = []
                for tag in soup.find_all(['p', 'div', 'br']):
                    if tag.name == 'br':
                        lines.append("")
                    else:
                        lines.append(tag.get_text())
                if not lines:
                    text = soup.get_text(separator='\n')
                    lines = text.splitlines()

        # a hand-edited fixed-width page: a tab pads a line to the next
        # 8-column stop ("  7 Aimee Brooks\t\t MDI" lines up with "MDIHS")
        # (a tab typed inside a name, "Hill\t, Braydan", was kept as one
        # column: each such line keeps whichever reading puts its time where
        # the other rows' times end)
        if any('\t' in l for l in lines) and any(re.match(r'^\s*={20,}', l) for l in lines):
            from collections import Counter
            _tm = re.compile(r'\d{1,2}:\d{2}(?:\.\d+)?')
            ends = Counter(m.end() for l in lines if '\t' not in l for m in [_tm.search(l)] if m)
            if ends:
                col = ends.most_common(1)[0][0]

                def _fit(l):
                    m = _tm.search(l)
                    return abs(m.end() - col) if m else 99
                lines = [min((l.expandtabs(8), l), key=_fit) if '\t' in l else l for l in lines]

        # Metadata extraction
        meet_date = None
        meet_name = None
        is_ms_meet = False
        
        # Check for MS keywords in filename or top lines
        ms_keywords = ["ms ", "-ms-", "middle school", "junior high", " jh ", "elementary"]
        if any(x in self.file_path.lower() for x in ms_keywords):
            is_ms_meet = True
        
        # Scan first 30 lines for date and meet name
        date_patterns = [
            r'(\d{1,2})/(\d{1,2})/(\d{2,4})',  # 12/6/2025 or 12/6/25
            r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})' # December 6, 2025
        ]
        
        month_map = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
            'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
        }

        potential_dates = []

        for line in lines[:30]:
            clean = line.strip()
            if not clean: continue
            
            # Simple heuristic for meet name: look for line with name before first bracket/event
            if not meet_name and not any(re.search(pat, line) for pat in date_patterns):
                if not "===" in line and not "Licensed to" in line and len(clean) > 5:
                    meet_name = clean
                    # whole-word "MS": the Hy-Tek license line of "Wilbur Race
                    # Systems" (or any "...ms ") is not a middle-school title
                    # (a venue line - "AUBURN MIDDLE SCHOOL - AUBURN,ME" -
                    # names where a high-school meet was held, not its level)
                    if re.search(r'(?<![a-z])ms\b|-ms-|middle school|junior high|\bjh\b|elementary',
                                 clean.lower()) and not re.search(
                                     r',\s*(ME|Maine|NH)\b|\s-\s+[A-Z][A-Za-z .]+$', clean):
                        is_ms_meet = True
            
            for pat in date_patterns:
                for m in re.finditer(pat, line):
                    # Check if this line is a record line
                    # Records usually look like "KVAC Record: R 9:57" or "R 10:00"
                    is_record = any(x in line.lower() for x in ["record:", "r  ", "ht:"])
                    if is_record:
                        continue
                    
                    try:
                        found_date = None
                        if '/' in m.group(0):
                            parts = m.group(0).split('/')
                            # assume m/d/y
                            m_str = parts[0].zfill(2)
                            d_str = parts[1].zfill(2)
                            y_str = parts[2]
                            if len(y_str) == 2: y_str = "20" + y_str
                            found_date = f"{y_str}-{m_str}-{d_str}"
                        else:
                            # Month DD, YYYY
                            m_name = m.group(1).lower()[:3]
                            if m_name in month_map:
                                m_str = month_map[m_name]
                                d_str = m.group(2).zfill(2)
                                y_str = m.group(3)
                                found_date = f"{y_str}-{m_str}-{d_str}"
                        
                        if found_date:
                            # Prioritize if line contains "Meet" or "Results"
                            priority = 0
                            if any(x in line.lower() for x in ["meet", "results", "wk"]):
                                priority = 10
                            potential_dates.append((priority, found_date))
                    except:
                        pass
        
        if potential_dates:
            # Sort by priority, then take the first one
            potential_dates.sort(key=lambda x: x[0], reverse=True)
            meet_date = potential_dates[0][1]

        # Venue line (XC course identity): e.g. "Twin Brook, Cumberland, ME"
        meet_venue = None
        for line in lines[:10]:
            clean = line.strip()
            if not clean or clean == meet_name or 'hy-tek' in clean.lower() \
                    or 'licensed' in clean.lower() or clean.lower() == 'results':
                continue
            if re.search(r'length|distance|weather|temp', clean, re.I):
                continue
            if re.search(r',\s*(ME|Maine|NH)\b', clean) or re.search(
                    r'\b(Park|Brook|Course|Country Club|Rec\b|Recreation|Farm|Fairground|Golf|Trails?)\b',
                    clean):
                if not re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', clean) and len(clean) < 60:
                    meet_venue = clean
                    break
        
        # Segment into events.
        # "Team Rankings" blocks can appear MID-FILE (e.g. girls rankings
        # between the girls and boys sections), so rankings mode must end as
        # soon as a new event header appears — otherwise everything after the
        # first rankings block is silently dropped.
        events = []
        current_event = None
        in_rankings = False
        ranking_lines = []

        for i, line in enumerate(lines):
            line_clean = line.strip()
            # Check for start of a team rankings block
            if "Team Rankings" in line_clean and ("Men" in line_clean or "Women" in line_clean or "Boys" in line_clean or "Girls" in line_clean):
                in_rankings = True
                if current_event:
                    events.append(current_event)
                    current_event = None
                ranking_lines.append(line)
                continue

            # Championship files rank each class separately inside one
            # event ("CLASS A Results" ... "CLASS B Results"), places
            # restarting at 1: each section is its own race. The column
            # ruler printed above the first section is carried over.
            if current_event and not in_rankings:
                if _XC_SCORES_LINE.match(line_clean):
                    current_event['in_scores'] = True
                m_sec = _SECTION_RE.match(line_clean)
                # a Mixed race ranked by sex with no class ("Results - Women"
                # ... "Results - Men"): each half is its own race
                m_gs = None if m_sec else re.match(r'^Results\s*-\s*(Women|Men|Girls|Boys)\b(?:\s.*)?$', line_clean, re.I)
                if m_gs and not current_event.get('in_scores') and 'section' not in current_event and \
                        (current_event.get('gender') == 'Mixed' or current_event.get('gsplit')):
                    g2 = _SECTION_GENDER[m_gs.group(1).lower()]
                    if not current_event.get('gsplit'):
                        current_event['gsplit'] = True
                        current_event['gprefix'] = list(current_event['lines'])
                        current_event['gender'] = g2
                    elif g2 != current_event['gender']:
                        events.append(current_event)
                        current_event = dict(current_event, gender=g2,
                                             lines=list(current_event['gprefix']))
                    continue
                if m_sec and not current_event.get('in_scores'):
                    label = f"{m_sec.group(1).capitalize()} {m_sec.group(2)}"
                    sec_gender = _SECTION_GENDER.get((m_sec.group(3) or '').lower())
                    if 'section' not in current_event:
                        current_event['section'] = label
                        current_event['prefix'] = list(current_event['lines'])
                        if sec_gender:
                            current_event['gender'] = sec_gender
                    elif (current_event['section'], current_event['gender']) != \
                            (label, sec_gender or current_event['gender']):
                        events.append(current_event)
                        current_event = dict(current_event, section=label,
                                             lines=list(current_event['prefix']))
                        if sec_gender:
                            current_event['gender'] = sec_gender
                    continue

            # Header pattern: "Event 1  Girls 4x800 Meter Relay" or "Girls 55 Meter Dash"
            m_event = re.search(r'Event\s+\d+\s+(Girls|Boys|Women|Men|Mixed)\s+(.*)', line_clean, re.IGNORECASE)
            # college exports abbreviate: "Event 1  M 8k Run CC  Varsity"
            if not m_event:
                m_event = re.search(r'^Event\s+\d+\s+([MWF])\s+(\S.*)', line_clean)
            # gender after the distance: "Event 6  4k Run CC Youth Boys"
            m_late = None if m_event else re.match(
                r'^Event\s+\d+\s+(\S.*?)\s*\b(Girls|Boys|Women|Men)\b\s*(.*)$', line_clean, re.I)
            if m_late:
                m_event = re.match(r'(\S+)\s+(.*)', f"{m_late.group(2)} "
                                   f"{(m_late.group(1) + ' ' + m_late.group(3)).strip()}")
            # Support Division headers ("Girls 50 Meter Dash 5th/6th grade") and
            # prefixed multi-event legs ("Indoor Pentathlon: #5 Girls 800 Meter Run")
            m_no_event = re.match(r'^\s*(?:[\w .]{0,30}:\s*#?\d*\s*)?(Girls|Boys|Women|Men|Mixed)\s+(.*)', line_clean, re.IGNORECASE)
            # RaceTab: "Varsity Boys Three Mile Run Finals" over a ruler
            if not m_no_event and not re.search(r'team\s+scores?', line_clean, re.I):
                m_no_event = re.match(r'^((?:Varsity|JV|Junior Varsity|Freshman|Open|Reserve|Middle School)'
                                      r'\s+)(Girls|Boys|Women|Men)\s+(.*?)(?:\s+Finals)?$', line_clean, re.I)
                if m_no_event:
                    m_no_event = re.match(r'(\S+)\s+(.*)', f"{m_no_event.group(2)} "
                                          f"{_number_words(m_no_event.group(3))} {m_no_event.group(1).strip()}")
            # USATF JO Hy-Tek: "2000 Meter Run CC 8 & Under Division Girls"
            if not m_no_event:
                m_late = re.match(r'^\s*(\d[\w .&/-]*?\b(?:Run|CC|XC)\b[\w .&/-]*?)\s+(Girls|Boys|Women|Men)\s*$',
                                  line_clean, re.I)
                if m_late:
                    m_no_event = re.match(r'(\S+)\s+(.*)', f"{m_late.group(2)} {m_late.group(1).strip()}")

            is_header = False
            gender = ""
            event_name = ""

            if m_event:
                is_header = True
                gender = m_event.group(1).strip()
                gender = {'M': 'Boys', 'W': 'Girls', 'F': 'Girls'}.get(gender, gender)
                if len(gender) > 1:
                    gender = gender.capitalize()
                if gender.lower() == "women": gender = "Girls"
                if gender.lower() == "men": gender = "Boys"
                event_name = m_event.group(2).strip()
            elif m_no_event and "Team Rankings" not in line_clean:
                # Require separator line for no-event-number headers to avoid false positives
                # (bib-first exports put the column ruler between the two)
                nxt = next((l for l in lines[i + 1:i + 4] if l.strip()), '')
                if (i + 1 < len(lines) and "====" in lines[i+1]) or (
                        i + 2 < len(lines) and "====" in lines[i + 2]
                        and re.search(r'\bName\b', lines[i + 1])
                        and re.search(r'\b(School|Team)\b', lines[i + 1])) or (
                        # "Boys 5k" straight over Hy-Tek rows (sub5 .txt pages)
                        len(line_clean) < 40 and not events and current_event is None
                        and re.match(r'^\s*\d{1,4}\s+\S.*\d:\d\d', nxt)
                        and not any(re.search(r'\bname\b', l, re.I) for l in lines[:i])
                        and re.search(r'\d\s*(k|km|mile)|run|race|cc\b|xc\b', line_clean, re.I)):
                    is_header = True
                    gender = m_no_event.group(1).strip()
                    if gender.lower() == "women": gender = "Girls"
                    if gender.lower() == "men": gender = "Boys"
                    event_name = m_no_event.group(2).strip()

            # A Hy-Tek column ruler with no event line anywhere above it
            # ("Individual Results" / Name Year Team Finals): one race, its
            # gender from the file name
            if not is_header and not events and current_event is None \
                    and re.search(r'\bName\b', line_clean) and re.search(r'\b(School|Team)\b', line_clean) \
                    and re.search(r'\b(Finals|Time)\b', line_clean) \
                    and any('====' in l for l in lines[max(0, i - 1):i + 2]):
                fn = self.file_path.lower()
                g = 'Girls' if re.search(r'girl|women', fn) else 'Boys' if re.search(r'boy|\bmen', fn) else None
                # (an "All Classes Combined" list re-ranks class races posted
                # on their own: not a race)
                if g and (getattr(self, 'allow_aggregate', False) or
                          not re.search(r'combin|new\s+england\s+qualif', ' '.join(lines[:i]) + fn, re.I)):
                    is_header, gender, event_name = True, g, 'Run CC'
                    lines[i - 1:i] = lines[i - 1:i]  # (no-op: keep the ruler with the event)

            # "....Event 2  Boys 1.9 Mile Run CC" is Hy-Tek's page-break
            # continuation of the current event, not a new race
            if is_header and current_event and line_clean.startswith('..') \
                    and current_event['original_event_name'] == event_name.strip() \
                    and current_event['gender'] == gender:
                continue

            if is_header:
                in_rankings = False  # rankings block ends at the next event
                if current_event:
                    events.append(current_event)

                # Normalize the event name
                normalized_name = self.normalize_event_name(event_name)

                current_event = {
                    "gender": gender,
                    "event_name": normalized_name,
                    "original_event_name": event_name, # Keep original for reference
                    "lines": [],
                    "is_relay": any(x in normalized_name.lower() or x in event_name.lower() for x in ["relay", "4x"]),
                    "is_ms": is_ms_meet
                }
            elif in_rankings:
                ranking_lines.append(line)
            elif current_event:
                current_event["lines"].append(line)
        if current_event:
            events.append(current_event)
            
        parsed_events = []
        for ev in events:
            results = self.parse_event_block(ev)
            if results:
                parsed_events.append({
                    "event": ev["event_name"],
                    "gender": ev["gender"],
                    "is_relay": ev["is_relay"],
                    "results": results
                })
                if ev.get("section"):
                    parsed_events[-1]["section"] = ev["section"]

        # A Mixed race whose rows carry sex ("W17", "M40") is two races
        # for the store: split it by the rows' own sex, order kept.
        split = []
        for pe in parsed_events:
            rs = pe['results']
            bare = pe['gender'] == 'Mixed' and sum(
                1 for r in rs if re.match(r'[MWFB]\s+\S', r.get('school') or '')) >= 0.8 * len(rs)
            for r in rs:
                if r.get('sex') or pe['is_relay']:
                    continue
                m1 = re.match(r'([MWFB])(\d{1,2})\s+(\S.*)$', r.get('school') or '') or (
                    bare and re.match(r'([MWFB])()\s+(\S.*)$', r.get('school') or ''))
                m2 = re.search(r'\s+([MWFB])(\d{1,2})$', r.get('athlete') or '')
                if m1:
                    r['school'] = m1.group(3)
                if m2:
                    r['athlete'] = r['athlete'][:m2.start()].strip()
                mm = m1 or m2
                if mm:
                    r['sex'] = 'Girls' if mm.group(1) in 'WF' else 'Boys'
                    r['grade'] = normalize_grade(mm.group(2) or '')
            sx = [r.get('sex') for r in rs]
            sx = [r.get('sex') for r in rs]
            # (a sex column that says "M" for every runner of a mixed race
            # carries no information: leave the race for the school-suffix split)
            if pe['gender'] == 'Mixed' and len({x for x in sx if x}) == 1:
                for r in rs:
                    r.pop('sex', None)
            if pe['gender'] == 'Mixed' and rs and sum(1 for x in sx if x) >= 0.8 * len(rs) \
                    and len({x for x in sx if x}) > 1:
                try:
                    from backend.parsers.namegender import name_gender
                except ImportError:
                    from parsers.namegender import name_gender
                for r in rs:  # "Jamie Bell  M  Incredi-Bells": a bare M/W
                    if not r.get('sex'):
                        m1 = re.match(r'([MWFB])\s+(\S.*)$', r.get('school') or '')
                        if m1:
                            r['school'] = m1.group(2)
                            r['sex'] = 'Girls' if m1.group(1) in 'WF' else 'Boys'
                        else:
                            r['sex'] = name_gender(r.get('athlete'))
                for g in ('Girls', 'Boys', None):
                    part = [r for r in rs if r.get('sex') == g]
                    if part:
                        split.append(dict(pe, gender=g or 'Mixed', results=part))
                continue
            split.append(pe)
        parsed_events = split

        # A page break that repeats the event header without the "...."
        # continuation mark splits one race in two; the second part's
        # places carry on from the first (51 after 50), a new race's
        # restart at 1.
        merged = []
        for pe in parsed_events:
            prev = merged[-1] if merged else None
            if prev and not pe['is_relay'] and \
                    (prev['event'], prev['gender'], prev.get('section')) == \
                    (pe['event'], pe['gender'], pe.get('section')):
                lp = [r.get('place') for r in prev['results'] if r.get('place')]
                fp = [r.get('place') for r in pe['results'] if r.get('place')]
                if lp and fp and fp[0] > 1 and fp[0] >= lp[-1]:
                    prev['results'].extend(pe['results'])
                    continue
            merged.append(pe)
        parsed_events = merged

        # Parse official team rankings from the collected rankings lines only
        # (they no longer run to EOF, so relay rows can't contaminate them)
        team_rankings = self.parse_team_rankings(ranking_lines, 0 if ranking_lines else None)

        return {
            "meet_name": meet_name,
            "date": meet_date,
            "venue": meet_venue,
            "events": parsed_events,
            "team_rankings": team_rankings
        }

    @staticmethod
    def parse_team_rankings(lines, start_idx):
        """Parse official team rankings from the 'Team Rankings' section.

        Returns a list of dicts, one per gender block:
            [
                {
                    "gender": "Girls" | "Boys",
                    "events_scored": int,
                    "teams": [{"rank": int, "team": str, "score": float}, ...]
                },
                ...
            ]
        """
        if start_idx is None:
            return []

        rankings = []
        current_block = None

        for line in lines[start_idx:]:
            stripped = line.strip()

            # Detect ranking header: "Women - Team Rankings - 19 Events Scored"
            m_header = re.match(
                r'(Women|Men|Girls|Boys)\s*-\s*Team Rankings\s*-\s*(\d+)\s*Events?\s*Scored',
                stripped, re.IGNORECASE
            )
            if m_header:
                gender = m_header.group(1).strip()
                if gender.lower() == 'women':
                    gender = 'Girls'
                elif gender.lower() == 'men':
                    gender = 'Boys'
                current_block = {
                    'gender': gender,
                    'events_scored': int(m_header.group(2)),
                    'teams': []
                }
                rankings.append(current_block)
                continue

            if not current_block:
                continue

            # Skip separator lines
            if '=====' in stripped or not stripped:
                continue

            # Parse team ranking entries.  HY-TEK formats them as:
            #   "    1) Brunswick High School      215        2) Medomak Valley High Schoo 110"
            # There can be 1 or 2 entries per line.  Team names may be
            # truncated, leaving only 1 space before the score.  Scores
            # can have decimals (e.g. "247.33").
            # Strategy: split the line at "N) " boundaries to isolate
            # individual entries, then extract rank, team, and score.
            entries = re.split(r'(?=\d+\)\s)', stripped)
            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue
                m = re.match(r'(\d+)\)\s+(.*?)\s+(\d+(?:\.\d+)?)\s*$', entry)
                if m:
                    rank = int(m.group(1))
                    team = m.group(2).strip()
                    score = float(m.group(3))
                    current_block['teams'].append({
                        'rank': rank,
                        'team': team,
                        'score': score
                    })

        return rankings

    _HL_ROW = re.compile(r'^\s*\*?(\d{1,4})\s+(?=\S)')  # "*1" marks a qualifier
    # finish/pace times: "19:26.22", "6:15.4", "1:02:13.5"; Hy-Tek prefixes
    # judged ties with J and exhibition with x, suffixes records with R/#/*
    _HL_TIME = re.compile(
        r'(?<!\S)([JjXx*]?)(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d{1,3})?)([A-Za-z*#@$!%&]{0,2})(?!\S)')
    _HL_NOPLACE = re.compile(r'^\s*--\s+(?=[A-Za-z])')
    _HL_STATUS = re.compile(r'(?<!\S)(DNF|DNS|DQ|SCR)(?!\S)')
    _HL_GRADE = re.compile(r'(?<!\S)(\d{1,2}|FR|SO|JR|SR|Fr|So|Jr|Sr|--)(?!\S)')

    def parse_headerless_block(self, ev):
        """Individual results with no column-header row:

              1 Henri Rivard              12 Marshwood             16:13.74    1
              1 Andrew Chingos            SO Brunswick         6:15.4   19:26.22    1

        Hy-Tek pads every field to a fixed width, so the grade column sits at
        the same position on every row; it is located by vote and the name /
        school split there. The finish time is the LAST time on the row:
        some exports print a per-mile pace (or splits) before it. After it
        come team-score places and notes ("19:34.20*   1  *course record")."""
        rows = []
        for line in ev["lines"]:
            if not line.strip() or '===' in line:
                continue
            m = self._HL_ROW.match(line) or self._HL_NOPLACE.match(line)
            if not m:
                continue
            times = list(self._HL_TIME.finditer(line, m.end()))
            if times:
                fin = times[-1]
                body_end = times[0].start()
                mark, exhib = fin.group(2), fin.group(1) in ('x', 'X')
                after = fin.end()
            else:
                # unplaced finishers: " -- Anna Klingle  11 Brunswick   DNF   3"
                st = self._HL_STATUS.search(line, m.end())
                if not st:
                    continue
                body_end, mark, exhib = st.start(), st.group(1).upper(), False
                after = st.end()
            # printed place ("32" twice marks a tie) and, after the finish,
            # the runner's team-score place (blank for non-scorers)
            place = int(m.group(1)) if m.re is self._HL_ROW else None
            tp = re.match(r'\s+(\d{1,3})(?=\s|$)', line[after:])
            if tp and ev.get('heat_col'):   # "16:13.34   2   1": H# first
                tp = re.match(r'\s+(\d{1,3})(?=\s|$)', line[after + tp.end():])
            team_place = int(tp.group(1)) if tp else None
            if not re.search(r'[A-Za-z]', line[m.end():body_end]):
                continue
            start = m.end()
            if ev.get('bib_first'):  # "  1   654  Eastman, Silas ..."
                mb = re.match(r'#?\d+\s+(?=[A-Za-z])', line[start:])
                if mb:
                    start += mb.end()
            rows.append((line, start, body_end, (mark, exhib, place, team_place)))
        if len(rows) < 3:
            return self._untimed_rows(ev)

        # vote for the grade column (right edge: "9" and "12" right-align)
        from collections import Counter
        votes = Counter()
        for line, start, body_end, _ in rows:
            for g in self._HL_GRADE.finditer(line, start, body_end):
                if g.start() > start:  # never the first name token
                    votes[g.end()] += 1
        grade_end = None
        if votes:
            col, n = votes.most_common(1)[0]
            if n >= 0.5 * len(rows):
                grade_end = col
        school_col = None
        if grade_end is None:
            gaps = Counter()
            for line, start, body_end, _ in rows:
                g = re.search(r'\S\s{2,}(?=\S)', line[start:body_end])
                if g:
                    gaps[start + g.end()] += 1
            if gaps:
                school_col = gaps.most_common(1)[0][0]

        results = []
        # the number after a cross-country finish is the team-score place
        # (after a track mark it is meet points)
        xc_event = _is_xc_event(ev.get('original_event_name') or ev.get('event_name') or '')
        for line, start, body_end, fin in rows:
            grade = ''
            if grade_end is not None:
                gm = None
                for g in self._HL_GRADE.finditer(line, start, body_end):
                    if g.start() > start and abs(g.end() - grade_end) <= 1 \
                            and (gm is None or g.end() == grade_end):
                        gm = g
                if gm is None:
                    # hand-edited rows and mis-encoded names shift the
                    # columns ("Ethan Roach   *       FR Old Town"): accept a
                    # grade anywhere once it stands apart from the name
                    for g in self._HL_GRADE.finditer(line, start, body_end):
                        if g.start() > start and g.group(1) != '--' \
                                and line[g.start() - 2:g.start()] == '  ':
                            gm = g
                            break
                if gm is None:
                    # a long name squeezes the gap to one space: "Donahue
                    # Hanscom, Mike SO MTA" - the grade follows "Last, First"
                    mc = re.compile(r'[^,]*,\s*\S+(?: \S+)?? ((?:FR|SO|JR|SR|[5-9]|1[0-2]))(?= +[A-Za-z])')
                    mm = mc.match(line, start)
                    if mm and mm.end(1) < body_end:
                        gm = re.compile(r'\S+').search(line, mm.start(1))
                if gm:
                    name, grade = line[start:gm.start()], gm.group(1) if gm.re is self._HL_GRADE else gm.group(0)
                    school = line[gm.end():body_end]
                else:
                    # blank or garbled ("S0") grade cell: the grade field is
                    # the 2 columns ending at grade_end
                    cut = grade_end - 2
                    name, school = line[start:cut], line[grade_end:body_end]
                    if line[grade_end:grade_end + 1].strip():
                        school = line[cut:body_end]  # school starts in the cell
                    gap = re.search(r'\S\s{2,}(?=\S)', line[start:body_end])
                    if line[cut - 1:cut].strip() or (
                            gap and start + gap.end() < cut - 1 and line[cut - 1:cut + 1].strip()):
                        # the name ran past the field, or a drifted PDF row
                        # starts its school left of the grade cell ("chicoine,
                        # alex    Elhs Boys X-Country"): names never hold a
                        # double space, so the first one ends the name
                        parts = re.split(r'\s{2,}', line[start:body_end].strip(), 1)
                        if len(parts) != 2:
                            continue
                        name, school = parts
            elif school_col is not None and school_col < body_end \
                    and not line[school_col - 1:school_col].strip():
                name, school = line[start:school_col], line[school_col:body_end]
                inner = re.search(r'\S(\s{2,})\S', name.strip())
                if inner:  # drifted row: the school began before the column
                    body = line[start:body_end].strip()
                    name, school = re.split(r'\s{2,}', body, 1)
            else:
                parts = re.split(r'\s{2,}', line[start:body_end].strip(), 1)
                if len(parts) != 2:
                    # "Donahue Hanscom, Mike SO MTA": single spaces only
                    body = line[start:body_end].strip()
                    mm = re.match(r'([^,]*,\s*\S+(?: \S+)??) (FR|SO|JR|SR|[5-9]|1[0-2]) +([A-Za-z].*)$',
                                  body) or re.match(  # "Nicholas Dieffenbacher-Krall FR Old Town"
                        r'([A-Z][\w\'.-]*(?: [A-Z][\w\'.-]*)+?) (FR|SO|JR|SR) +([A-Za-z].*)$', body)
                    if not mm:
                        continue
                    parts = [mm.group(1), mm.group(3)]
                    grade = mm.group(2)
                name, school = parts
            # stray annotation marks ("Ethan Roach   *")
            name = re.sub(r'(?:\s+[*#]+)+$', '', name.strip())
            name = re.sub(r'^#\d+\s+', '', name)  # bib: "#379 Martin, Josiah"
            # PDF text drifts cells off the voted grade column: a grade
            # left on either side of the split ("Merrill, Kristen   SO" |
            # "SR Mt. Ararat High School")
            school = school.strip()
            if not grade:
                # (an age column - 16, 17 - is cut off the same way; it
                # normalises to no grade)
                mg = re.match(r'(FR|SO|JR|SR|\d{1,2}(?:st|nd|rd|th|t)?)\s+(?=[A-Za-z])', school)
                if mg:
                    grade, school = mg.group(1), school[mg.end():]
                else:
                    mg = re.search(r'\s{2,}(FR|SO|JR|SR|\d{1,2})$', name)
                    if mg:
                        grade, name = mg.group(1), name[:mg.start()]
            name = re.sub(r'\s*-\s*(?:\d|V|JV)$', '', name)  # "Mayer, Lucas - 5"
            school = re.sub(r'^(?:[*#]+\s+)+', '', school.strip())
            if not name or not school or not re.search(r'[A-Za-z]', school):
                continue
            entry = {
                "athlete": name,
                "school": school,
                "result": fin[0],
                "grade": normalize_grade(grade),
                "type": "Finals",
            }
            if fin[1]:
                entry["exhibition"] = True
            if fin[2] is not None:
                entry["place"] = fin[2]
            if fin[3] is not None and xc_event:
                entry["team_place"] = fin[3]
            if ev.get("is_ms") and not entry["grade"]:
                entry["grade"] = "MS"
            results.append(entry)
        return results

    _UNTIMED = re.compile(r'^\s*(\d{1,4})\s+(\S.*?\S)\s{2,}(\S.*?)(?:\s{2,}(\d{1,3}))?\s*$')

    def _untimed_rows(self, ev):
        """A cross-country race posted with places and team points but no
        times ("  2 Mann, Blake   York Middle School   1"): the finish order
        is the result. Rows keep an empty mark (nothing to store as a
        performance) but their place and team place, so the team scores
        still check. Only when nearly every numbered row is untimed."""
        if not _is_xc_event(ev.get('original_event_name') or ev.get('event_name') or ''):
            return []
        lines = ev['lines']
        cut = next((i for i, l in enumerate(lines) if re.search(r'team\s+scores?', l, re.I)), len(lines))
        numbered = [l for l in lines[:cut] if re.match(r'^\s*\d{1,4}\s+[A-Za-z]', l)]
        if len(numbered) < 5 or any(self._HL_TIME.search(l) for l in numbered):
            return []
        out = []
        for l in numbered:
            m = self._UNTIMED.match(l)
            if not m:
                continue
            school = re.sub(r'^(?:J?V)\s+', '', m.group(3).strip())  # "V   FR Cony"
            grade = ''
            mg = re.match(r'(FR|SO|JR|SR|\d{1,2})\s+(?=[A-Za-z])', school)
            if mg:
                grade, school = mg.group(1), school[mg.end():]
            if re.search(r'\d', re.sub(r"\s(?:(?:19|20)\d\d|'\d{1,2})$", '', school)):
                continue        # (a club name may end in its year: "Brunswick CC 2011")
            name = re.sub(r'\s*-\s*(?:\d|V|JV)$|\s+J?V$', '', m.group(2).strip())
            r = {'athlete': name, 'school': school, 'result': '',
                 'grade': normalize_grade(grade), 'type': 'Finals', 'place': int(m.group(1))}
            if m.group(4):
                r['team_place'] = int(m.group(4))
            out.append(r)
        if len(out) < 0.9 * len(numbered):
            return []
        return out

    def parse_event_block(self, ev):
        lines = ev["lines"]
        is_relay = ev["is_relay"]
        
        name_idx = -1
        school_idx = -1
        anchor_col = -1
        stop_col = -1 # Column index to stop reading (e.g. before H#)
        anchor_type = None 
        header_row_idx = -1
        
        yr_idx = -1
        for i, line in enumerate(lines):
            if not is_relay:
                if "Name" in line and ("School" in line or "Team" in line):
                    name_idx = line.find("Name")
                    school_idx = line.find("School") if "School" in line else line.find("Team")
                    yr_idx = line.find("Yr") if "Yr" in line else line.find("Year")
                    if yr_idx == -1 and re.search(r'\bAge\b', line):
                        yr_idx = re.search(r'\bAge\b', line).start()  # "W17" / "M40"
                    header_row_idx = i
            else:
                if ("School" in line or "Team" in line) and ("Finals" in line or "Prelims" in line or "Seed" in line):
                    school_idx = line.find("School") if "School" in line else line.find("Team")
                    header_row_idx = i

            if header_row_idx != -1:
                if "Finals" in line:
                    anchor_col = line.find("Finals") + len("Finals")
                    anchor_type = "Finals"
                elif "Prelims" in line:
                    anchor_col = line.find("Prelims") + len("Prelims")
                    anchor_type = "Prelims"
                elif "Seed" in line:
                    anchor_col = line.find("Seed") + len("Seed")
                    anchor_type = "Seed"
                elif re.search(r'\bTime\b', line):
                    # bib-first exports: "Comp#  Name  School  Time Points"
                    anchor_col = re.search(r'\bTime\b', line).end()
                    anchor_type = "Finals"
                
                # Check for columns to the right of the result to establish a boundary
                # "Wind" appears immediately after the mark in HY-TEK wind-legal meets;
                # cutting there prevents wind readings from being picked up as marks.
                stop_col = -1
                right_headers = ["Wind", "H#", "Points", "Pts"]
                if anchor_col != -1:
                    for h in right_headers:
                        h_idx = line.find(h, anchor_col)
                        if h_idx != -1:
                            stop_col = h_idx
                            break
                break
                
        if header_row_idx == -1:
            # Hy-Tek .txt exports (most XC championships on sub5) print no
            # "Name Year School" ruler at all; read the columns off the rows
            # (a block with a "School ... Finals" ruler is a team event, e.g.
            # a medley relay not named "Relay": not header-less)
            if not is_relay and not any(
                    re.search(r'\b(School|Team)\b.*\b(Finals|Prelims|Seed|Time)\b', l)
                    for l in lines):
                return self.parse_headerless_block(ev)
            return []

        # XC exports with a per-mile pace column ("Avg Mile  Finals"): in
        # PDF text the cells drift off the header positions and the anchor
        # lands on the pace. The finish is always the last time on the row.
        # Bib-first exports ("Comp#  Name  School  Time Points") drift off
        # the header positions in PDF text the same way.
        hdr = lines[header_row_idx]
        bib_first = bool(re.search(r'Comp\s*#|\bBib\b', hdr, re.I))
        if not is_relay and (bib_first or re.search(
                r'Avg\.?\s*Mile|\bPace\b|Per\s*Mile|Min/Mi', hdr, re.I)):
            rows = self.parse_headerless_block(
                dict(ev, lines=lines[header_row_idx + 1:], bib_first=bib_first,
                     heat_col=bool(re.search(r'H#', hdr))))
            if rows:
                return rows

        events = [] # Renamed from event_results
        current_relay = None
        xc_event = _is_xc_event(ev.get('original_event_name') or ev.get('event_name') or '')
        start_idx = header_row_idx + 1
        if start_idx < len(lines) and "====" in lines[start_idx]:
            start_idx += 1
            
        for line in lines[start_idx:]:
            if not line.strip() or "---" in line: continue
            
            if "Team Rankings" in line:
                 break
            
            # Skip lines that look like Team Rankings items (e.g., "1) York High School 48")
            # BUT only for individual events. Relay runner lines look like "1) Name..."
            if not is_relay and re.match(r'^\s*\d+\)\s+[A-Za-z]', line):
                continue
            
            if not is_relay:
                # Check for split line pattern: "36.264 (36.264)" or "1:11.703 (35.439)"
                # This must happen before ignoring short lines, as splits can be shorter than the full result row
                split_matches = re.findall(r'\(((?:\d+:)?\d+\.\d+)\)', line)
                if split_matches and len(split_matches) >= 1:
                    # Verify line looks like a series of splits (mostly numbers and parens)
                    # Simple heuristic: if it has multiple parens or matches the specific cumulative (split) structure
                    if re.search(r'(?:\d+:)?\d+\.\d+\s+\((?:\d+:)?\d+\.\d+\)', line):
                         if events: # Renamed from event_results
                            last_entry = events[-1] # Renamed from event_results
                            if "splits" not in last_entry:
                                last_entry["splits"] = []
                            last_entry["splits"].extend(split_matches)
                         continue

                # Individual Logic
                if len(line) < school_idx: continue
                potential_name_area = line[:school_idx].strip()
                if not potential_name_area or potential_name_area.lower() in ["finals", "preliminaries", "prelims"]:
                    continue
                
                # Default right boundary if no stop column found
                right_boundary = stop_col if stop_col != -1 else anchor_col + 12

                if len(line) >= anchor_col - 5:
                    # Truncate line at the right boundary to avoid reading Heat# or Points
                    sub = line[:right_boundary].rstrip()
                    if sub:
                        raw_candidate = sub.split()[-1]
                        res_val = raw_candidate

                        # FIX: Check for smashed results (e.g. "19-05.5019-01") where Seed + Result merged
                        # If it fits pattern: [digits/.-]+ [digits/.-]+
                        # We try to split it.
                        if len(raw_candidate) > 8 and re.search(r'\d', raw_candidate):
                            # Look for a digit transition that signifies a new number starting
                            # e.g. "5019" -> "50" "19". 
                            # But formatted marks are X-Y.Z.
                            # Regex: Look for a boundary where a new number clearly starts?
                            # Hard to do reliably without context.
                            # Alternative: Use anchor_col to re-slice the line if possible.
                            pass

                        # Improved Logic: Search Zone around Anchor Column
                        if anchor_col != -1:
                             # Ideally, the result starts near anchor_col
                             # Find token closest to anchor_col
                             parts = sub.split()
                             best_part = None
                             min_dist = 999
                             
                             curr_idx = 0
                             for p in parts:
                                 # Find location of p in sub
                                 loc = sub.find(p, curr_idx)
                                 if loc != -1:
                                     curr_idx = loc + len(p)
                                     # Distance from start of token to anchor_col
                                     dist = abs(loc - anchor_col)
                                     # Result usually starts AT or BEFORE anchor_col (since anchor is "Finals")
                                     # "Finals" header is often right-aligned or centered? No, usually Left.
                                     
                                     if re.search(r'\d', p) or p.upper() in ["DQ", "DNS", "NH", "FOUL", "DNF"]:
                                         if dist < min_dist:
                                            min_dist = dist
                                            best_part = p
                             
                             if best_part and min_dist < 20:
                                 res_val = best_part
                        
                        # Handle Exhibition marks (prefixed with X) — keep the
                        # mark but flag it so meet scoring can exclude it
                        is_exhibition = False
                        if res_val.upper().startswith('X') and len(res_val) > 1:
                             res_val = res_val[1:]
                             is_exhibition = True

                        # Check if result looks valid
                        is_res_numeric = bool(re.search(r'\d', res_val))
                        is_res_standard = res_val.upper() in ["DQ", "FOUL", "NH", "NM", "DNS", "DNF", "SCR"]
                        
                        if is_res_numeric or is_res_standard:
                            res_pos = line.rfind(res_val, 0, right_boundary + 2)
                            
                            # Try splitting truncated line to avoid Heat# or Points
                            # We split by 2+ spaces. 
                            parts = [p.strip() for p in re.split(r'\s{2,}', sub) if p.strip()]
                            
                            # Usually: [Rank], Name, [Grade], School, Mark, [Wind], [H#]
                            # Identify result index by looking for the first mark-like token
                            # scanning from the right but skipping wind readings and heat numbers.
                            # Wind readings have exactly one decimal place and abs value <= 9.9
                            # (e.g. "0.7", "-1.4", "+2.2").  Performance marks always have two
                            # decimal places ("14.56"), a colon ("1:23.45"), or a feet-inches
                            # hyphen ("33-04.25"), so the one-decimal test is a reliable filter.
                            def _is_wind_reading(token):
                                t = token.strip()
                                if t.upper() in ('NWI', '+NWI', 'NWI+'):
                                    return True
                                t = re.sub(r'[a-zA-Z#]', '', t).strip()
                                if re.match(r'^[+-]?\d{1,2}\.\d$', t):
                                    try:
                                        return abs(float(t)) <= 9.9
                                    except ValueError:
                                        pass
                                return False

                            res_idx = -1
                            for k in range(len(parts)-1, 0, -1):
                                p = parts[k]
                                is_mark_like = ((re.search(r'\d', p) and ('.' in p or ':' in p or '-' in p))
                                                or p.upper() in ["DQ", "NH", "NM", "DNS", "DNF", "FOUL", "SCR"])
                                if not is_mark_like:
                                    continue
                                if _is_wind_reading(p):
                                    continue
                                res_idx = k
                                break
                            
                            if res_idx != -1:
                                res_val = parts[res_idx]
                                # School/Name boundary depends on where the res_val is in the original line
                                res_pos = line.find(res_val, name_idx + 1)
                                res_end = res_pos + len(res_val) if res_pos >= 0 else -1
                                
                                # Use anchor_col and school_idx to try to split Name/School
                                grade_val = ""
                                row_school_idx = school_idx
                                if yr_idx != -1 and yr_idx > name_idx and yr_idx < school_idx:
                                    name_val = line[name_idx:yr_idx].strip()
                                    grade_val = line[yr_idx:school_idx].strip()
                                    # a name longer than its field pushes the
                                    # year and school right ("Nicholas
                                    # Dieffenbacher-Krall FR Old Town")
                                    if yr_idx > 0 and line[yr_idx - 1:yr_idx + 1].strip() == line[yr_idx - 1:yr_idx + 1] \
                                            and line[yr_idx - 1].isalpha():
                                        mo = re.match(r'\s*(\S.*?\S)\s+(FR|SO|JR|SR|\d{1,2})\s+(?=[A-Za-z])',
                                                      line[name_idx:res_pos])
                                        if mo:
                                            name_val, grade_val = mo.group(1), mo.group(2)
                                            row_school_idx = name_idx + mo.end() + 5
                                else:
                                    name_val = line[name_idx:school_idx].strip()

                                # Clean name (remove leading rank/number)
                                name_val = re.sub(r'^[\s#\-]*\d+[\s.\-]*', '', name_val).strip()
                                # Clean trailing grade numbers if they leaked (e.g. "Adams, Aaron 10")
                                name_val = re.sub(r'\s+\d+$', '', name_val).strip()

                                # SKIP: If name_val is a status keyword (happens in field event series)
                                if name_val.upper() in ["FOUL", "SCR", "NH", "NM", "DNS", "DNF", "DQ", "ND", "NT", "X"]:
                                    continue
                                
                                # SKIP: If name_val looks like a mark (digits + separators)
                                # ("Verhey, Jake-1": a runner-order tag is not a mark)
                                if re.search(r'\d', name_val) and (
                                        not re.search(r'[A-Za-z]{2}', name_val)
                                        or re.search(r'\d[:.]\d', name_val)):
                                    continue
                                # team-order / varsity tags on the name:
                                # "Verhey, Jake-1", "Deveau, Adam - V"
                                name_val = re.sub(r'\s*-\s*(?:\d|V|JV)$', '', name_val)
                                
                                # Extract school
                                area_start = max(0, row_school_idx - 5)
                                # (not inside a name filling its field:
                                # "Elizavyetta Bachkousk    Tripp Middle School")
                                while 0 < area_start < row_school_idx and line[area_start - 1:area_start + 1].isalpha():
                                    area_start += 1
                                school_area = line[area_start:res_pos]
                                m_school = re.search(r'\S', school_area)
                                if m_school:
                                    school_raw = school_area[m_school.start():].strip()
                                    if grade_val and school_raw.startswith(grade_val + " "):
                                        school_raw = school_raw[len(grade_val):].strip()
                                    school_val = re.sub(r'^\d+\s+', '', school_raw).strip()
                                    # Take only the first part if it splits by large gaps
                                    school_val = re.split(r'\s{2,}', school_val)[0].strip()
                                    # later PDF pages drift right: the year
                                    # cell lands at the start of the school
                                    mg = re.match(r'(FR|SO|JR|SR|\d{1,2})\s+(?=[A-Za-z])', school_val)
                                    if mg and not grade_val:
                                        grade_val, school_val = mg.group(1), school_val[mg.end():]
                                else:
                                    school_val = "Unknown"

                                # Strip trailing wind reading before cleaning
                                # (e.g. "14.02q -0.9" or "12.57 NWI" when single-space separated)
                                res_val = re.sub(r'\s+(?:NWI\+?|[+-]?\d\.\d)\s*$', '', res_val, flags=re.IGNORECASE).strip()

                                original_res = res_val
                                is_standard = res_val.upper() in ["DQ", "FOUL", "NH", "NM", "DNS", "DNF", "SCR"]
                                is_numeric = bool(re.match(r'^[0-9:.-]+$', res_val))

                                warnings = []
                                if not (is_standard or is_numeric):
                                    cleaned = re.sub(r'[^0-9:.-]', '', res_val)
                                    if cleaned:
                                        res_val = cleaned
                                        warnings.append(f"Original result: {original_res}")
                                    else:
                                        warnings.append(f"Result contains unusual characters: {original_res}")

                                # NEW: Check for numbers in Athlete/School
                                if re.search(r'\d', name_val):
                                    warnings.append(f"Athlete name contains numbers: {name_val}")
                                if re.search(r'\d', school_val):
                                    warnings.append(f"School name contains numbers: {school_val}")
                                
                                entry = {
                                    "athlete": name_val,
                                    "school": school_val,
                                    "result": res_val,
                                    "grade": normalize_grade(grade_val),
                                    "type": anchor_type
                                }
                                # open / alumni races print sex+age: "W17"
                                msx = re.fullmatch(r'([MWFB])(\d{1,2})?', grade_val)
                                if msx:
                                    entry["sex"] = 'Girls' if msx.group(1) in 'WF' else 'Boys'
                                    # "W7": sex and grade in one cell (an age
                                    # past 12 normalises to no grade)
                                    entry["grade"] = normalize_grade(msx.group(2) or '')
                                if is_exhibition:
                                    entry["exhibition"] = True
                                mpl = re.match(r'\s*\*?(\d{1,4})\s', line)
                                if mpl:
                                    entry["place"] = int(mpl.group(1))
                                if xc_event and res_end > 0:
                                    tp = re.match(r'\s+(\d{1,3})(?=\s|$)', line[res_end:])
                                    if tp and 'H#' in lines[header_row_idx]:
                                        tp = re.match(r'\s+(\d{1,3})(?=\s|$)', line[res_end + tp.end():])
                                    if tp:
                                        entry["team_place"] = int(tp.group(1))
                                if ev.get("is_ms") and not entry["grade"]:
                                    entry["grade"] = "MS"
                                
                                if warnings: entry["warnings"] = warnings
                                if name_val and school_val and res_val != anchor_type:
                                    events.append(entry) # Renamed from event_results
            else:
                # Relay Logic
                
                # Check for splits FIRST
                split_matches = re.findall(r'\(((?:\d+:)?\d+\.\d+)\)', line)
                if split_matches and len(split_matches) >= 1:
                    # Verify line looks like a series of splits
                    if re.search(r'(?:\d+:)?\d+\.\d+\s+\((?:\d+:)?\d+\.\d+\)', line):
                         if current_relay:
                            if "splits" not in current_relay:
                                current_relay["splits"] = []
                            current_relay["splits"].extend(split_matches)
                         continue

                runner_matches = re.findall(r'(\d\)\s+.*?)(?=\s*\d\)|$)', line)
                if runner_matches and current_relay:
                    for m in runner_matches:
                        runner = re.sub(r'^\d\)\s+', '', m).strip()
                        runner = re.sub(r'\s+\d+$', '', runner)
                        current_relay["athletes"].append(runner)
                elif len(line) > school_idx:
                    # Default right boundary if no stop column found
                    right_boundary = stop_col if stop_col != -1 else anchor_col + 15
                    
                    sub = line[:right_boundary].rstrip()
                    if sub:
                        # Smart split: the mark is usually the token with ':' or '.'
                        # Scan parts from right to find it
                        parts = sub.split()
                        res_val = None
                        for p in reversed(parts):
                            if (re.search(r'\d', p) and ('.' in p or ':' in p or '-' in p)) or p.upper() in ["DQ", "NH", "NM", "DNS", "DNF", "FOUL", "SCR"]:
                                res_val = p
                                break
                        
                        if not res_val and parts:
                             res_val = parts[-1]

                        if res_val:
                            # Handle Exhibition marks (prefixed with X, e.g. XDQ, X2:05.56)
                            relay_exhibition = False
                            if res_val.upper().startswith('X') and len(res_val) > 1:
                                res_val = res_val[1:]
                                relay_exhibition = True

                            is_res_numeric = bool(re.search(r'\d', res_val))
                            is_res_standard = res_val.upper() in ["DQ", "FOUL", "NH", "NM", "DNS", "DNF", "SCR"]
                            
                            if is_res_numeric or is_res_standard:
                                res_pos = line.rfind(res_val, 0, right_boundary + 5)
                                school_part = line[school_idx:res_pos].strip()
                                school_part = re.sub(r'^\s*(?:#|--|\d+)\s+', '', school_part).strip()
                                school_part = re.split(r'\s{2,}', school_part)[0].strip()
                                
                                # Validation: reject empty, purely-numeric, or misread runner lines
                                # Also reject "LastName, FirstName" patterns — these are individual
                                # event rows from a two-column PDF bleeding into the relay section.
                                if not school_part or school_part.replace('.', '').isdigit() or "1)" in school_part:
                                    continue
                                if re.match(r'^[A-Za-z][A-Za-z\'-]+,\s+[A-Za-z]', school_part):
                                    continue

                                if school_part and res_val != anchor_type:
                                    if res_val.upper() != "DQ":
                                        res_val = re.sub(r'q$', '', res_val, flags=re.IGNORECASE)
                                    # Strip trailing wind reading before cleaning
                                    res_val = re.sub(r'\s+(?:NWI\+?|[+-]?\d\.\d)\s*$', '', res_val, flags=re.IGNORECASE).strip()
                                    original_res = res_val
                                is_standard = res_val.upper() in ["DQ", "FOUL", "NH", "NM", "DNS", "DNF", "SCR"]
                                is_numeric = bool(re.match(r'^[0-9:.-]+$', res_val))
                                
                                warnings = []
                                if not (is_standard or is_numeric):
                                    cleaned = re.sub(r'[^0-9:.-]', '', res_val)
                                    if cleaned:
                                        res_val = cleaned
                                        warnings.append(f"Original result: {original_res}")
                                    else:
                                        warnings.append(f"Result contains unusual characters: {original_res}")

                                current_relay = {
                                    "school": school_part,
                                    "result": res_val,
                                    "athletes": [],
                                    "type": anchor_type
                                }
                                if relay_exhibition:
                                    current_relay["exhibition"] = True
                                if ev.get("is_ms"):
                                    current_relay["grade"] = "MS"
                                    
                                if warnings: current_relay["warnings"] = warnings
                                events.append(current_relay)

        # Cross-country PDFs shift their columns from page to page (page 2
        # rows start at column 0 and run ~10 characters wider), so the
        # page-1 ruler cuts later pages' times off (or just their
        # hundredths and team points). The header-less reading
        # (finish = last time on the row) is position-free: take it when it
        # finds rows the ruler lost and agrees on the rows both found.
        if not is_relay and not events:
            untimed = self._untimed_rows(dict(ev, lines=lines[header_row_idx + 1:]))
            if untimed:
                return untimed
        if not is_relay and xc_event and len(events) >= 5:
            alt = self.parse_headerless_block(dict(ev, lines=lines[header_row_idx + 1:],
                                                   heat_col='H#' in lines[header_row_idx]))
            # marks the ruler sliced short ("22:45.6" of "22:45.63")
            hdr = {e['athlete'].split(',')[0]: e.get('result', '') for e in events}
            sliced = sum(1 for a in alt if hdr.get(a['athlete'].split(',')[0], a['result']) != a['result']
                         and a['result'].startswith(hdr.get(a['athlete'].split(',')[0], '')))
            cut = sum(1 for e in events if re.fullmatch(r'\d+:\d\d', e.get('result', '')))
            alt_cut = sum(1 for e in alt if re.fullmatch(r'\d+:\d\d', e.get('result', '')))
            if alt_cut < cut:
                sliced = max(sliced, 1)
            if len(alt) > len(events) or (len(alt) == len(events) and sliced):
                names = {e['athlete'].split(',')[0] for e in events}
                pairs = {(e['athlete'], e['school']) for e in events}
                # marks the ruler sliced mid-token ("21:0", "22:")
                broken = sum(1 for e in events
                             if not re.fullmatch(r'\d+:\d\d(?:\.\d+)?|DNF|DNS|DQ|SCR', e.get('result', '')))
                agree_names = sum(1 for a in alt if a['athlete'].split(',')[0] in names) >= 0.9 * len(events)
                agree_pairs = sum(1 for a in alt if (a['athlete'], a['school']) in pairs) >= 0.9 * len(events)
                if agree_pairs or ((broken or sliced) and agree_names):
                    return alt
        return events

if __name__ == "__main__":
    test_files = [
        ("backend/data/sub5_archive/2026/Indoor/emitl2a20dec2025.htm", "parsed_results_meet2a.json"),
        ("backend/data/sub5_archive/2026/Indoor/KVACMeet1AResults-1.htm", "parsed_results_kvac.json"),
        ("backend/data/sub5_archive/2026/Indoor/ResultsSMAA-1.htm", "parsed_results_smaa.json")
    ]
    
    for file_path, output_name in test_files:
        if not os.path.exists(file_path):
            print(f"Skipping missing file: {file_path}")
            continue
            
        parser = Sub5ColumnParser(file_path)
        res = parser.parse()
        
        with open(output_name, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=4, ensure_ascii=False)
            
        print(f"Successfully parsed {len(res)} events from {os.path.basename(file_path)} to {output_name}")
