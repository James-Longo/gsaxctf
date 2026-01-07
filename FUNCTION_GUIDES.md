# Track & Field Team App - Function Guides

This document explains the logic and structure of the major features in this application, helping developers modify and maintain them.

---

## 📊 PVC Simulator (`ui/src/PerformanceList.jsx`)

The PVC Simulator predicts the scoring of a "PVC Small Schools" championship meet based on all-time best performances for the selected year and season.

### 🧩 Core Logic
1.  **School Filtering**: Only schools defined in `getPVCSchools(year, season)` are included.
    - *To Modify*: Update the school list in `getPVCSchools` if conference alignment changes.
2.  **Event Normalization**: Only events matching keys in `EVENT_ALIASES` are counted. This avoids scoring non-championship events (like the Pentathlon).
3.  **Grouping**: Data is grouped by event. Only the absolute best performance for each athlete (individual) or team (relay) in that specific event/season/year is kept.
4.  **Simulation / Optimization**:
    - **Event Limit (Greedy Selection)**: Maine Track & Field rules limit athletes to 3 events total (including relays). The simulator uses a **Greedy Algorithm** to optimize team scores:
        1. All possible scoring "actions" (individual results and relay results) are pooled and sorted by points (highest first).
        2. The simulator iterates through this list, selecting events until an athlete hits their 3-event limit.
        3. **Relay Decision**: A relay is only selected if **every identified member** on that relay team has fewer than 3 events already assigned. If even one member has already been assigned 3 higher-scoring events, the entire relay is skipped for that team.
    - **Scoring**: Standard 10-8-6-4-2-1 scoring.
    - **Tie Splitting**: Points are automatically split for ties (e.g., if two athletes tie for 1st, they each get 9 points `(10+8)/2`).

---

## 🚀 PR Pop Calculator (`ui/src/PRPopCalculator.jsx`)

This component identifies "PR Pops"—performances in a specific meet that are **strictly better** than any previous performance by that athlete in that event.

### 🧩 Core Logic
1.  **Meet Selection**: Users can select a specific meet from the history of their selected team.
2.  **Comparison**: For every result in the selected meet, the calculator searches all *previous* dates in the database for that athlete and event.
3.  **Strict Improvement**: A "Pop" is only triggered if the new mark is better than the historical best (PR). First-time competitors are excluded.
4.  **Improvement Formatting**: Uses `formatImprovement` to display clearly how much better the mark was (e.g., `-0.45s` or `+6.00"`).

---

## 📋 Create Meet Sheet (`ui/src/MeetSheet.jsx`)

Generates a print-friendly document showing which athletes are entered in which events.

### 🧩 Core Logic
- **External Source**: Fetches entry data from a specific Google Sheets CSV export URL.
- **Parsing**: Logic in `MeetSheet.jsx` splits the CSV into Girls and Boys tables based on header row detection (`4x8`, `55H`, etc.).
- **Manual Overrides**: Allows the coach to manually check/uncheck events to refine the heat sheet before printing.

---

## ⚙️ Core Utilities (`ui/src/utils.js`)

These utilities are used across the entire app for accurate data comparison.

### `parseMark(mark)`
- **Distances**: Converts strings like `19-05.50` or `4' 10"` into total inches (float).
- **Times**: Converts strings like `7.24` or `9:57.12` into total seconds (float).
- **Invalidation**: Correctly flags strings like `DNF`, `DQ`, `FOUL`, etc., as non-comparable.

### `isBetter(a, b)`
- Simple boolean check: `(a is better than b)`.
- Automatically handles the "Distance = Higher is better" vs "Time = Lower is better" logic based on the detected format from `parseMark`.

---

## 🐍 Backend Scraper & Parser (`backend/`)

### `prototype_parser.py`
This is a **column-aware text parser** designed for Sub5.com's fixed-width output.
- **Header Detection**: Scans the first 30 lines for meet names and dates.
- **Block Segmentation**: Splits the text file into "Event Blocks".
- **Column Analysis**: Locates specific columns (Name, School, Finals) and uses their indices to extract data precisely, even when names or schools are long.
- **Split Parsing**: Detects cumulative split patterns like `1:11.703 (35.439)` and extracts them into a list.

### `scraper.py`
- **Session Management**: Tracks which meets have already been scraped for which year/season.
- **Deduplication**: Ensures the same result isn't inserted twice into SQLite.
- **Normalization**: Standardizes school names (e.g., "GSA" vs "George Stevens Academy") using a lookup map to ensure the UI can filter them correctly.
