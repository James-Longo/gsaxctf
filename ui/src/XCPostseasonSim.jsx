import React, { useState, useEffect, useMemo } from 'react'
import { asset, fetchGz } from './utils'

/**
 * XC postseason forecast: conference, regional and state meets simulated
 * from every runner's season rating (backend/xc_postseason.py, published by
 * backend/xc_postseason_publish.py). Regionals feed the state meets inside
 * each simulation, so a state field is whoever qualified in that run.
 */


const pct = (x) => x == null ? '' : x >= 0.995 ? '>99%' : x > 0 && x < 0.005 ? '<1%' : `${Math.round(x * 100)}%`
const pctCls = (x) => x == null ? '' : x >= 0.5 ? 'xs-hi' : x < 0.02 ? 'xs-lo' : ''
const fmtDate = (s) => new Date(s + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
const shortName = (m) => m.name.replace(' Championship', '').replace(' Regional', '')
const ROWS = 50
const PLACES = ['1st', '2nd', '3rd', '4th+']
const DIV_KEY = 'xs-div'
const savedDiv = () => { try { return localStorage.getItem(DIV_KEY) } catch { return null } }

export default function XCPostseasonSim({ followTeam }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [gender, setGender] = useState('Boys')
  const [meetId, setMeetId] = useState(null)
  const [team, setTeam] = useState(null)
  const [query, setQuery] = useState('')
  const [showAll, setShowAll] = useState(false)
  // a meet scored by division (PVC Large / Small) shows one division at a
  // time; the choice is remembered, and 'All' shows both
  const [divPick, setDivPick] = useState(savedDiv)
  const pickDiv = (d) => { setDivPick(d); setTeam(null); setShowAll(false); try { localStorage.setItem(DIV_KEY, d) } catch { /* private mode */ } }

  useEffect(() => {
    fetchGz(asset('/data/xc_postseason.json.gz')).then(setData).catch(e => setError(String(e)))
  }, [])

  // open on the first meet the followed team is in
  useEffect(() => {
    if (!data || meetId) return
    const first = data.meets.find(m => data.data[gender][m.id]?.teams.some(t => t.store === followTeam))
    setMeetId((first || data.meets[0]).id)
  }, [data, gender, followTeam, meetId])

  useEffect(() => { setTeam(null); setShowAll(false) }, [meetId, gender])

  const meetsByDate = useMemo(() => {
    const out = {}
    for (const m of data?.meets || []) (out[m.date] ||= []).push(m)
    return Object.entries(out).sort(([a], [b]) => a.localeCompare(b))
  }, [data])

  if (error) return <div className="xs"><p>Could not load the forecast: {error}</p></div>
  if (!data || !meetId) return <div className="xs"><p>Loading forecast...</p></div>

  const meet = data.meets.find(m => m.id === meetId)
  const race = data.data[gender][meetId]
  const isReg = meetId.startsWith('reg')
  const isState = meetId.startsWith('state')
  const followed = (t) => followTeam && t.store === followTeam
  const divs = [...new Set(race.teams.map(t => t.div).filter(Boolean))].sort().reverse()
  const div = divs.length ? (divs.includes(divPick) || divPick === 'All' ? divPick
    : race.teams.find(followed)?.div || (divs.includes('Small') ? 'Small' : divs[0])) : null
  const inDiv = (x) => !div || div === 'All' || x.div === div
  const teams = race.teams.filter(inDiv)
  const followedSchool = teams.find(followed)?.team

  // order in the race (within the division, for a meet scored by
  // division), kept when the list is filtered
  const rankOf = new Map()
  const divCount = {}
  for (const a of race.athletes) {
    divCount[a.div] = (divCount[a.div] || 0) + 1
    rankOf.set(a, divCount[a.div])
  }
  let runners = race.athletes.filter(inDiv)
  if (team) runners = runners.filter(a => a.school === team)
  const q = query.trim().toLowerCase()
  if (q) runners = runners.filter(a => `${a.name} ${a.school}`.toLowerCase().includes(q))
  const shown = showAll || team || q ? runners : runners.filter(a => rankOf.get(a) <= ROWS)
  let lastRunnerDiv = null
  const runnerCols = isReg || isState ? 7 : 6

  let lastDiv = null
  let rank = 0
  const teamCols = isReg ? 8 : 7

  return (
    <div className="xs">
      <div className="xs-bar">
        <div className="xs-seg" role="group" aria-label="Gender">
          {['Boys', 'Girls'].map(g => (
            <button key={g} className={g === gender ? 'active' : ''} onClick={() => setGender(g)}>{g}</button>
          ))}
        </div>
        {divs.length > 0 && (
          <div className="xs-seg" role="group" aria-label="Division">
            {[...divs, 'All'].map(d => (
              <button key={d} className={d === div ? 'active' : ''} onClick={() => pickDiv(d)}>{d}</button>
            ))}
          </div>
        )}
        <div className="xs-meets">
          {meetsByDate.map(([d, ms]) => (
            <div key={d} className="xs-day">
              <span className="xs-date">{fmtDate(d)}</span>
              <div className="xs-day-btns">
                {ms.map(m => {
                  const t = data.data[gender][m.id]?.teams.find(followed)
                  return (
                    <button key={m.id} onClick={() => setMeetId(m.id)}
                      className={`${m.id === meetId ? 'active' : ''} ${t ? 'has-follow' : ''}`}
                      title={t ? `${t.team}: ${pct(m.id.startsWith('reg') ? t.qual : t.win)} ${m.id.startsWith('reg') ? 'to states' : 'win'}` : m.venue || ''}>
                      {shortName(m)}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="xs-meta">
        <strong>{meet.name}</strong> · {gender} · {fmtDate(meet.date)}{meet.venue ? ` · ${meet.venue}` : ''}
        {meet.asof && <> · forecast from results through {fmtDate(meet.asof)}</>}
      </div>

      <div className="xs-grid">
        <div className="table-container xs-panel">
          <table className="performance-table xs-table">
            <thead>
              <tr>
                <th className="num">#</th><th>Team</th>
                {PLACES.map(p => <th key={p} className="num">{p}</th>)}
                {isReg && <th className="num">States</th>}
                <th className="num" title="Median simulated score">Score</th>
              </tr>
            </thead>
            <tbody>
              {teams.length === 0 && <tr><td colSpan={teamCols} className="xs-empty">No team has five rated runners yet.</td></tr>}
              {teams.map(t => {
                const divRow = t.div !== lastDiv && t.div && div === 'All'
                if (t.div !== lastDiv) { lastDiv = t.div; rank = 0 }
                rank++
                return (
                  <React.Fragment key={`${t.div}|${t.team}`}>
                    {divRow && <tr className="xs-div"><td colSpan={teamCols}>{t.div}</td></tr>}
                    <tr className={`xs-team ${followed(t) ? 'xs-follow' : ''} ${team === t.team ? 'xs-sel' : ''}`}
                      onClick={() => setTeam(team === t.team ? null : t.team)}>
                      <td className="num">{rank}</td>
                      <td>{t.team}{t.appear < 0.9 && <span className="xs-chip" title="Qualifies for this meet as a team in this share of simulations">{pct(t.appear)} qualify</span>}</td>
                      {t.odds.map((p, i) => <td key={i} className={`num ${i < 3 ? pctCls(p) : 'xs-plain'}`}>{pct(p)}</td>)}
                      {isReg && <td className={`num ${pctCls(t.qual)}`}>{pct(t.qual)}</td>}
                      <td className="num">{t.score}</td>
                    </tr>
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="xs-panel">
          <div className="xs-runner-bar">
            <input className="xs-search" placeholder="Filter runners" value={query} onChange={e => setQuery(e.target.value)} />
            {team && <button className="xs-clear" onClick={() => setTeam(null)}>{team} ✕</button>}
            {!team && followedSchool && <button className="xs-clear ghost" onClick={() => setTeam(followedSchool)}>{followedSchool}</button>}
          </div>
          <div className="table-container">
            <table className="performance-table xs-table">
              <thead>
                <tr>
                  <th className="num">#</th><th>Runner</th><th>Team</th>
                  <th className="num" title="Expected time on the Festival of Champions course">Expected</th>
                  <th className="num" title="Median simulated place (80% of simulations)">Place</th>
                  <th className="num">Top 10</th>
                  {isReg && <th className="num">States</th>}
                  {isState && <th className="num" title="Share of simulations in which the runner qualifies">In field</th>}
                </tr>
              </thead>
              <tbody>
                {shown.length === 0 && <tr><td colSpan={runnerCols} className="xs-empty">No runners match.</td></tr>}
                {shown.map((a, i) => {
                  const divRow = a.div !== lastRunnerDiv && a.div && div === 'All'
                  lastRunnerDiv = a.div
                  return (
                  <React.Fragment key={`${a.name}|${a.school}|${i}`}>
                  {divRow && <tr className="xs-div"><td colSpan={runnerCols}>{a.div}</td></tr>}
                  <tr className={a.school === followedSchool ? 'xs-follow' : ''}>
                    <td className="num">{rankOf.get(a)}</td>
                    <td>
                      {a.name}{a.grade ? <span className="xs-gr"> {a.grade}</span> : null}
                      {a.n === 0 && <span className="xs-chip" title="No race this season on file: rated from last season">prior</span>}
                    </td>
                    <td className="xs-school">{a.school}</td>
                    <td className="num" title={a.races.length ? a.races.map(r => `${r[0]}  ${r[1]}`).join('\n') : 'Rated from last season'}>{a.t}</td>
                    <td className="num xs-range">{a.med} <span className="xs-spread">({a.p10}–{a.p90})</span></td>
                    <td className={`num ${pctCls(a.top10)}`}>{pct(a.top10)}</td>
                    {isReg && <td className={`num ${pctCls(a.qual)}`}>{pct(a.qual)}</td>}
                    {isState && <td className={`num ${pctCls(a.start)}`}>{pct(a.start)}</td>}
                  </tr>
                  </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
          {!showAll && !team && !q && runners.length > shown.length && (
            <button className="xs-more" onClick={() => setShowAll(true)}>All {runners.length} runners</button>
          )}
        </div>
      </div>
    </div>
  )
}
