import React, { useState, useEffect, useMemo } from 'react'
import { asset, fetchGz } from './utils'
import AthleteProfile from './AthleteProfile'
import SearchSelect from './SearchSelect'

/**
 * Summer track: the USATF Maine Youth Developmental Summer Series (14 & under).
 * Kids race for summer clubs in two-year age groups, so this tab has its own
 * data (ui/public/data/summer.json.gz from backend/summer_track.py) and its
 * own board: results by meet, and a record board by club, age group and event,
 * kept apart from the school records.
 */

const HOME_CLUB = 'Blue Hill Peninsula'   // GSA's summer program
const FIELD = /jump|vault|put|shot|discus|javelin|throw|turbo|softball|hammer/i
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

export default function SummerTrack({ view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [club, setClub] = useState(HOME_CLUB)
  const [meet, setMeet] = useState(null)
  const [gender, setGender] = useState('Girls')
  const [athlete, setAthlete] = useState(null)

  useEffect(() => {
    fetchGz(asset('/data/summer.json.gz')).then(setData).catch(e => setError(String(e)))
  }, [])

  const rows = useMemo(() => {
    if (!data) return []
    const c = Object.fromEntries(data.cols.map((k, i) => [k, i]))
    return data.rows.map(r => Object.fromEntries(Object.entries(c).map(([k, i]) => [k, r[i]])))
  }, [data])

  // Maine series clubs first; clubs seen only at Junior Olympic / regional meets after
  const clubs = useMemo(() => {
    const n = {}
    rows.forEach(r => { if (r.club) n[r.club] = (n[r.club] || 0) + 1 })
    const series = new Set(data?.series_clubs || [])
    const all = Object.keys(n).sort((a, b) => a.localeCompare(b))
    return { series: all.filter(c => series.has(c)), other: all.filter(c => !series.has(c)) }
  }, [rows, data])

  // One runner: the athletic.net id where printed; otherwise name, gender and
  // club (a common name in another club is another kid). Rows without the id
  // join the id'd runner with the same name, gender and club.
  const runners = useMemo(() => {
    const key = (r) => `${r.name}|${r.gender}|${r.club}`
    const aidOf = {}
    rows.forEach(r => { if (r.aid && r.name) aidOf[key(r)] ||= r.aid })
    const by = {}
    rows.forEach((r, i) => {
      // relay teams and points events (pentathlon) are not one runner's marks
      if (r.legs || !r.name || /athlon/i.test(r.event) || r.value == null) return
      const id = r.aid || aidOf[key(r)] || key(r)
      const a = (by[id] ||= { id, name: r.name, gender: r.gender, clubs: new Set(), rows: [] })
      a.clubs.add(r.club)
      a.rows.push(i)
    })
    return Object.values(by)
  }, [rows])

  const meetOrder = useMemo(() => data
    ? data.meets.map((m, i) => ({ ...m, i })).sort((a, b) => (b.date || '').localeCompare(a.date || ''))
    : [], [data])

  if (error) return <div className="summer-track"><p>Could not load summer results: {error}</p></div>
  if (!data) return <div className="summer-track"><p>Loading summer results...</p></div>

  const inClub = (r) => club === 'All' || r.club === club
  const clubPicker = (
    <div className="filter-group">
      <label>Club</label>
      <select value={club} onChange={e => setClub(e.target.value)}>
        <option value="All">All clubs</option>
        <optgroup label="Maine summer series clubs">
          {clubs.series.map(c => <option key={c} value={c}>{c}</option>)}
        </optgroup>
        {clubs.other.length > 0 && (
          <optgroup label="Other clubs (Junior Olympic meets)">
            {clubs.other.map(c => <option key={c} value={c}>{c}</option>)}
          </optgroup>
        )}
      </select>
    </div>
  )

  if (view === 'records') {
    // best mark per runner, top 10 per gender / age group / event
    const boards = {}
    rows.filter(r => r.gender === gender && inClub(r)).forEach(r => {
      const key = `${r.age_group}|${r.event}`
      const who = r.legs ? `${r.club}: ${r.legs}` : (r.aid || r.name)
      const field = FIELD.test(r.event)
      const b = (boards[key] ||= {})
      if (!b[who] || (field ? r.value > b[who].value : r.value < b[who].value)) b[who] = r
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
          const field = FIELD.test(ev)
          const list = Object.values(boards[k]).sort((a, b) => field ? b.value - a.value : a.value - b.value).slice(0, 10)
          return (
            <div key={k} className="summer-board">
              <h3>{ev} <span className="summer-age">{age}</span></h3>
              <table className="summer-table">
                <tbody>
                  {list.map((r, i) => {
                    const m = data.meets[r.meet]
                    return (
                      <tr key={i}>
                        <td>{i + 1}</td>
                        <td>{r.legs || r.name}{club === 'All' && <span className="summer-club"> · {r.club}</span>}</td>
                        <td className="summer-mark">{r.mark}</td>
                        <td>{m.date}</td>
                        <td><a href={m.url} target="_blank" rel="noopener noreferrer">{m.name}</a></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )
        })}
      </div>
    )
  }

  if (view === 'athlete-profile') {
    const list = runners.filter(a => club === 'All' || a.clubs.has(club))
      .sort((a, b) => a.name.localeCompare(b.name))
    // opens on the club's runner with the most marks
    const cur = list.find(a => a.id === athlete)
      || list.reduce((b, a) => (!b || a.rows.length > b.rows.length ? a : b), null)
    const perfs = cur ? cur.rows.map(i => {
      const r = rows[i], m = data.meets[r.meet]
      const field = FIELD.test(r.event)
      return {
        id: i, event: r.event, mark: r.mark, date: m.date, year: (m.date || '').slice(0, 4),
        meet_name: m.name, age: r.age,
        // field values are meters; the profile charts inches (to the quarter inch)
        numericValue: field ? Math.round(r.value * 39.3701 * 4) / 4 : r.value, isTime: !field,
      }
    }) : []
    return (
      <div className="summer-track">
        <div className="filter-bar">
          {clubPicker}
          <div className="filter-group">
            <label>Athlete</label>
            <SearchSelect value={cur?.id ?? ''} onChange={setAthlete}
              options={list.map(a => ({ value: a.id, label: a.name,
                secondary: club === 'All' ? [...a.clubs].join(', ') : `${a.rows.length}` }))}
              placeholder="Search athletes..." minSearch={club === 'All' ? 2 : 0} />
          </div>
        </div>
        {cur ? <AthleteProfile performances={perfs} selectedAthlete={cur} />
          : <p>No athletes for this club.</p>}
      </div>
    )
  }

  // Results: one meet, grouped by event
  const mi = meet ?? (meetOrder.find(m => rows.some(r => r.meet === m.i && inClub(r)))?.i ?? meetOrder[0]?.i)
  const m = data.meets[mi]
  const groups = {}
  rows.filter(r => r.meet === mi && inClub(r)).forEach(r => {
    (groups[`${r.gender}|${r.age_group}|${r.event}`] ||= []).push(r)
  })
  const gkeys = Object.keys(groups).sort((a, b) => {
    const [xa, ga, ea] = a.split('|'), [xb, gb, eb] = b.split('|')
    return xa.localeCompare(xb) || evRank(ea) - evRank(eb) || ageRank(ga) - ageRank(gb)
  })
  return (
    <div className="summer-track">
      <div className="filter-bar">
        {clubPicker}
        <div className="filter-group">
          <label>Meet</label>
          <select value={mi} onChange={e => setMeet(+e.target.value)}>
            {meetOrder.map(x => <option key={x.i} value={x.i}>{x.date} {x.name}{x.season === 'Indoor' ? ' (indoor)' : ''}</option>)}
          </select>
        </div>
      </div>
      {m && <p className="summer-note">{m.date} · {m.venue} · <a href={m.url} target="_blank" rel="noopener noreferrer">full results</a></p>}
      {gkeys.length === 0 && <p>No results for this club at this meet.</p>}
      {gkeys.map(k => {
        const [g, age, ev] = k.split('|')
        return (
          <div key={k} className="summer-board">
            <h3>{g} {ev} <span className="summer-age">{age}</span></h3>
            <table className="summer-table">
              <tbody>
                {groups[k].sort((a, b) => (a.place ?? 999) - (b.place ?? 999)).map((r, i) => (
                  <tr key={i}>
                    <td>{r.place ?? ''}</td>
                    <td>{r.legs || r.name}{club === 'All' && <span className="summer-club"> · {r.club}</span>}</td>
                    <td className="summer-mark">{r.mark}</td>
                    <td>{r.age ? `age ${r.age}` : ''}</td>
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
