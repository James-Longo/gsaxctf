import React, { useState, useMemo } from 'react';
import { parseMark, normalizeEvent } from './utils';

function mean(arr) {
    return arr.reduce((a, b) => a + b, 0) / arr.length;
}

function stdDev(arr) {
    const m = mean(arr);
    return Math.sqrt(mean(arr.map(x => (x - m) ** 2)));
}



function fmtSecs(secs) {
    if (!secs || isNaN(secs)) return '-';
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    if (m === 0) return s.toFixed(2);
    return `${m}:${s < 10 ? '0' : ''}${s.toFixed(2)}`;
}

const SEGMENT_COLORS = ['#4a90d9', '#5ba55a', '#d97b4a', '#9b59b6', '#c0392b', '#1abc9c', '#e67e22', '#2980b9'];

const SplitExplorer = ({ performances, loading }) => {
    const [selectedEvent, setSelectedEvent] = useState('');
    const [filterTeam, setFilterTeam] = useState('All');
    const [selectedLapCount, setSelectedLapCount] = useState('');

    const eventsWithSplits = useMemo(() => {
        const map = {};
        performances.forEach(p => {
            if (!p.splits || p.splits.length <= 1) return;
            const ev = normalizeEvent(p.event);
            if (!map[ev]) map[ev] = { count: 0, lapCounts: {} };
            map[ev].count++;
            const lc = p.splits.length;
            map[ev].lapCounts[lc] = (map[ev].lapCounts[lc] || 0) + 1;
        });
        return Object.entries(map)
            .sort((a, b) => b[1].count - a[1].count)
            .map(([ev, d]) => {
                const lapCounts = Object.entries(d.lapCounts)
                    .sort((a, b) => b[1] - a[1])
                    .map(([lc]) => parseInt(lc));
                return { event: ev, count: d.count, lapCounts };
            });
    }, [performances]);

    const currentEvent = selectedEvent || eventsWithSplits[0]?.event || '';
    const currentEventData = eventsWithSplits.find(e => e.event === currentEvent);
    const availableLapCounts = currentEventData?.lapCounts || [];
    const currentLapCount = parseInt(selectedLapCount) || availableLapCounts[0] || 0;

    const teams = useMemo(() => {
        const s = new Set(
            performances
                .filter(p => p.splits?.length === currentLapCount && normalizeEvent(p.event) === currentEvent)
                .map(p => p.team)
                .filter(Boolean)
        );
        return ['All', ...Array.from(s).sort()];
    }, [performances, currentEvent, currentLapCount]);

    const parsed = useMemo(() => {
        if (!currentLapCount) return [];
        return performances.flatMap(p => {
            if (!p.splits || p.splits.length !== currentLapCount) return [];
            if (normalizeEvent(p.event) !== currentEvent) return [];
            if (filterTeam !== 'All' && p.team !== filterTeam) return [];
            const total = parseMark(p.mark);
            if (!total.valid || total.value <= 0) return [];
            const splitSecs = p.splits.map(s => parseMark(s).value);
            if (splitSecs.some(s => !s)) return [];
            const ratios = splitSecs.map(s => s / total.value);
            return [{ totalSecs: total.value, splitSecs, ratios }];
        });
    }, [performances, currentEvent, filterTeam, currentLapCount]);

    const stats = useMemo(() => {
        if (!parsed.length) return null;
        const sorted = [...parsed].sort((a, b) => a.totalSecs - b.totalSecs);
        const topN = Math.max(1, Math.floor(sorted.length * 0.10));
        const topGroup = sorted.slice(0, topN);
        const botGroup = sorted.slice(-topN);

        const laps = Array.from({ length: currentLapCount }, (_, i) => {
            const allRatios = parsed.map(p => p.ratios[i]);
            const allTimes = parsed.map(p => p.splitSecs[i]);
            const topRatios = topGroup.map(p => p.ratios[i]);
            const botRatios = botGroup.map(p => p.ratios[i]);
            return {
                lap: i + 1,
                avgTime: mean(allTimes),
                avgRatio: mean(allRatios),
                topRatio: mean(topRatios),
                botRatio: mean(botRatios),
                stdRatio: stdDev(allRatios),
            };
        });

        return { laps, n: parsed.length, topN };
    }, [parsed, currentLapCount]);

    const isRelay = currentEvent.toLowerCase().includes('relay');
    const lapLabel = i => isRelay ? `Leg ${i}` : `Lap ${i}`;

    if (loading) return <div className="loading-state">Loading split data...</div>;
    if (!eventsWithSplits.length) return <div className="loading-state">No split data available.</div>;

    return (
        <div className="split-explorer">
            <h2>Split Explorer</h2>


            <div className="filter-bar">
                <div className="filter-group">
                    <label>Event</label>
                    <select value={currentEvent} onChange={e => setSelectedEvent(e.target.value)}>
                        {eventsWithSplits.map(({ event, count }) => (
                            <option key={event} value={event}>{event} ({count})</option>
                        ))}
                    </select>
                </div>
                <div className="filter-group">
                    <label>Team</label>
                    <select value={filterTeam} onChange={e => setFilterTeam(e.target.value)}>
                        {teams.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                </div>
                {availableLapCounts.length > 1 && (
                    <div className="filter-group">
                        <label>Split Count</label>
                        <select value={currentLapCount} onChange={e => setSelectedLapCount(e.target.value)}>
                            {availableLapCounts.map(lc => (
                                <option key={lc} value={lc}>{lc} splits</option>
                            ))}
                        </select>
                    </div>
                )}
            </div>

            {!stats ? (
                <p className="no-data">No valid split data for this selection.</p>
            ) : (
                <div className="split-stats">
                    <p className="stats-summary">
                        {stats.n} performances &mdash; top {stats.topN} (10%) used for fast profile
                    </p>

                    <div className="pacing-profile-section">
                        <h3>Pacing Profile</h3>
                        <p className="profile-explainer">Each block represents one {isRelay ? 'leg' : 'lap'} as a share of total race time.</p>
                        <div className="pacing-profile">
                            {[
                                { label: 'All athletes', ratios: stats.laps.map(l => l.avgRatio), fast: false },
                                { label: 'Fast 10%', ratios: stats.laps.map(l => l.topRatio), fast: true },
                            ].map(({ label, ratios, fast }) => (
                                <div key={label} className="profile-row">
                                    <span className="profile-label">{label}</span>
                                    <div className="profile-bar-track">
                                        {ratios.map((ratio, i) => (
                                            <div
                                                key={i}
                                                className="profile-segment"
                                                style={{
                                                    width: `${ratio * 100}%`,
                                                    backgroundColor: SEGMENT_COLORS[i % SEGMENT_COLORS.length],
                                                    opacity: fast ? 1 : 0.55,
                                                }}
                                                title={`${lapLabel(i + 1)}: ${(ratio * 100).toFixed(2)}%`}
                                            >
                                                {ratio > 0.07 && (
                                                    <span className="profile-segment-label">{(ratio * 100).toFixed(1)}%</span>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))}
                            {(() => {
                                const avgRatios = stats.laps.map(l => l.avgRatio);
                                const rawGaps = stats.laps.map(l => l.topRatio - l.avgRatio);
                                const maxAbs = Math.max(...rawGaps.map(Math.abs), 0.001);
                                const sumAbs = rawGaps.reduce((acc, g) => acc + Math.abs(g), 0);
                                
                                const hexToRgb = (hex) => {
                                    const r = parseInt(hex.slice(1, 3), 16);
                                    const g = parseInt(hex.slice(3, 5), 16);
                                    const b = parseInt(hex.slice(5, 7), 16);
                                    return `${r}, ${g}, ${b}`;
                                };

                                return (
                                    <div className="profile-row">
                                        <span className="profile-label">Top 10% Δ</span>
                                        <div className="profile-bar-track">
                                            {avgRatios.map((_, i) => {
                                                const g = rawGaps[i];
                                                const widthPercent = sumAbs > 0 ? (Math.abs(g) / sumAbs) * 100 : 0;
                                                const intensity = Math.min(Math.abs(g) / maxAbs, 1);
                                                const hex = SEGMENT_COLORS[i % SEGMENT_COLORS.length];
                                                const bg = `rgba(${hexToRgb(hex)}, ${0.15 + intensity * 0.85})`;
                                                return (
                                                    <div
                                                        key={i}
                                                        className="profile-segment"
                                                        style={{ width: `${widthPercent}%`, backgroundColor: bg }}
                                                        title={`${lapLabel(i + 1)}: ${g >= 0 ? '+' : ''}${(g * 100).toFixed(2)}%`}
                                                    >
                                                        {widthPercent > 7 && (
                                                            <span className="profile-segment-label">
                                                                {g >= 0 ? '+' : ''}{(g * 100).toFixed(1)}%
                                                            </span>
                                                        )}
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </div>
                                );
                            })()}
                            <div className="profile-legend">
                                {stats.laps.map((lap, i) => (
                                    <span key={i} className="legend-item">
                                        <span className="legend-dot" style={{ backgroundColor: SEGMENT_COLORS[i % SEGMENT_COLORS.length] }} />
                                        {lapLabel(lap.lap)}
                                    </span>
                                ))}
                            </div>
                        </div>

                    </div>

                </div>
            )}
        </div>
    );
};

export default SplitExplorer;
