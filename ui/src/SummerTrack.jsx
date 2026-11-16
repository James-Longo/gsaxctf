import React, { useState, useEffect, useMemo } from 'react'
import { FIELD, ageRank, loadSummer } from './summerData'
import SearchSelect from './SearchSelect'
import Tip from './Tip'

/**
 * Summer track: the USATF Maine Youth Developmental Summer Series (14 & under).
 * Kids race for summer clubs in two-year age groups, so this tab has its own
 * data (ui/public/data/summer.json.gz from backend/summer_track.py): results
 * laid out like the school seasons', and a record board
 * by club, age group and event, kept apart from the school records.
 */

const HOME_CLUB = 'Blue Hill Peninsula'   // GSA's summer program
// field marks and multi-event point totals ('Pentathlon'; its legs read as the leg)
const higher = (e) => FIELD.test(e) || /^(tri|pent|hept|dec)athlon$/i.test(e)
const SHOW = 2000   // rows rendered for all clubs at once (~140k rows); one club shows all
const evRank = (e) => {
  const m = e.match(/^(\d+)/)
  if (FIELD.test(e)) return 10000 + e.charCodeAt(0)
  if (/relay/i.test(e)) return 9000 + (m ? +m[1] : 0)
  return (m ? +m[1] : 5000) + (/hurdle/i.test(e) ? 0.5 : 0) + (/walk/i.test(e) ? 0.7 : 0)
}

// the age group, like the grade beside a school result; the printed age on
// hover. The hint covers the whole cell so the cell wraps as plain text.
const Age = ({ r }) => r.age_group ? <span className="xs-gr"> {r.age_group}</span> : null
const ageTip = (r) => r.age_group && r.age ? `age ${r.age}` : ''

