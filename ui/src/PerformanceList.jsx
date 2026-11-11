import { Fragment, useState, useMemo, useEffect } from 'react'
import { parseMark, normalizeEvent, isDistanceEvent, asset, fetchGz } from './utils'
import './App.css'

// Typical championship mark vs the mean of an athlete's two best marks that season, as a
// log-scale spread by event family: robust SD of the misses over 164 PVC/EMITL and state
// championships 2003-2026, x1.25 (the scale with the best top-3 Brier score in that backtest).
const CHAMP_SPREAD = {
    sprint: 1.25 * 0.0164, hurdles: 1.25 * 0.0249, distance: 1.25 * 0.0247, relay: 1.25 * 0.0235,
    jumps: 1.25 * 0.0416, throws: 1.25 * 0.0647, walk: 1.25 * 0.0383,
}
const SIMS = 2000

function eventFamily(event) {
    const e = (event || '').toLowerCase()
    if (e.includes('relay')) return 'relay'
    if (e.includes('hurdle')) return 'hurdles'
    if (e.includes('jump') || e.includes('vault')) return 'jumps'
    if (e.includes('shot') || e.includes('discus') || e.includes('javelin')) return 'throws'
    if (e.includes('walk')) return 'walk'
    if (/\b(55|100|200|400)m dash/.test(e)) return 'sprint'
    return 'distance'
}

// A mark on a log scale where lower is better (times as they are, distances negated).
function logMark(mark, event) {
    const p = parseMark(mark, isDistanceEvent(event))
    if (!p.valid || !(p.value > 0)) return null
    return p.isTime ? Math.log(p.value) : -Math.log(p.value)
}

// Chances as the XC page shows them.
const PLACES = ['1st', '2nd', '3rd', '4th+']
const pct = (x) => x == null ? '' : x >= 0.995 ? '>99%' : x > 0 && x < 0.005 ? '<1%' : `${Math.round(x * 100)}%`
const pctCls = (x) => x == null ? '' : x >= 0.5 ? 'xs-hi' : x < 0.02 ? 'xs-lo' : ''

// Small seeded generator, so the same page shows the same chances.
function mulberry32(a) {
    return () => {
        a |= 0; a = (a + 0x6D2B79F5) | 0
        let t = Math.imul(a ^ (a >>> 15), 1 | a)
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296
    }
}

