# Track & Field Team App

This app allows you to parse athletic.net pages and view athlete performance history on a dashboard.

## Quick Start
1.  Double-click **`Launch Dashboard.bat`** in this folder.
2.  The backend and frontend will start in minimized windows.
3.  Your browser will open to `http://localhost:5173`.

## How it works
- **`athletic.net pages/`**: Put your HTML files here.
- **`src/parse_athletic_net.py`**: Run this manually if you add new files to update the database.
- **`track_app.db`**: The SQLite database storing all athlete data.
- **`backend/`**: FastAPI server.
- **`ui/`**: React frontend.
- **`AGENT_INSTRUCTIONS.md`**: Critical context and deployment guides for AI agents.

## Deployment & Maintenance
For details on how to sync data and deploy to production, please refer to **`AGENT_INSTRUCTIONS.md`**.

## Requirements
- Python 3.x
- Node.js & npm
