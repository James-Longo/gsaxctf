import React, { useState, useMemo, useEffect } from 'react'
import { computeRecords, coopTeams, mergeBoard } from './records.js'
import { OFFICIAL_BOARDS, BOARD_EVENTS } from './officialBoards.js'
import './App.css'
import Tip from './Tip'

// A team's record board for the season type in view (Indoor or Outdoor):
// the best mark ever per event and gender, from the results store, for the
// events on GSA's official boards. Rules are in records.js; a team with an
// official board (officialBoards.js) shows the board's mark where it beats
// these results (e.g. before 2003). The comparison itself is internal:
// `npm run check:boards`. Click an event for its all-time top 10.
function RecordBoard({ performances, selectedTeam, manifest, loadTeamData, season, runnerId, athletes, meetLinks }) {
    const [open, setOpen] = useState(new Set())
    useEffect(() => { setOpen(new Set()) }, [selectedTeam, season])

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
    const board = OFFICIAL_BOARDS[selectedTeam]?.[season]
    const records = useMemo(() => mergeBoard(
        computeRecords(rows, { season, runnerId, nameOf })
            .filter(r => BOARD_EVENTS[season]?.has(`${r.gender}|${r.event}`)),
        board), [rows, season, runnerId, nameOf, board])

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
    const rulesTitle = [
        `Best mark per event in this site's results${years.length ? ` (${years[0]}–${years[years.length - 1]})` : ''}`,
        board && `the ${selectedTeam} record board fills records these results lack`,
        coops.length > 0 && `includes co-op squads: ${coops.map(t => t.name).join(', ')}`,
        'one entry per runner; DQ/DNF/foul marks excluded; hand times as written; click an event for its top 10',
    ].filter(Boolean).join('; ')
    // a relay whose results print only the school ("George Stevens Academy Relay")
    const noLegs = (e) => e.legs && e.legs.length < 2

    return (
        <div className="record-board">
            <div className="header-row">
                <h2><Tip tip={rulesTitle}>{selectedTeam} {season} Records</Tip></h2>
            </div>
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
                                                    <button type="button" className="text-btn" aria-expanded={isOpen}
                                                        onClick={(ev) => { ev.stopPropagation(); toggle(k) }}>
                                                        {r.event}<span className="splits-toggle" aria-hidden="true">{isOpen ? ' ▲' : ' ▼'}</span>
                                                    </button>
                                                </td>}
                                                {i === 0 && <td rowSpan={r.record.length} className="mark-cell">{e.mark}</td>}
                                                <td>{who(e)}{r.record.length > 1 && i === 0 && <span className="badge">tie</span>}{noLegs(e) && <Tip glue className="badge board-badge" tip="No result or other source found names the runners">names?</Tip>}</td>
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
