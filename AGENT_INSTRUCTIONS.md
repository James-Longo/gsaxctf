# Agent Instructions & Guidelines

This document provides critical context for future AI agents working on this codebase.

## Project Structure
- `backend/`: Python scraper and data processing logic. Uses SQLite (`track_app.db`).
- `ui/`: React frontend (Vite).
- `track_app.db`: The source of truth for all performance data.
- `ui/public/data.json`: The exported data consumed by the frontend.

## Key Workflows

### 1. Data Updates
Whenever the scrapers or parsers are modified, you must:
1. Re-run the sync/resync scripts (e.g., `backend/resync_db.py`).
2. Run `backend/export_for_web.py` to update the frontend's `data.json`.

### 2. Deployment
**CRITICAL:** Always run Vercel deployments from the **root directory**, not the `ui` directory.
```powershell
npx vercel --prod
```

### 3. Split Support
Split data is stored as a JSON string in the `splits` column of the `performances` table in the database. When exporting to `data.json`, ensure they are parsed back into JSON arrays (handled in `export_for_web.py`).

## Common Gotchas
- **React Imports:** Always ensure `import React from 'react'` is present if using `React.Fragment` or JSX that requires the React object, as the build environment may enforce it.
- **Athlete ID Types:** The athlete dropdown values are strings, but database IDs are often numbers. Ensure type conversion (e.g., `String(id)`) when filtering in `App.jsx`.
