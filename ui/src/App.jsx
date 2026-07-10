import React, { useState, useEffect, useMemo, useRef } from 'react'
import { isBetter, normalizeEvent, parseMark, isDistanceEvent } from './utils'
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
import SplitExplorer from './SplitExplorer'
import SearchSelect from './SearchSelect'
import XCCourseExplorer from './XCCourseExplorer'

function App() {
  const [dataLoaded, setDataLoaded] = useState(false)
  const [manifest, setManifest] = useState([])
  const [allAthletes, setAllAthletes] = useState([])
  const [loadedSeasons, setLoadedSeasons] = useState({}) // key -> data array
  
  const [selectedTeam, setSelectedTeam] = useState('George Stevens Academy')
  const [selectedAthlete, setSelectedAthlete] = useState(ALL_ATHLETES)
  const [activeTab, setActiveTab] = useState('history')
  const [loadingProgress, setLoadingProgress] = useState({ current: 0, total: 0 })

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

  // 1. Initial Load: Manifest and Athlete Registry
  useEffect(() => {
    const loadInitial = async () => {
      try {
        const manifestRes = await fetch('/data/manifest.json');
        const manifestData = await manifestRes.json();
        const athletesData = await fetchJsonGz('/data/athletes.json.gz');
        
        setManifest(manifestData);
        setAllAthletes(athletesData);
        
        // Find default team slug
        const defaultTeam = manifestData.teams.find(t => t.name === selectedTeam) || manifestData.teams[0];
        if (defaultTeam) {
           loadTeamData(defaultTeam.slug, null, defaultTeam.seasons, defaultTeam.name);
        }
        setDataLoaded(true);
      } catch (err) {
        console.error('Data load failed:', err);
      }
    };
    loadInitial();
  }, [])

  // Team data is chunked per season: /data/teams/{slug}/{year}_{season}.json.
  // Rows are stored slim (no team/year/season/id fields — they're derivable);
  // enrich them here to the full shape the components expect.
  // chunkKeys limits which season chunks load (null = all seasons the team has);
  // seasonsHint lets callers pass the team's season list before manifest state lands.
  const slugifyAthlete = (name, team) => {
    const raw = `${name.toLowerCase()}--${team.toLowerCase()}`;
    return raw.replace(/[^a-zA-Z0-9_]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
  };
  // Chunks are stored gzipped (.json.gz) to fit hosting limits; decompress
  // client-side. Falls back to parsing as plain JSON if the server (or a
  // proxy) already decoded it.
  const fetchJsonGz = async (url) => {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
    if (url.endsWith('.gz')) {
      const buf = await res.arrayBuffer();
      const bytes = new Uint8Array(buf);
      if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
        const ds = new DecompressionStream('gzip');
        const stream = new Response(buf).body.pipeThrough(ds);
        return JSON.parse(await new Response(stream).text());
      }
      return JSON.parse(new TextDecoder().decode(buf));
    }
    return res.json();
  };
  const inFlight = useRef(new Set());
  const loadTeamData = async (slug, chunkKeys = null, seasonsHint = null, nameHint = null) => {
    const team = manifest.teams?.find(t => t.slug === slug);
    const seasons = seasonsHint || team?.seasons || [];
    const teamName = nameHint || team?.name || slug.replace(/_/g, ' ');
    const wanted = chunkKeys ? seasons.filter(s => chunkKeys.includes(s)) : seasons;
    await Promise.all(wanted.map(async (key) => {
      const cacheKey = `${slug}|${key}`;
      if (loadedSeasons[cacheKey] || inFlight.current.has(cacheKey)) return;
      inFlight.current.add(cacheKey);
      try {
        const data = await fetchJsonGz(`/data/teams/${slug}/${key}.json.gz`);
        const [year, season] = [key.slice(0, key.indexOf('_')), key.slice(key.indexOf('_') + 1)];
        data.forEach((p, i) => {
          if (!p.team) p.team = teamName;
          if (!p.year) p.year = year;
          if (!p.season) p.season = season;
          if (!p.splits) p.splits = [];
          if (p.date && p.date !== 'Unknown' && !p.date.includes('T')) p.date = p.date + 'T12:00:00';
          if (!p.athlete_id) p.athlete_id = slugifyAthlete(p.athlete_name || '', teamName);
          if (!p.id) p.id = `${slug}|${key}|${i}`;
        });
        setLoadedSeasons(prev => ({ ...prev, [cacheKey]: data }));
      } catch (err) {
        console.error(`Failed to load team data for ${slug} ${key}:`, err);
        inFlight.current.delete(cacheKey);
      }
    }));
  };

  const teamFullyLoaded = (t) =>
    (t.seasons || []).every(s => loadedSeasons[`${t.slug}|${s}`]);

  // 2. Load team data when selection changes.
  // Single team: load its whole history (chunks fetch in parallel).
  // All teams: loading every chunk of every team would be hundreds of MB, so
  // load only chunks matching the year/season filters (latest year when the
  // year filter is 'All').
  useEffect(() => {
    if (!manifest.teams) return;
    if (selectedTeam === 'All') {
      const allYears = Array.from(new Set((manifest.seasons || []).map(s => s.split('_')[0]))).sort();
      const latestYear = allYears.slice(-1)[0];
      const years = filterYear === 'Last4' ? allYears.slice(-4)
        : filterYear !== 'All' ? [filterYear] : [latestYear];
      const types = filterSeasonType !== 'All' ? [filterSeasonType] : ['Indoor', 'Outdoor', 'XC'];
      const wanted = years.flatMap(y => types.map(t => `${y}_${t}`));
      manifest.teams.forEach(t => loadTeamData(t.slug, wanted, t.seasons, t.name));
    } else {
      const team = manifest.teams.find(t => t.name === selectedTeam);
      if (team) loadTeamData(team.slug, null, team.seasons, team.name);
    }
  }, [selectedTeam, manifest, filterYear, filterSeasonType]);

  useEffect(() => {
    if (selectedAthlete && selectedAthlete.id !== 'all' && selectedAthlete.primary_team) {
      const team = manifest.teams?.find(t => t.name === selectedAthlete.primary_team);
      if (team) loadTeamData(team.slug, null, team.seasons, team.name);
    }
  }, [selectedAthlete, manifest]);

  // Derive all loaded performances into one flat array
  const allPerformances = useMemo(() => {
    return Object.values(loadedSeasons).flat();
  }, [loadedSeasons]);

  // Derived: Unique Teams (from manifest now)
  const teams = useMemo(() => {
    return (manifest.teams || []).map(t => t.name).sort();
  }, [manifest])

  // Type-ahead options: teams grouped by level, biggest programs first
  const LEVEL_LABELS = { hs: 'High School', ms: 'Middle School', college: 'College' }
  const teamOptions = useMemo(() => {
    const opts = [{ value: 'All', label: 'All Teams' }]
    const order = { hs: 0, ms: 1, college: 2 }
    const sorted = [...(manifest.teams || [])].sort((a, b) =>
      (order[a.level] ?? 3) - (order[b.level] ?? 3) || b.count - a.count)
    for (const t of sorted) {
      opts.push({
        value: t.name, label: t.name,
        group: LEVEL_LABELS[t.level] || 'Other',
        secondary: `${t.count.toLocaleString()} results`,
      })
    }
    return opts
  }, [manifest])

  const athleteOptions = useMemo(() => {
    const base = [{ value: 'all', label: 'All Athletes' }]
    const source = selectedTeam === 'All' ? allAthletes
      : allAthletes.filter(a => a.primary_team === selectedTeam)
    return base.concat(source.map(a => ({
      value: a.id, label: a.name,
      secondary: selectedTeam === 'All' ? a.primary_team : undefined,
    })))
  }, [allAthletes, selectedTeam])

  // Derived: Athletes for the current view
  const filteredAthletes = useMemo(() => {
    if (selectedTeam === 'All') return allAthletes;
    return allAthletes.filter(a => a.primary_team === selectedTeam);
  }, [allAthletes, selectedTeam]);

  // Current performances to display
  const performances = useMemo(() => {
    if (!selectedAthlete || !dataLoaded) return []
    if (selectedAthlete.id === 'all') {
      if (selectedTeam === 'All') return allPerformances
      return allPerformances.filter(p => p.team === selectedTeam)
    }
    // Filter by athlete_id across ALL loaded data (handles transfers if they exist in loaded files)
    return allPerformances.filter(p => p.athlete_id === selectedAthlete.id)
  }, [allPerformances, selectedAthlete, selectedTeam, dataLoaded])

  // Rest of the logic (Stats, filtering, sorting) is the same...
  const { filteredPerformances, years, seasonTypes, events, meets } = useMemo(() => {
    const runningBests = {} 
    const runningSeasonBests = {} 
    const prIds = new Set()
    const sbIds = new Set()
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
      const normEvent = normalizeEvent(p.event)
      const prK = `${p.athlete_id}|${normEvent}|${type}`
      const sbK = `${p.athlete_id}|${year}|${type}|${normEvent}`
      
      if (!seenEvents.has(prK)) {
        firstPerfIds.add(p.id)
        seenEvents.add(prK)
      }
      
      const pParsed = parseMark(p.mark, isDistanceEvent(p.event))
      if (pParsed.valid) {
        // A performance is a PR if it's the first one OR better than any previous one in this season type
        if (!runningBests[prK] || isBetter(p.mark, runningBests[prK], p.event)) {
          runningBests[prK] = p.mark
          prIds.add(p.id)
        }
        
        // A performance is a Season Best if it's the first of the year/type OR better than any previous in that year/type
        if (!runningSeasonBests[sbK] || isBetter(p.mark, runningSeasonBests[sbK], p.event)) {
          runningSeasonBests[sbK] = p.mark
          sbIds.add(p.id)
        }
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
        isCalculatedPR: prIds.has(perf.id),
        isCalculatedSB: sbIds.has(perf.id)
      }
    })

    const allYears = Array.from(new Set((manifest.seasons || []).map(s => s.split('_')[0]))).sort((a,b) => b-a);
    const last4 = new Set(allYears.slice(0, 4));

    const matches = (p, filters) => {
      const { year, type, event, meet, team } = filters
      const yearOk = year === 'All' ||
        (year === 'Last4' ? last4.has(p.derivedYear) : p.derivedYear === year)
      return yearOk &&
        (type === 'All' || p.derivedType === type) &&
        (event === 'All' || normalizeEvent(p.event) === normalizeEvent(event)) &&
        (meet === 'All' || p.meetWithYear === meet) &&
        (team === 'All' || selectedAthlete.id !== 'all' || p.team === team)
    }

    const availableYears = allYears;
    const availableTypes = Array.from(new Set((manifest.seasons || []).map(s => s.split('_')[1]))).sort();

    const availableEvents = Array.from(new Set(
      enriched.filter(p => matches(p, { year: filterYear, type: filterSeasonType, event: 'All', meet: filterMeet, team: selectedTeam })).map(p => p.event)
    )).sort()

    const availableMeets = Array.from(new Set(
      enriched.filter(p => matches(p, { year: filterYear, type: filterSeasonType, event: filterEvent, meet: 'All', team: selectedTeam })).map(p => p.meetWithYear)
    )).sort()

    let filtered = enriched.filter(p => matches(p, { year: filterYear, type: filterSeasonType, event: filterEvent, meet: filterMeet, team: selectedTeam }))
    if (showPRsOnly) filtered = filtered.filter(p => p.is_pr)

    filtered.sort((a, b) => {
      let comparison = 0
      if (sortField === 'date') comparison = new Date(a.date) - new Date(b.date)
      else if (sortField === 'mark') {
        if (isBetter(a.mark, b.mark, a.event)) comparison = 1
        else if (isBetter(b.mark, a.mark, a.event)) comparison = -1
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
    if (activeTab !== 'splits' || !manifest.teams) return;
    manifest.teams.filter(t => t.has_splits).forEach(t => loadTeamData(t.slug, null, t.seasons, t.name));
  }, [activeTab, manifest]);

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
            <button onClick={() => setActiveTab('xc-courses')} className={`nav-btn ${activeTab === 'xc-courses' ? 'active' : ''}`}>XC Courses</button>
            {false && <button onClick={() => setActiveTab('splits')} className={`nav-btn ${activeTab === 'splits' ? 'active' : ''}`}>Split Explorer</button>}
          </div>

          {isLocalDev && (
            <div className="dev-controls">
              <button className={`update-btn ${isScraping ? 'loading' : ''}`} onClick={() => handleScrape(false)} disabled={isScraping}>Update</button>
              {isScraping && <div className="progress-text">{scrapeStatus.message} {scrapeStatus.progress}%</div>}
            </div>
          )}
        </div>

        <div className="main-content">
          {!dataLoaded ? (
            <div className="loading-state">
              <div className="loading-spinner"></div>
              <p>Loading Team History...</p>
              <div className="progress-bar-container">
                <div 
                  className="progress-bar-fill" 
                  style={{ width: `${(loadingProgress.current / loadingProgress.total) * 100}%` }}
                ></div>
              </div>
              <p className="progress-detail">{loadingProgress.current} / {loadingProgress.total} seasons</p>
            </div>
          ) : (
          <>
          {activeTab === 'analyzer' ? (
            <PerformanceList performances={allPerformances} isBetter={isBetter} manifest={manifest} loadTeamData={loadTeamData} />
          ) : activeTab === 'pr-pop' ? (
            <PRPopCalculator performances={allPerformances} selectedTeam={selectedTeam} isBetter={isBetter} manifest={manifest} loadTeamData={loadTeamData} />
          ) : activeTab === 'practice' ? (
            <PracticeResults />
          ) : activeTab === 'footage' ? (
            <Footage />
          ) : activeTab === 'xc-courses' ? (
            <XCCourseExplorer />
          ) : activeTab === 'predictor' ? (
            <ResultPredictor performances={allPerformances} />
          ) : activeTab === 'splits' ? (
            <SplitExplorer
              performances={allPerformances}
              loading={manifest.teams?.some(t => t.has_splits && !teamFullyLoaded(t))}
            />
          ) : (
            <>
              <div className="filter-bar">
                <div className="filter-group">
                  <label>Team</label>
                  <SearchSelect
                    value={selectedTeam}
                    onChange={setSelectedTeam}
                    options={teamOptions}
                    placeholder="Search teams..."
                  />
                </div>

                <div className="filter-group">
                  <label>Athlete</label>
                  <SearchSelect
                    value={selectedAthlete.id}
                    onChange={(val) => {
                      if (val === 'all') setSelectedAthlete(ALL_ATHLETES)
                      else {
                        const ath = allAthletes.find(a => String(a.id) === String(val))
                        if (ath) setSelectedAthlete(ath)
                      }
                    }}
                    options={athleteOptions}
                    placeholder="Search athletes..."
                    minSearch={selectedTeam === 'All' ? 2 : 0}
                  />
                </div>

                {activeTab === 'history' && (
                  <>
                    <div className="filter-group">
                      <label>Year</label>
                      <select value={filterYear} onChange={e => setFilterYear(e.target.value)}>
                        <option value="All">All Years</option>
                        <option value="Last4">Last 4 Years</option>
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
                        {events.map(ev => <option key={ev} value={ev}>{normalizeEvent(ev)}</option>)}
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
                      {filteredPerformances.map(p => {
                        const hasSplits = p.splits && p.splits.length > 0
                        const isExpanded = expandedSplits.has(p.id)
                        const colSpan = selectedAthlete.id === 'all' ? 6 : 5
                        return (
                          <React.Fragment key={p.id}>
                            <tr className={p.is_pr ? 'pr-row' : ''}>
                              <td>{p.date.split('T')[0]}</td>
                              {selectedAthlete.id === 'all' && <td>{p.athlete_name}</td>}
                              <td>{p.grade}</td>
                              <td>{normalizeEvent(p.event)}</td>
                              <td>
                                {p.mark}
                                {hasSplits && (
                                  <span className="splits-toggle" onClick={() => toggleSplits(p.id)}>
                                    {isExpanded ? ' ▲' : ' ▼'}
                                  </span>
                                )}
                                {p.is_pr && <span className="badge pr">{p.season === 'Indoor' ? 'PRᵢ' : p.season === 'Outdoor' ? 'PRₒ' : 'PR'}</span>}
                              </td>
                              <td>{p.meet_name}</td>
                            </tr>
                            {isExpanded && (
                              <tr className="splits-row">
                                <td colSpan={colSpan}>
                                  <div className="splits-container">
                                    <div className="splits-list">
                                      {p.splits.map((split, i) => (
                                        <span key={i} className="split-item">
                                          <span className="split-index">Lap {i + 1}</span>
                                          <span className="split-val">{split}</span>
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        )
                      })}
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
