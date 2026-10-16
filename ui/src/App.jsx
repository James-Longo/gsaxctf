import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { isBetter, normalizeEvent, parseMark, isDistanceEvent, asset } from './utils'
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
import XCPostseasonSim from './XCPostseasonSim'
import RecordBoard from './RecordBoard'

// The site is split by sport. Each sport has its own tabs, and every view's
// season filter is pinned to it. `team` tabs (track team tools) sit below a
// divider.
const TRACK_TABS = ['history', 'records', 'sim', 'pr-pop', 'athlete-profile', 'predictor']
const SPORTS = {
  xc: { label: 'Cross Country', season: 'XC', tabs: ['history', 'sim', 'xc-courses'], team: [] },
  indoor: { label: 'Indoor', season: 'Indoor', tabs: TRACK_TABS, team: ['practice', 'footage'] },
  outdoor: { label: 'Outdoor', season: 'Outdoor', tabs: TRACK_TABS, team: ['practice', 'footage'] },
}
// Athlete Profiles opens on this runner when no athlete is chosen
const DEFAULT_PROFILE_ATHLETE = 'owen-cannon-george-stevens-academy'
const sportTabs = (sp) => [...SPORTS[sp].tabs, ...SPORTS[sp].team]
const TAB_LABELS = {
  history: 'Results', records: 'Records', sim: 'Postseason Simulator', 'pr-pop': 'PR Pop', 'athlete-profile': 'Athlete Profiles',
  'xc-courses': 'Courses', predictor: "Owen's Predictor", practice: 'Practice', footage: 'Footage',
}
// Days since July 1 (a season calendar, so indoor's Dec-Mar doesn't wrap),
// on a fixed leap year. Matches json_store._season_offset.
const seasonOffset = (month, day) => {
  const start = (month > 7 || (month === 7 && day >= 1)) ? Date.UTC(2000, 6, 1) : Date.UTC(1999, 6, 1)
  return Math.round((Date.UTC(2000, month - 1, day) - start) / 86400000)
}
// The sport in season on date `d`. `windows` comes from the manifest: each
// season type's earliest and latest result date ('MM-DD'), measured from the
// data. Inside a window, that sport; inside two (the day one ends and the
// next begins), the one that started more recently; between seasons, the
// next one to start. Without windows, a fixed month rule.
const sportForDate = (windows, d = new Date()) => {
  const keys = Object.keys(SPORTS).filter(k => windows?.[SPORTS[k].season])
  if (!keys.length) {
    const m = d.getMonth() + 1
    return m >= 8 && m <= 11 ? 'xc' : m === 12 || m <= 3 ? 'indoor' : 'outdoor'
  }
  const off = (md) => seasonOffset(+md.slice(0, 2), +md.slice(3, 5))
  const t = seasonOffset(d.getMonth() + 1, d.getDate())
  const w = keys.map(k => ({ k, s: off(windows[SPORTS[k].season].start), e: off(windows[SPORTS[k].season].end) }))
  const inside = w.filter(x => x.s <= t && t <= x.e).sort((a, b) => b.s - a.s)
  if (inside.length) return inside[0].k
  return w.sort((a, b) => ((a.s - t + 366) % 366) - ((b.s - t + 366) % 366))[0].k
}
// URL hash is #sport/tab, e.g. #xc/sim. `explicit` is false when the URL
// names no sport, so the default can follow the manifest's season windows.
const readHash = (windows) => {
  const [sp, tab] = window.location.hash.replace(/^#/, '').split('/')
  const sport = SPORTS[sp] ? sp : sportForDate(windows)
  return { sport, tab: sportTabs(sport).includes(tab) ? tab : 'history', explicit: !!SPORTS[sp] }
}

function App() {
  const [dataLoaded, setDataLoaded] = useState(false)
  const [manifest, setManifest] = useState([])
  const [allAthletes, setAllAthletes] = useState([])
  const [loadedSeasons, setLoadedSeasons] = useState({}) // key -> data array
  const [meetLinks, setMeetLinks] = useState({}) // '<year>_<season>' -> meet_name -> source url
  
  const [selectedTeam, setSelectedTeam] = useState('George Stevens Academy')
  const [selectedAthlete, setSelectedAthlete] = useState(ALL_ATHLETES)
  const [sport, setSport] = useState(() => readHash().sport)
  const [activeTab, setActiveTab] = useState(() => readHash().tab)
  // read before the URL sync below rewrites the hash
  const urlChoseSport = useRef(readHash().explicit)
  const seasonWindows = useRef(null)
  const [loadingProgress, setLoadingProgress] = useState({ current: 0, total: 0 })

  const [expandedSplits, setExpandedSplits] = useState(new Set())

  // Filter states
  const [filterYear, setFilterYear] = useState('All')
  const filterSeasonType = SPORTS[sport].season
  const [filterEvent, setFilterEvent] = useState('All')
  const [filterMeet, setFilterMeet] = useState('All')
  const [showPRsOnly, setShowPRsOnly] = useState(false)

  // Sort states
  const [sortField, setSortField] = useState('date')
  const [sortDirection, setSortDirection] = useState('desc')

  useEffect(() => {
    const want = `#${sport}/${activeTab}`
    if (window.location.hash !== want) window.history.replaceState(null, '', want)
  }, [sport, activeTab])
  useEffect(() => {
    const onHash = () => {
      const h = readHash(seasonWindows.current)
      setSport(h.sport); setActiveTab(h.tab)
      // a link to a tab this sport doesn't have lands on Results; say so in the URL
      if (window.location.hash !== `#${h.sport}/${h.tab}`) window.history.replaceState(null, '', `#${h.sport}/${h.tab}`)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const switchSport = (sp) => {
    setSport(sp)
    if (!sportTabs(sp).includes(activeTab)) setActiveTab('history')
    setFilterEvent('All'); setFilterMeet('All')
  }
  const isXC = sport === 'xc'
  const sportPerformances = (perfs) => perfs.filter(p => p.season === SPORTS[sport].season)


  // 1. Initial Load: Manifest and Athlete Registry
  useEffect(() => {
    const loadInitial = async () => {
      try {
        const manifestRes = await fetch(asset('/data/manifest.json'));
        const manifestData = await manifestRes.json();
        const athletesData = await fetchJsonGz(asset('/data/athletes.json.gz'));
        
        setManifest(manifestData);
        setAllAthletes(athletesData);
        // links to each meet's full results; the table works without them
        fetchJsonGz(asset('/data/meet_links.json.gz')).then(setMeetLinks).catch(() => {});
        // open on the sport that's in season by the data's own season dates
        // (unless the URL already chose one)
        seasonWindows.current = manifestData.season_windows || null;
        if (!urlChoseSport.current) {
          const sp = sportForDate(seasonWindows.current);
          setSport(sp);
          setActiveTab(t => sportTabs(sp).includes(t) ? t : 'history');
        }
        
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
        const data = await fetchJsonGz(asset(`/data/teams/${slug}/${key}.json.gz`));
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
      const allYears = Array.from(new Set((manifest.seasons || []).filter(s => s.endsWith(`_${filterSeasonType}`)).map(s => s.split('_')[0]))).sort();
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
      // a runner's career can sit in several team folders (school spellings)
      for (const name of selectedAthlete.teams || [selectedAthlete.primary_team]) {
        const team = manifest.teams?.find(t => t.name === name);
        if (team) loadTeamData(team.slug, null, team.seasons, team.name);
      }
    }
  }, [selectedAthlete, manifest]);

  // The athlete catalog (backend/athlete_catalog.py) groups a runner's
  // spellings: a registry entry lists the store ids it covers in `members`.
  // runnerId() maps a row's store id to the runner it belongs to.
  const runnerOf = useMemo(() => {
    const m = {}
    for (const a of allAthletes) for (const id of a.members || []) m[id] = a.id
    return m
  }, [allAthletes])
  const runnerId = useCallback((p) => runnerOf[p.athlete_id] || p.athlete_id, [runnerOf])

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
  // Every picker lists only what exists in the sport being viewed.
  const sportSeason = SPORTS[sport].season
  const teamOptions = useMemo(() => {
    const opts = [{ value: 'All', label: 'All Teams' }]
    const order = { hs: 0, ms: 1, college: 2 }
    const n = t => t.counts?.[sportSeason] ?? 0
    const sorted = (manifest.teams || [])
      .filter(t => (t.seasons || []).some(k => k.endsWith(`_${sportSeason}`)))
      .sort((a, b) => (order[a.level] ?? 3) - (order[b.level] ?? 3) || n(b) - n(a))
    for (const t of sorted) {
      opts.push({
        value: t.name, label: t.name,
        group: LEVEL_LABELS[t.level] || 'Other',
        secondary: `${n(t).toLocaleString()} results`,
      })
    }
    return opts
  }, [manifest, sportSeason])

  const athleteOptions = useMemo(() => {
    const base = [{ value: 'all', label: 'All Athletes' }]
    const source = allAthletes.filter(a =>
      (selectedTeam === 'All' || a.primary_team === selectedTeam || a.teams?.includes(selectedTeam)) &&
      (!a.sports || a.sports.includes(sportSeason)))
    return base.concat(source.map(a => ({
      value: a.id, label: a.name,
      // relay teams after the runners, under their own heading
      group: a.kind === 'relay' ? 'Relay teams' : undefined,
      secondary: selectedTeam === 'All' ? a.primary_team : (a.aka?.length ? `also ${a.aka.join(', ')}` : undefined),
      search: a.aka?.join(' '),
    })))
  }, [allAthletes, selectedTeam, sportSeason])

  // Derived: Athletes for the current view
  const filteredAthletes = useMemo(() => {
    if (selectedTeam === 'All') return allAthletes;
    return allAthletes.filter(a => a.primary_team === selectedTeam || a.teams?.includes(selectedTeam));
  }, [allAthletes, selectedTeam]);

  // Current performances to display
  const performances = useMemo(() => {
    if (!selectedAthlete || !dataLoaded) return []
    if (selectedAthlete.id === 'all') {
      if (selectedTeam === 'All') return allPerformances
      return allPerformances.filter(p => p.team === selectedTeam)
    }
    // Filter by athlete_id across ALL loaded data (handles transfers if they exist in loaded files)
    return allPerformances.filter(p => runnerId(p) === selectedAthlete.id)
  }, [allPerformances, selectedAthlete, selectedTeam, dataLoaded, runnerId])

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
      const prK = `${runnerId(p)}|${normEvent}|${type}`
      const sbK = `${runnerId(p)}|${year}|${type}|${normEvent}`
      
      if (!seenEvents.has(prK)) {
        firstPerfIds.add(p.id)
        seenEvents.add(prK)
      }
      
      const pParsed = parseMark(p.mark, isDistanceEvent(p.event))
      // (an exhibition mark - "X4:29.26" - is shown but never a PR or season best)
      if (pParsed.valid && !p.exhibition) {
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

    const allYears = Array.from(new Set((manifest.seasons || []).filter(s => s.endsWith(`_${filterSeasonType}`)).map(s => s.split('_')[0]))).sort((a,b) => b-a);
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

    // one option per displayed event: many raw labels can normalize to the
    // same event (every XC distance label is "Boys Cross Country")
    const eventByLabel = new Map()
    enriched.filter(p => matches(p, { year: filterYear, type: filterSeasonType, event: 'All', meet: filterMeet, team: selectedTeam }))
      .forEach(p => { const k = normalizeEvent(p.event); if (!eventByLabel.has(k)) eventByLabel.set(k, p.event) })
    const availableEvents = [...eventByLabel.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, raw]) => raw)

    const availableMeets = Array.from(new Set(
      enriched.filter(p => matches(p, { year: filterYear, type: filterSeasonType, event: filterEvent, meet: 'All', team: selectedTeam })).map(p => p.meetWithYear)
    )).sort()

    let filtered = enriched.filter(p => matches(p, { year: filterYear, type: filterSeasonType, event: filterEvent, meet: filterMeet, team: selectedTeam }))
    if (showPRsOnly) filtered = filtered.filter(p => p.is_pr)

    filtered.sort((a, b) => {
      let comparison = 0
      // undated rows ('Unknown') sort as oldest instead of breaking the sort
      if (sortField === 'date') comparison = (Date.parse(a.date) || 0) - (Date.parse(b.date) || 0)
      else if (sortField === 'mark') {
        if (isBetter(a.mark, b.mark, a.event)) comparison = 1
        else if (isBetter(b.mark, a.mark, a.event)) comparison = -1
      }
      return sortDirection === 'asc' ? comparison : -comparison
    })

    return { filteredPerformances: filtered, years: availableYears, seasonTypes: availableTypes, events: availableEvents, meets: availableMeets }
  }, [performances, filterYear, filterSeasonType, filterEvent, filterMeet, selectedTeam, showPRsOnly, sortField, sortDirection, manifest, runnerId])

  useEffect(() => {
    if (activeTab !== 'splits' || !manifest.teams) return;
    manifest.teams.filter(t => t.has_splits).forEach(t => loadTeamData(t.slug, null, t.seasons, t.name));
  }, [activeTab, manifest]);

  useEffect(() => {
    setFilterYear('All'); setFilterEvent('All'); setFilterMeet('All')
    setSortField('date'); setSortDirection('desc'); setExpandedSplits(new Set())
    if (selectedTeam !== 'All' && selectedAthlete.id !== 'all') setSelectedAthlete(ALL_ATHLETES)
  }, [selectedTeam])

  useEffect(() => {
    setFilterYear('All'); setFilterEvent('All'); setFilterMeet('All')
  }, [selectedAthlete])

  // Opening Athlete Profiles with no athlete chosen shows the default
  // runner, in every sport (switching sport keeps whoever is selected).
  useEffect(() => {
    if (activeTab !== 'athlete-profile' || selectedAthlete.id !== 'all') return
    const ath = allAthletes.find(a => a.id === DEFAULT_PROFILE_ATHLETE)
    if (ath) setSelectedAthlete(ath)
  }, [activeTab, allAthletes])

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
      <h1 className="no-print">GSAXCTF</h1>
      <div className="sport-switch no-print" role="tablist" aria-label="Sport">
        {Object.entries(SPORTS).map(([key, sp]) => (
          <button key={key} role="tab" aria-selected={sport === key}
            className={sport === key ? 'active' : ''} onClick={() => switchSport(key)}>{sp.label}</button>
        ))}
      </div>

      <div className="dashboard-layout">
        <div className="sidebar">
          <div className="nav-buttons">
            {SPORTS[sport].tabs.map(t => (
              <button key={t} onClick={() => setActiveTab(t)} className={`nav-btn ${activeTab === t ? 'active' : ''}`}>{TAB_LABELS[t]}</button>
            ))}
            {SPORTS[sport].team.length > 0 && <hr className="nav-divider" />}
            {SPORTS[sport].team.map(t => (
              <button key={t} onClick={() => setActiveTab(t)} className={`nav-btn ${activeTab === t ? 'active' : ''}`}>{TAB_LABELS[t]}</button>
            ))}
          </div>

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
          {activeTab === 'sim' ? (
            sport === 'xc'
              ? <XCPostseasonSim followTeam={selectedTeam} />
              : <PerformanceList performances={allPerformances} isBetter={isBetter} manifest={manifest} loadTeamData={loadTeamData} season={SPORTS[sport].season} />
          ) : activeTab === 'pr-pop' ? (
            <PRPopCalculator performances={sportPerformances(allPerformances)} selectedTeam={selectedTeam} isBetter={isBetter} manifest={manifest} loadTeamData={loadTeamData} />
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

                {activeTab !== 'records' && <div className="filter-group">
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
                </div>}

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
                // XC: no PRs (a time depends on the course, so the fastest
                // "5K" is mostly the fastest course) and no event column
                // (one event per gender; the label is only a distance guess)
                <div className="table-container">
                  <table className="performance-table">
                    <thead>
                      <tr>
                        <th onClick={() => handleSort('date')}>Date</th>
                        {selectedAthlete.id === 'all' && <th>Athlete</th>}
                        <th>Gr</th>
                        {!isXC && <th>Event</th>}
                        <th onClick={() => handleSort('mark')}>Result</th>
                        <th>Meet</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredPerformances.map(p => {
                        const hasSplits = p.splits && p.splits.length > 0
                        const isExpanded = expandedSplits.has(p.id)
                        const colSpan = (selectedAthlete.id === 'all' ? 6 : 5) - (isXC ? 1 : 0)
                        const showPR = p.is_pr && !isXC
                        return (
                          <React.Fragment key={p.id}>
                            <tr className={showPR ? 'pr-row' : ''}>
                              <td>{p.date.split('T')[0]}</td>
                              {selectedAthlete.id === 'all' && <td>{p.athlete_name}</td>}
                              <td>{p.grade}</td>
                              {!isXC && <td>{normalizeEvent(p.event)}</td>}
                              <td>
                                {p.mark}
                                {hasSplits && (
                                  <span className="splits-toggle" onClick={() => toggleSplits(p.id)}>
                                    {isExpanded ? ' ▲' : ' ▼'}
                                  </span>
                                )}
                                {showPR && <span className="badge pr">{p.season === 'Indoor' ? 'PRᵢ' : p.season === 'Outdoor' ? 'PRₒ' : 'PR'}</span>}
                              </td>
                              <td>
                                {meetLinks[`${p.year}_${p.season}`]?.[p.meet_name]
                                  ? <a className="meet-link" href={meetLinks[`${p.year}_${p.season}`][p.meet_name]} target="_blank" rel="noopener noreferrer">{p.meet_name}</a>
                                  : p.meet_name}
                              </td>
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
              ) : activeTab === 'records' ? (
                <RecordBoard performances={allPerformances} selectedTeam={selectedTeam} manifest={manifest}
                  loadTeamData={loadTeamData} season={SPORTS[sport].season} runnerId={runnerId} athletes={allAthletes} meetLinks={meetLinks} />
              ) : (
                <AthleteProfile performances={sportPerformances(performances)} selectedAthlete={selectedAthlete} />
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
