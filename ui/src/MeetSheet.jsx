import React, { useState, useEffect } from 'react';

const REGULAR_SEASON_ORDER = [
    "Girls 4X800m Relay", "Boys 4X800m Relay",
    "55 M. Hurdles Prelim Girls", "55 M. Hurdles Prelim Boys",
    "55 M. Hurdles Final Girls", "55 M. Hurdles Final Boys",
    "55 M. Dash Prelim Girls", "55 M. Dash Prelim Boys",
    "55 M. Dash Final Girls", "55 M. Dash Final Boys",
    "One Mile Girls", "One Mile Boys",
    "400 M. Run Girls", "400 M. Run Boys",
    "800 M. Run Girls", "800 M. Run Boys",
    "200 M. Dash Girls", "200 M. Dash Boys",
    "Two Mile Run Girls", "Two Mile Run Boys",
    "4X200m Relay Girls", "4X200m Relay Boys",
    "FIELD EVENTS",
    "Shot Put Boys", "High Jump Boys", "Long Jump Girls", "Pole Vault Girls",
    "Long Jump Boys", "High Jump Girls", "Shot Put Girls", "Pole Vault Boys",
    "Triple Jump Girls", "Triple Jump Boys"
];

const CHAMPIONSHIP_SEASON_ORDER = [
    "Girls 4X800m Relay", "Boys 4X800m Relay",
    "55 M. Hurdles Prelim Girls", "55 M. Hurdles Prelim Boys",
    "55 M. Dash Prelim Girls", "55 M. Dash Prelim Boys",
    "55 M. Hurdles Final Girls", "55 M. Hurdles Final Boys",
    "55 M. Dash Final Girls", "55 M. Dash Final Boys",
    "One Mile Girls", "One Mile Boys",
    "400 M. Run Girls", "400 M. Run Boys",
    "800 M. Run Girls", "800 M. Run Boys",
    "200 M. Dash Girls", "200 M. Dash Boys",
    "Two Mile Run Girls", "Two Mile Run Boys",
    "4X200m Relay Girls", "4X200m Relay Boys",
    "FIELD EVENTS",
    "Shot Put Boys", "High Jump Boys", "Long Jump Girls", "Pole Vault Girls",
    "Long Jump Boys", "High Jump Girls", "Shot Put Girls", "Pole Vault Boys",
    "Triple Jump Girls", "Triple Jump Boys"
];

