import React, { useState, useMemo, useEffect } from 'react'
import { computeRecords, coopTeams } from './records.js'
import './App.css'

// A team's record board for the season type in view (Indoor or Outdoor):
// the best mark ever per event and gender, from the results store. Rules are
// in records.js. Click an event for its all-time top 10.
function RecordBoard({ performances, selectedTeam, manifest, loadTeamData, season, runnerId, athletes, meetLinks }) {
    const [fromYear, setFromYear] = useState('All')
    const [open, setOpen] = useState(new Set())
    useEffect(() => { setOpen(new Set()); setFromYear('All') }, [selectedTeam, season])

    // co-op squads the school hosts count toward its records
    const coops = useMemo(() => coopTeams(selectedTeam, manifest.teams || [])
        .filter(t => (t.seasons || []).some(k => k.endsWith(`_${season}`))), [selectedTeam, manifest, season])
    useEffect(() => {
        for (const t of coops) loadTeamData(t.slug, null, t.seasons, t.name)
    }, [coops])

    const teamNames = useMemo(() => new Set([selectedTeam, ...coops.map(t => t.name)]), [selectedTeam, coops])
    const rows = useMemo(() => performances.filter(p => teamNames.has(p.team) && p.season === season),
        [performances, teamNames, season])
    const nameOf = useMemo(() => {
        const m = new Map((athletes || []).map(a => [a.id, a.name]))
        return (id) => m.get(id)
    }, [athletes])
    const years = useMemo(() => [...new Set(rows.map(p => p.year))].sort(), [rows])
    const records = useMemo(() => computeRecords(rows, {
        season, runnerId, nameOf, fromYear: fromYear === 'All' ? null : fromYear,
    }), [rows, season, runnerId, nameOf, fromYear])

    if (selectedTeam === 'All') {
        return <div className="empty-state"><p>Choose a team to see its record board.</p></div>
    }

    const toggle = (k) => setOpen(prev => {
        const next = new Set(prev)
        if (next.has(k)) next.delete(k); else next.add(k)
        return next
    })
    const meetCell = (e, season) => {
        const url = meetLinks?.[`${e.year}_${season}`]?.[e.meet]
        return url ? <a className="meet-link" href={url} target="_blank" rel="noopener noreferrer">{e.meet}</a> : e.meet
    }
    const who = (e) => e.legs && e.legs.length > 1 ? e.legs.join(', ') : e.name
    const genders = [...new Set(records.map(r => r.gender))]

    return (
        <div className="record-board">
            <div className="header-row">
                <h2>{selectedTeam} {season} Records</h2>
                <div className="filter-group">
                    <label>From</label>
                    <select value={fromYear} onChange={e => setFromYear(e.target.value)}>
                        <option value="All">All years</option>
                        {years.map(y => <option key={y} value={y}>{y}</option>)}
                    </select>
                </div>
            </div>
            <p className="record-note">
                Best mark per event in the results on this site{years.length ? ` (${years[0]}–${years[years.length - 1]})` : ''}.
                One entry per runner across name spellings; DQ/DNF/foul and similar marks don't count.
                Hand times count as written. Click an event for its top 10.
                {coops.length > 0 && ` Includes co-op squads: ${coops.map(t => t.name).join(', ')}.`}
            </p>
            {!records.length && <div className="empty-state"><p>No {season.toLowerCase()} results loaded for this team yet.</p></div>}
            {genders.map(g => (
                <div key={g} className="table-container record-section">
                    <h3>{g || 'Other'}</h3>
                    <table className="performance-table record-table">
                        <thead>
                            <tr><th>Event</th><th>Mark</th><th>Athlete</th><th>Date</th><th>Meet</th></tr>
                        </thead>
                        <tbody>
                            {records.filter(r => r.gender === g).map(r => {
                                const k = `${r.gender}|${r.event}`
                                const isOpen = open.has(k)
                                return (
                                    <React.Fragment key={k}>
                                        {r.record.map((e, i) => (
                                            <tr key={i} className="record-row" onClick={() => toggle(k)}>
                                                {i === 0 && <td rowSpan={r.record.length} className="record-event">
                                                    {r.event}<span className="splits-toggle">{isOpen ? ' ▲' : ' ▼'}</span>
                                                </td>}
                                                {i === 0 && <td rowSpan={r.record.length} className="mark-cell">{e.mark}</td>}
                                                <td>{who(e)}{r.record.length > 1 && i === 0 && <span className="badge">tie</span>}</td>
                                                <td className="record-date">{e.date}</td>
                                                <td>{meetCell(e, season)}</td>
                                            </tr>
                                        ))}
                                        {isOpen && (
                                            <tr className="splits-row">
                                                <td colSpan={5}>
                                                    <table className="record-top">
                                                        <tbody>
                                                            {r.top.map((e, i) => (
                                                                <tr key={i}>
                                                                    <td>{i + 1}</td><td>{e.mark}</td><td>{who(e)}</td>
                                                                    <td className="record-date">{e.date}</td><td>{meetCell(e, season)}</td>
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </td>
                                            </tr>
                                        )}
                                    </React.Fragment>
                                )
                            })}
                        </tbody>
                    </table>
                </div>
            ))}
        </div>
    )
}

export default RecordBoard
