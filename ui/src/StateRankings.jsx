import React, { useState, useMemo } from 'react';
import schoolClasses from './data/school_classes.json';
import { isBetter } from './utils';

const StateRankings = ({ allPerformances }) => {
    const [selectedYear, setSelectedYear] = useState('2026');
    const [selectedSex, setSelectedSex] = useState('Girls');
    const [selectedClass, setSelectedClass] = useState('B'); // Default to Class B (Small School) as requested
    const [selectedEvent, setSelectedEvent] = useState('55m Dash');

    const years = useMemo(() => {
        const y = new Set(allPerformances.map(p => p.year).filter(Boolean));
        return Array.from(y).sort((a, b) => b - a);
    }, [allPerformances]);

    const filteredRankings = useMemo(() => {
        // 1. Filter by Year, Sex, and Class
        let filtered = allPerformances.filter(p => {
            const matchesYear = p.year === selectedYear;
            const matchesSex = p.event.toLowerCase().includes(selectedSex.toLowerCase());

            // Match event (case-insensitive and partial match to handle "Girls 55m Dash" vs "55m Dash")
            const matchesEvent = p.event.toLowerCase().includes(selectedEvent.toLowerCase());

            if (!matchesYear || !matchesSex || !matchesEvent) return false;

            // Class matching logic
            const schoolClass = schoolClasses[p.team];
            if (selectedClass === 'All') return true;
            return schoolClass === selectedClass;
        });

        // 2. Find BEST performance per athlete in this filtered set
        const bestsByAthlete = {};
        filtered.forEach(p => {
            const key = p.athlete_id;
            if (!bestsByAthlete[key] || isBetter(p.mark, bestsByAthlete[key].mark)) {
                bestsByAthlete[key] = p;
            }
        });

        // 3. Sort by performance
        return Object.values(bestsByAthlete).sort((a, b) => {
            if (isBetter(a.mark, b.mark)) return -1;
            if (isBetter(b.mark, a.mark)) return 1;
            return 0;
        });
    }, [allPerformances, selectedYear, selectedSex, selectedClass, selectedEvent]);

    const events = useMemo(() => {
        const e = new Set(allPerformances
            .filter(p => p.event.toLowerCase().includes(selectedSex.toLowerCase()))
            .map(p => {
                // Strip "Girls " or "Boys " from the start to get the base event name
                return p.event.replace(/^(Girls|Boys)\s+/i, '');
            })
        );
        return Array.from(e).sort();
    }, [allPerformances, selectedSex]);

    return (
        <div className="state-rankings-container">
            <div className="header-row">
                <h2>State Rankings by Class</h2>
                <div className="record-count">{filteredRankings.length} Athletes</div>
            </div>

            <div className="filter-bar">
                <div className="filter-group">
                    <label>Year</label>
                    <select value={selectedYear} onChange={e => setSelectedYear(e.target.value)}>
                        {years.map(y => <option key={y} value={y}>{y}</option>)}
                    </select>
                </div>

                <div className="filter-group">
                    <label>Sex</label>
                    <select value={selectedSex} onChange={e => setSelectedSex(e.target.value)}>
                        <option value="Girls">Girls</option>
                        <option value="Boys">Boys</option>
                    </select>
                </div>

                <div className="filter-group">
                    <label>Class</label>
                    <select value={selectedClass} onChange={e => setSelectedClass(e.target.value)}>
                        <option value="All">All Classes</option>
                        <option value="A">Class A (Large)</option>
                        <option value="B">Class B (Small)</option>
                    </select>
                </div>

                <div className="filter-group">
                    <label>Event</label>
                    <select value={selectedEvent} onChange={e => setSelectedEvent(e.target.value)}>
                        {events.map(ev => <option key={ev} value={ev}>{ev}</option>)}
                    </select>
                </div>
            </div>

            <div className="table-container">
                <table className="performance-table">
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Athlete</th>
                            <th>Team</th>
                            <th>Class</th>
                            <th>Result</th>
                            <th>Date</th>
                            <th>Meet</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredRankings.length > 0 ? (
                            filteredRankings.map((p, idx) => (
                                <tr key={p.id}>
                                    <td>{idx + 1}</td>
                                    <td className="athlete-name-cell">{p.athlete_name}</td>
                                    <td>{p.team}</td>
                                    <td>{schoolClasses[p.team] || '-'}</td>
                                    <td><strong>{p.mark}</strong></td>
                                    <td>{p.date.split('T')[0]}</td>
                                    <td>{p.meet_name}</td>
                                </tr>
                            ))
                        ) : (
                            <tr>
                                <td colSpan="7" className="no-results">No rankings found for these filters</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default StateRankings;
