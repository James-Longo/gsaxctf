# Agent Instructions & Guidelines

This document provides critical context for future AI agents working on this codebase.

## Project Structure
- `backend/`: Python scraper and data processing logic (JSON flat-file store).
- `ui/`: React frontend (Vite).
- `ui/public/data/teams/*.json`: The store — one file per team, consumed directly by the frontend.
- `backend/data/sub5_archive/{year}/{season}/`: Raw downloaded meet files (2003-2026).
- `backend/data/parsed_results/{year}/{season}/`: Parsed per-meet JSON (incl. `team_rankings`).
- `backend/data/meet_verification.json`: Per-meet QA/QC confidence verdicts.

## Key Components
- **`backend/parser.py`**: The **primary parser** (Sub5ColumnParser) for Sub5 HTML files. Handles individual and relay results, splits, exhibition marks, and official Team Rankings blocks. Joins ALL `<pre>` blocks; splits multi-column PDF pages; can rebuild scrambled PDFs from word coordinates (PyMuPDF).
- **`backend/scraper_v2.py`**: The pipeline — season config (`SEASONS`, 2003-2026), parallel download/parse with a **parser retry chain**, normalization via the team registry, and single-pass store sync. The chain rejects parses whose marks are out of finishing order (spliced columns).
- **`backend/parsers/`**: format-specific parsers the chain falls back through:
  `hytek.py` (standard/SMAA line formats), `column.py` (wraps Sub5ColumnParser),
  `htmltable.py` (HTML grids: labeled rows, place grids, 3-row event triples, RaceTab _full exports),
  `looselist.py` (ranked/unranked lists, collapsed PDFs, dual-meet sheets with score-line code resolution),
  `placegrid.py` (Event x place matrices incl. Team:/Time: sub-row sheets),
  `newsprint.py` (newspaper agate, prose paragraphs, email-mangled streams, one-token-per-line Word exports).
- **`backend/build_team_registry.py`**: generates `backend/data/team_registry.json` — canonical team names + level-aware aliases (hs/ms/college), built from name clustering AND athlete-roster overlap (same-season shared athletes = same team). Rerun after big data changes; hand-edit MANUAL_ALIASES for stragglers.
- **`backend/qaqc.py`**: data quality checks + meet-scoring verification.
- **`backend/audit_unparsed.py`**: maintains `backend/data/unparsed_audit.json` — every zero-result archive file with a format class and disposition (not-results / unrecoverable / todo). This is the completeness ledger: the goal state is zero `todo`.

## Key Workflows

### 1. Data Updates
Run from the repo root:

- Incremental update (weekly CI): `python3 -m backend.scraper_v2`
  Downloads new files, parses only changed files, syncs new meets (~1-2 min).
- After parser changes: `python3 -m backend.scraper_v2 --wipe`
  Force re-parses all ~6,000 files in parallel and rebuilds the store (~3 min).
- After sync/normalization-only changes: `python3 -m backend.scraper_v2 --resync-only`
  Rebuilds the store from existing parsed JSONs without re-parsing.
- QA/QC + confidence report: `python3 backend/qaqc.py` (run from `backend/`)
  Re-scores every meet from parsed results and compares against the official
  Team Rankings in the source file; a mismatch means a parsing or scoring bug.
  Writes per-meet verdicts (verified / verified_close / mismatch / no_rankings,
  plus mark-order sanity) to `backend/data/meet_verification.json`.

### 2. Deployment
**CRITICAL:** Always run Vercel deployments from the **root directory**, not the `ui` directory,
and always with `--archive=tgz` (the store has ~11k chunk files; Vercel's free tier caps
raw uploads at 5,000 files):
```
npx vercel --prod --archive=tgz
```
The store is gzipped on disk (`teams/{slug}/{year}_{season}.json.gz`, `athletes.json.gz`) to
stay under Vercel's 500MB bundle cap; the UI decompresses with DecompressionStream and
re-derives the slim rows' team/year/season/id fields on load (see `loadTeamData` in App.jsx
and `json_store.slim_row`/`enrich_rows`).

### 3. Split Support
Split data is stored as a JSON string in the `splits` column of the `performances` table in the database. When exporting to `data.json`, ensure they are parsed back into JSON arrays (handled in `export_for_web.py`). The parser detects splits formatted as `Cumulative (Split)` (e.g., `1:11.703 (35.439)`).

## UI & Documentation Standards
- **No Emojis:** Never use emojis in documentation, UI labels, or comments. Maintain a professional, clean aesthetic.

## Common Gotchas
- **React Imports:** Always ensure `import React from 'react'` is present if using `React.Fragment` or JSX that requires the React object, as the build environment may enforce it.
- **Athlete ID Types:** The athlete dropdown values are strings, but database IDs are often numbers. Ensure type conversion (e.g., `String(id)`) when filtering in `App.jsx`.
- **Primary Parser:** Ensure any changes to parsing logic are made in `backend/parser.py` OR the specialized parsers in `backend/parsers/` if the `FormatDetector` is updated.

