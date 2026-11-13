import { Fragment, useState, useMemo, useEffect } from 'react'
import { parseMark, normalizeEvent, isDistanceEvent, asset, fetchGz } from './utils'
import './App.css'
import Tip from './Tip'

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
    const [expandedTeams, setExpandedTeams] = useState({})
    const [gender, setGender] = useState('Boys')
    const g = gender.toLowerCase()
    const ofGender = (event) => (event || '').startsWith(gender)
    const [targetTeam, setTargetTeam] = useState('George Stevens Academy')
    const [competitionType, setCompetitionType] = useState('PVC');
    const [view, setView] = useState('entries')
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

    // The postseason predictor's predictions (backend/track_champ_predict.py): entry chances,
    // predicted marks and place chances per championship. Past meets: predicted the day before
    // by models fitted on the other seasons.
    const [predFile, setPredFile] = useState(null)
    const [predIndex, setPredIndex] = useState(null)
    useEffect(() => {
        fetch(asset('/data/track_preds/index.json')).then(r => r.json()).then(setPredIndex).catch(() => setPredIndex([]))
    }, [])
    useEffect(() => {
        setPredFile(null)
        if (!(predIndex || []).includes(`${filterYear}_${filterSeason}`)) return
        let live = true
        fetchGz(asset(`/data/track_preds/${filterYear}_${filterSeason}.json.gz`))
            .then(d => { if (live) setPredFile(d) })
            .catch(() => {})
        return () => { live = false }
    }, [filterYear, filterSeason, predIndex])

    const baseSchools = useMemo(() => competitionType === 'Everyone' ? null
        : competitionType === 'PVC' ? getPVCSchools(filterYear, filterSeason) : getStateSchools(filterYear, filterSeason),
        [competitionType, filterYear, filterSeason])

    // This competition's championship per gender: the PVC (indoor: EMITL) small-school
    // meet, or the state meet of the team being optimized (else the class most listed schools ran in).
    const champIds = useMemo(() => {
        const src = champFile || predFile
        if (!src || !baseSchools) return ''
        const ids = []
        for (const g of ['Boys', 'Girls']) {
            const cs = src.champs.filter(c => c.gender === g && (competitionType === 'PVC'
                ? c.kind === 'conf' && /small|all/i.test(c.division || '')
                : c.kind === 'state'))
            const count = c => c.teams.filter(t => schoolOf(t.team, baseSchools)).length
            const ranIn = c => c.teams.some(t => schoolOf(t.team, baseSchools) === targetTeam)
            cs.sort((a, b) => (ranIn(b) - ranIn(a)) || (count(b) - count(a)))
            if (cs.length) ids.push(cs[0].id)
        }
        return ids.join(',')
    }, [champFile, predFile, baseSchools, competitionType, targetTeam])
    // (keyed by id, so picking another team in the same class recomputes nothing)
    const champs = useMemo(() => {
        if (!champIds || !champFile) return null
        const ids = champIds.split(',')
        return Object.fromEntries(champFile.champs.filter(c => ids.includes(c.id)).map(c => [c.gender, c]))
    }, [champFile, champIds])
    // a prediction is on file for this season but not loaded yet: show neither it nor the fallback
    const predPending = (predIndex || []).includes(`${filterYear}_${filterSeason}`) && !predFile
    const preds = useMemo(() => {
        if (!champIds || !predFile) return null
        const ids = champIds.split(',')
        return Object.fromEntries(predFile.champs.filter(c => ids.includes(c.id)).map(c => [c.gender, c]))
    }, [predFile, champIds])

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

    // seasons with results, and a season about to start once it is predicted
    const yearOptions = useMemo(() => [...new Set([...years, ...(predIndex || [])
        .filter(k => k.endsWith(`_${filterSeason}`)).map(k => k.split('_')[0])])].sort((a, b) => b - a),
        [years, predIndex, filterSeason])
    // the latest of those when the chosen one has neither
    useEffect(() => {
        if (predIndex && yearOptions.length && !yearOptions.includes(filterYear)) setFilterYear(yearOptions[0])
    }, [yearOptions, filterYear, predIndex])

    // Places scored: the championship's own table; else PVC six, states eight.
    const SCORING_RULES = useMemo(() => Object.values(champs || {})[0]?.table || Object.values(preds || {})[0]?.table
        || (competitionType === 'States' ? [10, 8, 6, 5, 4, 3, 2, 1] : [10, 8, 6, 4, 2, 1]), [champs, preds, competitionType]);

    // Treat Indoor/Outdoor differently: 4 event limit for Outdoor, 3 for Indoor.
    const EVENT_LIMIT = (filterSeason && filterSeason.toLowerCase().includes('indoor')) ? 3 : 4;

    const scrollToEvent = (groupTitle) => {
        const targetId = `event-${groupTitle.replace(/[^a-z0-9]/gi, '-')}`;
        const element = document.getElementById(targetId);
        if (element) {
            const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            element.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'start' });
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

        if (filterSeason === 'Outdoor') return outdoor;
        return indoor;
    }, [filterSeason]);

    // The predictor's meet for the selected gender, in the page's team and event names.
    const predicted = useMemo(() => {
        const p = preds?.[gender]
        if (!p) return null
        const teamOf = t => (activeSchools && schoolOf(t, activeSchools)) || t
        const byTeam = {}
        const placePts = {}   // points for each row's predicted place, summed by team
        const base = k => { const b = k.replace(/^(Boys|Girls) /, ''); return /^1[01]0m Hurdles$/.test(b) ? '100m/110m Hurdles' : b }
        const order = k => { const i = SCORING_EVENTS.indexOf(base(k)); return i < 0 ? 99 : i }
        const events = Object.entries(p.events).map(([ev, rows]) => {
            const key = normalizeEvent(`${gender} ${ev}`, filterSeason)
            // rows come ordered by expected points: that order is the predicted place
            const out = rows.map((r, i) => ({ ...r, team: teamOf(r.t), pp: SCORING_RULES[i] || 0 }))
            out.forEach(r => {
                if (r.pp) placePts[r.team] = (placePts[r.team] || 0) + r.pp
                if (r.pp || r.x >= 0.5) (byTeam[r.team] = byTeam[r.team] || []).push({ key, ...r })
            })
            return { key, rows: out }
        }).sort((a, b) => order(a.key) - order(b.key))
        Object.values(byTeam).forEach(rs => rs.sort((a, b) => b.pp - a.pp || b.x - a.x))
        // team totals stay expected points (ranking teams by predicted-place totals did worse: 2026-11-12)
        const teams = p.teams.map(t => ({ team: teamOf(t.team), pts: Math.round(t.pts), op: placePts[teamOf(t.team)] || 0,
            odds: [...t.p, Math.max(0, 1 - t.p[0] - t.p[1] - t.p[2])] }))
        return { teams, events, byTeam, cutoff: p.cutoff, basis: p.basis || 'predicted' }
    }, [preds, gender, activeSchools, filterSeason, SCORING_EVENTS, SCORING_RULES])
    const pageTeam = t => (activeSchools && schoolOf(t, activeSchools)) || t
    const eventOrder = key => {
        const b = key.replace(/^(Boys|Girls) /, '')
        const i = SCORING_EVENTS.indexOf(/^1[01]0m Hurdles$/.test(b) ? '100m/110m Hurdles' : b)
        return i < 0 ? 99 : i
    }

    const groupedData = useMemo(() => {
        const groups = {};

        // First group all performances by groupKey -> athleteKey
        const rawGrouped = {};

        const sourceData = filteredData;
        const activeSeason = filterSeason;

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
    }, [filteredData, isBetter, SCORING_EVENTS, filterSeason]);

    const optimizedData = useMemo(() => {
        if (filterYear === 'All' || filterSeason === 'All' || Object.keys(groupedData).length === 0) {
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
        if (filterYear === 'All' || filterSeason === 'All') return { incomplete: true };

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
        filteredData.forEach(p => {
            const v = logMark(p.mark, p.event)
            if (v == null) return
            const k = `${normalizeEvent(p.event, filterSeason)}|${p.isRelay ? p.pvcTeam : `${p.athlete_id}|${p.pvcTeam}`}`;
            (out[k] = out[k] || []).push(v)
        })
        return out
    }, [filteredData, filterSeason])

    // Each team's chance of finishing 1st, 2nd, 3rd and 4th or lower: the predicted entries'
    // meet run SIMS times, each mark drawn around the mean of the athlete's two best marks
    // with the event family's championship-day spread (CHAMP_SPREAD).
    const placeOdds = useMemo(() => {
        const out = { boys: {}, girls: {} }
        if (loadingState.isLoading || predicted) return out   // once, when every team's results are in
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
    }, [optimizedData, seasonMarks, SCORING_RULES, loadingState.isLoading, g, predicted])

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
                            <span className="spinner ps-spinner" style={{
                                width: '14px',
                                height: '14px',
                                border: '2px solid rgba(128, 0, 0, 0.2)',
                                borderTop: '2px solid #800000',
                                borderRadius: '50%',
                                display: 'inline-block'
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
                    <Tip styled className={view === 'entries' ? 'active' : ''} onClick={() => setView('entries')}
                        tip={`Each athlete's chance of entering each event, relay legs included (${EVENT_LIMIT} events at most)`}>Entries</Tip>
                    <Tip styled className={view === 'outcomes' ? 'active' : ''} onClick={() => setView('outcomes')}
                        tip="Team and event results simulated from the entries: the actual entries once a meet is run, else the predicted ones">Outcomes</Tip>
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
                            {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
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
                        <label><Tip tip="State meet: The state meet of the team being optimized">Competition</Tip></label>
                        <select value={competitionType} onChange={e => setCompetitionType(e.target.value)}>
                            <option value="PVC">PVC Small Schools</option>
                            <option value="States">State meet</option>
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
                    <div className="record-count">{`${filteredData.length} Results`}</div>
                </div>
            </div>

            {view === 'entries' && (preds?.[gender]
                ? <EntryPanel key={preds[gender].id} champ={preds[gender]} gender={gender} season={filterSeason} teamOf={pageTeam}
                    targetTeam={targetTeam} order={eventOrder} meet={champCutoff?.meet} />
                : !predPending && <div className="empty-state"><p>No entry prediction for this meet.</p></div>)}

            {view === 'outcomes' && <>
            {predicted && (
                <div className="ps-standings">
                    <div className="table-container">
                        <table className="performance-table xs-table">
                            <thead>
                                <tr>
                                    <th className="num">#</th><th>Team</th>
                                    {PLACES.map(p => <th key={p} className="num"><Tip tip={predicted.basis === 'entered'
                                        ? 'Share of simulated meets run with the actual entries, marks varying as at past championships'
                                        : "Share of simulated meets: entries drawn from each athlete's entry chance, marks varying as at past championships"}>{p}</Tip></th>)}
                                    <th className="num"><Tip tip="Expected points">Pts</Tip></th>
                                </tr>
                            </thead>
                            <tbody>
                                {predicted.teams.map((t, i) => {
                                    const key = `${t.team}-${g}`
                                    const mine = predicted.byTeam[t.team] || []
                                    return (
                                        <Fragment key={i}>
                                            <tr className={`xs-team ${t.team === targetTeam ? 'xs-follow' : ''} ${expandedTeams[key] ? 'xs-sel' : ''}`}
                                                onClick={() => setExpandedTeams(prev => ({ ...prev, [key]: !prev[key] }))}>
                                                <td className="num">{i + 1}</td>
                                                <td><button type="button" className="text-btn" aria-expanded={!!expandedTeams[key]}
                                                    onClick={(e) => { e.stopPropagation(); setExpandedTeams(prev => ({ ...prev, [key]: !prev[key] })) }}>{t.team}</button></td>
                                                {t.odds.map((o, k) => <td key={k} className={`num ${k < 3 ? pctCls(o) : 'xs-plain'}`}>{pct(o)}</td>)}
                                                <td className="num"><Tip tip={`${t.op} from the predicted places`}>{t.pts}</Tip></td>
                                            </tr>
                                            {expandedTeams[key] && mine.length > 0 && (
                                                <tr className="ps-breakdown"><td colSpan={7}>
                                                    {mine.map((r, j) => (
                                                        <div key={j} className="breakdown-row">
                                                            <button type="button" className="text-btn b-event clickable-event" onClick={(e) => { e.stopPropagation(); scrollToEvent(r.key) }}>{r.key}</button>
                                                            <span className="b-athlete">{r.n || 'Relay'}</span>
                                                            <Tip className="b-pts" tip={`Expected ${r.x.toFixed(1)}`}>{r.pp ? `+${r.pp}` : '–'}</Tip>
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
            )}
            {!predicted && !predPending && optimizedTeamScores && !optimizedTeamScores.incomplete && (() => {
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
                                        {PLACES.map(p => <th key={p} className="num"><Tip tip={`Share of ${SIMS} simulated meets, marks varying as at past championships`}>{p}</Tip></th>)}
                                        <th className="num"><Tip tip="Points with each team's predicted entries at their season bests">Pts</Tip></th>
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
                                                    <td><button type="button" className="text-btn" aria-expanded={!!expandedTeams[key]}
                                                        onClick={(e) => { e.stopPropagation(); setExpandedTeams(prev => ({ ...prev, [key]: !prev[key] })) }}>{team}</button></td>
                                                    {[0, 1, 2, 3].map(k => <td key={k} className={`num ${k < 3 ? pctCls(o?.[k]) : 'xs-plain'}`}>{o ? pct(o[k]) : ''}</td>)}
                                                    <td className="num">{(pts[team]?.pts ?? 0).toFixed(1)}</td>
                                                </tr>
                                                {expandedTeams[key] && pts[team] && (
                                                    <tr className="ps-breakdown"><td colSpan={7}>
                                                        {pts[team].breakdown.map((item, j) => (
                                                            <div key={j} className="breakdown-row">
                                                                <button type="button" className="text-btn b-event clickable-event" onClick={(e) => { e.stopPropagation(); scrollToEvent(item.groupTitle) }}>{item.event}</button>
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

            {actual && predicted && (
                <TrackResultPanel actual={actual} predicted={{ [g]: predicted.teams }} gender={g} targetTeam={targetTeam} meet={champCutoff?.meet}
                    odds={{ [g]: Object.fromEntries(predicted.teams.map(t => [t.team, t.odds])) }} />
            )}
            {actual && !predicted && !predPending && optimizedTeamScores && !optimizedTeamScores.incomplete && (
                <TrackResultPanel actual={actual} predicted={optimizedTeamScores} odds={placeOdds} gender={g} targetTeam={targetTeam} meet={champCutoff?.meet} />
            )}

            {predicted && (
                <div className="analyzer-results">
                    {predicted.events.map(({ key, rows }) => {
                        const act = actual?.[g]?.events[key]
                        const shown = rows.filter(r => r.x >= 0.1 || r.p >= 0.5 || (r.pl && r.pl <= SCORING_RULES.length))
                        const placed = new Set(shown.map(r => r.pl).filter(Boolean))
                        const missed = (act || []).filter(a => a.pts && !placed.has(a.pl))
                        const byPl = new Map((act || []).map(a => [a.pl, a]))
                        return (
                            <div key={key} id={`event-${key.replace(/[^a-z0-9]/gi, '-')}`} className="event-section">
                                <h3 className="event-title">{key}</h3>
                                <div className="table-container">
                                    <table className="performance-table">
                                        <thead>
                                            <tr>
                                                <th><Tip tip="Predicted place (by expected points)">Pred.</Tip></th>
                                                <th>Name</th>
                                                <th>Team</th>
                                                <th><Tip tip="Predicted mark">Mark</Tip></th>
                                                {predicted.basis !== 'entered' && <th className="num"><Tip tip="Chance of entering this event">Entry</Tip></th>}
                                                <th><Tip tip="Points for the predicted place">Points</Tip></th>
                                                {act && <th className="ps-act"><Tip tip={`Place at ${champCutoff?.meet || 'the championship'}`}>Place</Tip></th>}
                                                {act && <th><Tip tip="Mark at the championship">Result</Tip></th>}
                                                {act && <th><Tip tip="Points scored">Pts</Tip></th>}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {shown.map((r, i) => {
                                                const a = r.pl ? byPl.get(r.pl) : null
                                                return (
                                                    <tr key={i} className={r.team === targetTeam ? 'xs-follow' : ''}>
                                                        <td>{i + 1}</td>
                                                        <td className="athlete-name-cell">{r.n || 'Relay'}</td>
                                                        <td>{r.team}</td>
                                                        <td className="mark-cell">{r.m}</td>
                                                        {predicted.basis !== 'entered' && <td className={`num ${pctCls(r.p)}`}>{pct(r.p)}</td>}
                                                        <td className="points-cell"><Tip tip={`Expected ${r.x.toFixed(1)}`}>{r.pp ? `+${r.pp}` : '-'}</Tip></td>
                                                        {act && <td className="ps-act"><Tip tip={a ? '' : 'Did not compete in this event at the championship'}>{a ? a.pl : '–'}</Tip></td>}
                                                        {act && <td className="mark-cell">{a ? a.m : ''}</td>}
                                                        {act && <td className="points-cell">{a?.pts ? `+${a.pts}` : ''}</td>}
                                                    </tr>
                                                )
                                            })}
                                            {missed.map((a, i) => (
                                                <tr key={`m${i}`} className="ps-unpredicted">
                                                    <td>–</td>
                                                    <td className="athlete-name-cell">{a.n}<Tip glue className="xs-chip" tip="Scored, but the model had no mark for them in this event">not predicted</Tip></td>
                                                    <td>{a.team}</td>
                                                    <td></td>{predicted.basis !== 'entered' && <td></td>}<td></td>
                                                    <td className="ps-act">{a.pl}</td>
                                                    <td className="mark-cell">{a.m}</td>
                                                    <td className="points-cell">{a.pts ? `+${a.pts}` : ''}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}

            {!predicted && !predPending && <div className="analyzer-results">
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
                                        <th><Tip tip="Rank by the scoring basis">{act ? 'Pred.' : 'Rank'}</Tip></th>
                                        <th>Name</th>
                                        <th>Team</th>
                                        <th>Mark</th>
                                        <th><Tip tip="Predicted points">Points</Tip></th>
                                        {act && <th className="ps-act"><Tip tip={`Place at ${champCutoff?.meet || 'the championship'}`}>Place</Tip></th>}
                                        {act && <th><Tip tip="Mark at the championship">Result</Tip></th>}
                                        {act && <th><Tip tip="Points scored">Pts</Tip></th>}
                                    </tr>
                                </thead>
                                <tbody>
                                    {rows.map(({ pred: res, act: a }, idx) => (
                                        <tr key={idx} className={res ? '' : 'ps-unpredicted'}>
                                            <td>{res ? res.calculatedRank : '–'}</td>
                                            <td className="athlete-name-cell">{res ? res.athlete_name : a.n}
                                                {!res && <Tip glue className="xs-chip" tip="Scored, but not among the predicted entries">not predicted</Tip>}</td>
                                            <td>{res ? res.pvcTeam : a.team}</td>
                                            <td className="mark-cell">{res ? res.mark : ''}</td>
                                            <td className="points-cell">
                                                {res && res.optimizedPts > 0 ? `+${res.optimizedPts.toFixed(1)}` : '-'}
                                            </td>
                                            {act && <td className="ps-act"><Tip tip={a ? '' : 'Did not compete in this event at the championship'}>{a ? a.pl : '–'}</Tip></td>}
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
            </div>}
            </>}
        </div>
    );
}

/** Entry chances for one team at one championship: every athlete and event
 * (relay legs included, after the event limit), or one athlete's events;
 * for a meet already run, who entered. */
function EntryPanel({ champ, gender, season, teamOf, targetTeam, order, meet }) {
    const ran = champ.basis === 'entered'
    const key = ev => normalizeEvent(`${gender} ${ev}`, season)
    const short = ev => key(ev).replace(/^(Boys|Girls) /, '')
    // (small: one meet's rows, so recomputed each render)
    const rank = new Map(champ.teams.map((t, i) => [teamOf(t.team), i]))
    const teams = [...new Set(Object.values(champ.entries || {}).flatMap(rs => rs.map(r => teamOf(r.t))))]
        .sort((a, b) => (rank.get(a) ?? 999) - (rank.get(b) ?? 999) || a.localeCompare(b))
    const [pick, setPick] = useState(null)
    const team = pick && teams.includes(pick) ? pick : teams.includes(targetTeam) ? targetTeam : teams[0]
    const [ath, setAth] = useState('')
    const grid = (() => {
        const athletes = {}, relay = {}
        const cell = (n, ev, r) => { ((athletes[n] = athletes[n] || {}))[ev] = r }
        Object.entries(champ.entries || {}).forEach(([ev, rs]) => rs.forEach(r => {
            if (teamOf(r.t) !== team) return
            if (/Relay/.test(ev)) relay[ev] = r
            else if (r.n) cell(r.n, ev, r)
        }))
        Object.entries(champ.legs || {}).forEach(([ev, rs]) => rs.forEach(r => {
            if (teamOf(r.t) === team && r.n) cell(r.n, ev, r)
        }))
        const events = [...new Set([...Object.keys(relay), ...Object.values(athletes).flatMap(Object.keys)])]
            .sort((a, b) => order(key(a)) - order(key(b)))
        const sum = evs => Object.values(evs).reduce((t, r) => t + r.p, 0)
        const names = Object.keys(athletes).sort((a, b) => sum(athletes[b]) - sum(athletes[a]))
        return { athletes, relay, events, names }
    })()
    const who = grid.names.includes(ath) ? ath : ''
    const cells = Object.values(grid.athletes).flatMap(Object.values)
    const entered = cells.filter(r => r.e)
    const mark = r => ran && r ? (r.e ? ' ✓' : '') : ''
    const tip = r => !r ? (ran ? 'Did not enter' : '') : ran ? (r.e ? 'Entered' : 'Did not enter') : ''
    return (
        <div className="ps-entries">
            <div className="filter-bar analyzer-filters">
                <div className="filter-group">
                    <label>Team</label>
                    <select value={team || ''} onChange={e => { setPick(e.target.value); setAth('') }}>
                        {teams.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                </div>
                <div className="filter-group">
                    <label>Athlete</label>
                    <select value={who} onChange={e => setAth(e.target.value)}>
                        <option value="">All athletes</option>
                        {grid.names.map(n => <option key={n} value={n}>{n}</option>)}
                    </select>
                </div>
                {ran && <div className="record-count">
                    <Tip tip="Sum of the entry chances">{cells.reduce((t, r) => t + r.p, 0).toFixed(1)} expected</Tip>
                    {' · '}<Tip tip={`Entries at ${meet || 'the championship'}, relay legs included`}>{entered.length} entered</Tip>
                    {' · '}<Tip tip="Entries that had a chance of 50% or more">{entered.filter(r => r.p >= 0.5).length} called</Tip>
                </div>}
            </div>
            {who ? (
                <div className="table-container">
                    <table className="performance-table xs-table ps-entry-one">
                        <thead><tr><th>Event</th><th className="num"><Tip tip="Chance of entering (relays: of running a leg)">Chance</Tip></th>
                            {ran && <th className="ps-act"><Tip tip={`At ${meet || 'the championship'}`}>Entered</Tip></th>}</tr></thead>
                        <tbody>
                            {grid.events.filter(ev => grid.athletes[who][ev]).map(ev => {
                                const r = grid.athletes[who][ev]
                                return (
                                    <tr key={ev}>
                                        <td>{short(ev)}</td>
                                        <td className={`num ${pctCls(r.p)}`}>{pct(r.p)}</td>
                                        {ran && <td className="ps-act">{r.e ? '✓' : '–'}</td>}
                                    </tr>
                                )
                            })}
                        </tbody>
                    </table>
                </div>
            ) : (
                <div className="table-container">
                    <table className="performance-table xs-table ps-entry-grid">
                        <thead><tr><th>Athlete</th>{grid.events.map(ev => <th key={ev} className="num">{short(ev)}</th>)}</tr></thead>
                        <tbody>
                            {Object.keys(grid.relay).length > 0 && (
                                <tr className="ps-relay-row">
                                    <td><Tip tip="The team's chance of entering the relay">Relay team</Tip></td>
                                    {grid.events.map(ev => {
                                        const r = grid.relay[ev]
                                        return <td key={ev} className={`num ${r ? pctCls(r.p) : ''}`}><Tip tip={tip(r)}>{r ? pct(r.p) : ''}{mark(r)}</Tip></td>
                                    })}
                                </tr>
                            )}
                            {grid.names.map(n => (
                                <tr key={n} className="ps-click" onClick={() => setAth(n)}>
                                    <td className="athlete-name-cell"><button type="button" className="text-btn"
                                        onClick={(e) => { e.stopPropagation(); setAth(n) }}>{n}</button></td>
                                    {grid.events.map(ev => {
                                        const r = grid.athletes[n][ev]
                                        return <td key={ev} className={`num ${r ? pctCls(r.p) : ''} ${r?.e ? 'ps-in' : ''}`}><Tip tip={tip(r)}>
                                            {r && (r.p >= 0.005 || !r.e) ? pct(r.p) : ''}{mark(r)}</Tip></td>
                                    })}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    )
}

/** The simulated standings against the championship's real team scores. */
const top3 = (o) => o ? o[0] + o[1] + o[2] : null

function TrackResultPanel({ actual, predicted, odds, gender, targetTeam, meet }) {
    return (
        <div className="xs-result ps-result">
            <h3 className="xs-h"><Tip tip={meet}>Predicted vs result</Tip></h3>
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
                                            <th className="num"><Tip tip="Place in the simulated standings">Predicted<br />place</Tip></th>
                                            <th className="num"><Tip tip="Predicted score">Pred.<br />score</Tip></th>
                                            <th className="num"><Tip tip="Share of simulated meets in which the team finished top 3">Top 3<br />chance</Tip></th>
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
                                                    <td className="num">{pPts[t.team] != null ? +pPts[t.team].toFixed(1) : '–'}</td>
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