export default function MeetSheet() {
    const [data, setData] = useState({ girls: [], boys: [] });
    const [loading, setLoading] = useState(true);
    const [seasonType, setSeasonType] = useState("indoor_regular");
    const [meetName, setMeetName] = useState("");

    useEffect(() => {
        const sheet_url = "https://docs.google.com/spreadsheets/d/1iWUERpoQgetunqBOCZM2ep8HOhdX1RcLw59uJaA5hCY/export?format=csv";
        fetch(sheet_url)
            .then(res => res.text())
            .then(csv_data => {
                const lines = csv_data.split('\n');

                const event_map = {
                    "4x8": "4X800m Relay",
                    "55H": "55 M. Hurdles",
                    "55": "55 M. Dash",
                    "1mi": "One Mile",
                    "400": "400 M. Run",
                    "800": "800 M. Run",
                    "200": "200 M. Dash",
                    "2mi": "Two Mile Run",
                    "4x2": "4X200m Relay",
                    "LJ": "Long Jump",
                    "TJ": "Triple Jump",
                    "HJ": "High Jump",
                    "PV": "Pole Vault",
                    "SP": "Shot Put"
                };

                const parseTable = (linesChunk) => {
                    if (!linesChunk) return [];
                    let header = null;
                    let dataStart = 0;
                    for (let i = 0; i < linesChunk.length; i++) {
                        if (linesChunk[i].includes("4x8") && linesChunk[i].includes("55H")) {
                            header = linesChunk[i].split(',');
                            dataStart = i + 1;
                            break;
                        }
                    }
                    if (!header) return [];
                    const results = [];
                    for (let i = dataStart; i < linesChunk.length; i++) {
                        const cols = linesChunk[i].split(',');
                        if (!cols || !cols[0].trim() || cols[0].trim() === "Total") continue;
                        const athleteName = cols[0].trim();
                        const athleteEvents = [];
                        for (let j = 1; j < header.length; j++) {
                            if (j >= cols.length) continue;
                            const val = cols[j].trim().toLowerCase();
                            if (["x", "y", "?", "(y)", "(x)"].includes(val)) {
                                const eventAbbrev = header[j].trim();
                                if (event_map[eventAbbrev]) {
                                    athleteEvents.push({
                                        name: event_map[eventAbbrev],
                                        role: val
                                    });
                                }
                            }
                        }
                        if (athleteEvents.length > 0) {
                            results.push({ name: athleteName, events: athleteEvents });
                        }
                    }
                    return results;
                };

                let girlsChunk = [];
                let boysChunk = [];
                let currentChunk = girlsChunk;
                let seenFirstTable = false;
                lines.forEach(line => {
                    if (line.includes("4x8") && line.includes("55H")) {
                        if (seenFirstTable) currentChunk = boysChunk;
                        seenFirstTable = true;
                    }
                    currentChunk.push(line);
                });

                setData({
                    girls: parseTable(girlsChunk),
                    boys: parseTable(boysChunk)
                });
                setLoading(false);
            })
            .catch(err => {
                console.error('Error fetching meet data:', err);
                setLoading(false);
            });
    }, []);

    if (loading) return <div className="loading">Loading meet data...</div>;

    const isChampionship = seasonType.includes('championship');
    const isOutdoor = seasonType.includes('outdoor');
    const order = isChampionship ? CHAMPIONSHIP_SEASON_ORDER : REGULAR_SEASON_ORDER;

    // TODO: Outdoor data handling when available
    if (isOutdoor) {
        // For now, outdoor is TODO
    }

    const getAthletesForEvent = (eventName) => {
        const isGirls = eventName.toLowerCase().includes('girls');
        const isBoys = eventName.toLowerCase().includes('boys');

        // Normalize event name for matching
        const baseEvent = eventName
            .replace('Girls', '')
            .replace('Boys', '')
            .replace('Prelim', '')
            .replace('Final', '')
            .trim();

        const list = isGirls ? data.girls : (isBoys ? data.boys : []);

        return list.filter(athlete =>
            athlete.events.some(e => baseEvent.includes(e.name) || e.name.includes(baseEvent))
        ).map(a => {
            const eventInfo = a.events.find(e => baseEvent.includes(e.name) || e.name.includes(baseEvent));
            return { name: a.name, role: eventInfo.role };
        });
    };

    const handlePrint = () => {
        const name = prompt("Enter Meet Name:");
        if (name !== null) {
            const originalTitle = document.title;
            const printTitle = name || "Meet Sheet";
            document.title = printTitle;
            setMeetName(name);

            // Small timeout to allow state to update before print dialog
            setTimeout(() => {
                window.print();
                // Restore title after print dialog closes
                document.title = originalTitle;
            }, 100);
        }
    };

    return (
        <div className="meet-sheet-container">
            <div className="meet-sheet-controls no-print">
                <div className="toggle-group">
                    <label>Season Type:</label>
                    <select
                        className="season-select"
                        value={seasonType}
                        onChange={(e) => setSeasonType(e.target.value)}
                    >
                        <option value="indoor_regular">Indoor Regular</option>
                        <option value="indoor_championship">Indoor Championship</option>
                        <option value="outdoor_regular">Outdoor Regular (TODO)</option>
                        <option value="outdoor_championship">Outdoor Championship (TODO)</option>
                    </select>
                </div>
                <button className="print-btn" onClick={handlePrint}>Print Meet Sheet</button>
            </div>

            <div className="meet-sheet-content">
                <header className="meet-sheet-header">
                    {meetName ? (
                        <h1 className="meet-title-print">{meetName}</h1>
                    ) : (
                        <h1 className="no-print">Meet Sheet</h1>
                    )}
                    <p className="no-print">
                        {seasonType.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}
                    </p>
                </header>

                <div className="events-grid-3col">
                    {(() => {
                        const trackEvents = [];
                        const fieldEvents = [];
                        let isCollectingField = false;

                        order.forEach((event) => {
                            if (event === "FIELD EVENTS") {
                                isCollectingField = true;
                                return;
                            }
                            const athletes = getAthletesForEvent(event);
                            const isRelay = event.toLowerCase().includes('relay');

                            const element = (idx) => (
                                <div key={event} className="event-block">
                                    <div className="event-name">{idx ? `${idx}. ` : ""}{event}</div>
                                    <div className="athlete-list">
                                        {athletes.length > 0 ? (
                                            [...athletes].sort((a, b) => {
                                                if (!isRelay) return 0;
                                                const roles = { 'x': 1, 'y': 2, '(x)': 3, '(y)': 3 };
                                                return (roles[a.role] || 9) - (roles[b.role] || 9);
                                            }).map((a, i) => {
                                                let label = "";
                                                if (isRelay) {
                                                    if (a.role === 'x') label = " (A)";
                                                    else if (a.role === 'y') label = " (B)";
                                                    else if (a.role === '(x)' || a.role === '(y)') label = " (Alt)";
                                                }
                                                const isFinal55 = event.includes("55") && event.includes("Final");
                                                return (
                                                    <div key={i} className={`athlete-name ${isFinal55 ? 'tentative' : ''}`}>
                                                        {a.name}{label}
                                                    </div>
                                                );
                                            })
                                        ) : (
                                            <div className="no-athletes">No entries</div>
                                        )}
                                    </div>
                                </div>
                            );

                            if (isCollectingField) fieldEvents.push(element);
                            else trackEvents.push(element);
                        });

                        const numTrackRows = Math.ceil(trackEvents.length / 2);
                        const col1 = trackEvents.slice(0, numTrackRows);
                        const col2 = trackEvents.slice(numTrackRows);
                        const col3 = fieldEvents;

                        return (
                            <React.Fragment>
                                <div className="sheet-column">
                                    {col1.map((el, i) => el(i + 1))}
                                </div>
                                <div className="sheet-column">
                                    {col2.map((el, i) => el(numTrackRows + i + 1))}
                                </div>
                                <div className="sheet-column">
                                    {col3.map((el) => el(null))}
                                </div>
                            </React.Fragment>
                        );
                    })()}
                </div>
            </div>
        </div>
    );
}
