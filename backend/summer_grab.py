"""Save a browser capture that the app wrote to a tool-results file into backend/data/summer/raw.

The capture is returned from the page padded past the inline size limit, so it
is saved to disk without passing through the conversation (backend/summer_track.py).
usage: python3 -m backend.summer_grab <tool-results file> <dest name, e.g. an-672097.tsv>
"""
import json
import os
import sys

src, name = sys.argv[1], sys.argv[2]
raw = json.load(open(src))[0]['text']
text, _ = json.JSONDecoder().raw_decode(raw)   # the returned string, JSON-quoted, then the tool's own note
body = text.split('<<CAPTURE>>\n', 1)[-1].split('\n<<END>>', 1)[0]
dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'summer', 'raw', name)
os.makedirs(os.path.dirname(dest), exist_ok=True)
open(dest, 'w', encoding='utf-8').write(body)
print(dest, len(body), 'chars,', body.count('\n## '), 'events,', body.count('\n') + 1, 'lines')
