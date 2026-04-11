import React, { useState, useEffect, useMemo } from 'react';
import './App.css';

const PracticeResults = () => {
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [filterName, setFilterName] = useState('All');
    const [filterSurface, setFilterSurface] = useState('All');
    const [filterEvent, setFilterEvent] = useState('20m Fly');
    const [viewMode, setViewMode] = useState('leaderboard'); // 'leaderboard' or 'sessions'

    useEffect(() => {
        const SHEET_CSV_URL = 'https://docs.google.com/spreadsheets/d/1fql3yYQs_9OZZmS8-KHDliEPTKl__ZFZ592E8dkZD7Q/export?format=csv';

        const eventsConfig = [
            { col: '20m Fly', type: 'time', surfaceCol: '20m Fly Surface' },
            { col: 'Half Court Dash', type: 'time', surface: 'Gym' },
            { col: 'Triple Broad Jump', type: 'distance', surfaceCol: 'Triple Broad Jump Surface' },
            { col: 'Shuttle Run', type: 'time', surfaceCol: 'Shuttle Run Surface' },
            { col: 'Quintuple Bound', type: 'distance', surfaceCol: 'Quintuple Bound Surface' }
        ];

        const parseDistanceVal = (val) => {
            if (!val || !val.includes('-')) return null;
            try {
                const [ft, ins] = val.split('-').map(Number);
                return ft * 12 + (ins || 0);
            } catch { return null; }
        };

        const formatDistance = (inches) => {
            if (inches == null) return 'x';
            const ft = Math.floor(inches / 12);
            const ins = Math.round((inches % 12) * 100) / 100;
            return `${ft}-${ins}`;
        };

        const median = (arr) => {
            const sorted = [...arr].sort((a, b) => a - b);
            const mid = Math.floor(sorted.length / 2);
            return sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
        };

        const parseCSV = (text) => {
            // Proper CSV parser that handles quoted fields (e.g. "2.30h, 2.79h")
            const parseCSVLine = (line) => {
                const fields = [];
                let current = '';
                let inQuotes = false;
                for (let i = 0; i < line.length; i++) {
                    const ch = line[i];
                    if (inQuotes) {
                        if (ch === '"' && (i + 1 >= line.length || line[i + 1] === ',')) {
                            inQuotes = false;
                        } else {
                            current += ch;
                        }
                    } else {
                        if (ch === '"') {
                            inQuotes = true;
                        } else if (ch === ',') {
                            fields.push(current.trim());
                            current = '';
                        } else {
                            current += ch;
                        }
                    }
                }
                fields.push(current.trim());
                return fields;
            };

            const lines = text.split('\n').filter(l => l.trim());
            if (lines.length < 2) return [];
            const headers = parseCSVLine(lines[0]);
            const rows = [];
            for (let i = 1; i < lines.length; i++) {
                const cols = parseCSVLine(lines[i]);
                const row = {};
                headers.forEach((h, idx) => { row[h] = (cols[idx] || '').trim(); });
                rows.push(row);
            }
            return rows;
        };

        const fetchData = async () => {
            try {
                const response = await fetch(SHEET_CSV_URL);
                if (!response.ok) throw new Error('Failed to fetch practice results from Google Sheets');
                const csvText = await response.text();
                const rows = parseCSV(csvText);

                const parsed = [];
                for (const row of rows) {
                    if (!row['Name'] || !row['Name'].trim()) continue;
                    const date = (row['Date'] || '').trim();
                    const name = row['Name'].trim();

                    for (const event of eventsConfig) {
                        const rawVal = (row[event.col] || '').trim();
                        if (!rawVal) continue;

                        let eventSurface = 'Track';
                        if (event.surface) eventSurface = event.surface;
                        else if (event.surfaceCol) eventSurface = (row[event.surfaceCol] || '').trim() || 'Track';

                        const trials = rawVal.split(',').map(t => t.trim());
                        const isHand = trials.some(t => t.toLowerCase().includes('h'));
                        const validTrials = [];

                        for (const t of trials) {
                            if (!t || t.toLowerCase() === 'x') continue;
                            const cleanT = t.toLowerCase().replace('h', '');
                            if (event.type === 'time') {
                                const v = parseFloat(cleanT);
                                if (!isNaN(v)) validTrials.push(v);
                            } else {
                                const d = parseDistanceVal(cleanT);
                                if (d !== null) validTrials.push(d);
                            }
                        }

                        if (validTrials.length === 0) continue;

                        let performanceVal;
                        const meanSdEvents = ['20m Fly', 'Half Court Dash', 'Shuttle Run'];

                        if (event.type === 'distance') {
                            performanceVal = Math.max(...validTrials);
                        } else if (meanSdEvents.includes(event.col)) {
                            performanceVal = validTrials.reduce((a, b) => a + b, 0) / validTrials.length;
                        } else {
                            performanceVal = median(validTrials);
                        }

                        parsed.push({
                            name,
                            date,
                            event: event.col,
                            surface: eventSurface,
                            trials,
                            is_hand_timed: isHand,
                            median_mark: performanceVal,
                            mark_type: event.type,
                            formatted_median: event.type === 'distance' ? formatDistance(performanceVal) : String(Math.round(performanceVal * 100) / 100)
                        });
                    }
                }
                setResults(parsed);
            } catch (err) {
                console.error('Practice Results data error:', err);
                setError(err.message);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []);

    const parseDistance = (val) => {
        if (!val || typeof val !== 'string') return null;
        if (!val.includes('-')) return parseFloat(val);
        try {
            const [ft, ins] = val.split('-').map(parseFloat);
            return (ft * 12) + (ins || 0);
        } catch (e) {
            return null;
        }
    };

    const names = useMemo(() => {
        const n = new Set(results.map(r => r.name));
        return ['All', ...Array.from(n).sort()];
    }, [results]);

    const surfaces = useMemo(() => {
        const s = new Set(results.map(r => r.surface));
        return ['All', ...Array.from(s).sort()];
    }, [results]);

    const events = useMemo(() => {
        const e = new Set(results.map(r => r.event));
        return Array.from(e).sort();
    }, [results]);

    const filteredResults = useMemo(() => {
        return results.filter(r => {
            return (filterName === 'All' || r.name === filterName) &&
                (filterSurface === 'All' || r.surface === filterSurface) &&
                (filterEvent === 'All' || r.event === filterEvent);
        });
    }, [results, filterName, filterSurface, filterEvent]);

    const leaderboard = useMemo(() => {
        const dataMap = {};

        filteredResults.forEach(r => {
            if (!dataMap[r.name]) {
                dataMap[r.name] = {
                    name: r.name,
                    replicates: []
                };
            }

            const isTime = r.mark_type === 'time';
            const isHand = r.is_hand_timed;
            const isDistance = r.mark_type === 'distance';

            const numericTrials = (r.trials || []).map(t => {
                if (isDistance) return parseDistance(String(t));
                const cleanT = String(t).toLowerCase().replace('h', '');
                return parseFloat(cleanT);
            }).filter(v => v !== null && !isNaN(v));

            if (numericTrials.length === 0) return;

            // NEW: For 20m Fly and Half Court Dash, treat each day as a single replicate (Mean/SD)
            // regardless of whether it is hand-timed or automatic.
            const sessionMeanSdEvents = ['20m Fly', 'Half Court Dash', 'Shuttle Run'];
            const shouldForceSessionReplicate = sessionMeanSdEvents.includes(r.event);

            if (isHand || shouldForceSessionReplicate) {
                // One replicate per session with Mean and SD
                const mean = numericTrials.reduce((a, b) => a + b, 0) / numericTrials.length;
                let sd = 0;
                if (numericTrials.length > 1) {
                    const variance = numericTrials.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / numericTrials.length;
                    sd = Math.sqrt(variance);
                }
                dataMap[r.name].replicates.push({
                    val: mean,
                    sd: sd,
                    isHand: isHand,
                    date: r.date,
                    mark_type: r.mark_type,
                    raw_result: r
                });
            } else {
                // Automatic: Each trial is its own replicate (for other events like jumps if automatic)
                numericTrials.forEach(t => {
                    dataMap[r.name].replicates.push({
                        val: t,
                        sd: 0,
                        isHand: false,
                        date: r.date,
                        mark_type: r.mark_type,
                        raw_result: r
                    });
                });
            }
        });

        const summary = Object.values(dataMap).map(athlete => {
            if (athlete.replicates.length === 0) return null;
            const isTime = athlete.replicates[0].mark_type === 'time';

            // Sort replicates to find the best one
            const sortedReplicates = [...athlete.replicates].sort((a, b) => isTime ? a.val - b.val : b.val - a.val);
            const best = sortedReplicates[0];

            let mphEstimate = null;
            if (filterEvent === '20m Fly') {
                mphEstimate = (44.7388 / (best.val || 1));
            }

            return {
                name: athlete.name,
                best: best,
                mphEstimate,
                replicatesCount: athlete.replicates.length
            };
        }).filter(Boolean);

        return summary.sort((a, b) => {
            if (filterEvent === '20m Fly') {
                return (b.mphEstimate || 0) - (a.mphEstimate || 0);
            }
            if (a.best.mark_type === 'distance') {
                return (b.best.val || 0) - (a.best.val || 0);
            }
            return (a.best.val || 0) - (b.best.val || 0);
        });
    }, [filteredResults, filterEvent]);

    const sessions = useMemo(() => {
        const grouped = {};
        filteredResults.forEach(r => {
            if (!grouped[r.date]) grouped[r.date] = [];
            grouped[r.date].push(r);
        });
        return Object.entries(grouped).sort((a, b) => new Date(b[0]) - new Date(a[0]));
    }, [filteredResults]);

    const eventColorScales = useMemo(() => {
        const scales = {};
        const byEvent = {};
        results.forEach(r => {
            if (!byEvent[r.event]) byEvent[r.event] = [];
            byEvent[r.event].push(r);
        });

        Object.keys(byEvent).forEach(ev => {
            const evResults = byEvent[ev];
            const isTimeEvent = evResults[0].mark_type === 'time';
            const isDistEvent = evResults[0].mark_type === 'distance';

            const vals = [];
            evResults.forEach(r => {
                (r.trials || []).forEach(t => {
                    let v;
                    if (isDistEvent) v = parseDistance(String(t));
                    else v = parseFloat(String(t).toLowerCase().replace('h', ''));
                    if (v !== null && !isNaN(v)) vals.push(v);
                });
            });

            if (vals.length === 0) {
                scales[ev] = () => '#6ee7b7';
                return;
            }

            const min = Math.min(...vals);
            const max = Math.max(...vals);
            const colors = ['#065f46', '#047857', '#059669', '#10b981', '#34d399', '#6ee7b7'];
            const bestBound = isTimeEvent ? min : max;
            const worstBound = isTimeEvent ? max : min;

            scales[ev] = (val) => {
                if (val === null || isNaN(val)) return 'transparent';
                if (min === max) return colors[0];
                let normalized = (val - worstBound) / (bestBound - worstBound);
                normalized = Math.max(0, Math.min(1, normalized));
                let index = Math.floor((1 - normalized) * colors.length);
                if (index >= colors.length) index = colors.length - 1;
                return colors[index];
            };
        });

        return scales;
    }, [results]);

    const getEventColor = (val, eventName) => {
        if (!eventColorScales[eventName]) return '#6ee7b7';
        return eventColorScales[eventName](val);
    };

    if (loading) return <div className="loading-state">Loading Practice Results...</div>;
    if (error) return <div className="error-state">Error: {error}</div>;

    return (
        <div className="practice-results-container">
            <div className="header-row">
                <h2>Practice Results - Dashboard</h2>
                <div className="view-toggle">
                    <button
                        className={`toggle-btn ${viewMode === 'leaderboard' ? 'active' : ''}`}
                        onClick={() => setViewMode('leaderboard')}
                    >
                        Leaderboard
                    </button>
                    <button
                        className={`toggle-btn ${viewMode === 'sessions' ? 'active' : ''}`}
                        onClick={() => setViewMode('sessions')}
                    >
                        Sessions
                    </button>
                </div>
            </div>

            {filterEvent === '20m Fly' && (
                <div className="setup-info">
                    <div className="info-item"><strong>Acceleration distance:</strong> 30m / 98' 5"</div>
                    <div className="info-item"><strong>Fly distance:</strong> 20m / 65' 7"</div>
                </div>
            )}

            <div className="filter-bar">
                <div className="filter-group">
                    <label>Event</label>
                    <select value={filterEvent} onChange={e => setFilterEvent(e.target.value)}>
                        {events.map(ev => <option key={ev} value={ev}>{ev}</option>)}
                    </select>
                </div>
                <div className="filter-group">
                    <label>Athlete</label>
                    <select value={filterName} onChange={e => setFilterName(e.target.value)}>
                        {names.map(n => <option key={n} value={n}>{n}</option>)}
                    </select>
                </div>
                <div className="filter-group">
                    <label>Surface</label>
                    <select value={filterSurface} onChange={e => setFilterSurface(e.target.value)}>
                        {surfaces.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                </div>
            </div>

            {viewMode === 'leaderboard' ? (
                <div className="table-container">
                    <table className="performance-table">
                        <thead>
                            <tr>
                                <th>Rank</th>
                                <th>Athlete</th>
                                <th>{
                                    filterEvent === '20m Fly' ? 'Top Speed (MPH)' :
                                        (filterEvent.includes('Jump') || filterEvent.includes('Bound')) ? 'Best Distance (Feet-Inches)' :
                                            (filterEvent === 'Shuttle Run' || filterEvent === 'Half Court Dash') ? 'Fastest Time (Seconds)' :
                                                `Reliable Mark (${filterEvent.includes('Jump') || filterEvent.includes('Bound') ? 'Inches' : 'Seconds'})`
                                }</th>
                                <th>Replicates</th>
                                <th>Date</th>
                            </tr>
                        </thead>
                        <tbody>
                            {leaderboard.map((a, idx) => (
                                <tr key={`${a.name}-${idx}`} className={idx === 0 ? 'top-row' : ''}>
                                    <td>{idx + 1}</td>
                                    <td className="athlete-name-cell">{a.name}</td>
                                    <td>
                                        <div
                                            className="result-badge"
                                            style={{
                                                backgroundColor: getEventColor(a.best.val, a.best.raw_result.event),
                                                color: 'white', padding: '4px 8px', borderRadius: '4px', display: 'inline-block', fontWeight: 'bold'
                                            }}
                                        >
                                            {filterEvent === '20m Fly' ? (a.mphEstimate || 0).toFixed(2) : (a.best.mark_type === 'distance' ?
                                                (Math.floor(a.best.val / 12) + '-' + (a.best.val % 12).toFixed(1)) :
                                                (a.best.val || 0).toFixed(2))}
                                            {a.best.sd > 0 && (
                                                <span style={{ fontSize: '0.75rem', marginLeft: '4px', opacity: 0.9, fontWeight: 'normal' }}>
                                                    ±{filterEvent === '20m Fly' ? (a.mphEstimate * (a.best.sd / a.best.val || 0)).toFixed(2) : (a.best.mark_type === 'distance' ? (a.best.sd / 12).toFixed(1) + "'" : a.best.sd.toFixed(2))}
                                                </span>
                                            )}
                                        </div>
                                    </td>
                                    <td>{a.replicatesCount}</td>
                                    <td style={{ fontSize: '0.85rem', color: '#666' }}>{a.best.date}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                </div>
            ) : (
                <div className="sessions-container">
                    {sessions.map(([date, sessionResults]) => (
                        <div key={date} className="session-block">
                            <h3 className="session-date">{date}</h3>
                            <div className="table-container">
                                <table className="performance-table">
                                    <thead>
                                        <tr>
                                            <th>Athlete</th>
                                            <th>{['20m Fly', 'Half Court Dash', 'Shuttle Run'].includes(filterEvent) ? 'Mean' : 'Median/Peak'}</th>
                                            <th>Trials</th>
                                            <th>Surface</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {sessionResults.sort((a, b) => {
                                            const isTime = a.mark_type === 'time';
                                            const isDist = a.mark_type === 'distance';
                                            const valA = isDist ? parseDistance(String(a.median_mark)) : parseFloat(String(a.median_mark).replace('h', ''));
                                            const valB = isDist ? parseDistance(String(b.median_mark)) : parseFloat(String(b.median_mark).replace('h', ''));
                                            return isTime ? valA - valB : valB - valA;
                                        }).map(r => (
                                            <tr key={`${r.name}-${r.event}-${r.date}`}>
                                                <td className="athlete-name-cell">{r.name}</td>
                                                <td>
                                                    <div
                                                        className="result-badge"
                                                        style={{
                                                            backgroundColor: getEventColor(r.mark_type === 'distance' ? parseDistance(String(r.median_mark)) : parseFloat(String(r.median_mark).replace('h', '')), r.event),
                                                            color: 'white', padding: '2px 6px', borderRadius: '4px', display: 'inline-block', fontSize: '0.85rem'
                                                        }}
                                                    >
                                                        {r.formatted_median}
                                                    </div>
                                                </td>
                                                <td>{Array.isArray(r.trials) ? r.trials.join(', ') : r.trials}</td>
                                                <td>{r.surface}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default PracticeResults;