function PostseasonSimulator({ performances, isBetter, manifest, loadTeamData, season }) {
    // Derive the current season and year from today's date.
    const getDefaultSeason = () => {
        const now = new Date();
        const month = now.getMonth() + 1; // 1-indexed
        const year = now.getFullYear();
        if (month >= 4 && month <= 10) {
            return { season: 'Outdoor', year: String(year) };
        } else if (month >= 11) {
            return { season: 'Indoor', year: String(year + 1) };
        } else {
            return { season: 'Indoor', year: String(year) };
        }
    };

    const { season: defaultSeason, year: defaultYear } = getDefaultSeason();

    const [filterYear, setFilterYear] = useState(defaultYear)
    // `season` (from the site's sport switch) pins Indoor or Outdoor
    const [filterSeason, setFilterSeason] = useState(season || defaultSeason)
    useEffect(() => { if (season) setFilterSeason(season) }, [season])
    const [filterEvent, setFilterEvent] = useState('All')
    const [scoreMethod, setScoreMethod] = useState('PR')
    const [expandedTeams, setExpandedTeams] = useState({})
    const [gender, setGender] = useState('Boys')
    const g = gender.toLowerCase()
    const ofGender = (event) => (event || '').startsWith(gender)
    const [targetTeam, setTargetTeam] = useState('George Stevens Academy')
    const [competitionType, setCompetitionType] = useState('PVC');
    const [view, setView] = useState('meet');
    const [seedData, setSeedData] = useState(null);

    useEffect(() => {
        if (scoreMethod === 'Seeds') {
            const file = competitionType === 'States' ? 'states_2026_outdoor.json' : 'pvc_2026_outdoor.json';
            const fetchUrl = asset(`/data/seeds/${file}`);
            
            fetch(fetchUrl)
                .then(r => r.json())
                .then(d => setSeedData(d))
                .catch(err => console.error('Failed to load seed data', err));
        }
    }, [scoreMethod, competitionType]);

    // Convert seed entries into perf-like objects compatible with groupedData / teamPools
    const seedPerfs = useMemo(() => {
        if (!seedData) return [];
        return seedData.entries.map(entry => ({
            event: normalizeEvent(entry.event, 'Outdoor'),
            mark: entry.mark,
            pvcTeam: entry.team,
            isRelay: entry.isRelay,
            athlete_id: entry.isRelay ? `relay_${entry.event}_${entry.team}` : (entry.athleteId || ''),
            athlete_name: entry.isRelay ? (entry.members || []).join(', ') : (entry.name || ''),
            derivedYear: seedData.meta.year,
            derivedType: seedData.meta.season,
        }));
    }, [seedData]);

    const squash = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
    // A store team belongs to a listed school when its name contains the
    // school's short key ("Central/Dexter (indoor track)" is Central and
    // Dexter's co-op) or equals the full name; middle schools never do.
    const schoolOf = (teamName, schools) => {
        const t = squash(teamName);
        if (/middle|junior|elementary|grades/i.test(teamName || '')) return null;
        for (const [key, val] of Object.entries(schools || {})) {
            if (key === "Central" && t.includes("maine")) continue;
            if (t.includes(squash(key)) || t === squash(val)) return val;
        }
        return null;
    };

    const getStateSchools = (year, season) => {
        const isOutdoor = (season && season.toLowerCase().includes('outdoor'));
        if (isOutdoor) {
            return {
                "Wells": "Wells High School", "Winslow": "Winslow High School", "Houlton": "Houlton High School",
                "Washington A": "Washington Academy", "Spruce Mountai": "Spruce Mountain High School",
                "Mountain Valle": "Mountain Valley High School", "Maranacook": "Maranacook Community High School",
                "Bucksport": "Bucksport High School", "Mt. View": "Mount View High School",
                "Maine Central": "Maine Central Institute", "Orono": "Orono High School",
                "Lisbon": "Lisbon/Oak Hill", "George Stevens": "George Stevens Academy",
                "Sacopee Valle": "Sacopee Valley High School", "Mattanawcook": "Mattanawcook Academy",
                "Central": "Central High School", "Hall-Dale": "Hall-Dale High School",
                "Dexter": "Dexter Regional High School", "Traip": "Traip Academy",
                "Fort Kent": "Fort Kent Community High School", "Calais": "Calais High School",
                "Sumner": "Sumner Memorial High School", "Winthrop": "Winthrop High School",
                "Kents Hill": "Kents Hill School", "Gould": "Gould Academy",
                "Dirigo": "Dirigo High School", "Mt. Abram": "Mt. Abram High School",
                "Madison": "Madison High School", "Old Orchard": "Old Orchard Beach High School",
                "North Yarmouth": "North Yarmouth Academy", "Maine Coast": "Maine Coast Waldorf School",
                "Monmouth": "Monmouth Academy", "Narraguagus": "Narraguagus High School",
                "Carrabec": "Carrabec High School", "Piscataquis": "Piscataquis Community High School",
                "Telstar": "Telstar Regional High School", "Penquis": "Penquis Valley High School",
                "Wiscasset": "Wiscasset/Boothbay", "Boothbay": "Wiscasset/Boothbay",
                "Buckfield": "Buckfield High School", "Madawaska": "Madawaska High School",
                "Penobscot Vall": "Penobscot Valley High School", "Fort Fairfiel": "Fort Fairfield High School",
                "Searsport": "Searsport District High School", "Richmond": "Richmond High School",
                "Lee": "Lee Academy", "Deer Isle": "Deer Isle-Stonington High School",
                "MSSM": "Maine School of Science and Mathematics", "Washburn": "Washburn District High School",
                "Bangor Chris": "Bangor Christian Schools", "Easton": "Easton High School",
                "Greenville": "Greenville High School", "Blue Hill Harb": "Blue Hill Harbor School",
                "Vinalhaven": "Vinalhaven School", "Greater Portl": "Greater Portland Christian School",
                "Seacoast": "Seacoast Christian School", "Chop Point": "Chop Point School",
                "North Haven": "North Haven Community School"
            };
        }
        return { "George Stevens": "George Stevens Academy", "Orono": "Orono High School", "Bucksport": "Bucksport High School" };
    };

    const getPVCSchools = (year, season) => {
        const isIndoor = (season && season.toLowerCase().includes('indoor'));
        if (isIndoor) {
            return {
                "Bangor Chris": "Bangor Christian Schools", "Bucksport": "Bucksport High School",
                "Central": "Central High School", "Dexter": "Dexter Regional High School",
                "George Stevens": "George Stevens Academy",
                "Mattanawcook": "Mattanawcook Academy", "Orono": "Orono High School",
                "PCHS": "Piscataquis Community High School", "Penquis": "Penquis Valley High School",
                "Searsport": "Searsport District High School", "Sumner": "Sumner/Narragaugus"
            };
        }
        return {
            "Bangor Chris": "Bangor Christian Schools", "Bucksport": "Bucksport High School",
            "Central": "Central High School", "Dexter": "Dexter Regional High School",
            "George Stevens": "George Stevens Academy",
            "Houlton": "Houlton High School", "Jonesport": "Jonesport-Beals High School",
            "Mattanawcook": "Mattanawcook Academy", "Narraguagus": "Narraguagus High School",
            "Orono": "Orono High School", "Penquis": "Penquis Valley High School",
            "Sumner": "Sumner Memorial High School", "Washington A": "Washington Academy"
        };
    };

    // The championship as it happened (backend/track_champ_results.py), one file per season.
    const [champFile, setChampFile] = useState(null)
    useEffect(() => {
        setChampFile(null)
        if (filterYear === 'All' || !['Indoor', 'Outdoor'].includes(filterSeason)) return
        let live = true
        fetchGz(asset(`/data/track_champs/${filterYear}_${filterSeason}.json.gz`))
            .then(d => { if (live) setChampFile(d) })
            .catch(() => {})
        return () => { live = false }
    }, [filterYear, filterSeason])

    const baseSchools = useMemo(() => competitionType === 'Everyone' ? null
        : competitionType === 'PVC' ? getPVCSchools(filterYear, filterSeason) : getStateSchools(filterYear, filterSeason),
        [competitionType, filterYear, filterSeason])

    // This competition's championship per gender: the PVC (indoor: EMITL) small-school
    // meet, or the state meet of the team being optimized (else the class most listed schools ran in).
    const champIds = useMemo(() => {
        if (!champFile || !baseSchools || scoreMethod === 'Seeds') return ''
        const ids = []
        for (const g of ['Boys', 'Girls']) {
            const cs = champFile.champs.filter(c => c.gender === g && (competitionType === 'PVC'
                ? c.kind === 'conf' && /small|all/i.test(c.division || '')
                : c.kind === 'state'))
            const count = c => c.teams.filter(t => schoolOf(t.team, baseSchools)).length
            const ranIn = c => c.teams.some(t => schoolOf(t.team, baseSchools) === targetTeam)
            cs.sort((a, b) => (ranIn(b) - ranIn(a)) || (count(b) - count(a)))
            if (cs.length) ids.push(cs[0].id)
        }
        return ids.join(',')
    }, [champFile, baseSchools, competitionType, targetTeam, scoreMethod])
    // (keyed by id, so picking another team in the same class recomputes nothing)
    const champs = useMemo(() => {
        if (!champIds) return null
        const ids = champIds.split(',')
        return Object.fromEntries(champFile.champs.filter(c => ids.includes(c.id)).map(c => [c.gender, c]))
    }, [champFile, champIds])

    // The schools in the competition: the listed ones plus anyone else who scored at the meet.
    const activeSchools = useMemo(() => {
        if (!baseSchools) return null
        const out = { ...baseSchools }
        Object.values(champs || {}).forEach(c => c.teams.forEach(t => {
            if (!schoolOf(t.team, out)) out[t.team] = t.team
        }))
        return out
    }, [baseSchools, champs])

    // A championship is predicted from results before it, never after.
    const champCutoff = useMemo(() => {
        const cs = Object.values(champs || {})
        if (!cs.length) return null
        const first = cs.reduce((a, b) => (a.date <= b.date ? a : b))
        return { date: first.date, meet: first.file }
    }, [champs])

    const loadingState = useMemo(() => {
        if (!manifest || !manifest.teams || filterYear === 'All' || filterSeason === 'All') {
            return { isLoading: false, expectedCount: 0, loadedCount: 0, loadingTeams: [], percent: 100 };
        }

        const seasonKey = `${filterYear}_${filterSeason}`.replace(' ', '_');

        // Find which teams in manifest belong to the competition AND participate in this season
        const expectedTeams = (manifest.teams || []).filter(t => {
            const participates = t.seasons && t.seasons.includes(seasonKey);
            if (!participates) return false;
            if (!activeSchools) return true;
            return schoolOf(t.name, activeSchools) !== null;
        });

        // Teams with this season's results in hand
        const loadedNames = new Set();
        (performances || []).forEach(p => {
            if (String(p.year) === String(filterYear) && p.season === filterSeason) loadedNames.add(p.team);
        });

        const loadingTeams = expectedTeams.filter(t => !loadedNames.has(t.name));
        const expectedCount = expectedTeams.length;
        const loadedCount = expectedCount - loadingTeams.length;
        const percent = expectedCount > 0 ? Math.round((loadedCount / expectedCount) * 100) : 100;

        return {
            isLoading: loadingTeams.length > 0,
            expectedCount,
            loadedCount,
            loadingTeams,
            percent
        };
    }, [manifest, performances, filterYear, filterSeason, activeSchools]);

    useEffect(() => {
        if (!loadTeamData) return;
        
        // only the season being simulated, not each team's whole history
        const key = `${filterYear}_${filterSeason}`
        loadingState.loadingTeams.forEach(t => loadTeamData(t.slug, [key]));
    }, [loadingState.loadingTeams, loadTeamData, filterYear, filterSeason]);

    const { filteredData, years, seasons, events } = useMemo(() => {
        if (!performances) return { filteredData: [], years: [], seasons: [], events: [] };

        // 1. Calculate available Years and Seasons first (from raw data)
        const rawYears = new Set();
        const rawSeasons = new Set();
        performances.forEach(p => {
            if (p.year) rawYears.add(p.year);
            if (p.season) {
                const m = p.season.match(/^(\d{4})\s+(.*)$/);
                if (m) rawSeasons.add(m[2]);
                else rawSeasons.add(p.season);
            }
        });

        // 2. If filters are not set, return empty data but populated options
        if (filterYear === 'All' || filterSeason === 'All') {
            return {
                filteredData: [],
                years: Array.from(rawYears).sort((a, b) => b - a),
                seasons: Array.from(rawSeasons).sort(),
                events: []
            }
        }

        const processed = performances.map(p => {
            let year = p.year;
            let type = p.season;
            if (p.season && p.season.match(/^\d{4}/)) {
                const m = p.season.match(/^(\d{4})\s+(.*)$/);
                year = m[1];
                type = m[2];
            }
            return {
                ...p,
                derivedYear: year,
                derivedType: type,
                pvcTeam: activeSchools ? schoolOf(p.team, activeSchools) : p.team,
                isRelay: p.event.toLowerCase().includes('relay') || p.event.toLowerCase().includes('4x')
            };
        }).filter(p => p.pvcTeam); // Only include valid schools for THIS season

        const matches = (p, filters) => {
            const { year, season, event } = filters;
            return (year === 'All' || p.derivedYear === year) &&
                (season === 'All' || p.derivedType === season) &&
                (event === 'All' || p.event === event);
        };

        const avYears = Array.from(new Set(processed.filter(p => p.derivedType === filterSeason).map(p => p.derivedYear))).sort((a, b) => b - a);
        const avSeasons = Array.from(new Set(processed.map(p => p.derivedType))).sort();
        const avEvents = Array.from(new Set(processed.map(p => p.event))).sort();

        // results from the championship's day on are left out
        const filtered = processed.filter(p => matches(p, { year: filterYear, season: filterSeason, event: filterEvent })
            && !(champCutoff && (p.date || '').slice(0, 10) >= champCutoff.date));

        return {
            filteredData: filtered,
            years: avYears,
            seasons: avSeasons,
            events: avEvents
        };
    }, [performances, filterYear, filterSeason, filterEvent, activeSchools, champCutoff]);

    // the latest season on file when the chosen one has no results (the season about to start)
    useEffect(() => {
        if (years.length && !years.includes(filterYear)) setFilterYear(years[0])
    }, [years, filterYear])

    // Places scored: the championship's own table; else PVC six, states eight.
    const SCORING_RULES = useMemo(() => Object.values(champs || {})[0]?.table
        || (competitionType === 'States' ? [10, 8, 6, 5, 4, 3, 2, 1] : [10, 8, 6, 4, 2, 1]), [champs, competitionType]);

    // Treat Indoor/Outdoor differently: 4 event limit for Outdoor, 3 for Indoor.
    const EVENT_LIMIT = (scoreMethod !== 'Seeds' && filterSeason && filterSeason.toLowerCase().includes('indoor')) ? 3 : 4;

    const scrollToEvent = (groupTitle) => {
        const targetId = `event-${groupTitle.replace(/[^a-z0-9]/gi, '-')}`;
        const element = document.getElementById(targetId);
        if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    };

    // Configuration for PVC Small Schools

    const SCORING_EVENTS = useMemo(() => {
        const indoor = [
            "4x800m Relay", "55m Hurdles", "55m Dash", "1 Mile Run", 
            "400m Dash", "800m Run", "200m Dash", "2 Mile Run", "4x200m Relay",
            "High Jump", "Pole Vault", "Long Jump", "Triple Jump", "Shot Put"
        ];

        const outdoor = [
            "4x800m Relay", "1600m Race Walk", "100m/110m Hurdles", "100m Dash", 
            "1600m Run", "4x100m Relay", "400m Dash", "300m Hurdles", 
            "800m Run", "200m Dash", "3200m Run", "4x400m Relay",
            "High Jump", "Pole Vault", "Long Jump", "Triple Jump", "Shot Put", "Discus", "Javelin"
        ];

        if (scoreMethod === 'Seeds' || filterSeason === 'Outdoor') return outdoor;
        return indoor;
    }, [filterSeason, scoreMethod]);

    const groupedData = useMemo(() => {
        const groups = {};

        // First group all performances by groupKey -> athleteKey
        const rawGrouped = {};

        // Seeds mode uses seed entries; other modes use historical filtered data
        const sourceData = scoreMethod === 'Seeds' ? seedPerfs : filteredData;
        const activeSeason = scoreMethod === 'Seeds' ? 'Outdoor' : filterSeason;

        sourceData.forEach(curr => {
            const markUpper = (curr.mark || "").toUpperCase();
            if (['DQ', 'DNF', 'NH', 'DNS', 'NM', 'FOUL', 'SCR', 'ND', 'NT', 'X', 'NWI'].includes(markUpper)) return;

            const normalizedFull = normalizeEvent(curr.event, activeSeason);
            const gender = normalizedFull.startsWith('Girls') ? 'Girls' : (normalizedFull.startsWith('Boys') ? 'Boys' : '');
            const baseName = normalizedFull.replace(/^(Girls|Boys)\s+/, '');
            const originalCanonical = baseName;

            const scoringKey = (baseName === '100m Hurdles' || baseName === '110m Hurdles')
                ? '100m/110m Hurdles'
                : baseName;

            if (!SCORING_EVENTS.includes(scoringKey)) return;

            const canonicalName = baseName;
            const groupKey = `${gender} ${canonicalName} (${curr.derivedType} ${curr.derivedYear})`.trim();

            if (!rawGrouped[groupKey]) {
                rawGrouped[groupKey] = {
                    athletes: {},
                    canonicalName: canonicalName,
                    gender: gender,
                    originalCanonical: originalCanonical,
                    orderIdx: SCORING_EVENTS.indexOf(scoringKey)
                };
            }

            const athleteKey = curr.isRelay ? curr.pvcTeam : `${curr.athlete_id}|${curr.pvcTeam}`;
            if (!rawGrouped[groupKey].athletes[athleteKey]) {
                rawGrouped[groupKey].athletes[athleteKey] = [];
            }
            rawGrouped[groupKey].athletes[athleteKey].push(curr);
        });

        // Now resolve each groupKey -> athleteKey to a single performance record
        Object.entries(rawGrouped).forEach(([groupKey, meta]) => {
            groups[groupKey] = {
                items: {},
                canonicalName: meta.canonicalName,
                gender: meta.gender,
                orderIdx: meta.orderIdx
            };

            Object.entries(meta.athletes).forEach(([athleteKey, perfs]) => {
                if (perfs.length === 0) return;

                let selectedPerf = null;
                perfs.forEach(p => {
                    if (!selectedPerf || isBetter(p.mark, selectedPerf.mark, meta.canonicalName)) {
                        selectedPerf = p;
                    }
                });

                if (selectedPerf) {
                    groups[groupKey].items[athleteKey] = {
                        ...selectedPerf,
                        event: `${meta.gender} ${meta.canonicalName}`.trim(),
                        originalCanonical: meta.originalCanonical
                    };
                }
            });
        });

        const finalGroups = {};
        
        // Sort keys by canonical order, then gender (Girls then Boys)
        const sortedKeys = Object.keys(groups).sort((a, b) => {
            const gA = groups[a];
            const gB = groups[b];
            
            if (gA.orderIdx !== gB.orderIdx) return gA.orderIdx - gB.orderIdx;
            
            if (gA.gender === 'Girls' && gB.gender === 'Boys') return -1;
            if (gA.gender === 'Boys' && gB.gender === 'Girls') return 1;
            return 0;
        });

        sortedKeys.forEach(groupKey => {
            const results = Object.values(groups[groupKey].items);

            results.sort((a, b) => {
                if (isBetter(a.mark, b.mark, groups[groupKey].canonicalName)) return -1;
                if (isBetter(b.mark, a.mark, groups[groupKey].canonicalName)) return 1;
                return 0;
            });

            let currentRank = 1;
            for (let i = 0; i < results.length; i++) {
                if (i > 0 && results[i].mark !== results[i - 1].mark) {
                    currentRank = i + 1;
                }
                results[i].calculatedRank = currentRank;
            }

            finalGroups[groupKey] = results;
        });

        return finalGroups;
    }, [filteredData, seedPerfs, isBetter, SCORING_EVENTS, scoreMethod]);

    const optimizedData = useMemo(() => {
        const bypassYearSeasonCheck = scoreMethod === 'Seeds';
        if ((!bypassYearSeasonCheck && (filterYear === 'All' || filterSeason === 'All')) || Object.keys(groupedData).length === 0) {
            return groupedData;
        }

        const scoringRules = SCORING_RULES;

        // 1. Extract all entries
        let individualEntries = [];
        let relayEntries = [];

        Object.entries(groupedData).forEach(([groupTitle, results]) => {
            results.forEach(res => {
                const entry = { ...res, groupTitle };
                if (res.isRelay) relayEntries.push(entry);
                else individualEntries.push(entry);
            });
        });

        // 2. Initial Potential Score Pass
        const calculatePoints = (entries) => {
            const groups = {};
            entries.forEach(e => {
                if (!groups[e.groupTitle]) groups[e.groupTitle] = [];
                groups[e.groupTitle].push(e);
            });

            Object.values(groups).forEach(results => {
                results.sort((a, b) => isBetter(a.mark, b.mark) ? -1 : isBetter(b.mark, a.mark) ? 1 : 0);

                let effectiveRank = 1;
                let validCount = 0;
                let lastValidMark = null;

                for (let i = 0; i < results.length; i++) {
                    const p = parseMark(results[i].mark);
                    if (!p.valid) {
                        results[i].tempRank = null;
                        results[i].potentialPts = 0;
                        continue;
                    }

                    if (validCount > 0 && results[i].mark !== lastValidMark) {
                        effectiveRank = validCount + 1;
                    }

                    results[i].tempRank = effectiveRank;
                    results[i].potentialPts = effectiveRank <= scoringRules.length ? scoringRules[effectiveRank - 1] : 0;

                    lastValidMark = results[i].mark;
                    validCount++;
                }
            });
        };

        calculatePoints([...individualEntries, ...relayEntries]);

        // 3. Optimization Logic (season-aware event limit: 3 for Indoor, 4 for Outdoor)
        const eventLimit = EVENT_LIMIT;
        // An athlete's event count = sum(individual events) + sum(relay participations)
        const athleteCounts = {}; // athlete_name -> count
        const athleteEntries = {}; // athlete_name -> [ {entry, pts} ]

        individualEntries.forEach(e => {
            const name = e.athlete_name || "Unknown";
            if (!athleteEntries[name]) athleteEntries[name] = [];
            athleteEntries[name].push(e);
        });

        relayEntries.forEach(e => {
            // Relays usually have athlete names like "A, B, C, D"
            const nameStr = e.athlete_name || "";
            const members = nameStr.split(',').map(n => n.trim()).filter(Boolean);
            members.forEach(m => {
                if (!athleteEntries[m]) athleteEntries[m] = [];
                athleteEntries[m].push({ ...e, isRelayLeg: true, relayRef: e });
            });
        });

        // Greedy Selection: Keep picking top entries until limits hit or no more points possible
        const selectedEntries = new Set(); // entry id or unique key
        // const athleteUsage = {}; // name -> count -- merged below


        const allPossibleScoringActions = [];
        individualEntries.forEach(e => {
            allPossibleScoringActions.push({
                type: 'ind',
                entry: e,
                pts: e.potentialPts,
                athlete: e.athlete_name,
                rank: e.tempRank || 999
            });
        });
        relayEntries.forEach(e => {
            const nameStr = e.athlete_name || "";
            const members = nameStr.split(',').map(n => n.trim()).filter(Boolean);
            allPossibleScoringActions.push({
                type: 'rel',
                entry: e,
                pts: e.potentialPts,
                athletes: members,
                rank: e.tempRank || 999
            });
        });

        // Sort actions by points descending, then by rank ascending
        allPossibleScoringActions.sort((a, b) => {
            if (b.pts !== a.pts) return b.pts - a.pts;
            return a.rank - b.rank;
        });

        const activeIndividualChoices = [];
        const activeRelayChoices = [];
        const athleteUsage = {}; // name -> count

        allPossibleScoringActions.forEach(action => {
            if (action.type === 'ind') {
                const usage = athleteUsage[action.athlete] || 0;
                if (usage < eventLimit) {
                    athleteUsage[action.athlete] = usage + 1;
                    activeIndividualChoices.push(action.entry);
                }
            } else {
                const members = action.athletes.filter(m => m && !m.toLowerCase().includes('school') && !m.toLowerCase().includes('relay'));
                if (members.length === 0) {
                    activeRelayChoices.push(action.entry);
                } else {
                    let canFit = true;
                    members.forEach(m => {
                        if ((athleteUsage[m] || 0) >= eventLimit) canFit = false;
                    });
                    if (canFit) {
                        members.forEach(m => {
                            athleteUsage[m] = (athleteUsage[m] || 0) + 1;
                        });
                        activeRelayChoices.push(action.entry);
                    }
                }
            }
        });

        // 4. Re-rank based on optimized selections
        const finalEntries = [...activeIndividualChoices, ...activeRelayChoices];
        const finalGroups = {};
        Object.keys(groupedData).forEach(k => { finalGroups[k] = [] });   // meet order
        finalEntries.forEach(e => {
            if (!finalGroups[e.groupTitle]) finalGroups[e.groupTitle] = [];
            finalGroups[e.groupTitle].push(e);
        });

        Object.entries(finalGroups).forEach(([title, results]) => {
            results.sort((a, b) => isBetter(a.mark, b.mark) ? -1 : isBetter(b.mark, a.mark) ? 1 : 0);

            let effectiveRank = 1;
            let validCount = 0;
            let lastValidMark = null;

            for (let i = 0; i < results.length; i++) {
                const p = parseMark(results[i].mark);
                if (!p.valid) {
                    results[i].calculatedRank = null;
                    results[i].optimizedPts = 0;
                    continue;
                }

                if (validCount > 0 && results[i].mark !== lastValidMark) {
                    effectiveRank = validCount + 1;
                }

                results[i].calculatedRank = effectiveRank;

                if (effectiveRank <= scoringRules.length) {
                    // Tie splitting logic
                    let tieCount = 1;
                    let j = i + 1;
                    // Only count ties for VALID marks
                    while (j < results.length && results[j].mark === results[i].mark && parseMark(results[j].mark).valid) {
                        tieCount++;
                        j++;
                    }

                    let pointSum = 0;
                    for (let k = effectiveRank - 1; k < Math.min(scoringRules.length, effectiveRank - 1 + tieCount); k++) {
                        pointSum += scoringRules[k];
                    }

                    const perAthlete = pointSum / tieCount;
                    for (let k = i; k < i + tieCount; k++) {
                        results[k].optimizedPts = perAthlete;
                    }

                    // Increment loop index and validCount by the number of people tied
                    // but we need to handle the loop index increment correctly
                    const jump = tieCount - 1;
                    lastValidMark = results[i].mark;
                    validCount += tieCount;
                    i += jump;
                } else {
                    results[i].optimizedPts = 0;
                    lastValidMark = results[i].mark;
                    validCount++;
                }
            }
        });

        Object.keys(finalGroups).forEach(k => { if (!finalGroups[k].length) delete finalGroups[k] });
        return finalGroups;
    }, [groupedData, filterYear, filterSeason, isBetter, EVENT_LIMIT, SCORING_RULES]);

    const optimizedTeamScores = useMemo(() => {
        if (scoreMethod !== 'Seeds' && (filterYear === 'All' || filterSeason === 'All')) return { incomplete: true };

        const scores = { boys: {}, girls: {} };

        Object.entries(optimizedData).forEach(([groupTitle, results]) => {
            if (results.length === 0) return;
            // Derive gender from event name if not present
            const eventName = results[0].event || "";
            const gender = eventName.toLowerCase().includes('girls') ? 'girls' : 'boys';

            results.forEach(res => {
                if (res.optimizedPts > 0) {
                    const team = res.pvcTeam;
                    if (!scores[gender][team]) scores[gender][team] = { total: 0, breakdown: [] };
                    scores[gender][team].total += res.optimizedPts;
                    scores[gender][team].breakdown.push({
                        event: res.event,
                        athlete: res.athlete_name || "Unknown",
                        mark: res.mark,
                        pts: res.optimizedPts,
                        groupTitle: groupTitle
                    });
                }
            });
        });

        const formatScores = (scoreMap) => Object.entries(scoreMap)
            .sort((a, b) => b[1].total - a[1].total)
            .map(([team, data]) => ({
                team,
                pts: data.total,
                breakdown: data.breakdown.sort((a, b) => b.pts - a.pts)
            }));

        return {
            boys: formatScores(scores.boys),
            girls: formatScores(scores.girls)
        };
    }, [optimizedData, filterYear, filterSeason]);

    // Each athlete's marks this season, on a log scale where lower is better.
    const seasonMarks = useMemo(() => {
        const out = {}
        if (scoreMethod === 'Seeds') return out
        filteredData.forEach(p => {
            const v = logMark(p.mark, p.event)
            if (v == null) return
            const k = `${normalizeEvent(p.event, filterSeason)}|${p.isRelay ? p.pvcTeam : `${p.athlete_id}|${p.pvcTeam}`}`;
            (out[k] = out[k] || []).push(v)
        })
        return out
    }, [filteredData, filterSeason, scoreMethod])

    // Each team's chance of finishing 1st, 2nd, 3rd and 4th or lower: the predicted entries'
    // meet run SIMS times, each mark drawn around the mean of the athlete's two best marks
    // with the event family's championship-day spread (CHAMP_SPREAD).
    const placeOdds = useMemo(() => {
        const out = { boys: {}, girls: {} }
        if (loadingState.isLoading) return out   // once, when every team's results are in
        const rand = mulberry32(1)
        const gauss = () => Math.sqrt(-2 * Math.log(1 - rand())) * Math.cos(2 * Math.PI * rand())
        const events = []
        Object.values(optimizedData).forEach(results => {
            if (!results.length) return
            const eg = (results[0].event || '').startsWith('Girls') ? 'girls' : 'boys'
            if (eg !== g) return
            const sd = CHAMP_SPREAD[eventFamily(results[0].event)]
            const rows = results.map(r => {
                const own = (seasonMarks[`${r.event}|${r.isRelay ? r.pvcTeam : `${r.athlete_id}|${r.pvcTeam}`}`] || []).slice().sort((a, b) => a - b)
                const best = own.length ? own.slice(0, 2) : [logMark(r.mark, r.event)]
                return best[0] == null ? null : { team: r.pvcTeam, mu: (best[0] + (best[1] ?? best[0])) / 2 }
            }).filter(Boolean)
            if (rows.length) events.push({ sd, rows })
        })
        const K = SCORING_RULES.length
        {
            const teams = [...new Set(events.flatMap(e => e.rows.map(r => r.team)))]
            const ti = new Map(teams.map((t, i) => [t, i]))
            const evs = events.map(e => ({ sd: e.sd, mu: Float64Array.from(e.rows, r => r.mu), team: Int32Array.from(e.rows, r => ti.get(r.team)) }))
            const counts = teams.map(() => [0, 0, 0, 0])
            const pts = new Float64Array(teams.length)
            const topV = new Float64Array(K), topT = new Int32Array(K)
            for (let s = 0; s < SIMS; s++) {
                pts.fill(0)
                for (const { sd, mu, team } of evs) {
                    // the K best draws, kept sorted by insertion
                    let n = 0
                    for (let i = 0; i < mu.length; i++) {
                        const v = mu[i] + sd * gauss()
                        if (n === K && v >= topV[K - 1]) continue
                        let j = n < K ? n++ : K - 1
                        while (j > 0 && topV[j - 1] > v) { topV[j] = topV[j - 1]; topT[j] = topT[j - 1]; j-- }
                        topV[j] = v; topT[j] = team[i]
                    }
                    for (let p = 0; p < n; p++) pts[topT[p]] += SCORING_RULES[p]
                }
                // top three teams this sim
                let a = -1, b = -1, c = -1
                for (let t = 0; t < teams.length; t++) {
                    if (a < 0 || pts[t] > pts[a]) { c = b; b = a; a = t }
                    else if (b < 0 || pts[t] > pts[b]) { c = b; b = t }
                    else if (c < 0 || pts[t] > pts[c]) c = t
                }
                for (let t = 0; t < teams.length; t++) counts[t][t === a ? 0 : t === b ? 1 : t === c ? 2 : 3]++
            }
            teams.forEach((t, i) => { out[g][t] = counts[i].map(n => n / SIMS) })
        }
        return out
    }, [optimizedData, seasonMarks, SCORING_RULES, loadingState.isLoading, g])

    const entryDecisions = useMemo(() => {
        if (!targetTeam || Object.keys(groupedData).length === 0) return null;

        const teamAthletes = {};

        Object.entries(groupedData).forEach(([groupTitle, results]) => {
            if (!ofGender(results[0]?.event)) return;
            let rankPos = 0;

            for (let i = 0; i < results.length; i++) {
                const res = results[i];
                const team = res.pvcTeam;
                const isRelay = res.isRelay;
                // Every athlete counts towards the rank if they have a valid performance
                rankPos++;

                if (team === targetTeam) {
                    const nameStr = res.athlete_name || "";
                    let names = [nameStr];
                    if (isRelay) {
                        names = nameStr.split(',').map(n => n.trim()).filter(n => n && !n.toLowerCase().includes('school') && !n.toLowerCase().includes('relay'));
                    }

                    names.forEach(name => {
                        if (!teamAthletes[name]) teamAthletes[name] = { scoringEvents: [] };
                        
                        let pts = rankPos <= SCORING_RULES.length ? SCORING_RULES[rankPos - 1] : 0;
                        if (isRelay) pts /= 4;

                        teamAthletes[name].scoringEvents.push({
                            event: res.event,
                            rank: rankPos,
                            expectedPoints: pts,
                            mark: res.mark,
                            isRelay: isRelay,
                            isScorable: rankPos <= SCORING_RULES.length,
                            originalCanonical: res.originalCanonical
                        });
                    });
                }
            }
        });

        const decisionAthletes = [];
        const straightforwardAthletes = [];

        const getEventIndex = (scoringEvent) => {
            return SCORING_EVENTS.indexOf(scoringEvent.originalCanonical);
        };

        Object.entries(teamAthletes).forEach(([name, data]) => {
            if (name === "Relay") return;

            // Deduplicate by event name (keep best rank)
            const bestEvs = {};
            data.scoringEvents.forEach(sev => {
                if (!bestEvs[sev.event] || sev.rank < bestEvs[sev.event].rank) {
                    bestEvs[sev.event] = sev;
                }
            });
            data.scoringEvents = Object.values(bestEvs).sort((a, b) => {
                if (b.expectedPoints !== a.expectedPoints) {
                    return b.expectedPoints - a.expectedPoints;
                }
                return a.rank - b.rank;
            });

            const scorableEvents = data.scoringEvents.filter(e => e.isScorable);
            const trackIndices = [...new Set(scorableEvents.map(e => getEventIndex(e.event)).filter(idx => idx >= 0))].sort((a, b) => a - b);
            let hasAdjacency = false;
            for (let i = 0; i < trackIndices.length - 1; i++) {
                if (trackIndices[i + 1] - trackIndices[i] === 1) {
                    hasAdjacency = true;
                    break;
                }
            }

            if (scorableEvents.length > EVENT_LIMIT || hasAdjacency) {
                decisionAthletes.push({
                    name,
                    scoringEvents: data.scoringEvents,
                    isAdjacent: hasAdjacency,
                    isVolume: scorableEvents.length > EVENT_LIMIT,
                    scorableCount: scorableEvents.length
                });
            } else if (data.scoringEvents.length > 0) {
                straightforwardAthletes.push({
                    name,
                    scoringEvents: data.scoringEvents,
                    scorableCount: scorableEvents.length
                });
            }
        });

        return {
            decisionAthletes: decisionAthletes.sort((a, b) => b.scorableCount - a.scorableCount || b.scoringEvents.length - a.scoringEvents.length),
            straightforwardAthletes: straightforwardAthletes.sort((a, b) => b.scorableCount - a.scorableCount || b.scoringEvents.length - a.scoringEvents.length)
        };
    }, [groupedData, targetTeam, SCORING_RULES, SCORING_EVENTS, EVENT_LIMIT, gender]);

    // What happened at the championship, in the simulator's names: per gender the
    // team order and each event's places, keyed like the event sections ('Girls 55m Hurdles').
    const actual = useMemo(() => {
        if (!champs) return null
        const teamOf = t => (activeSchools && schoolOf(t, activeSchools)) || t
        const out = {}
        Object.entries(champs).forEach(([g, c]) => {
            const totals = {}
            c.teams.forEach(t => { const k = teamOf(t.team); totals[k] = (totals[k] || 0) + (t.official ?? t.score) })
            const scores = Object.values(totals)
            const teams = Object.entries(totals).sort((a, b) => b[1] - a[1])
                .map(([team, score]) => ({ team, score, place: 1 + scores.filter(x => x > score).length }))
            const events = {}
            Object.entries(c.events).forEach(([ev, rows]) => {
                events[normalizeEvent(`${g} ${ev}`, filterSeason)] = rows.map(r => ({ ...r, team: teamOf(r.t) }))
            })
            out[g.toLowerCase()] = { champ: c, teams, events }
        })
        return out
    }, [champs, activeSchools, filterSeason])

    const rowKey = (name, team, isRelay) => isRelay ? `relay|${team}` : `${squash(name)}|${team}`

    // One event: the predicted entries beside their result, then scorers the prediction left out.
    const eventRows = (results) => {
        const g = (results[0].event || '').startsWith('Girls') ? 'girls' : 'boys'
        const act = actual?.[g]?.events[results[0].event]
        if (!act) return { rows: results.map(r => ({ pred: r })), act: null }
        const isRelay = !!results[0].isRelay
        const byKey = new Map(act.map(a => [rowKey(a.n, a.team, isRelay), a]))
        const used = new Set()
        const rows = results.map(r => {
            const k = rowKey(r.athlete_name, r.pvcTeam, isRelay)
            const a = byKey.get(k)
            if (a) used.add(k)
            return { pred: r, act: a }
        })
        act.forEach(a => {
            const k = rowKey(a.n, a.team, isRelay)
            if (a.pts && !used.has(k)) rows.push({ act: a })
        })
        return { rows, act }
    }

    return (
        <div className="analyzer-container">
            <div className="analyzer-header">
                <h2>Postseason Simulator</h2>
            </div>

            {loadingState.isLoading && (
                <div className="simulation-loading-banner" style={{
                    backgroundColor: 'rgba(128, 0, 0, 0.04)',
                    border: '1px solid rgba(128, 0, 0, 0.12)',
                    color: '#600000',
                    padding: '16px',
                    borderRadius: '10px',
                    marginBottom: '10px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '10px',
                    fontSize: '0.9rem',
                    fontWeight: '600',
                    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.02)'
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <span className="spinner" style={{
                                width: '14px',
                                height: '14px',
                                border: '2px solid rgba(128, 0, 0, 0.2)',
                                borderTop: '2px solid #800000',
                                borderRadius: '50%',
                                display: 'inline-block',
                                animation: 'spin 0.8s linear infinite'
                            }} />
                            <span>Loading postseason team results...</span>
                        </div>
                        <span style={{ fontSize: '0.85rem', color: '#718096' }}>
                            {loadingState.loadedCount} / {loadingState.expectedCount} Teams ({loadingState.percent}%)
                        </span>
                    </div>
                    <div style={{
                        width: '100%',
                        height: '6px',
                        backgroundColor: 'rgba(0, 0, 0, 0.05)',
                        borderRadius: '3px',
                        overflow: 'hidden'
                    }}>
                        <div style={{
                            width: `${loadingState.percent}%`,
                            height: '100%',
                            backgroundColor: '#800000',
                            borderRadius: '3px',
                            transition: 'width 0.4s cubic-bezier(0.4, 0, 0.2, 1)'
                        }} />
                    </div>
                    <div style={{ fontSize: '0.75rem', fontWeight: 'normal', color: '#718096', display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
                        <span>Remaining:</span>
                        {loadingState.loadingTeams.slice(0, 5).map(t => (
                            <span key={t.slug} style={{ background: 'rgba(0,0,0,0.04)', padding: '2px 6px', borderRadius: '4px', fontSize: '0.7rem' }}>
                                {t.name}
                            </span>
                        ))}
                        {loadingState.loadingTeams.length > 5 && (
                            <span style={{ fontSize: '0.7rem', fontStyle: 'italic' }}>
                                + {loadingState.loadingTeams.length - 5} more
                            </span>
                        )}
                    </div>
                </div>
            )}

            <div className="xs-bar ps-tabs">
                <div className="xs-seg" role="group" aria-label="View">
                    <button className={view === 'meet' ? 'active' : ''} onClick={() => setView('meet')}>Meet</button>
                    <button className={view === 'entries' ? 'active' : ''} onClick={() => setView('entries')}
                        title={`${targetTeam}: athletes with more than ${EVENT_LIMIT} scoring events or adjacent track events`}>Entry decisions</button>
                </div>
                <div className="xs-seg" role="group" aria-label="Gender">
                    {['Boys', 'Girls'].map(x => (
                        <button key={x} className={x === gender ? 'active' : ''} onClick={() => setGender(x)}>{x}</button>
                    ))}
                </div>
            </div>

            <div className="analyzer-controls">
                <div className="filter-bar analyzer-filters">
                    <div className="filter-group">
                        <label>Year</label>
                        <select value={filterYear} onChange={e => setFilterYear(e.target.value)}>
                            {years.map(y => <option key={y} value={y}>{y}</option>)}
                        </select>
                    </div>
                    {!season && (
                    <div className="filter-group">
                        <label>Season</label>
                        <select value={filterSeason} onChange={e => setFilterSeason(e.target.value)}>
                            <option value="All">All Seasons</option>
                            {seasons.map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                    </div>
                    )}
                    <div className="filter-group">
                        <label>Competition</label>
                        <select value={competitionType} onChange={e => setCompetitionType(e.target.value)}>
                            <option value="PVC">PVC Small Schools</option>
                            <option value="States" title="The state meet of the team being optimized">State meet</option>
                            <option value="Everyone">Everyone</option>
                        </select>
                    </div>
                    <div className="filter-group">
                        <label>Optimize For</label>
                        <select value={targetTeam} onChange={e => setTargetTeam(e.target.value)}>
                            {[...new Set(Object.values(activeSchools || getStateSchools(filterYear, filterSeason)))].map(t => (
                                <option key={t} value={t}>{t}</option>
                            ))}
                        </select>
                    </div>
                    <div className="filter-group">
                        <label>Scoring Basis</label>
                        <select value={scoreMethod} onChange={e => setScoreMethod(e.target.value)}>
                            <option value="PR">Season Best (SB)</option>
                            <option value="Seeds">Actual Seeds (5/29)</option>
                        </select>
                    </div>
                    <div className="record-count">{scoreMethod === 'Seeds' ? `${seedPerfs.length} Seeds` : `${filteredData.length} Results`}</div>
                </div>
            </div>

            {view === 'entries' && entryDecisions && (entryDecisions.decisionAthletes.length > 0 || entryDecisions.straightforwardAthletes.length > 0) && (
                <div className="entry-decisions-dashboard" style={{ marginTop: '12px' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(400px, 100%), 1fr))', gap: '20px' }}>
                        {entryDecisions.decisionAthletes.length > 0 && (
                            <div className="decision-card" style={{ background: '#fff5f5', border: '1px solid #feb2b2', borderRadius: '12px', padding: '20px' }}>
                                <h4 style={{ margin: '0 0 12px 0', color: '#c53030', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                    Decision Athletes (&gt;{EVENT_LIMIT} events or adjacent track)
                                </h4>
                                <div className="decisions-list" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                    {entryDecisions.decisionAthletes.map(ath => (
                                        <div key={ath.name} style={{ background: 'white', padding: '12px', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                                                <div style={{ fontWeight: 700, color: '#2d3748' }}>{ath.name}</div>
                                                <div style={{ display: 'flex', gap: '4px' }}>
                                                    {ath.isVolume && <span style={{ fontSize: '0.65rem', background: '#fed7d7', color: '#9b2c2c', padding: '1px 6px', borderRadius: '10px', fontWeight: 700 }}>VOLUME</span>}
                                                    {ath.isAdjacent && <span style={{ fontSize: '0.65rem', background: '#fffaf0', color: '#9c4221', padding: '1px 6px', borderRadius: '10px', fontWeight: 700, border: '1px solid #feebc8' }}>ADJACENT</span>}
                                                </div>
                                            </div>
                                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                                {ath.scoringEvents.map((ev, idx) => {
                                                    const isTop3Opportunity = ev.isScorable && idx < EVENT_LIMIT;
                                                    const isScoring = ev.isScorable;

                                                    let badgeStyle = {
                                                        fontSize: '0.75rem',
                                                        padding: '2px 8px',
                                                        borderRadius: '4px',
                                                        fontWeight: isScoring ? 600 : 400,
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        gap: '4px'
                                                    };

                                                    if (isTop3Opportunity) {
                                                        badgeStyle = { ...badgeStyle, background: '#c6f6d5', color: '#22543d', border: '1px solid #9ae6b4' };
                                                    } else if (isScoring) {
                                                        badgeStyle = { ...badgeStyle, background: '#edf2f7', color: '#4a5568', border: '1px solid #e2e8f0' };
                                                    } else {
                                                        badgeStyle = { ...badgeStyle, background: 'white', color: '#718096', border: '1px solid #f1f5f9' };
                                                    }

                                                    return (
                                                        <span key={ev.event} style={badgeStyle}>
                                                            {ev.isRelay && <span style={{ opacity: 0.8 }}></span>}
                                                            {ev.event} (<span style={{ fontWeight: 700 }}>#{ev.rank}</span>)
                                                        </span>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {entryDecisions.straightforwardAthletes.length > 0 && (
                            <div className="straightforward-card" style={{ background: '#f0fff4', border: '1px solid #9ae6b4', borderRadius: '12px', padding: '20px' }}>
                                <h4 style={{ margin: '0 0 12px 0', color: '#2f855a', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                    Straightforward Entries (&lt;={EVENT_LIMIT} Scoring Events)
                                </h4>
                                <div className="decisions-list" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                    {entryDecisions.straightforwardAthletes.map(ath => (
                                        <div key={ath.name} style={{ background: 'white', padding: '12px', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                                            <div style={{ fontWeight: 600, marginBottom: '6px', color: '#4a5568', fontSize: '0.9rem' }}>{ath.name}</div>
                                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                                {ath.scoringEvents.map((ev, idx) => {
                                                    const isTop3Opportunity = ev.isScorable && idx < EVENT_LIMIT;
                                                    const isScoring = ev.isScorable;

                                                    let badgeStyle = {
                                                        fontSize: '0.7rem',
                                                        padding: '2px 6px',
                                                        borderRadius: '4px',
                                                        fontWeight: isScoring ? 600 : 400,
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        gap: '3px'
                                                    };

                                                    if (isTop3Opportunity) {
                                                        badgeStyle = { ...badgeStyle, background: '#c6f6d5', color: '#22543d', border: '1px solid #9ae6b4' };
                                                    } else if (isScoring) {
                                                        badgeStyle = { ...badgeStyle, background: '#edf2f7', color: '#4a5568', border: '1px solid #e2e8f0' };
                                                    } else {
                                                        badgeStyle = { ...badgeStyle, background: 'white', color: '#718096', border: '1px solid #f1f5f9' };
                                                    }

                                                    return (
                                                        <span key={ev.event} style={badgeStyle}>
                                                            {ev.isRelay && <span style={{ fontSize: '0.6rem' }}></span>}
                                                            {ev.event} (<span style={{ fontWeight: 600 }}>#{ev.rank}</span>)
                                                        </span>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {view === 'meet' && <>
            {optimizedTeamScores && !optimizedTeamScores.incomplete && (() => {
                const pts = Object.fromEntries(optimizedTeamScores[g].map(t => [t.team, t]))
                const odds = placeOdds[g]
                // season-best points order; teams with entries but no points after them
                const teams = [...optimizedTeamScores[g].map(t => t.team),
                    ...Object.keys(odds).filter(t => !pts[t]).sort((a, b) => (odds[a][3] - odds[b][3]))]
                const scoringKey = n => /^1[01]0m Hurdles$/.test(n) ? '100m/110m Hurdles' : n
                const have = new Set(Object.values(optimizedData).filter(rs => rs.length && ofGender(rs[0].event)).map(rs => scoringKey(rs[0].originalCanonical)))
                const missing = SCORING_EVENTS.filter(ev => !have.has(ev))
                return (
                    <div className="ps-standings">
                        {missing.length > 0 && <p className="xs-note ps-missing">No results for: {missing.join(', ')}</p>}
                        <div className="table-container">
                            <table className="performance-table xs-table">
                                <thead>
                                    <tr>
                                        <th className="num">#</th><th>Team</th>
                                        {PLACES.map(p => <th key={p} className="num" title={`Share of ${SIMS} simulated meets, marks varying as at past championships`}>{p}</th>)}
                                        <th className="num" title="Points with each team's predicted entries at their season bests">Pts</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {teams.length === 0 && <tr><td colSpan={7} className="xs-empty">No results.</td></tr>}
                                    {teams.map((team, i) => {
                                        const key = `${team}-${g}`
                                        const o = odds[team]
                                        return (
                                            <Fragment key={team}>
                                                <tr className={`xs-team ${team === targetTeam ? 'xs-follow' : ''} ${expandedTeams[key] ? 'xs-sel' : ''}`}
                                                    onClick={() => setExpandedTeams(prev => ({ ...prev, [key]: !prev[key] }))}>
                                                    <td className="num">{i + 1}</td>
                                                    <td>{team}</td>
                                                    {[0, 1, 2, 3].map(k => <td key={k} className={`num ${k < 3 ? pctCls(o?.[k]) : 'xs-plain'}`}>{o ? pct(o[k]) : ''}</td>)}
                                                    <td className="num">{(pts[team]?.pts ?? 0).toFixed(1)}</td>
                                                </tr>
                                                {expandedTeams[key] && pts[team] && (
                                                    <tr className="ps-breakdown"><td colSpan={7}>
                                                        {pts[team].breakdown.map((item, j) => (
                                                            <div key={j} className="breakdown-row">
                                                                <span className="b-event clickable-event" onClick={(e) => { e.stopPropagation(); scrollToEvent(item.groupTitle) }}>{item.event}</span>
                                                                <span className="b-athlete">{item.athlete}</span>
                                                                <span className="b-pts">+{item.pts.toFixed(1)}</span>
                                                            </div>
                                                        ))}
                                                    </td></tr>
                                                )}
                                            </Fragment>
                                        )
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )
            })()}

            {actual && optimizedTeamScores && !optimizedTeamScores.incomplete && (
                <TrackResultPanel actual={actual} predicted={optimizedTeamScores} odds={placeOdds} gender={g} targetTeam={targetTeam} meet={champCutoff?.meet} />
            )}

            <div className="analyzer-results">
                {Object.keys(optimizedData).length > 0 ? (
                    Object.entries(optimizedData).filter(([, results]) => ofGender(results[0]?.event)).map(([groupTitle, results]) => {
                        const { rows, act } = eventRows(results)
                        return (
                        <div key={groupTitle} id={`event-${groupTitle.replace(/[^a-z0-9]/gi, '-')}`} className="event-section">
                            <h3 className="event-title">
                                {results[0].event}
                                <span className="event-meta">{results[0].derivedType} {results[0].derivedYear}</span>
                            </h3>
                            <div className="table-container">
                            <table className="performance-table">
                                <thead>
                                    <tr>
                                        <th title="Rank by the scoring basis">{act ? 'Pred.' : 'Rank'}</th>
                                        <th>Name</th>
                                        <th>Team</th>
                                        <th>Mark</th>
                                        <th title="Predicted points">Points</th>
                                        {act && <th className="ps-act" title={`Place at ${champCutoff?.meet || 'the championship'}`}>Place</th>}
                                        {act && <th title="Mark at the championship">Result</th>}
                                        {act && <th title="Points scored">Pts</th>}
                                    </tr>
                                </thead>
                                <tbody>
                                    {rows.map(({ pred: res, act: a }, idx) => (
                                        <tr key={idx} className={res ? '' : 'ps-unpredicted'}>
                                            <td>{res ? res.calculatedRank : '–'}</td>
                                            <td className="athlete-name-cell">{res ? res.athlete_name : a.n}
                                                {!res && <span className="xs-chip" title="Scored, but not among the predicted entries">not predicted</span>}</td>
                                            <td>{res ? res.pvcTeam : a.team}</td>
                                            <td className="mark-cell">{res ? res.mark : ''}</td>
                                            <td className="points-cell">
                                                {res && res.optimizedPts > 0 ? `+${res.optimizedPts.toFixed(1)}` : '-'}
                                            </td>
                                            {act && <td className="ps-act" title={a ? '' : 'Did not compete in this event at the championship'}>{a ? a.pl : '–'}</td>}
                                            {act && <td className="mark-cell">{a ? a.m : ''}</td>}
                                            {act && <td className="points-cell">{a?.pts ? `+${a.pts}` : ''}</td>}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            </div>
                        </div>
                    )})
                ) : (
                    <div className="empty-state">
                        <p>No results match your filters.</p>
                    </div>
                )}
            </div>
            </>}
        </div>
    );
}

/** The simulated standings against the championship's real team scores. */
const top3 = (o) => o ? o[0] + o[1] + o[2] : null

function TrackResultPanel({ actual, predicted, odds, gender, targetTeam, meet }) {
    return (
        <div className="xs-result ps-result">
            <h3 className="xs-h" title={meet}>Predicted vs result</h3>
            <div className="ps-result-grid">
                {[gender].map(g => {
                    const a = actual[g]
                    if (!a) return null
                    const pred = (predicted?.[g] || []).map(t => t.team)
                    const pPts = Object.fromEntries((predicted?.[g] || []).map(t => [t.team, t.pts]))
                    const winner = pred.length > 0 && a.teams[0] && pred[0] === a.teams[0].team
                    const podium = a.teams.slice(0, 3).filter(t => pred.slice(0, 3).includes(t.team)).length
                    const exact = a.teams.slice(0, 3).filter((t, i) => pred[i] === t.team).length
                    return (
                        <div key={g} className="xs-panel">
                            <div className="xs-sum-row ps-sum">
                                <span><b>{winner ? '✓' : '✗'}</b> winner {winner ? 'called' : 'missed'}</span>
                                <span><b>{podium} of 3</b> podium teams picked{exact ? `, ${exact} in the exact place` : ''}</span>
                            </div>
                            <div className="table-container">
                                <table className="performance-table xs-table">
                                    <thead>
                                        <tr>
                                            <th className="num">Place</th><th>Team</th><th className="num">Score</th>
                                            <th className="num" title="Place in the simulated standings">Predicted<br />place</th>
                                            <th className="num" title="Simulated score">Pred.<br />score</th>
                                            <th className="num" title="Share of simulated meets in which the team finished top 3">Top 3<br />chance</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {a.teams.map(t => {
                                            const pp = pred.indexOf(t.team) + 1 || null
                                            const off = pp ? pp - t.place : 0
                                            return (
                                                <tr key={t.team} className={t.team === targetTeam ? 'xs-follow' : ''}>
                                                    <td className="num">{t.place}</td>
                                                    <td>{t.team}</td>
                                                    <td className="num">{+t.score.toFixed(2)}</td>
                                                    <td className="num">{pp ?? '–'}{off ? <span className="xs-dim"> ({off > 0 ? '+' : '−'}{Math.abs(off)})</span> : null}</td>
                                                    <td className="num">{pPts[t.team] != null ? pPts[t.team].toFixed(1) : '–'}</td>
                                                    <td className={`num ${pctCls(top3(odds[g][t.team]))}`}>{odds[g][t.team] ? pct(top3(odds[g][t.team])) : '–'}</td>
                                                </tr>
                                            )
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

export default PostseasonSimulator;
