import React, { useState, useEffect, useMemo } from 'react'
import { asset, fetchGz } from './utils'

/**
 * XC postseason forecast: conference, regional and state meets simulated
 * from every runner's season rating (backend/xc_postseason.py, published by
 * backend/xc_postseason_publish.py, one file per season). Regionals feed the
 * state meets inside each simulation, so a state field is whoever qualified
 * in that run. A meet that has been run shows its result beside the forecast;
 * past seasons are the backtest's forecasts, each meet predicted from results
 * before it.
 */


const pct = (x) => x == null ? '' : x >= 0.995 ? '>99%' : x > 0 && x < 0.005 ? '<1%' : `${Math.round(x * 100)}%`
const pctCls = (x) => x == null ? '' : x >= 0.5 ? 'xs-hi' : x < 0.02 ? 'xs-lo' : ''
const fmtDate = (s) => new Date(s + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
const shortName = (m) => m.name.replace(' Championship', '').replace(' Regional', '')
const ROWS = 50
const PLACES = ['1st', '2nd', '3rd', '4th+']
const DIV_KEY = 'xs-div'
const savedDiv = () => { try { return localStorage.getItem(DIV_KEY) } catch { return null } }

const signed = (s) => `${s < 0 ? '−' : '+'}${Math.floor(Math.abs(s) / 60)}:${String(Math.round(Math.abs(s)) % 60).padStart(2, '0')}`
const secs = (t) => { const [m, s] = t.split(':').map(Number); return m * 60 + s }

export default function XCPostseasonSim({ followTeam }) {
  const [seasons, setSeasons] = useState(null)
  const [year, setYear] = useState(null)
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
    fetch(asset('/data/xc_postseason/index.json'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(ix => { setSeasons(ix.seasons); setYear(ix.seasons[0].year) })
      .catch(e => setError(String(e)))
  }, [])

  useEffect(() => {
    if (!year) return
    let live = true
    setData(null); setMeetId(null)
    fetchGz(asset(`/data/xc_postseason/${year}.json.gz`))
      .then(d => { if (live) setData(d) }).catch(e => setError(String(e)))
    return () => { live = false }
  }, [year])

  // open on the first meet the followed team is in; a past season can hold a
  // meet for one gender only, so a meet missing for this gender is replaced
  useEffect(() => {
    if (!data || (meetId && data.data[gender][meetId])) return
    const has = data.meets.filter(m => data.data[gender][m.id])
    const first = has.find(m => data.data[gender][m.id].teams.some(t => t.store === followTeam))
    setMeetId((first || has[0] || data.meets[0]).id)
  }, [data, gender, followTeam, meetId])

  useEffect(() => { setTeam(null); setShowAll(false) }, [meetId, gender])

  const meetsByDate = useMemo(() => {
    const out = {}
    for (const m of data?.meets || []) (out[m.date] ||= []).push(m)
    return Object.entries(out).sort(([a], [b]) => a.localeCompare(b))
  }, [data])

  if (error) return <div className="xs"><p>Could not load the forecast: {error}</p></div>
  if (!data || !meetId || !seasons || !data.data[gender][meetId]) return <div className="xs"><p>Loading forecast...</p></div>

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
  const actual = race.actual
  const pastSeason = data.kind === 'backtest'

  let lastDiv = null
  let rank = 0
  const teamCols = isReg ? 8 : 7

  return (
    <div className="xs">
      <div className="xs-bar">
        <select className="xs-year" aria-label="Season" value={year} onChange={e => setYear(Number(e.target.value))}>
          {seasons.map(s => <option key={s.year} value={s.year}>{s.year}{s.kind === 'forecast' ? '' : ' (backtest)'}</option>)}
        </select>
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
                  const r = data.data[gender][m.id]
                  if (!r) return null
                  const t = r.teams.find(followed)
                  return (
                    <button key={m.id} onClick={() => setMeetId(m.id)}
                      className={`${m.id === meetId ? 'active' : ''} ${t ? 'has-follow' : ''}`}
                      title={(t ? `${t.team}: ${pct(m.id.startsWith('reg') ? t.qual : t.win)} ${m.id.startsWith('reg') ? 'to states' : 'win'}` : m.venue || '') + (r.actual ? ' · result in' : '')}>
                      {shortName(m)}{r.actual && <span className="xs-done" aria-label="result in"> ✓</span>}
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
        {pastSeason && <span className="xs-note" title={`Model refit without ${data.year}; each meet predicted from results before it`}>Backtest</span>}
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
                  <th className="num" title={race.course_known === false ? 'Expected time on the Belfast course (no factor for this course yet), typical conditions' : `Expected time on this meet's course${meet.venue ? ` (${meet.venue})` : ''}, typical conditions`}>Expected</th>
                  <th className="num" title="Finishing place in 80% of simulations (10th to 90th percentile)">Range</th>
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
                    <td className="num xs-range">{a.p10 === a.p90 ? a.p10 : `${a.p10}–${a.p90}`}</td>
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

      {actual && <ResultPanel actual={actual} div={div} team={team} setTeam={setTeam} query={q}
        followTeam={followTeam} followedSchool={followedSchool} />}
    </div>
  )
}

/** Forecast against what happened at a meet that has been run. */
function ResultPanel({ actual, div, team, setTeam, query, followTeam, followedSchool }) {
  const [showAll, setShowAll] = useState(false)
  const inDiv = (x) => !div || div === 'All' || x.div === div
  const teams = actual.teams.filter(inDiv)
  let runners = actual.athletes.filter(inDiv)
  if (team) runners = runners.filter(a => a.school === team)
  if (query) runners = runners.filter(a => `${a.name} ${a.school}`.toLowerCase().includes(query))
  const shown = showAll || team || query ? runners : runners.slice(0, ROWS)
  const sums = Object.entries(actual.summary).filter(([d]) => !div || div === 'All' || d === div || d === '')
  const dns = actual.dns.filter(inDiv).filter(a => !team || a.school === team)
  const multi = sums.length > 1
  let lastDiv = null
  let lastRunnerDiv = null

  return (
    <div className="xs-result">
      <h3 className="xs-h">Forecast vs result</h3>
      <div className="xs-sum">
        {sums.map(([d, s]) => (
          <div key={d} className="xs-sum-row">
            {multi && <span className="xs-sum-div">{d}</span>}
            <span><b>{s.winner ? '✓' : '✗'}</b> winner {s.winner ? 'called' : 'missed'}</span>
            {s.podium != null && <span><b>{s.podium} of 3</b> podium teams picked{s.order ? `, ${s.order} in the exact place` : ''}</span>}
            {s.in_range != null && <span><b>{pct(s.in_range)}</b> of {s.runners} runners inside their range <span className="xs-dim">(80% expected)</span></span>}
            {s.place_err != null && <span>typical place miss <b>{Math.round(s.place_err)}</b></span>}
            {s.time_err != null && <span title="After removing the whole field's shift that day">typical time miss <b>{s.time_err} s</b></span>}
          </div>
        ))}
        {actual.day != null && (
          <div className="xs-sum-row xs-dim">
            Field ran {Math.abs(actual.day * 100).toFixed(1)}% {actual.day < 0 ? 'faster' : 'slower'} than forecast.
          </div>
        )}
      </div>

      <div className="xs-grid">
        <div className="table-container xs-panel">
          <table className="performance-table xs-table">
            <thead>
              <tr>
                <th className="num">Place</th><th>Team</th><th className="num">Score</th>
                <th className="num" title="Place in the forecast's order">Forecast</th>
                <th className="num" title="Median simulated score">Fc. score</th>
                <th className="num" title="Share of simulations in which the team finished in exactly this place">Chance</th>
              </tr>
            </thead>
            <tbody>
              {teams.map(t => {
                const divRow = t.div !== lastDiv && t.div && div === 'All'
                lastDiv = t.div
                const off = t.pred == null || t.place == null ? null : t.pred - t.place
                return (
                  <React.Fragment key={`${t.div}|${t.team}`}>
                    {divRow && <tr className="xs-div"><td colSpan={6}>{t.div}</td></tr>}
                    <tr className={`xs-team ${followTeam && t.store === followTeam ? 'xs-follow' : ''} ${team === t.team ? 'xs-sel' : ''}`}
                      onClick={() => setTeam(team === t.team ? null : t.team)}>
                      <td className="num">{t.place ?? '–'}</td>
                      <td>{t.team}{t.place == null && <span className="xs-chip" title="Fewer than five runners finished">no team score</span>}</td>
                      <td className="num">{t.score ?? '–'}</td>
                      <td className="num">{t.pred ?? '–'}{off ? <span className="xs-dim"> ({off > 0 ? '+' : '−'}{Math.abs(off)})</span> : null}</td>
                      <td className="num">{t.pscore ?? '–'}</td>
                      <td className="num">{t.p == null ? '–' : pct(t.p)}</td>
                    </tr>
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="xs-panel">
          <div className="table-container">
            <table className="performance-table xs-table">
              <thead>
                <tr>
                  <th className="num">Place</th><th>Runner</th><th className="xs-col-team">Team</th>
                  <th className="num">Time</th>
                  <th className="num" title="Expected time on this course, typical conditions">Forecast</th>
                  <th className="num" title="Actual minus forecast time">Diff</th>
                  <th className="num" title="Forecast finishing place in 80% of simulations">Range</th>
                </tr>
              </thead>
              <tbody>
                {shown.length === 0 && <tr><td colSpan={7} className="xs-empty">No runners match.</td></tr>}
                {shown.map((a, i) => {
                  const divRow = a.div !== lastRunnerDiv && a.div && div === 'All'
                  lastRunnerDiv = a.div
                  const inside = a.p10 != null && a.place >= a.p10 && a.place <= a.p90
                  return (
                    <React.Fragment key={`${a.name}|${a.school}|${i}`}>
                      {divRow && <tr className="xs-div"><td colSpan={7}>{a.div}</td></tr>}
                      <tr className={a.school === followedSchool ? 'xs-follow' : ''}>
                        <td className="num">{a.place}</td>
                        <td>{a.name}{a.grade ? <span className="xs-gr"> {a.grade}</span> : null}
                          {a.p10 == null && <span className="xs-chip" title="Not in the forecast (no rated race before the meet, or outside the team's top seven)">not forecast</span>}
                          <div className="xs-sub-school">{a.school}</div></td>
                        <td className="xs-school xs-col-team">{a.school}</td>
                        <td className="num">{a.t}</td>
                        <td className="num xs-dim">{a.pt ?? '–'}</td>
                        <td className="num">{a.pt ? signed(secs(a.t) - secs(a.pt)) : ''}</td>
                        <td className={`num xs-range ${a.p10 == null ? '' : inside ? 'xs-in' : 'xs-out'}`}>
                          {a.p10 == null ? '' : <>{a.p10 === a.p90 ? a.p10 : `${a.p10}–${a.p90}`} {inside ? '✓' : '✗'}</>}
                        </td>
                      </tr>
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
          {!showAll && !team && !query && runners.length > shown.length && (
            <button className="xs-more" onClick={() => setShowAll(true)}>All {runners.length} runners</button>
          )}
          {dns.length > 0 && (
            <p className="xs-dns">Forecast to run but not in the results: {dns.map(a => `${a.name} (${a.school})`).join(', ')}</p>
          )}
        </div>
      </div>
    </div>
  )
}
