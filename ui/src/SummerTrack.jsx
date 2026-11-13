import React, { useState, useEffect, useMemo, lazy, Suspense } from 'react'
import { asset, fetchGz } from './utils'
import SearchSelect from './SearchSelect'
import Tip from './Tip'

// charts (recharts) load when a profile is first opened
const AthleteProfile = lazy(() => import('./AthleteProfile'))

/**
 * Summer track: the USATF Maine Youth Developmental Summer Series (14 & under).
 * Kids race for summer clubs in two-year age groups, so this tab has its own
 * data (ui/public/data/summer.json.gz from backend/summer_track.py): results
 * and athlete profiles laid out like the school seasons', and a record board
 * by club, age group and event, kept apart from the school records.
 */

const HOME_CLUB = 'Blue Hill Peninsula'   // GSA's summer program
const FIELD = /jump|vault|put|shot|discus|javelin|throw|turbo|softball|hammer/i
// throws the school store prints to the whole inch; other field marks to the quarter
const WHOLE_INCH = /discus|javelin|hammer|turbo|softball/i
// field marks and multi-event point totals ('Pentathlon'; its legs read as the leg)
const higher = (e) => FIELD.test(e) || /^(tri|pent|hept|dec)athlon$/i.test(e)
const SHOW = 2000   // rows rendered for all clubs at once (~140k rows); one club shows all
// two-year groups, then the older USATF division names (2004-2008 Junior Olympic meets
// from sub5), then masters ranges ('40-49') last
const AGE_ORDER = ['8 & Under', '9-10', '11-12', '13-14', '15', '15-16', '17-18',
  'Bantam', 'Midget', 'Youth', 'Intermediate', 'Young']
const ageRank = (a) => (AGE_ORDER.indexOf(a) + 1) || (/^\d{2}-\d{2}$/.test(a) ? 100 + parseInt(a) : 99)
const evRank = (e) => {
  const m = e.match(/^(\d+)/)
  if (FIELD.test(e)) return 10000 + e.charCodeAt(0)
  if (/relay/i.test(e)) return 9000 + (m ? +m[1] : 0)
  return (m ? +m[1] : 5000) + (/hurdle/i.test(e) ? 0.5 : 0) + (/walk/i.test(e) ? 0.7 : 0)
}

// Summer event names in the school seasons' wording ("100 Meters" -> "100m Dash")
const eventLabel = (e) => e
  .replace(/^(\d+) Meters$/, (_, n) => +n <= 400 ? `${n}m Dash` : `${n}m Run`)
  .replace(/^(\d+)m Racewalk$/, '$1m Race Walk')
  .replace(/^(4x\d+) Relay$/, '$1m Relay')
  .replace(/^(\d+) Meters Steeplechase$/, '$1m Steeplechase')
  .replace(/^Shot Put Girls$/, 'Shot Put')

