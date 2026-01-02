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
        fetch('http://localhost:8000/meet-data')
            .then(res => res.json())
            .then(data => {
                setData(data);
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
