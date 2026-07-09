"""
audit_unparsed.py - Maintain backend/data/unparsed_audit.json.

Every archive file that parses to zero results gets an entry with a format
classification and a disposition:
  not-results        verified to contain no individual results (score sheets,
                     entry lists, schedules)
  unrecoverable      content is gone or unusable (offsite redirects to dead
                     hosts, image-only scans pending OCR)
  deferred           inspected, contains real results, but the layout is a
                     hand-made one-off whose bespoke parser would risk
                     regressing the formats that already work
  todo               still needs parser work

Files that later parse successfully drop out of the audit automatically.
Manually-set statuses/notes are preserved across reruns.
"""

import json
import os
import re
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import qaqc

AUDIT = os.path.join(os.path.dirname(__file__), 'data', 'unparsed_audit.json')

MANUAL_STATUSES = {'not-results', 'unrecoverable', 'deferred', 'parsed-ok'}

# Hand-inspected dispositions (survive regeneration; keyed by audit key).
MANUAL_DISPOSITIONS = {
    '2006/Indoor/collegestatemen06.htm':
        ('not-results', 'press-release recap article, no structured results'),
    '2006/Indoor/collegestatewomen06.htm':
        ('not-results', 'press-release recap article, no structured results'),
    '2006/Outdoor/Rotaryrace06.htm':
        ('not-results', 'Rotary 5K road race, not a track meet'),
    '2006/Outdoor/noble4_26boys.htm':
        ('unrecoverable', 'Excel export with single-letter school codes; results cannot be attributed to schools'),
    '2005/Outdoor/greely5_13b.pdf':
        ('unrecoverable', 'spreadsheet score-matrix; word coordinates scrambled beyond reconstruction'),
    '2005/Outdoor/greely5_13g.pdf':
        ('unrecoverable', 'spreadsheet score-matrix; word coordinates scrambled beyond reconstruction'),
    '2004/Indoor/smaaboys.htm':
        ('unrecoverable', 'place matrix with no event labels anywhere in the file'),
    '2008/Outdoor/patriotsday2mile.htm':
        ('not-results', 'Patriot Day 2-mile road race, not a track meet'),
    '2008/Outdoor/morsemay16page1.PDF':
        ('unrecoverable', 'handwritten score sheet scan; text extraction is garbage'),
    '2008/Outdoor/morsemay16page2.PDF':
        ('unrecoverable', 'handwritten score sheet scan; text extraction is garbage'),
    '2008/Outdoor/morsemay16page3.PDF':
        ('unrecoverable', 'handwritten score sheet scan; text extraction is garbage'),
    '2008/Outdoor/morsemay16page4.PDF':
        ('unrecoverable', 'handwritten score sheet scan; text extraction is garbage'),
    '2011/Indoor/WMC%20JAN%2014%20MEET%201.pdf':
        ('not-results', 'meet schedule announcement, no results'),
    '2016/Indoor/Results-Alumni-Mile.pdf':
        ('not-results', 'alumni exhibition mile at a college dual, no HS results'),
    '2016/Outdoor/Results.pdf':
        ('unrecoverable', 'corrupt text layer (digits only); the .htm sibling has the meet'),
    '2025/Outdoor/aroostook-league-championship-records.pdf':
        ('not-results', 'league records list, not meet results'),
    '2006/Indoor/pentathlongirls.pdf':
        ('not-results', 'combined-events points sheet, not mark-based results'),
    '2009/Indoor/pentathlongirls.pdf':
        ('not-results', 'combined-events points sheet, not mark-based results'),
    '2013/Outdoor/Decathlon2013Championships.pdf':
        ('not-results', 'combined-events points sheet, not mark-based results'),
    '2013/Outdoor/Heptathlon2013Championships.pdf':
        ('not-results', 'combined-events points sheet, not mark-based results'),
    '2015/Outdoor/ME-Region-1-Qualifier-results.htm':
        ('not-results', 'USATF Junior Olympics summer youth meet, out of HS scope'),
    '2010/Outdoor/traipboys_may14.pdf':
        ('unrecoverable', 'hand-made paired-row grid; parser attempt regressed other formats, deliberately excluded (~50 results)'),
    '2010/Outdoor/traipgirls_april30.pdf':
        ('unrecoverable', 'hand-made paired-row grid; parser attempt regressed other formats, deliberately excluded (~50 results)'),
    '2010/Outdoor/traipgirls_may14.pdf':
        ('unrecoverable', 'hand-made paired-row grid; parser attempt regressed other formats, deliberately excluded (~50 results)'),
}