const pad2 = (n) => String(n).padStart(2, '0')
// A field mark in feet as the school store prints it ("14-03.25", "92-00"),
// and its length in inches. Results print feet or meters; a meter mark is
// converted from the stored value and rounded down (to the quarter inch, the
// whole inch for throws).
function feet(r) {
  const whole = WHOLE_INCH.test(r.event)
  const m = r.mark.match(/^(\d+)-(\d+)(\.\d+)?$/)
  if (m) return [`${m[1]}-${pad2(m[2])}${m[3] ? m[3].padEnd(3, '0') : whole ? '' : '.00'}`, +m[1] * 12 + +(m[2] + (m[3] || ''))]
  if (r.value && /^\d+(\.\d+)?m?$/.test(r.mark)) {
    const q = whole ? 1 : 4
    const ins = Math.floor(r.value / 0.0254 * q + 1e-6) / q
    const ft = Math.floor(ins / 12), rest = ins - ft * 12, ii = Math.floor(rest)
    return [`${ft}-${pad2(ii)}${whole ? '' : '.' + pad2(Math.round((rest - ii) * 100))}`, ins]
  }
  return [r.mark, r.value != null ? r.value / 0.0254 : null]
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
    fetchGz(asset('/data/summer.json.gz')).then(setData).catch(e => setError(String(e)))
  }, [])

  // Rows with their meet, school-style event names, field marks in feet, the
  // runner they belong to (rid) and whether each is that runner's PR.
  // One runner: the athletic.net id where printed; otherwise name, gender and
  // club (a common name in another club is another kid). Rows without the id
  // join the id'd runner with the same name, gender and club.
  const { rows, runners } = useMemo(() => {
    if (!data) return { rows: [], runners: new Map() }
    const c = Object.fromEntries(data.cols.map((k, i) => [k, i]))
    const rows = data.rows.map((x, i) => {
      const r = Object.fromEntries(Object.entries(c).map(([k, j]) => [k, x[j]]))
      const m = data.meets[r.meet]
      r.i = i
      r.event = eventLabel(r.event)
      r.ev = `${r.gender} ${r.event}`
      r.field = FIELD.test(r.event)
      if (r.field) [r.mark, r.inches] = feet(r)
      r.date = m.date || ''
      r.year = r.date.slice(0, 4)
      r.meetName = m.name
      r.url = m.url
      return r
    })
    const key = (r) => `${r.name}|${r.gender}|${r.club}`
    const aidOf = {}
    rows.forEach(r => { if (r.aid && r.name) aidOf[key(r)] ||= r.aid })
    const runners = new Map()
    rows.forEach(r => {
      if (r.legs || !r.name) return
      r.rid = r.aid || aidOf[key(r)] || key(r)
      let a = runners.get(r.rid)
      if (!a) runners.set(r.rid, a = { id: r.rid, name: r.name, gender: r.gender, clubs: new Set(), rows: [] })
      a.clubs.add(r.club)
      a.rows.push(r.i)
    })
    // PR: the runner's best in the event (the earliest, on a tie); points events have none
    const best = {}
    const better = (a, b) => a.field ? a.value > b.value : a.value < b.value
    ;[...rows].sort((a, b) => a.date.localeCompare(b.date)).forEach(r => {
      if (!r.rid || r.value == null || /athlon/i.test(r.event)) return
      const k = `${r.rid}|${r.ev}`
      if (!best[k] || better(r, best[k])) best[k] = r
    })
    Object.values(best).forEach(r => { r.isPr = true })
    return { rows, runners }
  }, [data])

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
      <label>Club</label>
      <SearchSelect value={club} onChange={pickClub} options={clubOptions} placeholder="Search clubs..." />
    </div>
  )
  const athletePicker = (withAll, value) => (
    <div className="filter-group">
      <label>Athlete</label>
      <SearchSelect value={value} onChange={pickAthlete}
        options={[...(withAll ? [{ value: 'all', label: 'All Athletes' }] : []),
          ...clubRunners.map(a => ({ value: a.id, label: a.name,
            secondary: club === 'All' ? [...a.clubs].join(', ') : `${a.rows.length}` }))]}
        placeholder="Search athletes..." minSearch={club === 'All' ? 2 : 0} />
    </div>
  )

  if (view === 'athlete-profile') {
    // opens on the club's runner with the most marks
    const cur = runners.get(athlete)
      || clubRunners.reduce((b, a) => (!b || a.rows.length > b.rows.length ? a : b), null)
    const perfs = cur ? cur.rows.map(i => rows[i])
      // points events (pentathlon) don't chart as a time or a distance
      .filter(r => r.value != null && !/athlon/i.test(r.event))
      .map(r => ({
        id: r.i, event: r.event, mark: r.mark, date: r.date, year: r.year,
        meet_name: r.meetName, age: r.age,
        numericValue: r.field ? r.inches : r.value, isTime: !r.field,
      })) : []
    return (
      <div className="summer-track">
        <div className="filter-bar">
          {clubPicker}
          {athletePicker(false, cur?.id ?? '')}
        </div>
        {cur ? <Suspense fallback={null}><AthleteProfile performances={perfs} selectedAthlete={cur} /></Suspense>
          : <p>No athletes for this club.</p>}
      </div>
    )
  }

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
