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
    const [isChampionship, setIsChampionship] = useState(false);

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
                            if (["x", "y", "?", "(y)"].includes(val)) {
                                const eventAbbrev = header[j].trim();
                                if (event_map[eventAbbrev]) {
                                    athleteEvents.push(event_map[eventAbbrev]);
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

    const order = isChampionship ? CHAMPIONSHIP_SEASON_ORDER : REGULAR_SEASON_ORDER;

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
            athlete.events.some(e => baseEvent.includes(e) || e.includes(baseEvent))
        ).map(a => a.name);
    };

    const handlePrint = () => {
        window.print();
    };

    return (
        <div className="meet-sheet-container">
            <div className="meet-sheet-controls no-print">
                <div className="toggle-group">
                    <label>Season Type:</label>
                    <button
                        className={`toggle-btn ${!isChampionship ? 'active' : ''}`}
                        onClick={() => setIsChampionship(false)}
                    >
                        Regular
                    </button>
                    <button
                        className={`toggle-btn ${isChampionship ? 'active' : ''}`}
                        onClick={() => setIsChampionship(true)}
                    >
                        Championship
                    </button>
                </div>
                <button className="print-btn" onClick={handlePrint}>Print Meet Sheet</button>
            </div>

            <div className="meet-sheet-content">
                <header className="meet-sheet-header">
                    <h1>Meet Sheet</h1>
                    <p>{isChampionship ? 'Championship Season' : 'Regular Season'}</p>
                </header>

                <div className="events-grid">
                    {order.map((event, idx) => {
                        if (event === "FIELD EVENTS") {
                            return <div key={idx} className="field-events-divider"><h2>Field Events</h2></div>;
                        }

                        const athletes = getAthletesForEvent(event);
                        if (athletes.length === 0 && !event.includes('Relay')) return null;

                        return (
                            <div key={idx} className="event-block">
                                <div className="event-name">{event}</div>
                                <div className="athlete-list">
                                    {athletes.length > 0 ? (
                                        athletes.map((a, i) => <div key={i} className="athlete-name">{a}</div>)
                                    ) : (
                                        <div className="no-athletes">No entries</div>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
