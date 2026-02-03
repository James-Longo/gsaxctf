# Track & Field Team App - Function Guides

This document explains the logic and structure of the major features in this application, helping developers modify and maintain them.

---

## PVC Simulator (`ui/src/PerformanceList.jsx`)

The PVC Simulator predicts the scoring of a "PVC Small Schools" championship meet using three levels of sophistication.

### 1. Simulation Modes
- **Greedy**: Uses a simple greedy algorithm to select the top 3 events for each athlete based on point value. Relays are only selected if all members have slots available. This provides a "upper bound" estimate of potential.
- **Multi Simulation (Hill Climbing)**: Uses a statistical simulation. It generates multiple random opponent scenarios and then uses a **Hill-Climbing algorithm** to optimize the target team's roster.
    - It attempts to swap entries to maximize the average score across scenarios.
    - **Joint Surgical Swap**: Specifically handles "Relay Deadlocks" where a relay cannot be added because multiple members have reached their 3-event limit. It evaluates dropping the lowest-scoring individual event from each congested member to fit the relay.
- **Nash Equilibrium (Cascading)**: The most advanced mode. It simulates a "ladder" of competition where teams optimize tactically against their closest rivals.
    - It uses a **Cascading Solver** that iterates down the standings (1st vs 2nd, 2nd vs 3rd).
    - If a battle causes a ranking flip, the cascade restarts to ensure a stable equilibrium.
    - Identifies "Hold the Line" (defensive) vs "Title Match" (offensive) tactical shifts.

### 2. Core Constraints
- **Event Limit**: Maine Track & Field rules limit athletes to 3 events total (including relays).
- **Scoring**: Standard 10-8-6-4-2-1 scoring.
- **Tie Splitting**: Points are automatically split for ties (e.g., if two athletes tie for 1st, they each get 9 points `(10+8)/2`).

---

## Backend Logical Engines

The backend contains the game-theoretic core of the application.

### Nash Engine (`backend/nash_engine.py`)
This engine facilitates complex roster optimization that accounts for opponent behavior.
- **Net Value Matrix**: Calculates the points gained (or denied to an opponent) for every possible event entry.
- **Denial Weighting**: Allows the engine to value "blocking" an opponent (denial) alongside scoring points directly.
- **Optimal Roster Solver**: Uses a custom constrained optimizer to find the best 3 events per athlete (and 1 per relay) that maximizes the team's net value.

### Championship Engine (`backend/championship_engine.py`)
A high-level wrapper that manages full meet simulations.
- **Battle Logic**: Orchestrates "one-way Nash steps" where a challenger optimizes tactically against a defender.
- **Equilibrium Solver**: Iteratively runs battles until no team can improve their ranking or score by changing their roster, reaching a stable tournament state.
- **Strategic Insights**:
    - **Congested Athletes**: Identifies athletes who are scoring in 3 events but have a 4th event where they could also score high, providing a "pivot" point for coaches.
    - **Relay Bottlenecks**: Highlights specific athletes whose individual event load is preventing a high-scoring relay from being entered.

### Entry Decisions (`backend/championship_engine.py`)
This tool helps coaches make real-world lineup decisions.
- **Athlete Categorization**:
    - **Decision Athletes**: Athletes who either have >3 high-scoring events or have "Adjacent" track events (which might cause fatigue/short recovery).
    - **Straightforward Athletes**: Athletes with 1-3 clear scoring opportunities and no scheduling conflicts.
- **Adjacency Detection**: Detects track events that occur back-to-back in the Maine Indoor/Outdoor meet sequence (e.g., 400m and 800m).

---

## PR Pop Calculator (`ui/src/PRPopCalculator.jsx`)

Identifies "PR Pops"—performances in a specific meet that are strictly better than any previous performance.

### Logic
1.  **Meet Selection**: Filters results by meet and team.
2.  **Comparison**: For every result, it searches the historical database for that athlete and event.
3.  **Strict Improvement**: Triggers only if the new mark is better than the all-time best. First-time competitors (no history) are ignored to avoid noise.

---

## Core Utilities (`ui/src/utils.js`)

Essential for accurate data comparison across time and distance events.

### `parseMark(mark)`
- **Distances**: Converts `19-05.50` or `4' 10"` into float inches.
- **Times**: Converts `7.24` or `9:57.12` into float seconds.
- **Invalidation**: Handles `DNF`, `DQ`, `FOUL`, `NH`.

### `is_better(a, b, event)`
- Handles the inverse logic of track and field: **lower** time is better, but **higher** distance is better. Automatically detects event type to apply the correct comparison.
