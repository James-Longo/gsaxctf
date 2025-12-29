import React, { useState, useMemo } from 'react';
import { parseMark } from './utils';

const formatImprovement = (pNew, pOld) => {
    const diff = pOld.value - pNew.value; // For time: positive means improved (new is smaller). For distance: negative means improved (new is larger).

    if (pNew.isTime) {
        // Time: positive diff = improved
        const seconds = (pOld.value - pNew.value).toFixed(2);
        return `-${seconds}s`;
    } else {
        // Distance: new - old = improvement
        const inches = (pNew.value - pOld.value).toFixed(2);
        return `+${inches}"`;
    }
}

const PRPopCalculator = ({ performances, selectedTeam, isBetter }) => {
    const [selectedMeet, setSelectedMeet] = useState('latest');

    const { processedMeets, popResults, totalPrCount, currentMeetName } = useMemo(() => {
        if (!performances || performances.length === 0) return { processedMeets: [], popResults: [], totalPrCount: 0, currentMeetName: '' };

        // 1. First Pass: Find earliest dates for isFirstTime logic
        const firstDatesMap = {};
        const bestsMap = {};

        performances.forEach(p => {
            let type = p.season || 'Unknown';
            if (p.season) {
                const match = p.season.match(/^(\d{4})\s+(.*)$/);
                if (match) type = match[2];
            }

            const key = `${p.athlete_id}|${p.event}|${type}`;
            const pDateStr = p.date || '1970-01-01';
            if (!firstDatesMap[key] || new Date(pDateStr) < new Date(firstDatesMap[key])) {
                firstDatesMap[key] = pDateStr;
            }

            // Track bests overall for PR check
            if (!bestsMap[key] || isBetter(p.mark, bestsMap[key])) {
                bestsMap[key] = p.mark;
            }
        });

        // 2. Identify all meets for the selected team
        const teamMeets = Array.from(new Set(
            performances
                .filter(p => p.team === selectedTeam && p.date)
                .map(p => {
                    const dPart = p.date.includes('T') ? p.date.split('T')[0] : p.date;
                    return JSON.stringify({ name: p.meet_name, date: dPart, fullDate: p.date });
                })
        )).map(s => JSON.parse(s))
            .sort((a, b) => new Date(b.fullDate) - new Date(a.fullDate));

        if (teamMeets.length === 0) return { processedMeets: [], popResults: [], totalPrCount: 0, currentMeetName: '' };

        const targetMeet = selectedMeet === 'latest' ? teamMeets[0] : teamMeets.find(m => `${m.name}|${m.date}` === selectedMeet);
        const actualMeetName = targetMeet ? targetMeet.name : '';
        const actualMeetDate = targetMeet ? targetMeet.date : '';

        // 3. Find PR Pops for this meet
        // First, filter for ONLY the best performance of the day per athlete/event
        const meetPerformances = performances.filter(p =>
            p.team === selectedTeam &&
            p.meet_name === actualMeetName &&
            p.date && (p.date.includes(actualMeetDate) || p.date.startsWith(actualMeetDate))
        );

        const bestOfMeetDay = {};
        meetPerformances.forEach(p => {
            const key = `${p.athlete_id}|${p.event}`;
            if (!bestOfMeetDay[key] || isBetter(p.mark, bestOfMeetDay[key].mark)) {
                bestOfMeetDay[key] = p;
            }
        });

        const pops = Object.values(bestOfMeetDay).filter(p => {
            let type = p.season || 'Unknown';
            if (p.season) {
                const match = p.season.match(/^(\d{4})\s+(.*)$/);
                if (match) type = match[2];
            }

            // Find all historical performances for this athlete/event/type BEFORE THIS DAY
            const prevPerformances = performances.filter(prev =>
                prev.athlete_id === p.athlete_id &&
                prev.event === p.event &&
                new Date(prev.date.split('T')[0]) < new Date(actualMeetDate)
            );

            if (prevPerformances.length === 0) return false; // It's a first-time PR, not a Pop

            let bestPrev = null;
            prevPerformances.forEach(prev => {
                if (!bestPrev || isBetter(prev.mark, bestPrev)) {
                    bestPrev = prev.mark;
                }
            });

            // Must be STRICTLY BETTER than the best mark from previous days
            return bestPrev && isBetter(p.mark, bestPrev);
        });

        // Group by athlete with full details
        const groupedPops = pops.reduce((acc, p) => {
            const athleteName = p.athlete_name;
            if (!acc[athleteName]) acc[athleteName] = [];

            let pType = p.season || 'Unknown';
            if (p.season) {
                const match = p.season.match(/^(\d{4})\s+(.*)$/);
                if (match) pType = match[2];
            }

            // Find the best previous mark
            const prevPerformances = performances.filter(prev =>
                prev.athlete_id === p.athlete_id &&
                prev.event === p.event &&
                new Date(prev.date) < new Date(p.date)
                // We could also filter by pType but PR usually spans years in same event
            );

            let oldBest = null;
            prevPerformances.forEach(prev => {
                if (!oldBest || isBetter(prev.mark, oldBest)) {
                    oldBest = prev.mark;
                }
            });

            if (oldBest) {
                const pNew = parseMark(p.mark);
                const pOld = parseMark(oldBest);
                const improvement = (pNew.valid && pOld.valid) ? formatImprovement(pNew, pOld) : '';

                acc[athleteName].push({
                    event: p.event,
                    newPR: p.mark,
                    oldPR: oldBest,
                    improvement: improvement
                });
            }

            return acc;
        }, {});

        const totalPrs = Object.values(groupedPops).reduce((sum, events) => sum + events.length, 0);

        return {
            processedMeets: teamMeets,
            popResults: Object.entries(groupedPops).sort((a, b) => a[0].localeCompare(b[0])),
            totalPrCount: totalPrs,
            currentMeetName: actualMeetName
        };
    }, [performances, selectedTeam, selectedMeet, isBetter]);

    if (!selectedTeam || selectedTeam === 'All') {
        return <div className="pr-pop-container">Please select a specific team to use the PR Pop Calculator.</div>;
    }

    return (
        <div className="pr-pop-container">
            <div className="pr-pop-header">
                <h2>PR Pop Calculator</h2>
                <div className="meet-selector">
                    <label>Select Meet: </label>
                    <select
                        value={selectedMeet}
                        onChange={(e) => setSelectedMeet(e.target.value)}
                    >
                        <option value="latest">Latest Meet</option>
                        {processedMeets.map(m => (
                            <option key={`${m.name}|${m.date}`} value={`${m.name}|${m.date}`}>
                                {m.name} ({m.date})
                            </option>
                        ))}
                    </select>
                </div>
            </div>

            <div className="pr-pop-content">
                {popResults.length > 0 ? (
                    <div className="pop-list">
                        <h3>🎉 PR Pops for {currentMeetName}</h3>
                        <p className="pop-count">Total Pops: {totalPrCount}</p>
                        <div className="pop-grid">
                            {popResults.map(([athlete, events]) => (
                                <div key={athlete} className="pop-card">
                                    <div className="pop-athlete">{athlete}</div>
                                    <div className="pop-events">
                                        {events.map((res, idx) => (
                                            <div key={idx} className="pop-result-row">
                                                <span className="pop-event-name">{res.event}</span>
                                                <span className="pop-marks">
                                                    <span className="pop-new">{res.newPR}</span>
                                                    <span className="pop-old"> (from {res.oldPR})</span>
                                                </span>
                                                <span className="pop-delta">{res.improvement}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                ) : (
                    <div className="no-pops">
                        <p>No PR Pops found for this meet.</p>
                        <p className="hint">(First-time competitors are excluded)</p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default PRPopCalculator;
