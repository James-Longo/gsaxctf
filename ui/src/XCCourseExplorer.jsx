import React, { useState, useEffect, useMemo } from 'react'
import SearchSelect from './SearchSelect'

/**
 * XC Course Explorer - course equivalence built from athletes who raced
 * multiple courses in the same season (backend/xc_course_model.py).
 *
 * factor is multiplicative: predicted time on B = time on A * fB / fA.
 * It reflects both course length and difficulty.
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
    fetchGz('/data/xc_courses.json.gz').then(setData).catch(e => setError(String(e)))
  }, [])

  const options = useMemo(() => (data?.courses || []).map(c => ({
    value: c.course, label: c.course,
    secondary: `med ${c.medianTime} | ${c.athletes} athletes`,
  })), [data])

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
      <p className="xc-note">
        Equivalence computed from athletes who raced multiple courses in the same
        season ({data.event}). A course's factor combines its length and difficulty:
        1.05 means times there run about 5% slower than the median Maine course.
      </p>

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
            {byName[toCourse].course} runs {byName[toCourse].factor > byName[fromCourse].factor
              ? 'slower' : 'faster'} than {byName[fromCourse].course} by{' '}
            {Math.abs((byName[toCourse].factor / byName[fromCourse].factor - 1) * 100).toFixed(1)}%.
          </p>
        )}
      </div>

      <h3>
        Course Difficulty Ranking{' '}
        <button className="xc-sort" onClick={() => setSortAsc(a => !a)}>
          {sortAsc ? 'fastest first' : 'slowest first'}
        </button>
      </h3>
      <table className="results-table">
        <thead>
          <tr>
            <th>#</th><th>Course</th><th>Factor</th><th>vs median</th>
            <th>Median 5K</th><th>Athletes</th><th>Races</th><th>Years</th>
          </tr>
        </thead>
        <tbody>
          {ranked.map((c, i) => (
            <tr key={c.course}>
              <td>{i + 1}</td>
              <td>{c.course}</td>
              <td>{c.factor.toFixed(3)}</td>
              <td>{c.pct > 0 ? '+' : ''}{c.pct.toFixed(1)}%</td>
              <td>{c.medianTime}</td>
              <td>{c.athletes.toLocaleString()}</td>
              <td>{c.races}</td>
              <td>{c.years[0]}–{c.years[c.years.length - 1]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
