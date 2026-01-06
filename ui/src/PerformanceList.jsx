import { useState, useMemo } from 'react'
import { parseMark } from './utils'
import './App.css'

function PVCSimulator({ performances, isBetter }) {
    const [filterYear, setFilterYear] = useState('All')
    const [filterSeason, setFilterSeason] = useState('All')
    const [filterEvent, setFilterEvent] = useState('All')
    const [showSimulation, setShowSimulation] = useState(false)
    const [expandedTeams, setExpandedTeams] = useState({}) // { 'teamName-boys': true }

    const scrollToEvent = (groupTitle) => {
        const targetId = `event-${groupTitle.replace(/[^a-z0-9]/gi, '-')}`;
        const element = document.getElementById(targetId);
        if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    };

    // Configuration for PVC Small Schools
    const getPVCSchools = (year, season) => {
        // Specific Rule for Indoor 2026
        if (year === '2026' && season === 'Indoor') {
            return {
                "Bangor Chris": "Bangor Christian Schools",
                "Bucksport": "Bucksport High School",
                "Central": "Central High School",
                "Dexter": "Dexter Regional High School",
                "Foxcroft": "Foxcroft Academy",
                "George Stevens": "George Stevens Academy",
                "Mattanawcook": "Mattanawcook Academy",
                "Orono": "Orono High School",
                "PCHS": "Piscataquis Community High School",
                "Penquis": "Penquis Valley High School",
                "Searsport": "Searsport District High School",
                "Sumner": "Sumner/Narragaugus"
            };
        }

        // Default / Legacy List
        return {
            "Orono": "Orono High School",
            "George Steve": "George Stevens Academy",
            "Bucksport": "Bucksport High School",
            "Sumner": "Sumner/Narragaugus",
            "Central": "Central High School",
            "Foxcroft": "Foxcroft Academy",
            "Dexter": "Dexter Regional High School",
            "Piscataquis": "Piscataquis Community High School",
            "Penquis": "Penquis Valley High School",
            "Searsport": "Searsport District High School",
            "Mattanawcook": "Mattanawcook Academy",
            "Lee Academy": "Lee Academy",
            "Deer Isle": "Deer Isle-Stonington High School",
            "Bangor Chris": "Bangor Christian Schools",
            "Greenville": "Greenville High School",
            "Narraguagus": "Sumner/Narragaugus",
            "Washington Acad": "Washington Academy",
            "Calais": "Calais High School",
            "Shead": "Shead High School",
            "Fort Kent": "Fort Kent Community High School",
            "Caribou Hig": "Caribou High School",
            "Presque Isle": "Presque Isle High School",
            "Houlton": "Houlton High School"
        };
    };

    const { filteredData, years, seasons, events } = useMemo(() => {
        if (!performances) return { filteredData: [], years: [], seasons: [], events: [] };

        // 1. Calculate available Years and Seasons first (from raw data)
        const rawYears = new Set();
        const rawSeasons = new Set();
        performances.forEach(p => {
            if (p.year) rawYears.add(p.year);
            if (p.season) {
                const m = p.season.match(/^(\d{4})\s+(.*)$/);
                if (m) rawSeasons.add(m[2]);
                else rawSeasons.add(p.season);
            }
        });

        // 2. If filters are not set, return empty data but populated options
        if (filterYear === 'All' || filterSeason === 'All') {
            return {
                filteredData: [],
                years: Array.from(rawYears).sort((a, b) => b - a),
                seasons: Array.from(rawSeasons).sort(),
                events: []
            }
        }

        // 3. Get the specific team list for this context
        const activeSchools = getPVCSchools(filterYear, filterSeason);

        const processed = performances.map(p => {
            let year = p.year;
            let type = p.season;
            if (p.season && p.season.match(/^\d{4}/)) {
                const m = p.season.match(/^(\d{4})\s+(.*)$/);
                year = m[1];
                type = m[2];
            }

            // Detect PVC Team based on ACTIVE list
            let pvcTeam = null;
            for (const [key, val] of Object.entries(activeSchools)) {
                // Check against key (short) and val (long)
                const teamLower = p.team.toLowerCase();
                const filterKey = key.toLowerCase();

                // Specific fix for "Central" to avoid matching "Maine Central Institute"
                if (key === "Central" && teamLower.includes("maine")) {
                    continue;
                }

                if (teamLower.includes(filterKey) || teamLower === val.toLowerCase()) {
                    pvcTeam = val;
                    break;
                }
            }

            // Special check for PCHS acronym
            if (!pvcTeam && activeSchools["PCHS"] && (p.team === "PCHS" || p.team.includes("Piscataquis"))) {
                pvcTeam = activeSchools["PCHS"];
            }

            return {
                ...p,
                derivedYear: year,
                derivedType: type,
                pvcTeam: pvcTeam,
                isRelay: p.event.toLowerCase().includes('relay') || p.event.toLowerCase().includes('4x')
            };
        }).filter(p => p.pvcTeam); // Only include valid schools for THIS season

        const matches = (p, filters) => {
            const { year, season, event } = filters;
            return (year === 'All' || p.derivedYear === year) &&
                (season === 'All' || p.derivedType === season) &&
                (event === 'All' || p.event === event);
        };

        const avYears = Array.from(new Set(processed.map(p => p.derivedYear))).sort((a, b) => b - a);
        const avSeasons = Array.from(new Set(processed.map(p => p.derivedType))).sort();
        const avEvents = Array.from(new Set(processed.map(p => p.event))).sort();

        const filtered = processed.filter(p => matches(p, { year: filterYear, season: filterSeason, event: filterEvent }));

        return {
            filteredData: filtered,
            years: avYears,
            seasons: avSeasons,
            events: avEvents
        };
    }, [performances, filterYear, filterSeason, filterEvent]);

    const EVENT_ALIASES = {
        "55m Dash": ["55m Dash", "55 Meter Dash"],
        "200m Dash": ["200m Dash", "200 Meter Dash"],
        "400m Dash": ["400m Dash", "400 Meter Dash"],
        "800m Run": ["800m Run", "800 Meter Run"],
        "1 Mile Run": ["1 Mile Run"],
        "2 Mile Run": ["2 Mile Run"],
        "55m Hurdles": ["55m Hurdles", "55 Meter Hurdles"],
        "4x200m Relay": ["4x200m", "4x200 Meter"],
        "4x800m Relay": ["4x800m", "4x800 Meter"],
        "High Jump": ["High Jump"],
        "Pole Vault": ["Pole Vault"],
        "Long Jump": ["Long Jump"],
        "Triple Jump": ["Triple Jump"],
        "Shot Put": ["Shot Put"]
    };

    // Group by Event, Season, and Year for context-specific ranking
    const groupedData = useMemo(() => {
        const groups = {};

        filteredData.forEach(curr => {
            // Filter non-PVC events
            const eventLower = curr.event.toLowerCase();
            let isAllowed = false;

            // Check if current event matches any allowed alias
            for (const aliases of Object.values(EVENT_ALIASES)) {
                if (aliases.some(alias => eventLower.includes(alias.toLowerCase()))) {
                    isAllowed = true;
                    break;
                }
            }

            const isExcluded = eventLower.includes("pentathlon");

            if (!isAllowed || isExcluded) {
                return;
            }

            const groupKey = `${curr.event} (${curr.derivedType} ${curr.derivedYear})`;
            if (!groups[groupKey]) groups[groupKey] = {};

            // For Relays, use team as key. For Individual, use athlete_id
            const athleteKey = curr.isRelay ? curr.pvcTeam : `${curr.athlete_id}|${curr.pvcTeam}`;
            if (!groups[groupKey][athleteKey] || isBetter(curr.mark, groups[groupKey][athleteKey].mark)) {
                groups[groupKey][athleteKey] = curr;
            }
        });

        const finalGroups = {};
        Object.entries(groups).forEach(([groupKey, itemMap]) => {
            const results = Object.values(itemMap);

            results.sort((a, b) => {
                if (isBetter(a.mark, b.mark)) return -1;
                if (isBetter(b.mark, a.mark)) return 1;
                return 0;
            });

            let currentRank = 1;
            for (let i = 0; i < results.length; i++) {
                if (i > 0 && results[i].mark !== results[i - 1].mark) {
                    currentRank = i + 1;
                }
                results[i].calculatedRank = currentRank;
            }
            finalGroups[groupKey] = results;
        });

        return finalGroups;
    }, [filteredData, isBetter]);

    const optimizedData = useMemo(() => {
        if (!showSimulation || filterYear === 'All' || filterSeason === 'All' || Object.keys(groupedData).length === 0) {
            return groupedData;
        }

        const scoringRules = [10, 8, 6, 4, 2, 1];

        // 1. Extract all entries
        let individualEntries = [];
        let relayEntries = [];

        Object.entries(groupedData).forEach(([groupTitle, results]) => {
            results.forEach(res => {
                const entry = { ...res, groupTitle };
                if (res.isRelay) relayEntries.push(entry);
                else individualEntries.push(entry);
            });
        });

        // 2. Initial Potential Score Pass
        const calculatePoints = (entries) => {
            const groups = {};
            entries.forEach(e => {
                if (!groups[e.groupTitle]) groups[e.groupTitle] = [];
                groups[e.groupTitle].push(e);
            });

            Object.values(groups).forEach(results => {
                results.sort((a, b) => isBetter(a.mark, b.mark) ? -1 : isBetter(b.mark, a.mark) ? 1 : 0);

                let effectiveRank = 1;
                let validCount = 0;
                let lastValidMark = null;

                for (let i = 0; i < results.length; i++) {
                    const p = parseMark(results[i].mark);
                    if (!p.valid) {
                        results[i].tempRank = null;
                        results[i].potentialPts = 0;
                        continue;
                    }

                    if (validCount > 0 && results[i].mark !== lastValidMark) {
                        effectiveRank = validCount + 1;
                    }

                    results[i].tempRank = effectiveRank;
                    results[i].potentialPts = effectiveRank <= scoringRules.length ? scoringRules[effectiveRank - 1] : 0;

                    lastValidMark = results[i].mark;
                    validCount++;
                }
            });
        };

        calculatePoints([...individualEntries, ...relayEntries]);

        // 3. Optimization Logic (3 event limit)
        const eventLimit = 3;
        // An athlete's event count = sum(individual events) + sum(relay participations)
        const athleteCounts = {}; // athlete_name -> count
        const athleteEntries = {}; // athlete_name -> [ {entry, pts} ]

        individualEntries.forEach(e => {
            const name = e.athlete_name || "Unknown";
            if (!athleteEntries[name]) athleteEntries[name] = [];
            athleteEntries[name].push(e);
        });

        relayEntries.forEach(e => {
            // Relays usually have athlete names like "A, B, C, D"
            const nameStr = e.athlete_name || "";
            const members = nameStr.split(',').map(n => n.trim()).filter(Boolean);
            members.forEach(m => {
                if (!athleteEntries[m]) athleteEntries[m] = [];
                athleteEntries[m].push({ ...e, isRelayLeg: true, relayRef: e });
            });
        });

        // Greedy Selection: Keep picking top entries until limits hit or no more points possible
        const selectedEntries = new Set(); // entry id or unique key
        // const athleteUsage = {}; // name -> count -- merged below


        const allPossibleScoringActions = [];
        individualEntries.forEach(e => {
            allPossibleScoringActions.push({
                type: 'ind',
                entry: e,
                pts: e.potentialPts,
                athlete: e.athlete_name,
                rank: e.tempRank || 999
            });
        });
        relayEntries.forEach(e => {
            const nameStr = e.athlete_name || "";
            const members = nameStr.split(',').map(n => n.trim()).filter(Boolean);
            allPossibleScoringActions.push({
                type: 'rel',
                entry: e,
                pts: e.potentialPts,
                athletes: members,
                rank: e.tempRank || 999
            });
        });

        // Sort actions by points descending, then by rank ascending
        allPossibleScoringActions.sort((a, b) => {
            if (b.pts !== a.pts) return b.pts - a.pts;
            return a.rank - b.rank;
        });

        const activeIndividualChoices = [];
        const activeRelayChoices = [];
        const athleteUsage = {}; // name -> count

        allPossibleScoringActions.forEach(action => {
            if (action.type === 'ind') {
                const usage = athleteUsage[action.athlete] || 0;
                if (usage < eventLimit) {
                    athleteUsage[action.athlete] = usage + 1;
                    activeIndividualChoices.push(action.entry);
                }
            } else {
                const members = action.athletes.filter(m => m && !m.toLowerCase().includes('school') && !m.toLowerCase().includes('relay'));
                if (members.length === 0) {
                    activeRelayChoices.push(action.entry);
                } else {
                    let canFit = true;
                    members.forEach(m => {
                        if ((athleteUsage[m] || 0) >= eventLimit) canFit = false;
                    });
                    if (canFit) {
                        members.forEach(m => {
                            athleteUsage[m] = (athleteUsage[m] || 0) + 1;
                        });
                        activeRelayChoices.push(action.entry);
                    }
                }
            }
        });

        // 4. Re-rank based on optimized selections
        const finalEntries = [...activeIndividualChoices, ...activeRelayChoices];
        const finalGroups = {};
        finalEntries.forEach(e => {
            if (!finalGroups[e.groupTitle]) finalGroups[e.groupTitle] = [];
            finalGroups[e.groupTitle].push(e);
        });

        Object.entries(finalGroups).forEach(([title, results]) => {
            results.sort((a, b) => isBetter(a.mark, b.mark) ? -1 : isBetter(b.mark, a.mark) ? 1 : 0);

            let effectiveRank = 1;
            let validCount = 0;
            let lastValidMark = null;

            for (let i = 0; i < results.length; i++) {
                const p = parseMark(results[i].mark);
                if (!p.valid) {
                    results[i].calculatedRank = null;
                    results[i].optimizedPts = 0;
                    continue;
                }

                if (validCount > 0 && results[i].mark !== lastValidMark) {
                    effectiveRank = validCount + 1;
                }

                results[i].calculatedRank = effectiveRank;

                if (effectiveRank <= scoringRules.length) {
                    // Tie splitting logic
                    let tieCount = 1;
                    let j = i + 1;
                    // Only count ties for VALID marks
                    while (j < results.length && results[j].mark === results[i].mark && parseMark(results[j].mark).valid) {
                        tieCount++;
                        j++;
                    }

                    let pointSum = 0;
                    for (let k = effectiveRank - 1; k < Math.min(scoringRules.length, effectiveRank - 1 + tieCount); k++) {
                        pointSum += scoringRules[k];
                    }

                    const perAthlete = pointSum / tieCount;
                    for (let k = i; k < i + tieCount; k++) {
                        results[k].optimizedPts = perAthlete;
                    }

                    // Increment loop index and validCount by the number of people tied
                    // but we need to handle the loop index increment correctly
                    const jump = tieCount - 1;
                    lastValidMark = results[i].mark;
                    validCount += tieCount;
                    i += jump;
                } else {
                    results[i].optimizedPts = 0;
                    lastValidMark = results[i].mark;
                    validCount++;
                }
            }
        });

        return finalGroups;
    }, [groupedData, showSimulation, filterYear, filterSeason, isBetter]);

    const optimizedTeamScores = useMemo(() => {
        if (!showSimulation) return null;
        if (filterYear === 'All' || filterSeason === 'All') return { incomplete: true };

        const scores = { boys: {}, girls: {} };

        Object.entries(optimizedData).forEach(([groupTitle, results]) => {
            if (results.length === 0) return;
            // Derive gender from event name if not present
            const eventName = results[0].event || "";
            const gender = eventName.toLowerCase().includes('girls') ? 'girls' : 'boys';

            results.forEach(res => {
                if (res.optimizedPts > 0) {
                    const team = res.pvcTeam;
                    if (!scores[gender][team]) scores[gender][team] = { total: 0, breakdown: [] };
                    scores[gender][team].total += res.optimizedPts;
                    scores[gender][team].breakdown.push({
                        event: res.event,
                        athlete: res.athlete_name || "Unknown",
                        mark: res.mark,
                        pts: res.optimizedPts,
                        groupTitle: groupTitle
                    });
                }
            });
        });

        const formatScores = (scoreMap) => Object.entries(scoreMap)
            .sort((a, b) => b[1].total - a[1].total)
            .map(([team, data]) => ({
                team,
                pts: data.total,
                breakdown: data.breakdown.sort((a, b) => b.pts - a.pts)
            }));

        return {
            boys: formatScores(scores.boys),
            girls: formatScores(scores.girls)
        };
    }, [optimizedData, showSimulation, filterYear, filterSeason]);

    return (
        <div className="analyzer-container">
            <div className="analyzer-header">
                <h2>PVC Championships Simulator</h2>
                <p className="subtitle">Simulating PVC Small Schools Championships using all-time best performances</p>
            </div>

            <div className="analyzer-controls">
                <div className="filter-bar analyzer-filters">
                    <div className="filter-group">
                        <label>Year</label>
                        <select value={filterYear} onChange={e => setFilterYear(e.target.value)}>
                            <option value="All">All Years</option>
                            {years.map(y => <option key={y} value={y}>{y}</option>)}
                        </select>
                    </div>
                    <div className="filter-group">
                        <label>Season</label>
                        <select value={filterSeason} onChange={e => setFilterSeason(e.target.value)}>
                            <option value="All">All Seasons</option>
                            {seasons.map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                    </div>
                    <div className="simulation-actions">
                        <button
                            className={`simulate-btn ${showSimulation ? 'active' : ''}`}
                            onClick={() => setShowSimulation(!showSimulation)}
                        >
                            {showSimulation ? '📊 Show Raw Results' : '🏆 Simulate Meet'}
                        </button>
                    </div>
                    <div className="record-count">{filteredData.length} Results</div>
                </div>
            </div>

            {showSimulation && optimizedTeamScores && (
                <div className="simulation-overlay">
                    {optimizedTeamScores.incomplete ? (
                        <div className="meet-leaderboard warn">
                            <p>⚠️ <strong>Please select a specific Year and Season</strong> to view the Meet Simulation.</p>
                        </div>
                    ) : (
                        <div className="leaderboards-container">
                            {(() => {
                                const foundEvents = new Set();
                                Object.values(optimizedData).forEach(r => {
                                    if (r.length > 0) foundEvents.add(r[0].event);
                                });

                                // Group expected events by likely gender if possible, but simplest is just check existence
                                // We'll just look for missing generic event types
                                const missingEvents = Object.entries(EVENT_ALIASES).filter(([canonical, aliases]) => {
                                    // Return true if NONE of the aliases are found in 'foundEvents'
                                    return !aliases.some(alias => {
                                        return Array.from(foundEvents).some(found => found.toLowerCase().includes(alias.toLowerCase()));
                                    });
                                }).map(([canonical]) => canonical);

                                if (missingEvents.length > 0) {
                                    return (
                                        <div className="missing-events-warning" style={{ gridColumn: '1 / -1', marginBottom: '1rem', padding: '1rem', background: '#fff3cd', borderRadius: '8px', border: '1px solid #ffeeba', color: '#856404' }}>
                                            ⚠️ <strong>Missing Events:</strong> No results found for: {missingEvents.join(', ')}.
                                        </div>
                                    );
                                }
                                return null;
                            })()}
                            <div className="meet-leaderboard boys">
                                <h3>🏃‍♂️ Boys Team Standings</h3>
                                <div className="leaderboard-grid">
                                    {optimizedTeamScores.boys.map((ts, idx) => (
                                        <div key={ts.team} className="leaderboard-wrapper">
                                            <div
                                                className={`leaderboard-item rank-${idx + 1} ${expandedTeams[`${ts.team}-boys`] ? 'expanded' : ''}`}
                                                onClick={() => setExpandedTeams(prev => ({ ...prev, [`${ts.team}-boys`]: !expandedTeams[`${ts.team}-boys`] }))}
                                            >
                                                <span className="team-rank">{idx + 1}</span>
                                                <span className="team-name">{ts.team}</span>
                                                <span className="team-points">{ts.pts.toFixed(1)}</span>
                                                <span className="expand-icon">{expandedTeams[`${ts.team}-boys`] ? '▼' : '▶'}</span>
                                            </div>
                                            {expandedTeams[`${ts.team}-boys`] && (
                                                <div className="team-breakdown">
                                                    {ts.breakdown.map((item, i) => (
                                                        <div key={i} className="breakdown-row">
                                                            <span
                                                                className="b-event clickable-event"
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    scrollToEvent(item.groupTitle);
                                                                }}
                                                                title={`Click to view results for ${item.event}`}
                                                            >
                                                                {item.event}
                                                            </span>
                                                            <span className="b-athlete">{item.athlete}</span>
                                                            <span className="b-pts">+{item.pts.toFixed(1)}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                    {optimizedTeamScores.boys.length === 0 && <p className="empty-scores">No results.</p>}
                                </div>
                            </div>
                            <div className="meet-leaderboard girls">
                                <h3>🏃‍♀️ Girls Team Standings</h3>
                                <div className="leaderboard-grid">
                                    {optimizedTeamScores.girls.map((ts, idx) => (
                                        <div key={ts.team} className="leaderboard-wrapper">
                                            <div
                                                className={`leaderboard-item rank-${idx + 1} ${expandedTeams[`${ts.team}-girls`] ? 'expanded' : ''}`}
                                                onClick={() => setExpandedTeams(prev => ({ ...prev, [`${ts.team}-girls`]: !expandedTeams[`${ts.team}-girls`] }))}
                                            >
                                                <span className="team-rank">{idx + 1}</span>
                                                <span className="team-name">{ts.team}</span>
                                                <span className="team-points">{ts.pts.toFixed(1)}</span>
                                                <span className="expand-icon">{expandedTeams[`${ts.team}-girls`] ? '▼' : '▶'}</span>
                                            </div>
                                            {expandedTeams[`${ts.team}-girls`] && (
                                                <div className="team-breakdown">
                                                    {ts.breakdown.map((item, i) => (
                                                        <div key={i} className="breakdown-row">
                                                            <span
                                                                className="b-event clickable-event"
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    scrollToEvent(item.groupTitle);
                                                                }}
                                                                title={`Click to view results for ${item.event}`}
                                                            >
                                                                {item.event}
                                                            </span>
                                                            <span className="b-athlete">{item.athlete}</span>
                                                            <span className="b-pts">+{item.pts.toFixed(1)}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                    {optimizedTeamScores.girls.length === 0 && <p className="empty-scores">No results.</p>}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}

            <div className="analyzer-results">
                {Object.keys(optimizedData).length > 0 ? (
                    Object.entries(optimizedData).map(([groupTitle, results]) => (
                        <div key={groupTitle} id={`event-${groupTitle.replace(/[^a-z0-9]/gi, '-')}`} className="event-section">
                            <h3 className="event-title">
                                {results[0].event}
                                <span className="event-meta">{results[0].derivedType} {results[0].derivedYear}</span>
                            </h3>
                            <table className="performance-table">
                                <thead>
                                    <tr>
                                        <th>Rank</th>
                                        <th>Name</th>
                                        <th>Team</th>
                                        <th>Mark</th>
                                        <th>Date</th>
                                        {showSimulation && <th>Points</th>}
                                    </tr>
                                </thead>
                                <tbody>
                                    {results.map((res, idx) => (
                                        <tr key={idx}>
                                            <td>{res.calculatedRank}</td>
                                            <td className="athlete-name-cell">{res.athlete_name}</td>
                                            <td>{res.pvcTeam}</td>
                                            <td className="mark-cell">{res.mark}</td>
                                            <td>{res.date ? res.date.split('T')[0] : 'N/A'}</td>
                                            {showSimulation && (
                                                <td className="points-cell">
                                                    {res.optimizedPts > 0 ? `+${res.optimizedPts.toFixed(1)}` : '-'}
                                                </td>
                                            )}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ))
                ) : (
                    <div className="empty-state">
                        <p>No results match your filters.</p>
                    </div>
                )}
            </div>
        </div>
    );
}

export default PVCSimulator;
