# Track & Field Team Management Platform

A sophisticated analytics and management platform for Track & Field coaches, specifically optimized for the PVC (Penobscot Valley Conference) Small Schools division. This application transforms raw Sub5 performance data into actionable strategic insights.

## Key Features

- **Performance Dashboard**: Real-time parsing and visualization of athlete performance history from Sub5.com fixed-width data.
- **Advanced PVC Simulator**: Predictive modeling for championship meets using three distinct simulation modes:
    - **Greedy**: Rapid point-maximizing roster optimization.
    - **Multi Simulation**: Statistical simulation using Hill-Climbing algorithms to handle athlete event limits.
    - **Nash Equilibrium**: Advanced engine that simulates tactical "jockeying" between teams and solves cross-relay member constraints.
- **PR Pop Calculator**: Instantly identifies "PR Pops"—performances that strictly improve upon an athlete's historical best.

## Quick Start

1.  **Launch**: Double-click **`Launch Dashboard.bat`** in the root folder.
2.  **Access**: Your browser will automatically open to `http://localhost:5173`.
3.  **Analyze**: select your team and season to view performance history or run simulations.

## Requirements

- **Python**: 3.10+ (for the Nash Engine and scraping)
- **Node.js & npm**: (for the React-based UI)
- **SQLite3**: (database included)

## Documentation

- **[Development Guide](DEVELOPMENT_GUIDE.md)**: Architecture, data flow, and setup instructions.
- **[Function Guides](FUNCTION_GUIDES.md)**: Technical deep dives into the Nash Engine, Hill Climbing optimization, and drafting logic.

## AI Context
If you are an AI assistant working on this codebase, please refer to **[AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md)** for critical deployment guidelines and system architecture constraints.