export default function SummerTrack({ view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [club, setClub] = useState(HOME_CLUB)
  const [gender, setGender] = useState('Girls')
  const [athlete, setAthlete] = useState('all')
  const [year, setYear] = useState('All')
  const [event, setEvent] = useState('All')
  const [ageGroup, setAgeGroup] = useState('All')
  const [sortField, setSortField] = useState('date')
  const [sortDir, setSortDir] = useState('desc')

  useEffect(() => {
    loadSummer().then(setData).catch(e => setError(String(e)))
  }, [])
  const rows = data?.rows || []
  const runners = data?.runners || new Map()

  // Maine series clubs first; clubs seen only at Junior Olympic / regional meets after
  const clubOptions = useMemo(() => {
    const n = {}
    rows.forEach(r => { if (r.club) n[r.club] = (n[r.club] || 0) + 1 })
    const series = new Set(data?.series_clubs || [])
    const all = Object.keys(n).sort((a, b) => a.localeCompare(b))
    const opt = (g) => (c) => ({ value: c, label: c, group: g, secondary: `${n[c].toLocaleString()} results` })
    return [{ value: 'All', label: 'All Clubs' },
      ...all.filter(c => series.has(c)).map(opt('Maine summer series clubs')),
      ...all.filter(c => !series.has(c)).map(opt('Other clubs (Junior Olympic meets)'))]
  }, [rows, data])

  const clubRunners = useMemo(() => [...runners.values()]
    .filter(a => club === 'All' || a.clubs.has(club))
    .sort((a, b) => a.name.localeCompare(b.name)), [runners, club])

  const years = useMemo(() => [...new Set(rows.map(r => r.year).filter(Boolean))].sort((a, b) => b - a), [rows])

  if (error) return <div className="summer-track"><p>Could not load summer results: {error}</p></div>
  if (!data) return <div className="summer-track"><p>Loading summer results...</p></div>

  const inClub = (r) => club === 'All' || r.club === club
  const pickClub = (c) => { setClub(c); setAthlete('all'); setYear('All'); setEvent('All') }
  const pickAthlete = (a) => { setAthlete(a); setYear('All'); setEvent('All'); setAgeGroup('All') }
  const clubPicker = (
    <div className="filter-group">
      <label htmlFor="pick-club">Club</label>
      <SearchSelect id="pick-club" value={club} onChange={pickClub} options={clubOptions} placeholder="Search clubs..." />
    </div>
  )
  const athletePicker = (withAll, value) => (
    <div className="filter-group">
      <label htmlFor="pick-summer-athlete">Athlete</label>
      <SearchSelect id="pick-summer-athlete" value={value} onChange={pickAthlete}
        options={[...(withAll ? [{ value: 'all', label: 'All Athletes' }] : []),
          ...clubRunners.map(a => ({ value: a.id, label: a.name,
            secondary: club === 'All' ? [...a.clubs].join(', ') : `${a.rows.length}` }))]}
        placeholder="Search athletes..." minSearch={club === 'All' ? 2 : 0} />
    </div>
  )

  if (view === 'records') {
    // best mark per runner, top 10 per gender / age group / event
    const boards = {}
    rows.filter(r => r.gender === gender && inClub(r)).forEach(r => {
      const key = `${r.age_group}|${r.event}`
      const who = r.legs ? `${r.club}: ${r.legs}` : (r.rid || r.name)
      const b = (boards[key] ||= {})
      if (!b[who] || (higher(r.event) ? r.value > b[who].value : r.value < b[who].value)) b[who] = r
    })
    const keys = Object.keys(boards).sort((a, b) => {
      const [ga, ea] = a.split('|'), [gb, eb] = b.split('|')
      return ageRank(ga) - ageRank(gb) || evRank(ea) - evRank(eb) || ea.localeCompare(eb)
    })
    return (
      <div className="summer-track">
        <div className="filter-bar">
          {clubPicker}
          <div className="filter-group">
            <label>Gender</label>
            <select value={gender} onChange={e => setGender(e.target.value)}>
              <option>Girls</option><option>Boys</option><option>Mixed</option>
            </select>
          </div>
        </div>
        <p className="summer-note">Summer series marks only, kept apart from the school records. Ages are USATF age groups.</p>
        {keys.length === 0 && <p>No marks for this selection.</p>}
        {keys.map(k => {
          const [age, ev] = k.split('|')
          const list = Object.values(boards[k]).sort((a, b) => higher(ev) ? b.value - a.value : a.value - b.value).slice(0, 10)
          return (
            <div key={k} className="summer-board">
              <h3>{ev} <span className="summer-age">{age}</span></h3>
              <table className="summer-table">
                <tbody>
                  {list.map((r, i) => (
                    <tr key={i}>
                      <td>{i + 1}</td>
                      <td>{r.legs || r.name}{club === 'All' && <span className="summer-club"> · {r.club}</span>}</td>
                      <td className="summer-mark">{r.mark}</td>
                      <td>{r.date}</td>
                      <td><a href={r.url} target="_blank" rel="noopener noreferrer">{r.meetName}</a></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        })}
      </div>
    )
  }

  // Results: the school seasons' table (date, athlete, event, result, meet)
  const all = athlete === 'all'
  const last4 = new Set(years.slice(0, 4))
  const yearOk = (r) => year === 'All' || (year === 'Last4' ? last4.has(r.year) : r.year === year)
  const mine = all ? rows.filter(inClub) : (runners.get(athlete)?.rows || []).map(i => rows[i])
  const ageOk = (r) => ageGroup === 'All' || r.age_group === ageGroup
  const events = [...new Set(mine.filter(r => yearOk(r) && ageOk(r)).map(r => r.ev))].sort((a, b) => a.localeCompare(b))
  // the chosen group stays listed when another club or year has none
  const ages = [...new Set([...mine.filter(r => yearOk(r) && (event === 'All' || r.ev === event)).map(r => r.age_group),
    ...(ageGroup === 'All' ? [] : [ageGroup])])].filter(Boolean).sort((a, b) => ageRank(a) - ageRank(b))
  const shown = mine.filter(r => yearOk(r) && ageOk(r) && (event === 'All' || r.ev === event))
  const cap = all && club === 'All' ? SHOW : Infinity
  shown.sort((a, b) => {
    let d = 0
    if (sortField === 'date') d = a.date.localeCompare(b.date)
    else if (a.value != null && b.value != null) d = a.field ? a.value - b.value : b.value - a.value
    return sortDir === 'asc' ? d : -d
  })
  // aria-sort on the sorted column's header only
  const ariaSort = (f) => sortField === f ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined
  const sortBy = (f) => {
    if (sortField === f) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortField(f); setSortDir('desc') }
  }
  const who = (r) => r.legs || r.name || `${r.club} relay`
  const downloadCsv = () => {
    const q = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
    const csv = [['Athlete', 'Event', 'Result', 'Age group', 'Club', 'Date', 'Meet', 'Year'].join(','),
      ...shown.map(r => [who(r), r.ev, r.mark, r.age_group, r.club, r.date, r.meetName, r.year].map(q).join(','))].join('\n')
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }))
    link.download = 'summer.csv'; link.click()
  }
  return (
    <div className="summer-track">
      <div className="filter-bar">
        {clubPicker}
        {athletePicker(true, athlete)}
        <div className="filter-group">
          <label>Year</label>
          <select value={year} onChange={e => setYear(e.target.value)}>
            <option value="All">All Years</option>
            <option value="Last4">Last 4 Years</option>
            {years.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div className="filter-group">
          <label><Tip tip="USATF age group">Age group</Tip></label>
          <select value={ageGroup} onChange={e => setAgeGroup(e.target.value)}>
            <option value="All">All Ages</option>
            {ages.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
        <div className="filter-group">
          <label>Event</label>
          <select value={event} onChange={e => setEvent(e.target.value)}>
            <option value="All">All Events</option>
            {events.map(ev => <option key={ev} value={ev}>{ev}</option>)}
          </select>
        </div>
        <button className="download-btn" onClick={downloadCsv}>CSV</button>
      </div>
      <div className="table-container">
        <table className="performance-table">
          <thead>
            <tr>
              <th scope="col" aria-sort={ariaSort('date')}><button type="button" className="sort-btn" onClick={() => sortBy('date')}>Date</button></th>
              {all && <th scope="col">Athlete</th>}
              <th scope="col">Event</th>
              <th scope="col" aria-sort={ariaSort('mark')}><button type="button" className="sort-btn" onClick={() => sortBy('mark')}>Result</button></th>
              <th scope="col">Meet</th>
            </tr>
          </thead>
          <tbody>
            {shown.slice(0, cap).map(r => (
              <tr key={r.i} className={r.isPr ? 'pr-row' : ''}>
                <td>{all ? r.date : <Tip tip={ageTip(r)}>{r.date}<Age r={r} /></Tip>}</td>
                {all && <td><Tip tip={[r.club, ageTip(r)].filter(Boolean).join('\n')}>{who(r)}<Age r={r} /></Tip></td>}
                <td>{r.ev}</td>
                <td>{r.mark}{r.isPr && <span className="badge pr">PR</span>}</td>
                <td>{r.url
                  ? <a className="meet-link" href={r.url} target="_blank" rel="noopener noreferrer">{r.meetName}</a>
                  : r.meetName}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {shown.length > cap && <p className="summer-note"><Tip tip="Pick a club, athlete, year or event to narrow the list">
        {SHOW.toLocaleString()} of {shown.length.toLocaleString()}</Tip></p>}
    </div>
  )
}
