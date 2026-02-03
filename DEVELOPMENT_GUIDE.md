# Track & Field Team App - Development Guide

Welcome to the Track & Field Team App project! This guide provides everything a newcomer needs to know to understand, run, and modify this software. For technical deep dives into specific features, see the **[Function Guides](FUNCTION_GUIDES.md)**.

## Architecture Overview

The project is split into three main layers:
1.  **Ingestion Layer (`backend/scraper.py`, `backend/parsers/`)**: Downloads and parses fixed-width results from Sub5.com.
2.  **Analytical Layer (`backend/nash_engine.py`, `backend/championship_engine.py`)**: Sophisticated game-theoretic engines that handle roster optimization and tournament simulation.
3.  **Visualization Layer (`ui/`)**: A React application built with Vite that provides a dashboard for coaches.

## Getting Started

### Prerequisites
- Python 3.10+
- Node.js & npm

### Setup
1.  **Backend**:
    - Create a virtual environment: `python -m venv .venv`
    - Activate it: `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (Linux)
    - Install dependencies: `pip install -r backend/requirements.txt`
2.  **Frontend**:
    - Navigate to `ui/`
    - Install dependencies: `npm install`
3.  **Launch**:
    - Use the root-level `Launch Dashboard.bat` to start both backend and frontend.

## Key Files & Directories

### Core Components
- **`track_app.db`**: The SQLite database (Source of Truth).
- **`backend/scraper.py`**: The main scraping engine.
- **`backend/prototype_parser.py`**: The primary parser for Sub5 results.
- **`backend/nash_engine.py`**: Game-theoretic optimization logic.
- **`backend/championship_engine.py`**: Meet simulation and strategic insight generation.
- **`backend/main.py`**: FastAPI server logic.
- **`backend/export_for_web.py`**: Exports DB data to `ui/public/data.json`.

### Testing & Utility Scripts
- `backend/simulate_pvc_championship.py`: CLI-based championship simulator.
- `verify_dates.py`: Validation for parsed result dates.

## Data Flow
1.  **Ingest**: `scraper.py` fetches HTML; `prototype_parser.py` converts it to JSON.
2.  **Persist**: Scraper inserts JSON results into `track_app.db`.
3.  **Analyze**: Engines (`nash_engine`, `championship_engine`) process raw marks and calculate projected scoring and tactical swaps.
4.  **Export**: `export_for_web.py` creates `ui/public/data.json`.
5.  **Visualize**: The React UI (`ui/src/App.jsx`) reads the exported data and simulation results.

## Common Tasks
- **Updating Data**: Run `python backend/scraper.py` then `python backend/export_for_web.py`.
- **Modifying Optimization**: Edit `backend/nash_engine.py` for game theory changes or `PerformanceList.jsx` for UI-side Hill Climbing logic.
- **Deployment**: Refer to `AGENT_INSTRUCTIONS.md` for Vercel rules.
