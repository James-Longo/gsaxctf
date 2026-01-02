
import React, { useState, useEffect, useMemo } from 'react'
import { isBetter } from './utils'
import PerformanceList from './PerformanceList'
import PRPopCalculator from './PRPopCalculator'
import './App.css'

const ALL_ATHLETES = { id: 'all', name: 'All Athletes' }
const PERFORMANCE_ANALYZER = { id: 'analyzer', name: 'Performance Analyzer' }
const PR_POP_CALCULATOR = { id: 'pr-pop', name: 'PR Pop Calculator' }
const MEET_SHEET = { id: 'meet-sheet', name: 'Meet Sheet' }

import MeetSheet from './MeetSheet'

function App() {
  const [allPerformances, setAllPerformances] = useState([])
  const [dataLoaded, setDataLoaded] = useState(false)

  const [selectedTeam, setSelectedTeam] = useState('George Stevens Academy')
  const [selectedAthlete, setSelectedAthlete] = useState(ALL_ATHLETES)

  const [expandedSplits, setExpandedSplits] = useState(new Set())

  // Filter states
  const [filterYear, setFilterYear] = useState('All')
  const [filterSeasonType, setFilterSeasonType] = useState('All')
  const [filterEvent, setFilterEvent] = useState('All')
  const [filterMeet, setFilterMeet] = useState('All')
  const [showPRsOnly, setShowPRsOnly] = useState(false)

  // Sort states
  const [sortField, setSortField] = useState('date') // 'date' or 'mark/result'
  const [sortDirection, setSortDirection] = useState('desc')

  // Load static data on mount
  useEffect(() => {
    fetch('/data.json')
      .then(res => res.json())
      .then(data => {
        setAllPerformances(data)
        setDataLoaded(true)
      })
      .catch(err => {
        console.error('Error loading data.json:', err)
        // Fallback for local dev if data.json isn't exported yet
        fetch('http://localhost:8000/performances')
          .then(res => res.json())
          .then(data => {
            setAllPerformances(data)
            setDataLoaded(true)
          })
          .catch(e => console.error('Local dev fallback failed:', e))
      })
  }, [])

  // Derived: Unique Teams
  const teams = useMemo(() => {
    const t = new Set(allPerformances.map(p => p.team).filter(Boolean))
    return Array.from(t).sort()
  }, [allPerformances])

  // Derived: Athletes for the current view
  const athletes = useMemo(() => {
    let filtered = allPerformances
    if (selectedTeam !== 'All') {
      filtered = allPerformances.filter(p => p.team === selectedTeam)
    }

    const uniqueAthletes = {}
    filtered.forEach(p => {
      if (!uniqueAthletes[p.athlete_id]) {
        uniqueAthletes[p.athlete_id] = { id: p.athlete_id, name: p.athlete_name }
      }
    })

    return Object.values(uniqueAthletes).sort((a, b) => a.name.localeCompare(b.name))
  }, [allPerformances, selectedTeam])

  // Current performances to display (subset of allPerformances based on selectedAthlete)
  const performances = useMemo(() => {
    if (!selectedAthlete) return []
    if (selectedAthlete.id === 'all' || selectedAthlete.id === 'pr-pop' || selectedAthlete.id === 'analyzer') {
      return allPerformances
    }
    return allPerformances.filter(p => p.athlete_id === selectedAthlete.id)
  }, [allPerformances, selectedAthlete])

  const [isScraping, setIsScraping] = useState(false)
  const [scrapeStatus, setScrapeStatus] = useState({ message: '', progress: 0 })

  const isLocalDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'

  const handleScrape = async (full = false) => {
    if (!isLocalDev) return
    try {
      const url = `http://localhost:8000/scrape/sub5?full=${full}`
      const res = await fetch(url, { method: 'POST' })
      const result = await res.json()
      if (result.status === 'started' || result.status === 'busy') {
        setIsScraping(true)
      } else {
        throw new Error(result.message || 'Failed to start')
      }
    } catch (err) {
      console.error(err)
      alert(`Scrape failed to start: ${err.message}`)
    }
  }

  // Polling for scrape status (Local Only)
  useEffect(() => {
    if (!isLocalDev || !isScraping) return
    const interval = setInterval(async () => {
      try {
        const res = await fetch('http://localhost:8000/scrape/status')
        const data = await res.json()
        setScrapeStatus({ message: data.message, progress: data.progress })
        if (!data.is_active) {
          setIsScraping(false)
          if (data.message.includes('Finished')) {
            alert(data.message)
          }
          window.location.reload() // Reload to get new data.json if built
        }
      } catch (err) {
        console.error('Status check error:', err)
        clearInterval(interval)
      }
    }, 1000)
    return () => clearInterval(interval)
  }, [isScraping, isLocalDev])

  // Reset filters and sort when changing view (selectedAthlete or selectedTeam)
  useEffect(() => {
    setFilterYear('All')
    setFilterSeasonType('All')
    setFilterEvent('All')
    setFilterMeet('All')
    setSortField('date')
    setSortDirection('desc')
    setExpandedSplits(new Set())
  }, [selectedAthlete, selectedTeam])


  // Extract metadata and unique filter values
  const { filteredPerformances, years, seasonTypes, events, meets } = useMemo(() => {
    // Pass 1: Find absolute bests per (Athlete, Event, Type/Season)
    const absoluteBests = {} // key -> mark
    const absoluteBestIds = new Set()
    const seasonBests = {} // key -> mark
    const seasonBestIds = new Set()
    const firstPerfIds = new Set()
    const seenEvents = new Set()

    // 1a. Sort chronologically to find EARLIEST best and First-time
    const sortedChronological = [...performances].sort((a, b) => new Date(a.date) - new Date(b.date))

    sortedChronological.forEach(p => {
      let type = p.season
      let year = p.year
      const match = p.season.match(/^(\d{4})\s+(.*)$/)
      if (match) {
        year = year || match[1]
        type = match[2]
      }

      const prK = `${p.athlete_id}|${p.event}|${type}`
      const sbK = `${p.athlete_id}|${year}|${type}|${p.event}`

      // First Time
      if (!seenEvents.has(prK)) {
        firstPerfIds.add(p.id)
        seenEvents.add(prK)
      }

      // Track all-time best (Earliest one wins the badge if multiple exist)
      if (!absoluteBests[prK] || isBetter(p.mark, absoluteBests[prK])) {
        absoluteBests[prK] = p.mark
      }

      // Track season best
      if (!seasonBests[sbK] || isBetter(p.mark, seasonBests[sbK])) {
        seasonBests[sbK] = p.mark
      }
    })

    // 1b. Identify which specific IDs are the milestones (Earliest occurrence of absolute best)
    // To properly support the "tie" rule, we pick the FIRST one that matches the BEST
    const claimedPR = new Set()
    const claimedSB = new Set()

    sortedChronological.forEach(p => {
      let type = p.season
      let year = p.year
      const match = p.season.match(/^(\d{4})\s+(.*)$/)
      if (match) {
        year = year || match[1]
        type = match[2]
      }
      const prK = `${p.athlete_id}|${p.event}|${type}`
      const sbK = `${p.athlete_id}|${year}|${type}|${p.event}`

      if (p.mark === absoluteBests[prK] && !claimedPR.has(prK)) {
        absoluteBestIds.add(p.id)
        claimedPR.add(prK)
      }
      if (p.mark === seasonBests[sbK] && !claimedSB.has(sbK)) {
        seasonBestIds.add(p.id)
        claimedSB.add(sbK)
      }
    })

    const enriched = performances.map(perf => {
      let year = perf.year
      let type = perf.season
      if (!year || (type && type.match(/^\d{4}/))) {
        const match = perf.season.match(/^(\d{4})\s+(.*)$/)
        if (match) {
          year = match[1]
          type = match[2]
        } else {
          year = year || 'Unknown'
          type = type || perf.season
        }
      }

      const meetWithYear = `${perf.meet_name} (${year})`

      return {
        ...perf,
        derivedYear: year,
        derivedType: type,
        meetWithYear,
        isFirstTime: firstPerfIds.has(perf.id),
        isCalculatedPR: absoluteBestIds.has(perf.id),
        isCalculatedSB: seasonBestIds.has(perf.id)
      }
    })

    // Helper to check if a performance matches specific filters
    const matches = (p, filters) => {
      const { year, type, event, meet, team } = filters
      return (year === undefined || year === 'All' || p.derivedYear === year) &&
        (type === undefined || type === 'All' || p.derivedType === type) &&
        (event === undefined || event === 'All' || p.event === event) &&
        (meet === undefined || meet === 'All' || p.meetWithYear === meet) &&
        (team === undefined || team === 'All' || p.team === team)
    }

    // Dynamic Filter Options (Faceting)
    // Each set of options depends on ALL OTHER filters currently active
    const availableYears = Array.from(new Set(
      enriched.filter(p => matches(p, { type: filterSeasonType, event: filterEvent, meet: filterMeet, team: selectedTeam })).map(p => p.derivedYear)
    )).sort((a, b) => b - a)

    const availableTypes = Array.from(new Set(
      enriched.filter(p => matches(p, { year: filterYear, event: filterEvent, meet: filterMeet, team: selectedTeam })).map(p => p.derivedType)
    )).sort()

    const availableEvents = Array.from(new Set(
      enriched.filter(p => matches(p, { year: filterYear, type: filterSeasonType, meet: filterMeet, team: selectedTeam })).map(p => p.event)
    )).sort()

    const availableMeets = Array.from(new Set(
      enriched.filter(p => matches(p, { year: filterYear, type: filterSeasonType, event: filterEvent, team: selectedTeam })).map(p => p.meetWithYear)
    )).sort()

    // Second pass: Filter
    let filtered = enriched.filter(p => matches(p, { year: filterYear, type: filterSeasonType, event: filterEvent, meet: filterMeet, team: selectedTeam }))

    if (showPRsOnly) {
      filtered = filtered.filter(p => p.isCalculatedPR)
    }

    // Third pass: Sort
    filtered.sort((a, b) => {
      let comparison = 0
      if (sortField === 'date') {
        comparison = new Date(a.date) - new Date(b.date)
      } else if (sortField === 'mark' || sortField === 'result') {
        if (isBetter(a.mark, b.mark)) comparison = 1
        else if (isBetter(b.mark, a.mark)) comparison = -1
        else comparison = 0
      }
      return sortDirection === 'asc' ? comparison : -comparison
    })

    console.debug('Filter Debug:', {
      performancesCount: performances.length,
      filteredCount: filtered.length,
      availableYears,
      availableMeets
    })

    return {
      filteredPerformances: filtered,
      years: availableYears,
      seasonTypes: availableTypes,
      events: availableEvents,
      meets: availableMeets
    }
  }, [performances, filterYear, filterSeasonType, filterEvent, filterMeet, selectedTeam, showPRsOnly, sortField, sortDirection])

  const handleSort = (field) => {
    const canonicalField = field === 'result' ? 'mark' : field
    if (sortField === canonicalField) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(canonicalField)
      setSortDirection('desc') // Default to best/latest at top
    }
  }

  const toggleSplits = (id) => {
    setExpandedSplits(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const renderSortIcon = (field) => {
    if (sortField !== field) return null
    return sortDirection === 'asc' ? ' ↑' : ' ↓'
  }

  return (
    <div className="container">
      <h1>Track & Field Dashboard</h1>

      <div className="dashboard-layout">
        <div className="sidebar">
          {/* Main Navigation / Mode Switching */}
          <div className="nav-buttons">
            <button
              onClick={() => setSelectedAthlete(ALL_ATHLETES)}
              className={`nav-btn ${selectedAthlete && selectedAthlete.id !== 'analyzer' && selectedAthlete.id !== 'pr-pop' ? 'active' : ''}`}
            >
              🏃‍♂️ Performance History
            </button>
            <button
              onClick={() => setSelectedAthlete(PERFORMANCE_ANALYZER)}
              className={`nav-btn ${selectedAthlete?.id === 'analyzer' ? 'active' : ''}`}
            >
              📊 PVC Simulator
            </button>
            <button
              onClick={() => setSelectedAthlete(PR_POP_CALCULATOR)}
              className={`nav-btn ${selectedAthlete?.id === 'pr-pop' ? 'active' : ''}`}
            >
              🚀 PR Pop Calculator
            </button>
            <button
              onClick={() => setSelectedAthlete(MEET_SHEET)}
              className={`nav-btn ${selectedAthlete?.id === 'meet-sheet' ? 'active' : ''}`}
            >
              📋 Create Meet Sheet
            </button>
          </div>

          {isLocalDev && (
            <div className="dev-controls">
              <h3>Dev Controls</h3>
              <div className="action-buttons">
                <button
                  className={`update-btn ${isScraping ? 'loading' : ''}`}
                  onClick={() => handleScrape(false)}
                  disabled={isScraping}
                >
                  {isScraping ? 'Updating...' : 'Update Data'}
                </button>
                <div
                  className="full-rescrape-link"
                  onClick={() => {
                    if (window.confirm("This will wipe all currently saved data and re-download everything. Proceed?")) {
                      handleScrape(true);
                    }
                  }}
                  style={{
                    fontSize: '0.7rem',
                    color: '#a0aec0',
                    cursor: 'pointer',
                    marginTop: '4px',
                    textAlign: 'center',
                    textDecoration: 'underline'
                  }}
                >
                  Full Rescrape
                </div>
              </div>
            </div>
          )}

          {isScraping && (
            <div className="progress-container">
              <div className="progress-bar-bg">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${scrapeStatus.progress}%` }}
                ></div>
              </div>
              <div className="progress-text">
                <span className="progress-msg">{scrapeStatus.message}</span>
                <span className="progress-pct">{scrapeStatus.progress}%</span>
              </div>
            </div>
          )}

        </div>

        <div className="main-content">
          {selectedAthlete?.id === 'analyzer' ? (
            <PerformanceList performances={performances} isBetter={isBetter} />
          ) :
            selectedAthlete?.id === 'pr-pop' ? (
              <>
                <div className="filter-bar">
                  <div className="filter-group">
                    <label>Team</label>
                    <select
                      value={selectedTeam}
                      onChange={e => setSelectedTeam(e.target.value)}
                    >
                      <option value="All">All Teams</option>
                      {teams.map(team => (
                        <option key={team} value={team}>{team}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <PRPopCalculator
                  performances={performances}
                  selectedTeam={selectedTeam}
                  isBetter={isBetter}
                />
              </>
            ) : selectedAthlete?.id === 'meet-sheet' ? (
              <MeetSheet />
            ) : selectedAthlete && selectedAthlete.id !== 'analyzer' ? (
              <>
                <div className="header-row">
                  <h2>{selectedAthlete.name} - Performance History</h2>
                  <div className="record-count">{filteredPerformances.length} Results</div>
                </div>

                <div className="filter-bar">
                  <div className="filter-group">
                    <label>Team</label>
                    <select
                      value={selectedTeam}
                      onChange={e => setSelectedTeam(e.target.value)}
                    >
                      <option value="All">All Teams</option>
                      {teams.map(team => (
                        <option key={team} value={team}>{team}</option>
                      ))}
                    </select>
                  </div>

                  <div className="filter-group">
                    <label>Athlete</label>
                    <select
                      value={selectedAthlete ? selectedAthlete.id : 'all'}
                      onChange={(e) => {
                        const val = e.target.value;
                        if (val === 'all') setSelectedAthlete(ALL_ATHLETES);
                        else {
                          const ath = athletes.find(a => String(a.id) === val);
                          if (ath) setSelectedAthlete(ath);
                        }
                      }}
                    >
                      <option value="all">All Athletes</option>
                      {athletes.map(athlete => (
                        <option key={athlete.id} value={athlete.id}>{athlete.name}</option>
                      ))}
                    </select>
                  </div>

                  <div className="filter-group">
                    <label>Year</label>
                    <select value={filterYear} onChange={e => setFilterYear(e.target.value)}>
                      <option value="All">All Years</option>
                      {years.map(y => <option key={y} value={y}>{y}</option>)}
                    </select>
                  </div>

                  <div className="filter-group">
                    <label>Season</label>
                    <select value={filterSeasonType} onChange={e => setFilterSeasonType(e.target.value)}>
                      <option value="All">All Seasons</option>
                      {seasonTypes.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>

                  <div className="filter-group">
                    <label>Event</label>
                    <select value={filterEvent} onChange={e => setFilterEvent(e.target.value)}>
                      <option value="All">All Events</option>
                      {events.map(ev => <option key={ev} value={ev}>{ev}</option>)}
                    </select>
                  </div>

                  <div className="filter-group">
                    <label>Meet</label>
                    <select value={filterMeet} onChange={e => setFilterMeet(e.target.value)}>
                      <option value="All">All Meets</option>
                      {meets.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  </div>

                  <div className="simulation-toggle">
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={showPRsOnly}
                        onChange={e => setShowPRsOnly(e.target.checked)}
                      />
                      <span className="slider round"></span>
                    </label>
                    <span className="toggle-label">PRs Only</span>
                  </div>
                </div>

                <div className="table-container">
                  <table className="performance-table">
                    <thead>
                      <tr>
                        <th onClick={() => handleSort('date')} className="sortable">Date {renderSortIcon('date')}</th>
                        {selectedAthlete.id === 'all' && <th>Athlete</th>}
                        {selectedTeam === 'All' && <th>Team</th>}
                        {filterSeasonType === 'All' && <th>Season</th>}
                        {filterEvent === 'All' && <th>Event</th>}
                        <th onClick={() => handleSort('result')} className="sortable">Result {renderSortIcon('mark')}</th>
                        {filterMeet === 'All' && <th>Meet</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredPerformances.length > 0 ? (
                        filteredPerformances.map(perf => (
                          <React.Fragment key={perf.id}>
                            <tr className={perf.isCalculatedPR ? 'pr-row' : ''}>
                              <td>{perf.date.split('T')[0]}</td>
                              {selectedAthlete.id === 'all' && <td className="athlete-name-cell">{perf.athlete_name}</td>}
                              {selectedTeam === 'All' && <td>{perf.team}</td>}
                              {filterSeasonType === 'All' && <td>{perf.season}</td>}
                              {filterEvent === 'All' && <td>{perf.event}</td>}
                              <td>
                                <div className="result-cell-content">
                                  <span className="result-val">{perf.mark}</span>
                                  {!!perf.isCalculatedPR && <span className="badge pr">PR</span>}
                                  {!!perf.isCalculatedSB && <span className="badge sb">SB</span>}
                                  {!!perf.isFirstTime && <span className="badge first">*</span>}
                                  {perf.splits && perf.splits.length > 0 && (
                                    <button
                                      className="splits-toggle-btn"
                                      onClick={() => toggleSplits(perf.id)}
                                    >
                                      {expandedSplits.has(perf.id) ? 'Hide Splits' : 'Show Splits'}
                                    </button>
                                  )}
                                </div>
                              </td>
                              {filterMeet === 'All' && <td>{perf.meetWithYear}</td>}
                            </tr>
                            {expandedSplits.has(perf.id) && (
                              <tr className="splits-row">
                                <td colSpan="10">
                                  <div className="splits-container">
                                    <div className="splits-label">Splits:</div>
                                    <div className="splits-list">
                                      {perf.splits.map((s, idx) => (
                                        <div key={idx} className="split-item">
                                          <span className="split-index">{idx + 1}:</span>
                                          <span className="split-val">{s}</span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        ))
                      ) : (
                        <tr>
                          <td colSpan="10" className="no-results">No results match your filters</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="empty-state">
                <p>Select an athlete to view details.</p>
              </div>
            )}
        </div>
      </div>
    </div >
  )
}

export default App
