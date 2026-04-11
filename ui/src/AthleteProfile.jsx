
import React, { useMemo } from 'react';
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    Scatter
} from 'recharts';
import { parseMark } from './utils';
import './App.css';

const AthleteProfile = ({ performances, selectedAthlete }) => {
    const eventGroups = useMemo(() => {
        if (!performances) return {};

        const groups = {};
        performances.forEach(p => {
            const groupKey = p.event;

            if (!groups[groupKey]) groups[groupKey] = [];

            const parsed = parseMark(p.mark);
            if (parsed.valid) {
                groups[groupKey].push({
                    ...p,
                    numericValue: parsed.value,
                    isTime: parsed.isTime
                });
            }
        });

        // Calculate stats and prepare chart data for each event
        const processedGroups = {};
        Object.keys(groups).forEach(event => {
            const data = groups[event].sort((a, b) => new Date(a.date) - new Date(b.date));
            if (data.length === 0) return;

            const values = data.map(d => d.numericValue);
            const isTime = data[0].isTime;

            // Basic Stats
            const best = isTime ? Math.min(...values) : Math.max(...values);
            const sortedValues = [...values].sort((a, b) => a - b);
            const median = sortedValues[Math.floor(sortedValues.length / 2)];

            const mean = values.reduce((a, b) => a + b, 0) / values.length;
            const sd = Math.sqrt(values.map(x => Math.pow(x - mean, 2)).reduce((a, b) => a + b, 0) / values.length);

            // Group by year for multi-line chart
            const yearGroups = {};
            data.forEach(d => {
                const year = d.derivedYear || d.year;
                if (!yearGroups[year]) yearGroups[year] = { points: [] };

                const ts = new Date(d.date).getTime();
                yearGroups[year].points.push({ ...d, timestamp: ts });
            });

            // Calculate trends using timestamp
            Object.keys(yearGroups).forEach(year => {
                const pts = yearGroups[year].points;
                if (pts.length < 2) {
                    yearGroups[year].trend = pts;
                    return;
                }

                const n = pts.length;
                const sumX = pts.reduce((s, p) => s + p.timestamp, 0);
                const sumY = pts.reduce((s, p) => s + p.numericValue, 0);
                const sumXX = pts.reduce((s, p) => s + p.timestamp ** 2, 0);
                const sumXY = pts.reduce((s, p) => s + p.timestamp * p.numericValue, 0);

                const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX ** 2);
                const intercept = (sumY - slope * sumX) / n;

                const minX = Math.min(...pts.map(p => p.timestamp));
                const maxX = Math.max(...pts.map(p => p.timestamp));

                yearGroups[year].trend = [
                    { timestamp: minX, numericValue: slope * minX + intercept, isTrend: true },
                    { timestamp: maxX, numericValue: slope * maxX + intercept, isTrend: true }
                ];
            });

            // unique year ticks for XAxis
            const yearTicks = Array.from(new Set(data.map(d => {
                const date = new Date(d.date);
                return new Date(date.getFullYear(), 0, 1).getTime();
            }))).sort();

            processedGroups[event] = {
                data,
                yearGroups,
                yearTicks,
                stats: {
                    best: data.find(d => d.numericValue === best)?.mark,
                    median: isTime ? formatTime(median) : formatDistance(median),
                    sd: sd.toFixed(2),
                    count: data.length
                },
                isTime
            };
        });

        return processedGroups;
    }, [performances]);

    function formatTime(seconds) {
        if (seconds < 60) return seconds.toFixed(2);
        const mins = Math.floor(seconds / 60);
        const secs = (seconds % 60).toFixed(2);
        return `${mins}:${secs.padStart(5, '0')}`;
    }

    function formatDistance(inches) {
        const feet = Math.floor(inches / 12);
        const remainingInches = (inches % 12).toFixed(2);
        return `${feet}' ${remainingInches}"`;
    }

    const COLORS = ['#3182ce', '#38a169', '#d53f8c', '#805ad5', '#dd6b20', '#319795', '#e53e3e'];

    if (!selectedAthlete) {
        return (
            <div className="empty-state">
                <p>Please select a specific athlete to view their profile.</p>
            </div>
        );
    }

    return (
        <div className="athlete-profile">
            <div className="header-row">
                <h2>{selectedAthlete.name} - Athlete Profile</h2>
                <div className="record-count">{performances.length} Total Results</div>
            </div>

            {Object.entries(eventGroups).map(([event, group], index) => (
                <div key={event} className="event-profile-card">
                    <div className="event-profile-header">
                        <h3>{event}</h3>
                        <div className="event-stats-grid">
                            <div className="stat-item">
                                <span className="stat-label">Best</span>
                                <span className="stat-value highlight">{group.stats.best}</span>
                            </div>
                            <div className="stat-item">
                                <span className="stat-label">Median</span>
                                <span className="stat-value">{group.stats.median}</span>
                            </div>
                            <div className="stat-item">
                                <span className="stat-label">Std Dev</span>
                                <span className="stat-value">{group.stats.sd}</span>
                            </div>
                            <div className="stat-item">
                                <span className="stat-label">Appearances</span>
                                <span className="stat-value">{group.stats.count}</span>
                            </div>
                        </div>
                    </div>

                    <div className="event-chart-container">
                        <ResponsiveContainer width="100%" height={300}>
                            <LineChart margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                                <XAxis
                                    dataKey="timestamp"
                                    type="number"
                                    domain={['dataMin', 'dataMax']}
                                    ticks={group.yearTicks}
                                    tickFormatter={(val) => new Date(val).getFullYear()}
                                    stroke="#718096"
                                    fontSize={12}
                                />
                                <YAxis
                                    domain={['auto', 'auto']}
                                    reversed={group.isTime}
                                    tickFormatter={(val) => group.isTime ? formatTime(val) : formatDistance(val)}
                                    stroke="#718096"
                                    fontSize={12}
                                />
                                <Tooltip
                                    formatter={(value, name, props) => {
                                        if (props.payload.isTrend) return [group.isTime ? formatTime(value) : formatDistance(value), `${name} (Trend)`];
                                        return [group.isTime ? formatTime(value) : formatDistance(value), name];
                                    }}
                                    labelFormatter={(label) => `Date: ${new Date(label).toLocaleDateString()}`}
                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }}
                                />
                                <Legend />
                                {Object.keys(group.yearGroups).sort((a, b) => Number(a) - Number(b)).map((year, i) => (
                                    <React.Fragment key={year}>
                                        {/* Trend Line (Show in Legend) */}
                                        <Line
                                            data={group.yearGroups[year].trend}
                                            type="monotone"
                                            dataKey="numericValue"
                                            name={year}
                                            stroke={COLORS[i % COLORS.length]}
                                            strokeWidth={3}
                                            strokeDasharray="5 5"
                                            dot={false}
                                            activeDot={false}
                                            connectNulls
                                        />
                                        {/* Individual Points (Hidden from Legend) */}
                                        <Line
                                            data={group.yearGroups[year].points}
                                            type="monotone"
                                            dataKey="numericValue"
                                            name={year}
                                            stroke="none"
                                            dot={{ r: 4, fill: COLORS[i % COLORS.length], strokeWidth: 0 }}
                                            activeDot={{ r: 6 }}
                                            legendType="none"
                                        />
                                    </React.Fragment>
                                ))}
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            ))}
        </div>
    );
};

export default AthleteProfile;
