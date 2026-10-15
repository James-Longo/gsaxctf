import React, { useState, useEffect, useMemo } from 'react'
import { asset } from './utils'
import SearchSelect from './SearchSelect'

/**
 * XC Course Explorer - course equivalence built from athletes who raced
 * multiple courses in the same season (backend/xc_course_model.py).
 *
 * One number per course, multiplicative: time on B = time on A * fB / fA.
 * It absorbs everything that makes a race take longer -- length, hills,
 * footing -- and is measured from runners who raced both courses, so no
 * course distance is involved anywhere.
 */

const fetchGz = async (url) => {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const buf = await res.arrayBuffer()
  const bytes = new Uint8Array(buf)
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    const ds = new DecompressionStream('gzip')
    const stream = new Response(buf).body.pipeThrough(ds)
    return JSON.parse(await new Response(stream).text())
  }
  return JSON.parse(new TextDecoder().decode(buf))
}

const parseTime = (s) => {
  const m = String(s).trim().match(/^(\d{1,2}):([0-5]?\d)(?:\.(\d+))?$/)
  if (!m) return null
  return parseInt(m[1]) * 60 + parseInt(m[2]) + (m[3] ? parseFloat('0.' + m[3]) : 0)
}

const fmtTime = (secs) => {
  const mm = Math.floor(secs / 60)
  const ss = secs - mm * 60
  return `${mm}:${ss.toFixed(1).padStart(4, '0')}`
}

export default function XCCourseExplorer() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [fromCourse, setFromCourse] = useState('')
  const [toCourse, setToCourse] = useState('')
  const [timeInput, setTimeInput] = useState('19:00')
  const [sortAsc, setSortAsc] = useState(true)

  useEffect(() => {
    fetchGz(asset('/data/xc_courses.json.gz')).then(setData).catch(e => setError(String(e)))
  }, [])

  // A venue with more than one course needs something on the row to tell
  // them apart: the distance the results call it when the venue has races
  // of different lengths, and the years when one course changed between
  // eras (an older era is published as its own course).
  const label = useMemo(() => {
    const dists = {}, perVD = {}
    for (const c of (data?.courses || [])) {
      ;(dists[c.venue] ||= new Set()).add(c.distance)
      const k = `${c.venue}|${c.distance}`
      perVD[k] = (perVD[k] || 0) + 1
    }
    const m = {}
    for (const c of (data?.courses || [])) {
      let s = c.venue
      if (c.distance && dists[c.venue].size > 1) s += ` · ${c.distance}`
      // an era is contiguous: name it by its span, the current one "since"
      if (perVD[`${c.venue}|${c.distance}`] > 1) {
        const ys = c.years || []
        const newest = Math.max(...(data.courses.filter(x => x.venue === c.venue && x.distance === c.distance)
          .flatMap(x => (x.years || []).map(Number))))
        s += Number(ys[ys.length - 1]) === newest ? ` (since ${ys[0]})` : ` (${ys[0]}–${ys[ys.length - 1]})`
      }
      m[c.course] = s
    }
    return m
  }, [data])

  const options = useMemo(() => (data?.courses || []).map(c => ({
    value: c.course, label: label[c.course] || c.venue,
    secondary: `typical ${c.medianTime} | ${c.athletes} athletes`,
  })), [data, label])

  const byName = useMemo(() => {
    const m = {}
    for (const c of (data?.courses || [])) m[c.course] = c
    return m
  }, [data])

  const converted = useMemo(() => {
    const a = byName[fromCourse]
    const b = byName[toCourse]
    const t = parseTime(timeInput)
    if (!a || !b || t == null) return null
    return t * (b.factor / a.factor)
  }, [byName, fromCourse, toCourse, timeInput])

  const ranked = useMemo(() => {
    const rows = [...(data?.courses || [])]
    rows.sort((x, y) => sortAsc ? x.factor - y.factor : y.factor - x.factor)
    return rows
  }, [data, sortAsc])

  if (error) return <div className="xc-explorer"><p>Could not load course model: {error}</p></div>
  if (!data) return <div className="xc-explorer"><p>Loading course model...</p></div>

  return (
    <div className="xc-explorer">
      <h2>XC Course Explorer</h2>

      <div className="xc-converter">
        <h3>Time Converter</h3>
        <div className="xc-conv-row">
          <div className="filter-group">
            <label>Time</label>
            <input className="xc-time" value={timeInput}
                   onChange={e => setTimeInput(e.target.value)} placeholder="19:00" />
          </div>
          <div className="filter-group">
            <label>On course</label>
            <SearchSelect value={fromCourse} onChange={setFromCourse}
                          options={options} placeholder="Search courses..." />
          </div>
          <div className="filter-group">
            <label>Equivalent on</label>
            <SearchSelect value={toCourse} onChange={setToCourse}
                          options={options} placeholder="Search courses..." />
          </div>
          <div className="filter-group">
            <label>Result</label>
            <div className="xc-result">
              {converted != null ? fmtTime(converted) : '--:--'}
            </div>
          </div>
        </div>
        {converted != null && byName[fromCourse] && byName[toCourse] && (
          <p className="xc-note">
            A race at {label[toCourse]} takes{' '}
            {Math.abs((byName[toCourse].factor / byName[fromCourse].factor - 1) * 100).toFixed(1)}%{' '}
            {byName[toCourse].factor > byName[fromCourse].factor ? 'longer' : 'less'} than
            one at {label[fromCourse]}, from runners who raced both.
          </p>
        )}
      </div>

      <h3>Course Ratings</h3>
      <div className="table-container">
      <table className="performance-table">
        <thead>
          <tr>
            <th>#</th><th>Course</th>
            <th className="sortable active" onClick={() => setSortAsc(a => !a)}
                title="Sort by rating">
              Rating* {sortAsc ? '▲' : '▼'}
            </th>
            <th>Median time</th>
          </tr>
        </thead>
        <tbody>
          {ranked.map((c, i) => (
            <tr key={c.course}>
              <td>{i + 1}</td>
              <td>{label[c.course]}</td>
              <td>
                {c.factor.toFixed(3)}
                {c.factorSE != null && <span className="xc-se"> ±{c.factorSE.toFixed(3)}</span>}
              </td>
              <td>{c.medianTime}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <p className="xc-note">
        * Every rating is relative to the Festival of Champions course at
        Belfast, which is 1.000
      </p>
    </div>
  )
}
