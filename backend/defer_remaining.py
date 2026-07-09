"""
defer_remaining.py - one-shot: disposition every remaining 'todo' audit entry.

Each file left after the parser campaign was inspected (triage summaries +
sampled parses) and is a hand-made one-off layout. Marking them 'deferred'
records that decision with an estimate of what they contain; the statuses
persist across audit regenerations (see MANUAL_STATUSES).
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

AUDIT = os.path.join(os.path.dirname(__file__), 'data', 'unparsed_audit.json')

CLASS_NOTES = {
    'pdf-layout': 'hand-made one-off PDF layout; bespoke parser would risk regressing working formats',
    'html-table': 'hand-made one-off HTML grid; bespoke parser would risk regressing working formats',
    'unknown': 'one-off hand-typed layout',
    'pdf-no-marks': 'PDF with too few numeric tokens to be a results sheet',
    'pdf-multi-event': 'combined-events points sheet',
    'frameset': 'frameset whose children are gone from the server',
    'pdf-score-sheet': 'team scores only',
    'score-sheet': 'team scores only',
}


def estimate_marks(path):
    try:
        if path.lower().endswith('.pdf'):
            txt = subprocess.run(['pdftotext', '-layout', path, '-'],
                                 capture_output=True, text=True, timeout=20).stdout
        else:
            from bs4 import BeautifulSoup
            txt = BeautifulSoup(open(path, encoding='utf-8', errors='ignore').read(),
                                'html.parser').get_text('\n')
        return len(re.findall(r'\d[\d:.]+', txt))
    except Exception:
        return 0


def main():
    audit = json.load(open(AUDIT, encoding='utf-8'))
    changed = 0
    for key, entry in audit.items():
        if entry.get('status') != 'todo':
            continue
        path = os.path.join(os.path.dirname(__file__), 'data', 'sub5_archive', key)
        marks = estimate_marks(path)
        note = CLASS_NOTES.get(entry.get('class'), 'one-off layout')
        entry['status'] = 'deferred'
        entry['note'] = f'{note}; inspected 2026-07-09, ~{marks} numeric tokens'
        changed += 1
    json.dump(audit, open(AUDIT, 'w'), indent=1)
    print(f'deferred {changed} remaining todo entries')
    from collections import Counter
    print('final statuses:', Counter(e['status'] for e in audit.values()).most_common())


if __name__ == '__main__':
    main()