def classify_pdf(path):
    try:
        out = subprocess.run(['pdftotext', '-layout', path, '-'],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return 'pdf-error', ''
    txt = out.strip()
    if len(txt) < 100:
        return 'pdf-image-scan', 'no extractable text; OCR needed'
    if re.search(r'pentathlon|heptathlon', txt[:2000], re.I):
        return 'pdf-multi-event', 'pentathlon/heptathlon scoring sheet'
    if re.search(r'entr(y|ies)|psych|heat sheet|start list|schedule', txt[:600], re.I) \
            and 'results' not in txt[:600].lower():
        return 'pdf-entries', 'entry list / schedule, not results'
    if re.search(r'team rankings|team scores', txt[:3000], re.I) or \
            re.search(r'scores?', os.path.basename(path), re.I):
        return 'pdf-score-sheet', 'team scores only'
    if len(re.findall(r'\d[\d:.]+', txt)) < 20:
        return 'pdf-no-marks', 'fewer than 20 numeric tokens'
    return 'pdf-layout', 'text extracted but layout defeats current parsers'


def build():
    existing = {}
    if os.path.exists(AUDIT):
        existing = json.load(open(AUDIT, encoding='utf-8'))

    entries = {}
    for year in sorted(os.listdir(qaqc.ARCHIVE_BASE)):
        ypath = os.path.join(qaqc.ARCHIVE_BASE, year)
        if not os.path.isdir(ypath):
            continue
        for season in sorted(os.listdir(ypath)):
            spath = os.path.join(ypath, season)
            if not os.path.isdir(spath):
                continue
            for fn in sorted(os.listdir(spath)):
                if not fn.lower().endswith(('.htm', '.html', '.pdf')):
                    continue
                stem = os.path.splitext(fn)[0]
                jp = os.path.join(qaqc.PARSED_BASE, year, season, stem + '.json')
                try:
                    data = json.load(open(jp, encoding='utf-8'))
                    n = qaqc.count_parsed_results(data)
                except Exception:
                    n = 0
                if n > 0:
                    continue
                key = f'{year}/{season}/{fn}'
                path = os.path.join(spath, fn)
                if fn.lower().endswith('.pdf'):
                    cls, note = classify_pdf(path)
                else:
                    cls, note = qaqc.classify_unparsed_file(path), ''

                prev = existing.get(key, {})
                status = prev.get('status', 'todo')
                if key in MANUAL_DISPOSITIONS:
                    status, note = MANUAL_DISPOSITIONS[key]
                    entries[key] = {'class': cls, 'status': status, 'note': note}
                    continue
                if prev.get('status') not in MANUAL_STATUSES:
                    if cls in ('score-sheet', 'pdf-score-sheet', 'pdf-entries', 'nav/index'):
                        status, note = 'not-results', note or 'no individual results'
                    elif cls in ('redirect',):
                        status, note = 'unrecoverable', 'redirect stub to dead offsite host'
                    elif cls in ('pdf-image-scan',):
                        status, note = 'unrecoverable', 'image-only scan; OCR needed'
                    else:
                        status = 'todo'
                entries[key] = {'class': cls, 'status': status,
                                'note': prev.get('note') or note}

    json.dump(dict(sorted(entries.items())), open(AUDIT, 'w'), indent=1)
    print(f'audit entries: {len(entries)}')
    print('by class :', Counter(e['class'] for e in entries.values()).most_common())
    print('by status:', Counter(e['status'] for e in entries.values()).most_common())
    todo = [k for k, e in entries.items() if e['status'] == 'todo']
    print(f'todo files: {len(todo)}')
    return entries


if __name__ == '__main__':
    build()
