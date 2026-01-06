# Track & Field Team App - Development Guide

Welcome to the Track & Field Team App project! This guide provides everything a newcomer needs to know to understand, run, and modify this software. For technical deep dives into specific features, see the **[Function Guides](FUNCTION_GUIDES.md)**.

## 🏗️ Architecture Overview

The project is split into two main components:
1.  **Backend (`backend/`)**: A Python-based system responsible for scraping data from Sub5.com, parsing results, and managing the SQLite database. It also provides a FastAPI server for dynamic data access.
2.  **Frontend (`ui/`)**: A React application built with Vite that visualizes the performance data.

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Node.js & npm

### Setup
1.  **Backend**:
    - Create a virtual environment: `python -m venv .venv`
    - Activate it: `.venv\Scripts\activate` (Windows)
    - Install dependencies: `pip install -r backend/requirements.txt`
2.  **Frontend**:
    - Navigate to `ui/`
    - Install dependencies: `npm install`
3.  **Launch**:
    - Use the root-level `Launch Dashboard.bat` to start both backend and frontend simultaneously.

## 📁 Key Files & Directories

### Core Components
- **`track_app.db`**: The SQLite database (Source of Truth).
- **`backend/scraper.py`**: The main scraping engine.
- **`backend/prototype_parser.py`**: **CRITICAL** - Despite the name, this is the primary parser for Sub5 results.
- **`backend/main.py`**: FastAPI server logic.
- **`backend/export_for_web.py`**: Script to dump DB data into `ui/public/data.json` for the frontend.
- **`backend/resync_db.py`**: Rebuilds the database from local JSON files.

### 🧪 One-off / Testing Scripts (Can be ignored)
- `check_marks.py`: Quick check for DNF/DQ etc. in the DB.
- `verify_dates.py`: Validation script for parsed result dates.
- `backend/test_meet_parse.py`: Experimental parser testing.
- `backend/verify_prototype.py`: Verification for the prototype parser.

### 🗑️ Temporary / Unimportant Files
The following files are generated during debugging or one-off audits and are typically not needed for production:
- Root `.txt` files: `2026_hits.txt`, `audit_out.txt`, `audit_results.txt`, `debug_*.txt`, `scrape_*.txt`.
- Root `.json` files: `prototype_*.json`.

## 🔄 Data Flow
1.  **Scrape**: `backend/scraper.py` downloads HTML from Sub5.com.
2.  **Parse**: `backend/prototype_parser.py` (via scraper) converts HTML to JSON in `backend/data/parsed_results/`.
3.  **Sync**: `backend/scraper.py` (or `resync_db.py`) inserts JSON results into `track_app.db`.
4.  **Export**: `backend/export_for_web.py` creates `ui/public/data.json`.
5.  **View**: The React UI reads `data.json` to display the dashboard.

## 🛠️ Common Tasks
- **Updating Data**: Run `python backend/scraper.py` then `python backend/export_for_web.py`.
- **Modifying the UI**: Edit files in `ui/src/`. The dev server will hot-reload.
- **Deployment**: Read `AGENT_INSTRUCTIONS.md` for specific Vercel deployment rules.
