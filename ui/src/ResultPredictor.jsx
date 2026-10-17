import React, { useState, useEffect, useMemo } from 'react';
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Label } from 'recharts';
import { parseMark, formatTime, formatDistance, asset, fetchGz } from './utils';

// Most points the chart draws; the line is fit on every runner regardless.
const MAX_POINTS = 2000;

/**
 * Owen's Predictor: predict one event's best from another's. Fits and every
 * runner's bests come from backend/predictor_data.py (all teams, Indoor and
 * Outdoor, runners merged across spellings); nothing is computed here.
 */
export default function ResultPredictor() {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [event1, setEvent1] = useState("Boys 200 Meter Dash");
    const [event2, setEvent2] = useState("Boys 55 Meter Dash");
    const [inputValue, setInputValue] = useState("7");

    useEffect(() => {
        fetchGz(asset('/data/predictor.json.gz')).then(setData).catch(e => setError(String(e)));
    }, []);

    const analysisData = useMemo(() => {
        const fit = data?.fits[`${event1}|${event2}`];
        if (!fit) return null;

        const ys = new Map(data.events[event1]);
        const points = [];
        for (const [i, x] of data.events[event2]) {
            if (ys.has(i)) points.push({ x, y: ys.get(i), name: data.names[i] });
        }
        const step = Math.max(1, Math.ceil(points.length / MAX_POINTS));
        const xs = points.map(d => d.x);

        return {
            originalData: points.filter((_, k) => k % step === 0),
            slope: fit.slope,
            intercept: fit.intercept,
            minX: Math.min(...xs),
            maxX: Math.max(...xs),
            isTrack1: data.track.includes(event1),
            isTrack2: data.track.includes(event2),
            n: fit.n
        };
    }, [data, event1, event2]);

    const format1 = analysisData?.isTrack1 ? formatTime : formatDistance;
    const format2 = analysisData?.isTrack2 ? formatTime : formatDistance;

    const prediction = useMemo(() => {
        if (!analysisData || !inputValue) return null;
        const parsedInput = parseMark(inputValue);
        if (!parsedInput.valid || parsedInput.value === 0) return "Invalid input format";
        
        const predictedY = analysisData.slope * parsedInput.value + analysisData.intercept;
        return format1(predictedY);
    }, [analysisData, inputValue, format1]);

    const event2Type = data && !data.track.includes(event2) ? 'field' : 'track';

    // Reset input if switching between track and field to avoid invalid string pollution
    const [lastType, setLastType] = useState('track');
    if (lastType !== event2Type) {
        setLastType(event2Type);
        setInputValue("");
    }

    let inputUI;
    if (event2Type === 'field') {
        const parts = inputValue.includes('-') ? inputValue.split('-') : [inputValue, ''];
        inputUI = (
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <input 
                    type="number" 
                    value={parts[0] || ''} 
                    onChange={e => setInputValue(`${e.target.value}-${parts[1] || '0'}`)}
                    placeholder="ft"
                    style={{ width: '70px', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                /> <span style={{fontSize: '0.9em', color:'#666'}}>ft</span>
                <input 
                    type="number" step="0.25"
                    value={parts[1] || ''} 
                    onChange={e => setInputValue(`${parts[0] || '0'}-${e.target.value}`)}
                    placeholder="in"
                    style={{ width: '80px', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                /> <span style={{fontSize: '0.9em', color:'#666'}}>in</span>
            </div>
        );
    } else {
        const parts = inputValue.includes(':') ? inputValue.split(':') : (inputValue ? ['0', inputValue] : ['', '']);
        const mins = parts[0];
        const secsStr = parts[1] || '';
        const sParts = secsStr.includes('.') ? secsStr.split('.') : [secsStr, ''];
        const secs = sParts[0];
        const frac = sParts[1];

        const updateTime = (newM, newS, newF) => {
            const m = newM || '0';
            const s = newS || '00';
            const fStr = newF ? `.${newF}` : '';
            setInputValue(`${m}:${s}${fStr}`);
        };

        inputUI = (
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <input 
                    type="number" 
                    value={mins} 
                    onChange={e => updateTime(e.target.value, secs, frac)}
                    placeholder="min"
                    style={{ width: '60px', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                /> <span style={{fontSize: '0.9em', color:'#666'}}>m</span>
                <input 
                    type="number" 
                    value={secs} 
                    onChange={e => updateTime(mins, e.target.value, frac)}
                    placeholder="sec"
                    style={{ width: '60px', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                /> <span style={{fontSize: '0.9em', color:'#666'}}>s</span>
                <input 
                    type="number" 
                    value={frac} 
                    onChange={e => updateTime(mins, secs, e.target.value)}
                    placeholder="xx"
                    style={{ width: '60px', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                /> <span style={{fontSize: '0.9em', color:'#666'}}>ms</span>
            </div>
        );
    }

    const CustomTooltip = ({ active, payload }) => {
        if (active && payload && payload.length) {
            const data = payload[0].payload;
            return (
                <div style={{ backgroundColor: '#fff', padding: '10px', border: '1px solid #ccc', borderRadius: '4px', color: '#333' }}>
                    <p style={{ fontWeight: 'bold', margin: '0 0 5px 0' }}>{data.name}</p>
                    <p style={{ margin: '0' }}>{event2}: {format2(data.x)}</p>
                    <p style={{ margin: '0' }}>{event1}: {format1(data.y)}</p>
                </div>
            );
        }
        return null;
    };

    return (
        <div style={{ padding: '0 20px' }}>
            <div className="header-row" style={{ borderBottom: 'none', marginBottom: '10px' }}>
                <h2>Owen's Performance Predictor</h2>
            </div>
            
            <div className="filter-bar" style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', marginBottom: '30px' }}>
                <div className="filter-group">
                    <label>Predict This Event (Y)</label>
                    <select value={event1} onChange={(e) => setEvent1(e.target.value)}>
                        {(data?.order || []).map(ev => <option key={ev} value={ev}>{ev}</option>)}
                    </select>
                </div>
                <div className="filter-group">
                    <label>Based on This Event (X)</label>
                    <select value={event2} onChange={(e) => setEvent2(e.target.value)}>
                        {(data?.order || []).map(ev => <option key={ev} value={ev}>{ev}</option>)}
                    </select>
                </div>
                <div className="filter-group">
                    <label>{event2} Input</label>
                    {inputUI}
                </div>
            </div>

            {error ? (
                <div style={{ padding: '40px', textAlign: 'center', backgroundColor: '#f1f5f9', borderRadius: '8px' }}>
                    <p>Could not load the predictor data: {error}</p>
                </div>
            ) : !data ? (
                <div style={{ padding: '40px', textAlign: 'center', backgroundColor: '#f1f5f9', borderRadius: '8px' }}>
                    <p>Loading…</p>
                </div>
            ) : analysisData ? (
                <div>
                    <div style={{ backgroundColor: '#f8fafc', padding: '20px', borderRadius: '8px', marginBottom: '30px', border: '1px solid #e2e8f0' }}>
                        <h3 style={{ marginTop: '0', color: '#1e293b' }}>Predicted {event1}</h3>
                        <div style={{ fontSize: '2em', fontWeight: 'bold', color: '#0ea5e9', marginBottom: '10px' }}>
                            {prediction}
                        </div>
                        <div style={{ color: '#64748b', fontSize: '0.9em' }}>
                            <p style={{ margin: '0 0 5px 0' }}>Model built from <strong>{analysisData.n.toLocaleString()}</strong> athletes matching both events{analysisData.originalData.length < analysisData.n ? ` (chart shows ${analysisData.originalData.length.toLocaleString()} of them)` : ''}.</p>
                            <p style={{ margin: '0' }}>Equation: y = {analysisData.slope.toFixed(4)}x + {analysisData.intercept.toFixed(4)}</p>
                        </div>
                    </div>

                    <div style={{ width: '100%', height: 400, backgroundColor: 'white', padding: '20px', borderRadius: '8px', border: '1px solid #ccc' }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <ScatterChart margin={{ top: 20, right: 30, bottom: 20, left: 30 }}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis 
                                    type="number" 
                                    dataKey="x" 
                                    name={event2} 
                                    domain={['auto', 'auto']}
                                    tickFormatter={(val) => format2(val)}
                                >
                                    <Label value={event2} offset={-10} position="insideBottom" />
                                </XAxis>
                                <YAxis 
                                    type="number" 
                                    dataKey="y" 
                                    name={event1} 
                                    domain={['auto', 'auto']}
                                    tickFormatter={(val) => format1(val)}
                                >
                                    <Label value={event1} angle={-90} position="insideLeft" style={{ textAnchor: 'middle' }} />
                                </YAxis>
                                <Tooltip content={<CustomTooltip />} />
                                <Scatter name="Athletes" data={analysisData.originalData} fill="#0ea5e9" opacity={0.6} />
                                <ReferenceLine 
                                    segment={[
                                        { x: analysisData.minX, y: analysisData.slope * analysisData.minX + analysisData.intercept },
                                        { x: analysisData.maxX, y: analysisData.slope * analysisData.maxX + analysisData.intercept }
                                    ]} 
                                    stroke="#ef4444" 
                                    strokeWidth={2}
                                />
                            </ScatterChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            ) : (
                <div style={{ padding: '40px', textAlign: 'center', backgroundColor: '#f1f5f9', borderRadius: '8px' }}>
                    <p>Not enough data points combining these two events.</p>
                </div>
            )}
        </div>
    );
}
