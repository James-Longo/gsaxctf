import re
from .base import BaseParser

class HyTekBaseParser(BaseParser):
    def __init__(self, scraper=None):
        super().__init__(scraper)
        # Relay Pattern: Rank, Name, Mark, [Points]
        self.relay_pattern = re.compile(r'^\s*(\d+)\s+([^\d)]+?)\s+([a-zA-Z]?[\d:.\'-]{4,}[a-zA-Z*]*)(?:\s+|$)', re.MULTILINE)
        
        # Shared Junk Terms
        self.junk_terms = ['license', 'contractor', 'timing', 'results', 'page', 'hy-tek', 'meet manager', 'points', 'finals', 'prelims', 'rank', 'name', 'year', 'school', 'team', 'seed']

    def parse_common_lines(self, text, meet_url, season_type, row_parser_func):
        """
        Common loop for processing lines. 
        `row_parser_func` is a callback that takes (lines, i) and returns (result_dict, new_i) or None.
        """
        header, meet_date = self.get_meet_details(text)
        season_year = self.get_season_year(text, meet_url, season_type)
        
        # Clean text
        text = text.replace('\xa0', ' ').replace('\u00a0', ' ')
        
        # Event Header detection
        event_pattern = re.compile(r'(Girls|Boys|Women|Men)\s+([\d\w\s]+)', re.IGNORECASE)
        
        results = []
        lines = text.split('\n')
        current_event = None
        current_gender = None
        
        i = 0
        while i < len(lines):
            line = lines[i]
            line_clean = line.strip()
            
            if not line_clean: 
                i += 1
                continue
            
            # Header check
            if len(line_clean) < 80 and ("Girls" in line_clean or "Boys" in line_clean or "Women" in line_clean or "Men" in line_clean):
                ev_match = event_pattern.search(line_clean)
                if ev_match:
                    if "Relay" not in ev_match.group(2) and "Relay" not in line_clean:
                         # Ensure it's not a relay unless explicit
                         pass
                    
                    current_gender = ev_match.group(1)
                    current_event = ev_match.group(2).strip()
                    i += 1
                    continue
            
            if current_event:
                is_relay = "Relay" in current_event or "Relay" in line_clean
                
                if is_relay:
                    # Relays are usually standard across formats
                    # Rank, TeamName, Mark
                    parts = [p.strip() for p in re.split(r'\s{2,}', line.strip()) if p.strip()]
                    if len(parts) >= 3 and parts[0].isdigit():
                        rank = parts[0]
                        mark_idx = -1
                        # Find mark (digit with : or .)
                        for k in range(len(parts)-1, 0, -1):
                            if re.search(r'\d', parts[k]) and (':' in parts[k] or '.' in parts[k]):
                                mark_idx = k
                                break
                        
                        if mark_idx > 0:
                            mark = parts[mark_idx]
                            school = " ".join(parts[1:mark_idx])
                            full_event = self.clean_event_name(f"{current_gender} {current_event}")
                            results.append({
                                "athlete_name": school + " Relay",
                                "grade": "--", "school": school, "event": full_event,
                                "mark": mark.strip().strip('qQ*RxXJj'), "rank": rank, "points": "0", "gender": current_gender,
                                "season": f"{season_year} {season_type}", "date": meet_date, "meet_name": header, "meet_url": meet_url
                            })
                    i += 1
                    continue
                else:
                    # Delegate specific logic to the subclass strategy
                    res, new_i = row_parser_func(lines, i, current_gender, current_event, season_year, meet_date, header, meet_url)
                    if res:
                        results.append(res)
                        i = new_i
                    else:
                        i += 1
            else:
                i += 1

        return results

