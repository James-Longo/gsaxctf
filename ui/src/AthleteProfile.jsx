
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
import { parseMark, isDistanceEvent, normalizeEvent, gradeLabel } from './utils';
import './App.css';
import Tip from './Tip'

const COLORS = ['#3182ce', '#38a169', '#d53f8c', '#805ad5', '#dd6b20', '#319795', '#e53e3e'];
// grade colors are fixed so FR..SR read the same on every profile
const GRADE_COLORS = { 5: '#319795', 6: '#dd6b20', 7: '#e53e3e', 8: '#805ad5', MS: '#805ad5', 9: '#3182ce', 10: '#38a169', 11: '#d53f8c', 12: '#d69e2e' };

// A mark's chart category: grade as printed, else estimated from the runner's
// other years; summer rows have an age group instead.
const CLASS_NUM = { FR: 9, SO: 10, JR: 11, SR: 12 };
const gradeOf = (d) => {
    const p = String(d.grade ?? '').trim().toUpperCase();
    if (/^\d{1,2}$/.test(p)) return +p;
    if (CLASS_NUM[p]) return CLASS_NUM[p];
    if (d.grade_est) return +d.grade_est;
    return p === 'MS' ? 'MS' : null;
};

// relay rows carry no grade: take the runner's grade that school year
function classOf(d, yearGrade) {
    const g = gradeOf(d) ?? yearGrade[d.year] ?? null;
    if (g != null) return { key: 'g' + g, label: gradeLabel(String(g)), order: g === 'MS' ? 8.5 : g, color: GRADE_COLORS[g] || '#718096' };
    if (d.age_group) return { key: 'a' + d.age_group, label: d.age_group, order: 100 + d.ageRank, color: COLORS[d.ageRank % COLORS.length] };
    return { key: '?', label: '?', order: 999, color: '#a0aec0' };
}

