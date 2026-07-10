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
    """Return a clean grade string (8-12, FR/SO/JR/SR, or MS) or '' for junk."""
    if not g:
        return ''
    g = g.strip()
    if not g or g in ('--', '0', '22'):
        return ''
    if g in ('8', '9', '10', '11', '12', 'MS', 'FR', 'SO', 'JR', 'SR'):
        return g
    if g in _GRADE_MAP:
        return _GRADE_MAP[g]
    # "9 H", "11 B", "12 Finals" etc. — extract the leading grade number
    m = re.match(r'^(8|9|10|11|12)\b', g)
    if m:
        return m.group(1)
    return ''


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

        for std in self.standard_events:
            if std.lower() in event_name.lower():
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
        # sit ~4-6 chars before it)
        bounds = [0] + [max(0, s - 6) for s in starts[1:]] + [10 ** 6]
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
            if pres:
                text = "\n".join(p.get_text() for p in pres)
                lines = text.splitlines()
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
                    if any(x in clean.lower() for x in ms_keywords):
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

            # Header pattern: "Event 1  Girls 4x800 Meter Relay" or "Girls 55 Meter Dash"
            m_event = re.search(r'Event\s+\d+\s+(Girls|Boys|Women|Men|Mixed)\s+(.*)', line_clean, re.IGNORECASE)
            # Support Division headers ("Girls 50 Meter Dash 5th/6th grade") and
            # prefixed multi-event legs ("Indoor Pentathlon: #5 Girls 800 Meter Run")
            m_no_event = re.match(r'^\s*(?:[\w .]{0,30}:\s*#?\d*\s*)?(Girls|Boys|Women|Men|Mixed)\s+(.*)', line_clean, re.IGNORECASE)

            is_header = False
            gender = ""
            event_name = ""

            if m_event:
                is_header = True
                gender = m_event.group(1).strip()
                if gender.lower() == "women": gender = "Girls"
                if gender.lower() == "men": gender = "Boys"
                event_name = m_event.group(2).strip()
            elif m_no_event and "Team Rankings" not in line_clean:
                # Require separator line for no-event-number headers to avoid false positives
                if i + 1 < len(lines) and "====" in lines[i+1]:
                    is_header = True
                    gender = m_no_event.group(1).strip()
                    if gender.lower() == "women": gender = "Girls"
                    if gender.lower() == "men": gender = "Boys"
                    event_name = m_no_event.group(2).strip()

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
            return []
            
        events = [] # Renamed from event_results
        current_relay = None
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
                            for k in range(len(parts)-1, 1, -1):
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
                                
                                # Use anchor_col and school_idx to try to split Name/School
                                grade_val = ""
                                if yr_idx != -1 and yr_idx > name_idx and yr_idx < school_idx:
                                    name_val = line[name_idx:yr_idx].strip()
                                    grade_val = line[yr_idx:school_idx].strip()
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
                                if re.search(r'\d', name_val) and any(c in name_val for c in '.:-\''):
                                    continue
                                
                                # Extract school
                                area_start = max(0, school_idx - 5)
                                school_area = line[area_start:res_pos]
                                m_school = re.search(r'\S', school_area)
                                if m_school:
                                    school_raw = school_area[m_school.start():].strip()
                                    if grade_val and school_raw.startswith(grade_val + " "):
                                        school_raw = school_raw[len(grade_val):].strip()
                                    school_val = re.sub(r'^\d+\s+', '', school_raw).strip()
                                    # Take only the first part if it splits by large gaps
                                    school_val = re.split(r'\s{2,}', school_val)[0].strip()
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
                                if is_exhibition:
                                    entry["exhibition"] = True
                                if ev.get("is_ms"):
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
