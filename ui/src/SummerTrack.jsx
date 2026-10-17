import React, { useState, useEffect, useMemo } from 'react'
import { asset, fetchGz } from './utils'

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

  useEffect(() => {
    fetchGz(asset('/data/summer.json.gz')).then(setData).catch(e => setError(String(e)))
  }, [])

  const rows = useMemo(() => {
    if (!data) return []
    const c = Object.fromEntries(data.cols.map((k, i) => [k, i]))
    return data.rows.map(r => Object.fromEntries(Object.entries(c).map(([k, i]) => [k, r[i]])))
  }, [data])

  const clubs = useMemo(() => {
    const n = {}
    rows.forEach(r => { if (r.club) n[r.club] = (n[r.club] || 0) + 1 })
    return Object.keys(n).sort()
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
        {clubs.map(c => <option key={c} value={c}>{c}</option>)}
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