const AthleteProfile = ({ performances, selectedAthlete }) => {
    const eventGroups = useMemo(() => {
        if (!performances) return {};

        const groups = {};
        performances.forEach(p => {
            const groupKey = normalizeEvent(p.event);

            if (!groups[groupKey]) groups[groupKey] = [];

            // summer rows carry their value already (field marks print in feet or meters)
            const parsed = p.numericValue != null
                ? { valid: true, value: p.numericValue, isTime: p.isTime }
                : parseMark(p.mark, isDistanceEvent(p.event));
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
        // one runner only: All Athletes mixes runners
        const yearGrade = {};
        if (selectedAthlete && selectedAthlete.id !== 'all') performances.forEach(p => {
            const g = gradeOf(p);
            if (g != null && p.year && !(p.year in yearGrade)) yearGrade[p.year] = g;
        });

        Object.keys(groups).forEach(event => {
            // undated marks can't be placed in time: left out of the chart and progression
            const data = groups[event].filter(d => !isNaN(Date.parse(d.date)))
                .sort((a, b) => Date.parse(a.date) - Date.parse(b.date));
            if (data.length === 0) return;

            const values = data.map(d => d.numericValue);
            const isTime = data[0].isTime;

            // Basic Stats
            const best = isTime ? Math.min(...values) : Math.max(...values);
            const sortedValues = [...values].sort((a, b) => a - b);
            const median = sortedValues[Math.floor(sortedValues.length / 2)];

            const mean = values.reduce((a, b) => a + b, 0) / values.length;
            const sd = Math.sqrt(values.map(x => Math.pow(x - mean, 2)).reduce((a, b) => a + b, 0) / values.length);

            // dots colored by grade (summer: age group), youngest first
            const byClass = {};
            data.forEach(d => {
                const c = classOf(d, yearGrade);
                if (!byClass[c.key]) byClass[c.key] = { ...c, points: [] };
                byClass[c.key].points.push({ ...d, timestamp: new Date(d.date).getTime() });
            });
            const classes = Object.values(byClass).sort((a, b) => a.order - b.order);

            // unique year ticks for XAxis
            const yearTicks = Array.from(new Set(data.map(d => {
                const date = new Date(d.date);
                return new Date(date.getFullYear(), 0, 1).getTime();
            }))).sort();

            // PR progression: each mark that beat everything before it
            const progression = [];
            data.forEach(d => {
                const prev = progression[progression.length - 1];
                if (!prev || (d.isTime ? d.numericValue < prev.numericValue : d.numericValue > prev.numericValue)) {
                    progression.push({
                        ...d,
                        timestamp: Date.parse(d.date),
                        gain: prev ? Math.abs(d.numericValue - prev.numericValue) : null,
                        color: classOf(d, yearGrade).color,
                    });
                }
            });
            // the PR line holds its level out to the latest race
            const lastTs = Date.parse(data[data.length - 1].date);
            const prLine = [...progression];
            if (lastTs > prLine[prLine.length - 1].timestamp) {
                prLine.push({ ...prLine[prLine.length - 1], timestamp: lastTs, isHold: true });
            }

            processedGroups[event] = {
                data,
                progression,
                prLine,
                classes,
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
    }, [performances, selectedAthlete]);

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

    function formatGain(v, isTime) {
        if (isTime) return '−' + (v < 60 ? v.toFixed(2) : formatTime(v));
        if (v < 12) return '+' + v.toFixed(2).replace(/\.?0+$/, '') + '"';
        return '+' + formatDistance(v);
    }


    if (!selectedAthlete) {
        return (
            <div className="empty-state">
                <p>Please select a specific athlete to view their profile.</p>
            </div>
        );
    }

    // one runner's progression only (All Athletes mixes runners)
    const showProgression = selectedAthlete.id !== 'all';

    return (
        <div className="athlete-profile">
            <div className="header-row">
                <h2>{selectedAthlete.name} - Athlete Profile</h2>
                <div className="record-count">{performances.length} Total Results</div>
            </div>

            {Object.entries(eventGroups).map(([event, group]) => (
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
                                    formatter={(value, name) => [group.isTime ? formatTime(value) : formatDistance(value), name]}
                                    labelFormatter={(label) => `Date: ${new Date(label).toLocaleDateString()}`}
                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }}
                                />
                                <Legend itemSorter={(item) => group.classes.find(c => c.label === item.value)?.order ?? 9999} />
                                {group.classes.map(c => (
                                    <Line
                                        key={c.key}
                                        data={c.points}
                                        type="monotone"
                                        dataKey="numericValue"
                                        name={c.label}
                                        stroke={c.color}
                                        strokeWidth={0}
                                        dot={{ r: 4, fill: c.color, strokeWidth: 0 }}
                                        activeDot={{ r: 6 }}
                                        legendType="circle"
                                    />
                                ))}
                                {showProgression && (
                                    <Line
                                        data={group.prLine}
                                        type="stepAfter"
                                        dataKey="numericValue"
                                        name="PR"
                                        stroke="#1a202c"
                                        strokeWidth={2}
                                        dot={(props) => props.payload.isHold
                                            ? <g key={props.key} />
                                            : <circle key={props.key} cx={props.cx} cy={props.cy} r={4} fill={props.payload.color} stroke="#1a202c" strokeWidth={2} />}
                                        activeDot={false}
                                        isAnimationActive={false}
                                    />
                                )}
                            </LineChart>
                        </ResponsiveContainer>
                    </div>

                    {showProgression && (
                        <div className="pr-progression">
                            <h4>PR progression</h4>
                            <table className="performance-table">
                                <thead>
                                    <tr><th>Date</th><th>Result</th><th><Tip tip="Gain on the previous PR">+/−</Tip></th><th>Meet</th></tr>
                                </thead>
                                <tbody>
                                    {group.progression.map(p => (
                                        <tr key={p.id}>
                                            <td>{p.date.split('T')[0]}{p.grade ? <span className="xs-gr"> {gradeLabel(p.grade)}</span> : p.age ? <span className="xs-gr"> age {p.age}</span> : null}</td>
                                            <td>{p.mark}</td>
                                            <td className="pr-gain">{p.gain == null ? '' : formatGain(p.gain, group.isTime)}</td>
                                            <td>{p.meet_name}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            ))}
        </div>
    );
};

export default AthleteProfile;
