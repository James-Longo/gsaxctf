
import React, { useState, useEffect, useMemo } from 'react'
import { isBetter } from './utils'
import PerformanceList from './PerformanceList'
import PRPopCalculator from './PRPopCalculator'
import './App.css'

const ALL_ATHLETES = { id: 'all', name: 'All Athletes' }
const PERFORMANCE_ANALYZER = { id: 'analyzer', name: 'Performance Analyzer' }
const PR_POP_CALCULATOR = { id: 'pr-pop', name: 'PR Pop Calculator' }
const MEET_SHEET = { id: 'meet-sheet', name: 'Meet Sheet' }
const ATHLETE_PROFILE = { id: 'athlete-profile', name: 'Athlete Profile' }
const PRACTICE_RESULTS = { id: 'practice', name: 'Practice Results' }

import MeetSheet from './MeetSheet'
import AthleteProfile from './AthleteProfile'
import PracticeResults from './PracticeResults'
import ResultPredictor from './ResultPredictor'
import Footage from './Footage'

function App() {
  const [dataLoaded, setDataLoaded] = useState(false)
  const [manifest, setManifest] = useState([])
  const [allAthletes, setAllAthletes] = useState([])
  const [loadedSeasons, setLoadedSeasons] = useState({}) // key -> data array
  
  const [selectedTeam, setSelectedTeam] = useState('George Stevens Academy')
  const [selectedAthlete, setSelectedAthlete] = useState(ALL_ATHLETES)
  const [activeTab, setActiveTab] = useState('history')

  const [expandedSplits, setExpandedSplits] = useState(new Set())

  // Filter states
  const [filterYear, setFilterYear] = useState('All')
  const [filterSeasonType, setFilterSeasonType] = useState('All')
  const [filterEvent, setFilterEvent] = useState('All')
  const [filterMeet, setFilterMeet] = useState('All')
  const [showPRsOnly, setShowPRsOnly] = useState(false)

  // Sort states
  const [sortField, setSortField] = useState('date')
  const [sortDirection, setSortDirection] = useState('desc')

  const isLocalDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'

  // 1. Initial Load: Manifest and Athletes
  useEffect(() => {
    const loadCore = async () => {
      try {
        const [manifestRes, athletesRes] = await Promise.all([
          fetch('/data/manifest.json'),
          fetch('/data/athletes.json')
        ]);
        const manifestData = await manifestRes.json();
        const athletesData = await athletesRes.json();
        
        setManifest(manifestData);
        setAllAthletes(athletesData);

        // Load the latest season by default
        if (manifestData.length > 0) {
          const sorted = [...manifestData].sort((a,b) => b.key.localeCompare(a.key));
          const latestKey = sorted[0].key;
          await loadSeason(latestKey);
        }
        
        setDataLoaded(true);
      } catch (err) {
        console.error('Initial load failed:', err);
      }
    };
    loadCore();
  }, [])

  const loadSeason = async (key) => {
    if (loadedSeasons[key]) return;
    try {
      const res = await fetch(`/data/${key}.json`);
      const data = await res.json();
      setLoadedSeasons(prev => ({ ...prev, [key]: data }));
    } catch (err) {
      console.error(`Failed to load season ${key}:`, err);
    }
  };

  // 2. Automatically load data based on filters or selected athlete
  useEffect(() => {
    if (!manifest.length) return;

    if (filterYear !== 'All' && filterSeasonType !== 'All') {
      const key = `${filterYear}_${filterSeasonType}`.replace(' ', '_');
      if (manifest.find(m => m.key === key)) {
        loadSeason(key);
      }
    } else if (filterYear !== 'All') {
      // Load all seasons for that year
      manifest.filter(m => m.year === filterYear).forEach(m => loadSeason(m.key));
    }
  }, [filterYear, filterSeasonType, manifest]);

  useEffect(() => {
    if (selectedAthlete && selectedAthlete.id !== 'all' && selectedAthlete.seasons) {
      selectedAthlete.seasons.forEach(key => loadSeason(key));
    }
  }, [selectedAthlete]);

  // Derive all loaded performances into one flat array
  const allPerformances = useMemo(() => {
    return Object.values(loadedSeasons).flat();
  }, [loadedSeasons]);

  // Derived: Unique Teams
  const teams = useMemo(() => {
    const t = new Set(allPerformances.map(p => p.team).filter(Boolean))
    return Array.from(t).sort()
  }, [allPerformances])

  // Derived: Athletes for the current view (filtered by team if not All)
  const filteredAthletes = useMemo(() => {
    if (selectedTeam === 'All') return allAthletes;
    
    // This is tricky: we only know if an athlete is on a team if we've loaded their data
    // For now, let's filter the allAthletes list based on what we've seen in allPerformances
    const seenAthleteIds = new Set(allPerformances.filter(p => p.team === selectedTeam).map(p => p.athlete_id));
    return allAthletes.filter(a => seenAthleteIds.has(a.id));
  }, [allAthletes, allPerformances, selectedTeam]);

  // Current performances to display
  const performances = useMemo(() => {
    if (!selectedAthlete) return []
    if (selectedAthlete.id === 'all') {
      if (selectedTeam === 'All') return allPerformances
      return allPerformances.filter(p => p.team === selectedTeam)
    }
    return allPerformances.filter(p => p.athlete_id === selectedAthlete.id)
  }, [allPerformances, selectedAthlete, selectedTeam])

  // Rest of the logic (Stats, filtering, sorting) is the same...
  const { filteredPerformances, years, seasonTypes, events, meets } = useMemo(() => {
    const absoluteBests = {} 
    const absoluteBestIds = new Set()
    const seasonBests = {} 
    const seasonBestIds = new Set()
    const firstPerfIds = new Set()
    const seenEvents = new Set()

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
      if (!seenEvents.has(prK)) {
        firstPerfIds.add(p.id)
        seenEvents.add(prK)
      }
      if (!absoluteBests[prK] || isBetter(p.mark, absoluteBests[prK])) {
        absoluteBests[prK] = p.mark
      }
      if (!seasonBests[sbK] || isBetter(p.mark, seasonBests[sbK])) {
        seasonBests[sbK] = p.mark
      }
    })

    const claimedPR = new Set()
    const claimedSB = new Set()
    sortedChronological.forEach(p => {
      let type = p.season; let year = p.year
      const match = p.season.match(/^(\d{4})\s+(.*)$/)
      if (match) { year = year || match[1]; type = match[2] }
      const prK = `${p.athlete_id}|${p.event}|${type}`
      const sbK = `${p.athlete_id}|${year}|${type}|${p.event}`
      if (p.mark === absoluteBests[prK] && !claimedPR.has(prK)) {
        absoluteBestIds.add(p.id); claimedPR.add(prK)
      }
      if (p.mark === seasonBests[sbK] && !claimedSB.has(sbK)) {
        seasonBestIds.add(p.id); claimedSB.add(sbK)
      }
    })

    const enriched = performances.map(perf => {
      let year = perf.year; let type = perf.season
      const match = perf.season.match(/^(\d{4})\s+(.*)$/)
      if (match) { year = match[1]; type = match[2] }
      return {
        ...perf,
        derivedYear: year,
        derivedType: type,
        meetWithYear: `${perf.meet_name} (${year})`,
        isFirstTime: firstPerfIds.has(perf.id),
        isCalculatedPR: absoluteBestIds.has(perf.id),
        isCalculatedSB: seasonBestIds.has(perf.id)
      }
    })

    const matches = (p, filters) => {
      const { year, type, event, meet, team } = filters
      return (year === 'All' || p.derivedYear === year) &&
        (type === 'All' || p.derivedType === type) &&
        (event === 'All' || p.event === event) &&
        (meet === 'All' || p.meetWithYear === meet) &&
        (team === 'All' || p.team === team)
    }

    const availableYears = Array.from(new Set(manifest.map(m => m.year))).sort((a,b) => b-a);
    const availableTypes = Array.from(new Set(manifest.map(m => m.season))).sort();

    const availableEvents = Array.from(new Set(
      enriched.filter(p => matches(p, { year: filterYear, type: filterSeasonType, meet: filterMeet, team: selectedTeam })).map(p => p.event)
    )).sort()

    const availableMeets = Array.from(new Set(
      enriched.filter(p => matches(p, { year: filterYear, type: filterSeasonType, event: filterEvent, team: selectedTeam })).map(p => p.meetWithYear)
    )).sort()

    let filtered = enriched.filter(p => matches(p, { year: filterYear, type: filterSeasonType, event: filterEvent, meet: filterMeet, team: selectedTeam }))
    if (showPRsOnly) filtered = filtered.filter(p => p.isCalculatedPR)

    filtered.sort((a, b) => {
      let comparison = 0
      if (sortField === 'date') comparison = new Date(a.date) - new Date(b.date)
      else if (sortField === 'mark') {
        if (isBetter(a.mark, b.mark)) comparison = 1
        else if (isBetter(b.mark, a.mark)) comparison = -1
      }
      return sortDirection === 'asc' ? comparison : -comparison
    })

    return { filteredPerformances: filtered, years: availableYears, seasonTypes: availableTypes, events: availableEvents, meets: availableMeets }
  }, [performances, filterYear, filterSeasonType, filterEvent, filterMeet, selectedTeam, showPRsOnly, sortField, sortDirection, manifest])

  const [isScraping, setIsScraping] = useState(false)
  const [scrapeStatus, setScrapeStatus] = useState({ message: '', progress: 0 })

  const handleScrape = async (full = false) => {
    if (!isLocalDev) return
    try {
      const url = `http://localhost:8000/scrape/sub5?full=${full}`
      const res = await fetch(url, { method: 'POST' })
      const result = await res.json()
      if (result.status === 'started' || result.status === 'busy') setIsScraping(true)
    } catch (err) { alert(`Scrape failed: ${err.message}`) }
  }

  useEffect(() => {
    if (!isLocalDev || !isScraping) return
    const interval = setInterval(async () => {
      try {
        const res = await fetch('http://localhost:8000/scrape/status')
        const data = await res.json()
        setScrapeStatus({ message: data.message, progress: data.progress })
        if (!data.is_active) {
          setIsScraping(false); window.location.reload()
        }
      } catch (err) { clearInterval(interval) }
    }, 1000)
    return () => clearInterval(interval)
  }, [isScraping, isLocalDev])

  useEffect(() => {
    setFilterYear('All'); setFilterSeasonType('All'); setFilterEvent('All'); setFilterMeet('All')
    setSortField('date'); setSortDirection('desc'); setExpandedSplits(new Set())
    if (selectedTeam !== 'All' && selectedAthlete.id !== 'all') setSelectedAthlete(ALL_ATHLETES)
  }, [selectedTeam])

  useEffect(() => {
    setFilterYear('All'); setFilterSeasonType('All'); setFilterEvent('All'); setFilterMeet('All')
  }, [selectedAthlete])

  const handleDownloadCsv = () => {
    const headers = ['Athlete', 'Event', 'Result', 'Gr', 'Team', 'Date', 'Meet', 'Season', 'Year']
    const csvContent = [headers.join(','), ...filteredPerformances.map(p => [`"${p.athlete_name}"`,`"${p.event}"`,`"${p.mark}"`,`"${p.grade || ''}"`,`"${p.team}"`,`"${p.date.split('T')[0]}"`,`"${p.meet_name}"`,`"${p.season}"`,`"${p.year}"`].join(','))].join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'export.csv'; link.click()
  }

  const handleSort = (field) => {
    if (sortField === field) setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc')
    else { setSortField(field); setSortDirection('desc') }
  }

  const toggleSplits = (id) => {
    setExpandedSplits(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  return (
    <div className="container">
      <h1 className="no-print">Track & Field Dashboard</h1>

      <div className="dashboard-layout">
        <div className="sidebar">
          <div className="nav-buttons">
            <button onClick={() => setActiveTab('history')} className={`nav-btn ${activeTab === 'history' ? 'active' : ''}`}>History</button>
            <button onClick={() => setActiveTab('analyzer')} className={`nav-btn ${activeTab === 'analyzer' ? 'active' : ''}`}>Postseason Sim</button>
            <button onClick={() => setActiveTab('pr-pop')} className={`nav-btn ${activeTab === 'pr-pop' ? 'active' : ''}`}>PR Pop</button>
            <button onClick={() => setActiveTab('athlete-profile')} className={`nav-btn ${activeTab === 'athlete-profile' ? 'active' : ''}`}>Profile</button>
            <button onClick={() => setActiveTab('practice')} className={`nav-btn ${activeTab === 'practice' ? 'active' : ''}`}>Practice</button>
            <button onClick={() => setActiveTab('footage')} className={`nav-btn ${activeTab === 'footage' ? 'active' : ''}`}>Footage</button>
            <button onClick={() => setActiveTab('predictor')} className={`nav-btn ${activeTab === 'predictor' ? 'active' : ''}`}>Predictor</button>
          </div>

          {isLocalDev && (
            <div className="dev-controls">
              <button className={`update-btn ${isScraping ? 'loading' : ''}`} onClick={() => handleScrape(false)} disabled={isScraping}>Update</button>
              {isScraping && <div className="progress-text">{scrapeStatus.message} {scrapeStatus.progress}%</div>}
            </div>
          )}
        </div>

        <div className="main-content">
          {!dataLoaded ? <div className="loading-state">Initializing Dashboard...</div> : (
          <>
          {activeTab === 'analyzer' ? (
            <PerformanceList performances={allPerformances} isBetter={isBetter} manifest={manifest} loadSeason={loadSeason} />
          ) : activeTab === 'pr-pop' ? (
            <PRPopCalculator performances={allPerformances} selectedTeam={selectedTeam} isBetter={isBetter} manifest={manifest} loadSeason={loadSeason} />
          ) : activeTab === 'practice' ? (
            <PracticeResults />
          ) : activeTab === 'footage' ? (
            <Footage />
          ) : activeTab === 'predictor' ? (
            <ResultPredictor performances={allPerformances} />
          ) : (
            <>
              <div className="filter-bar">
                <div className="filter-group">
                  <label>Team</label>
                  <select value={selectedTeam} onChange={e => setSelectedTeam(e.target.value)}>
                    <option value="All">All Teams</option>
                    {teams.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>

                <div className="filter-group">
                  <label>Athlete</label>
                  <select
                    value={selectedAthlete.id}
                    onChange={e => {
                      const val = e.target.value
                      if (val === 'all') setSelectedAthlete(ALL_ATHLETES)
                      else {
                        const ath = allAthletes.find(a => String(a.id) === val)
                        if (ath) setSelectedAthlete(ath)
                      }
                    }}
                  >
                    <option value="all">All Athletes</option>
                    {filteredAthletes.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                  </select>
                </div>

                {activeTab === 'history' && (
                  <>
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
                        {seasonTypes.map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </div>
                    <div className="filter-group">
                      <label>Event</label>
                      <select value={filterEvent} onChange={e => setFilterEvent(e.target.value)}>
                        <option value="All">All Events</option>
                        {events.map(ev => <option key={ev} value={ev}>{ev}</option>)}
                      </select>
                    </div>
                    <button className="download-btn" onClick={handleDownloadCsv}>CSV</button>
                  </>
                )}
              </div>

              {activeTab === 'history' ? (
                <div className="table-container">
                  <table className="performance-table">
                    <thead>
                      <tr>
                        <th onClick={() => handleSort('date')}>Date</th>
                        {selectedAthlete.id === 'all' && <th>Athlete</th>}
                        <th>Gr</th>
                        <th>Event</th>
                        <th onClick={() => handleSort('mark')}>Result</th>
                        <th>Meet</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredPerformances.map(p => (
                        <tr key={p.id} className={p.isCalculatedPR ? 'pr-row' : ''}>
                          <td>{p.date.split('T')[0]}</td>
                          {selectedAthlete.id === 'all' && <td>{p.athlete_name}</td>}
                          <td>{p.grade}</td>
                          <td>{p.event}</td>
                          <td>{p.mark} {p.isCalculatedPR && <span className="badge pr">PR</span>}</td>
                          <td>{p.meet_name}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <AthleteProfile performances={performances} selectedAthlete={selectedAthlete} />
              )}
            </>
          )}
          </>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
