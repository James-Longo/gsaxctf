import React, { useState, useMemo, useEffect } from 'react';
import schoolClasses from './data/school_classes.json';
import { isBetter } from './utils';

const StateRankings = ({ allPerformances }) => {
    // 1. Determine available Years
    const years = useMemo(() => {
        const y = new Set(allPerformances.map(p => p.year).filter(Boolean));
        return Array.from(y).sort((a, b) => b - a);
    }, [allPerformances]);

    // 2. States
    const [selectedYear, setSelectedYear] = useState(years.length > 0 ? years[0] : '2026');
    const [selectedSex, setSelectedSex] = useState('Girls');
    const [selectedClass, setSelectedClass] = useState('B');
    const [selectedEventBase, setSelectedEventBase] = useState('55 Meter Dash');

    // Robust school class lookup
    const getSchoolClass = (teamName) => {
        if (!teamName) return null;
        const teamLower = teamName.toLowerCase().trim();

        // Exact match first
        if (schoolClasses[teamName]) return schoolClasses[teamName];

        // Partial match
        const sortedKeys = Object.keys(schoolClasses).sort((a, b) => b.length - a.length);
        for (const key of sortedKeys) {
            const keyLower = key.toLowerCase().trim();

            // Special case for Central vs Maine Central
            if (keyLower === 'central' && teamLower.includes('maine')) continue;

            if (teamLower.includes(keyLower)) {
                return schoolClasses[key];
            }
        }
        return null;
    };

    // 3. Derive available base events for the selected Sex
    const availableEvents = useMemo(() => {
        const prefixes = ['Girls', 'Boys'];
        const eventSet = new Set();

        allPerformances.forEach(p => {
            const lowerEvent = p.event.toLowerCase();
            const lowerSex = selectedSex.toLowerCase();

            if (lowerEvent.startsWith(lowerSex)) {
                // Extract base name by removing the sex prefix (e.g. "Girls 55 Meter Dash" -> "55 Meter Dash")
                const baseName = p.event.substring(selectedSex.length).trim();
                eventSet.add(baseName);
            }
        });
        return Array.from(eventSet).sort();
    }, [allPerformances, selectedSex]);

    // Handle initial state and sex changes
    useEffect(() => {
        if (availableEvents.length > 0) {
            // If current selection is invalid for new sex, pick a common one or the first available
            if (!availableEvents.includes(selectedEventBase)) {
                const search = ['55 Meter Dash', 'Shot Put', '200 Meter Dash'];
                const bestDefault = search.find(s => availableEvents.includes(s));
                setSelectedEventBase(bestDefault || availableEvents[0]);
            }
        }
    }, [selectedSex, availableEvents]);

    // 4. Filter and Rank
    const filteredRankings = useMemo(() => {
        const fullEventName = `${selectedSex} ${selectedEventBase}`;

        let filtered = allPerformances.filter(p => {
            if (p.year !== selectedYear) return false;
            // Exact match on full event string as stored in DB
            if (p.event !== fullEventName) return false;

            if (selectedClass !== 'All') {
                const sClass = getSchoolClass(p.team);
                if (sClass !== selectedClass) return false;
            }
            return true;
        });

        // Best per athlete
        const bests = {};
        filtered.forEach(p => {
            if (!bests[p.athlete_id] || isBetter(p.mark, bests[p.athlete_id].mark)) {
                bests[p.athlete_id] = p;
            }
        });

        return Object.values(bests).sort((a, b) => {
            if (isBetter(a.mark, b.mark)) return -1;
            if (isBetter(b.mark, a.mark)) return 1;
            return 0;
        });
    }, [allPerformances, selectedYear, selectedSex, selectedClass, selectedEventBase]);

    return (
        <div className="state-rankings-container">
            <div className="in-progress-note" style={{
                backgroundColor: '#fffaf0',
                border: '1px solid #feebc8',
                color: '#9c4221',
                padding: '12px 16px',
                borderRadius: '8px',
                marginBottom: '20px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                fontSize: '0.9rem',
                fontWeight: '500'
            }}>
                <span style={{ fontSize: '1.2rem' }}>⚠️</span>
                <span><strong>NOTE:</strong> This feature is currently in progress and may be inaccurate. Rankings are still being verified.</span>
            </div>

            <div className="header-row">
                <h2>State Rankings by Class</h2>
                <div className="record-count">{filteredRankings.length} Athletes Found</div>
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
                    <select value={selectedEventBase} onChange={e => setSelectedEventBase(e.target.value)}>
                        {availableEvents.map(ev => <option key={ev} value={ev}>{ev}</option>)}
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
                                    <td>{getSchoolClass(p.team) || '-'}</td>
                                    <td><strong>{p.mark}</strong></td>
                                    <td>{p.date.split('T')[0]}</td>
                                    <td>{p.meet_name}</td>
                                </tr>
                            ))
                        ) : (
                            <tr>
                                <td colSpan="7" className="no-results">
                                    No rankings found for "{selectedSex} {selectedEventBase}" in Class {selectedClass} ({selectedYear})
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default StateRankings;
