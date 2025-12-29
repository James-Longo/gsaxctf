import re
from bs4 import BeautifulSoup
import json
import os
import sys

class Sub5ColumnParser:
    def __init__(self, file_path):
        self.file_path = file_path
        self.headers = {'User-Agent': 'Mozilla/5.0'}
        self.standard_events = [
            "55 Meter Dash", "200 Meter Dash", "400 Meter Dash", "800 Meter Run",
            "1 Mile Run", "2 Mile Run", "55 Meter Hurdles", "55 Yard Hurdles", "High Jump",
            "Long Jump", "Triple Jump", "Pole Vault", "Shot Put",
            "600 Meter Run", "1000 Meter Run", "1600 Meter Run", "3200 Meter Run",
            "4x200 Meter Relay", "4x400 Meter Relay", "4x800 Meter Relay",
            "Indoor Pentathlon", "Racewalk", "100 Meter Dash", "110 Meter Hurdles",
            "100 Meter Hurdles", "300 Meter Hurdles", "400 Meter Hurdles", "Javelin Throw",
            "Discus Throw"
        ]

    def normalize_event_name(self, event_name):
        """
        Normalizes event names by matching against a list of standard events.
        If a standard event is a substring of the input, use the standard version.
        Prioritizes the longest match.
        """
        best_match = event_name
        max_len = 0
        
        for std in self.standard_events:
            if std.lower() in event_name.lower():
                if len(std) > max_len:
                    best_match = std
                    max_len = len(std)
        
        return best_match
        
    def parse(self):
        if not os.path.exists(self.file_path):
            return []
            
        with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
            html_content = f.read()
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Try to find <pre> specifically if possible
        pre = soup.find('pre')
        if pre:
            text = pre.get_text()
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
        
        # Segment into events
        events = []
        current_event = None
        
        for i, line in enumerate(lines):
            # Header pattern: "Event 1  Girls 4x800 Meter Relay" or "Girls 55 Meter Dash"
            m_event = re.search(r'Event\s+\d+\s+(Girls|Boys)\s+(.*)', line, re.IGNORECASE)
            m_no_event = re.match(r'^\s*(Girls|Boys)\s+(.*)$', line, re.IGNORECASE)
            
            is_header = False
            gender = ""
            event_name = ""
            
            if m_event:
                is_header = True
                gender = m_event.group(1).strip()
                event_name = m_event.group(2).strip()
            elif m_no_event:
                if i + 1 < len(lines) and "=====" in lines[i+1]:
                    is_header = True
                    gender = m_no_event.group(1).strip()
                    event_name = m_no_event.group(2).strip()
            
            if is_header:
                if current_event:
                    events.append(current_event)
                
                # Normalize the event name
                normalized_name = self.normalize_event_name(event_name)
                
                current_event = {
                    "gender": gender,
                    "event_name": normalized_name,
                    "original_event_name": event_name, # Keep original for reference
                    "lines": [],
                    "is_relay": any(x in normalized_name.lower() or x in event_name.lower() for x in ["relay", "4x"])
                }
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
                
        return {
            "meet_name": meet_name,
            "date": meet_date,
            "events": parsed_events
        }

    def parse_event_block(self, ev):
        lines = ev["lines"]
        is_relay = ev["is_relay"]
        
        name_idx = -1
        school_idx = -1
        anchor_col = -1
        stop_col = -1 # Column index to stop reading (e.g. before H#)
        anchor_type = None 
        header_row_idx = -1
        
        for i, line in enumerate(lines):
            if not is_relay:
                if "Name" in line and "School" in line:
                    name_idx = line.find("Name")
                    school_idx = line.find("School")
                    header_row_idx = i
            else:
                if "School" in line and ("Finals" in line or "Prelims" in line):
                    school_idx = line.find("School")
                    header_row_idx = i
            
            if header_row_idx != -1:
                if "Finals" in line:
                    anchor_col = line.find("Finals") + len("Finals")
                    anchor_type = "Finals"
                elif "Prelims" in line:
                    anchor_col = line.find("Prelims") + len("Prelims")
                    anchor_type = "Prelims"
                
                # Check for columns to the right of the result to establish a boundary
                # Common headers: H# (Heat), Points, Pts
                stop_col = -1
                right_headers = ["H#", "Points", "Pts"]
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
                        res_val = sub.split()[-1]
                        
                        # Handle Exhibition marks (prefixed with X)
                        if res_val.upper().startswith('X') and len(res_val) > 1:
                             res_val = res_val[1:]

                        # Check if result looks valid
                        is_res_numeric = bool(re.search(r'\d', res_val))
                        is_res_standard = res_val.upper() in ["DQ", "FOUL", "NH", "NM", "DNS", "DNF", "SCR"]
                        
                        if is_res_numeric or is_res_standard:
                            res_pos = line.rfind(res_val, 0, right_boundary + 2)
                            
                            # Extract name
                            # Clean leading place markers like "1 ", "2 ", "-- "
                            name_clean = re.sub(r'^\s*(?:#|--|\d+)\s+', '', line[:school_idx]).strip()
                            name_val = re.split(r'\s{2,}', name_clean)[0].strip()
                            if name_val.isdigit() or not name_val: continue
                            
                            # Extract school
                            area_start = max(0, school_idx - 5)
                            school_area = line[area_start:res_pos]
                            m_school = re.search(r'\S', school_area)
                            if m_school:
                                school_raw = school_area[m_school.start():].strip()
                                school_val = re.sub(r'^\d+\s+', '', school_raw).strip()
                                school_val = re.split(r'\s{2,}', school_val)[0].strip()
                                
                                if anchor_type and anchor_type in school_val:
                                    school_val = school_val.replace(anchor_type, "").strip()
                                
                                if res_val.upper() != "DQ":
                                    res_val = re.sub(r'q$', '', res_val, flags=re.IGNORECASE)
                                
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
                                
                                entry = {
                                    "athlete": name_val,
                                    "school": school_val,
                                    "result": res_val,
                                    "type": anchor_type
                                }
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
                    right_boundary = stop_col if stop_col != -1 else anchor_col + 12
                    
                    sub = line[:right_boundary].rstrip()
                    if sub:
                        res_val = sub.split()[-1]
                        
                        # Handle Exhibition marks (prefixed with X, e.g. XDQ, X2:05.56)
                        if res_val.upper().startswith('X') and len(res_val) > 1:
                            res_val = res_val[1:]

                        is_res_numeric = bool(re.search(r'\d', res_val))
                        is_res_standard = res_val.upper() in ["DQ", "FOUL", "NH", "NM", "DNS", "DNF", "SCR"]
                        
                        if is_res_numeric or is_res_standard:
                            res_pos = line.rfind(res_val, 0, right_boundary + 2)
                            school_part = line[school_idx:res_pos].strip()
                            school_part = re.sub(r'^\s*(?:#|--|\d+)\s+', '', school_part).strip()
                            school_part = re.split(r'\s{2,}', school_part)[0].strip()
                            
                            # Validation: School name should not be purely numeric or empty
                            # Also check for "1)" which might indicate a misread relay runner line
                            if not school_part or school_part.replace('.', '').isdigit() or "1)" in school_part:
                                continue

                            if school_part and res_val != anchor_type:
                                if res_val.upper() != "DQ":
                                    res_val = re.sub(r'q$', '', res_val, flags=re.IGNORECASE)
                                
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
                                if warnings: current_relay["warnings"] = warnings
                                events.append(current_relay)
                            
        return events

if __name__ == "__main__":
    test_files = [
        ("backend/data/sub5_archive/2026/emitl2a20dec2025.htm", "prototype_results_meet2a.json"),
        ("backend/data/sub5_archive/2026/KVACMeet1AResults-1.htm", "prototype_results_kvac.json"),
        ("backend/data/sub5_archive/2026/ResultsSMAA-1.htm", "prototype_results_smaa.json")
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