class HyTekStandardParser(HyTekBaseParser):
    def parse(self, text, meet_url, season_type):
        """Standard Parser: Rank Name Grade School Mark"""
        return self.parse_common_lines(text, meet_url, season_type, self.parse_row)

    def parse_row(self, lines, i, gender, event, season, date, meet_name, url):
        line = lines[i].strip()
        parts = [p.strip() for p in re.split(r'\s{2,}|\t', line) if p.strip()]
        
        if len(parts) < 3: return None, i

        rank = parts[0].strip('.')
        if not rank.isdigit(): return None, i

        # Look for Grade (digits 7-12 or --)
        grade_idx = -1
        for idx, p in enumerate(parts):
            # We skip rank (0) and name parts. Grade usually comes after name.
            # But "Madison Rose" is 1 part if we split by 2 spaces. 
            if idx < 1: continue 
            
            if p == '--' or (p.isdigit() and 7 <= int(p) <= 12):
                grade_idx = idx
                break
        
        if grade_idx == -1: return None, i # Standard parser mandates a grade column
        
        name = " ".join(parts[1:grade_idx]) # Name is everything before grade
        grade = parts[grade_idx]
        
        # School is next, Mark is usually last (ignoring points)
        # Scan from end for mark
        mark_idx = -1
        for k in range(len(parts)-1, grade_idx, -1):
             p = parts[k]
             if re.search(r'\d', p) and (':' in p or '.' in p) and len(p) > 2:
                 mark_idx = k
                 break
        
        if mark_idx == -1: return None, i
        
        mark = parts[mark_idx]
        school = " ".join(parts[grade_idx+1:mark_idx])

        if self.is_junk(name, school): return None, i
        
        full_event = self.clean_event_name(f"{gender} {event}")
        if self.scraper and not self.scraper.mark_is_reasonable(mark, full_event):
             return None, i

        return {
            "athlete_name": name.strip(),
            "grade": grade, "school": school.strip(), "event": full_event,
            "mark": mark.strip('qQ*RxXJj'), "rank": rank, "points": "0", "gender": gender,
            "season": f"{season} Outdoor" if "Outdoor" in url else f"{season} Indoor", "date": date, "meet_name": meet_name, "meet_url": url
        }, i + 1

    def is_junk(self, name, school):
        lname = name.lower()
        lschool = school.lower()
        if any(x in lname for x in self.junk_terms) or any(x in lschool for x in self.junk_terms): return True
        return False

class HyTekSMAAParser(HyTekBaseParser):
    def parse(self, text, meet_url, season_type):
        """SMAA Parser: Rank Name School Mark [Heat] - NO GRADE COLUMN"""
        return self.parse_common_lines(text, meet_url, season_type, self.parse_row)

    def parse_row(self, lines, i, gender, event, season, date, meet_name, url):
        line = lines[i].strip()
        parts = [p.strip() for p in re.split(r'\s{2,}|\t', line) if p.strip()]
        
        if len(parts) < 3: return None, i

        rank = parts[0].strip('.')
        if not rank.isdigit(): return None, i
        
        # Structure: Rank, Name, School, Mark...
        # Name is usually index 1
        name = parts[1]
        
        # Find Mark (digits with . or :)
        mark_idx = -1
        for k in range(len(parts)-1, 1, -1):
             p = parts[k]
             # SMAA marks often have trailing chars or heat numbers separately
             if re.search(r'\d', p) and (':' in p or '.' in p) and len(p) > 3:
                 mark_idx = k
                 break
        
        if mark_idx == -1: return None, i
        
        mark = parts[mark_idx]
        school = " ".join(parts[2:mark_idx])
        grade = "--" # SMAA has no grade

        if self.is_junk(name, school): return None, i
        
        full_event = self.clean_event_name(f"{gender} {event}")
        # Sanity check
        if self.scraper and not self.scraper.mark_is_reasonable(mark, full_event):
             return None, i
        
        return {
            "athlete_name": name.strip(),
            "grade": grade, "school": school.strip(), "event": full_event,
            "mark": mark.strip('qQ*RxXJj'), "rank": rank, "points": "0", "gender": gender,
            "season": f"{season} Outdoor" if "Outdoor" in url else f"{season} Indoor", "date": date, "meet_name": meet_name, "meet_url": url
        }, i + 1

    def is_junk(self, name, school):
        lname = name.lower()
        lschool = school.lower()
        if any(x in lname for x in self.junk_terms) or any(x in lschool for x in self.junk_terms): return True
        # Explicit check for "School" or "Finals" in name column which happens in headers
        if name in ["School", "Year", "Finals"]: return True
        return False
