import { useState, useMemo, useEffect } from 'react'
import { parseMark, normalizeEvent, isDistanceEvent } from './utils'
import './App.css'

function PostseasonSimulator({ performances, isBetter, manifest, loadTeamData }) {
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
    const [filterSeason, setFilterSeason] = useState(defaultSeason)
    const [filterEvent, setFilterEvent] = useState('All')
    const [showSimulation, setShowSimulation] = useState(false)
    const [expandedTeams, setExpandedTeams] = useState({}) 
    const [robustSimResults, setRobustSimResults] = useState(null)
    const [isRobustLoading, setIsRobustLoading] = useState(false)
    const [targetTeam, setTargetTeam] = useState('George Stevens Academy')
    const [simProgress, setSimProgress] = useState(0);
    const [simIterations, setSimIterations] = useState(50);
    const [strategicLog, setStrategicLog] = useState([]);
    const [competitionType, setCompetitionType] = useState('PVC');
    const [isDashboardCollapsed, setIsDashboardCollapsed] = useState(false);

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

    const loadingState = useMemo(() => {
        if (!manifest || !manifest.teams || filterYear === 'All' || filterSeason === 'All') {
            return { isLoading: false, expectedCount: 0, loadedCount: 0, loadingTeams: [], percent: 100 };
        }
        
        const seasonKey = `${filterYear}_${filterSeason}`.replace(' ', '_');
        const activeSchools = competitionType === 'PVC' ? getPVCSchools(filterYear, filterSeason) : getStateSchools(filterYear, filterSeason);
        
        // Find which teams in manifest belong to the expected activeSchools AND participate in this season
        const expectedTeams = (manifest.teams || []).filter(t => {
            const participates = t.seasons && t.seasons.includes(seasonKey);
            if (!participates) return false;
            
            // Match against activeSchools values
            return Object.values(activeSchools).some(schoolName => 
                t.name.toLowerCase() === schoolName.toLowerCase()
            );
        });
        
        // Find which expected team slugs are loaded
        const loadedSlugs = new Set();
        (performances || []).forEach(p => {
            const teamObj = manifest.teams.find(t => t.name === p.team);
            if (teamObj) {
                loadedSlugs.add(teamObj.slug);
            }
        });
        
        const loadingTeams = expectedTeams.filter(t => !loadedSlugs.has(t.slug));
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
    }, [manifest, performances, filterYear, filterSeason, competitionType]);

    useEffect(() => {
        if (!manifest || !manifest.teams || !loadTeamData) return;

        if (filterYear !== 'All' && filterSeason !== 'All') {
            const seasonKey = `${filterYear}_${filterSeason}`.replace(' ', '_');
            manifest.teams.forEach(t => {
                if (t.seasons && t.seasons.includes(seasonKey)) {
                    loadTeamData(t.slug);
                }
            });
        } else if (filterYear !== 'All') {
            manifest.teams.forEach(t => {
                if (t.seasons && t.seasons.some(s => s.startsWith(filterYear))) {
                    loadTeamData(t.slug);
                }
            });
        } else if (filterSeason !== 'All') {
            manifest.teams.forEach(t => {
                if (t.seasons && t.seasons.some(s => s.endsWith(filterSeason.replace(' ', '_')))) {
                    loadTeamData(t.slug);
                }
            });
        }
    }, [filterYear, filterSeason, manifest, loadTeamData]);

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

        // 3. Get the specific team list for this context
        const activeSchools = competitionType === 'PVC' ? getPVCSchools(filterYear, filterSeason) : getStateSchools(filterYear, filterSeason);

        const processed = performances.map(p => {
            let year = p.year;
            let type = p.season;
            if (p.season && p.season.match(/^\d{4}/)) {
                const m = p.season.match(/^(\d{4})\s+(.*)$/);
                year = m[1];
                type = m[2];
            }

            // Detect PVC Team based on ACTIVE list
            let pvcTeam = null;
            for (const [key, val] of Object.entries(activeSchools)) {
                // Check against key (short) and val (long)
                const teamLower = p.team.toLowerCase();
                const filterKey = key.toLowerCase();

                // Specific fix for "Central" to avoid matching "Maine Central Institute"
                if (key === "Central" && teamLower.includes("maine")) {
                    continue;
                }

                if (teamLower.includes(filterKey) || teamLower === val.toLowerCase()) {
                    pvcTeam = val;
                    break;
                }
            }

            // Special check for PCHS acronym
            if (!pvcTeam && activeSchools["PCHS"] && (p.team === "PCHS" || p.team.includes("Piscataquis"))) {
                pvcTeam = activeSchools["PCHS"];
            }

            return {
                ...p,
                derivedYear: year,
                derivedType: type,
                pvcTeam: pvcTeam,
                isRelay: p.event.toLowerCase().includes('relay') || p.event.toLowerCase().includes('4x')
            };
        }).filter(p => p.pvcTeam); // Only include valid schools for THIS season

        const matches = (p, filters) => {
            const { year, season, event } = filters;
            return (year === 'All' || p.derivedYear === year) &&
                (season === 'All' || p.derivedType === season) &&
                (event === 'All' || p.event === event);
        };

        const avYears = Array.from(new Set(processed.map(p => p.derivedYear))).sort((a, b) => b - a);
        const avSeasons = Array.from(new Set(processed.map(p => p.derivedType))).sort();
        const avEvents = Array.from(new Set(processed.map(p => p.event))).sort();

        const filtered = processed.filter(p => matches(p, { year: filterYear, season: filterSeason, event: filterEvent }));

        return {
            filteredData: filtered,
            years: avYears,
            seasons: avSeasons,
            events: avEvents
        };
    }, [performances, filterYear, filterSeason, filterEvent, competitionType]);

    const teamPools = useMemo(() => {
        const pools = {};
        if (!performances) return pools; // Use performances or filteredData? filteredData is derived in render? No, let's verify. filteredData is likely derived.
        // Wait, filteredData is a prop or state? Check lines 1-10. Not in view.
        // Assuming filteredData is available in scope.

        // Actually, filteredData is usually derived inside the component body.
        // Let's use filteredData if it is available in scope.
        // Based on previous reads, filteredData seems to be derived.
        // I will use `filteredData` in the dependency array. 

        // Re-implementing logic:
        (filteredData || []).forEach(p => {
            const markUpper = (p.mark || "").toUpperCase();
            if (['DQ', 'DNF', 'NH'].includes(markUpper)) return;

            const team = p.pvcTeam;
            if (!pools[team]) pools[team] = {};

            const isRelay = p.isRelay;
            const athleteKey = isRelay ? `relay_${p.event}` : p.athlete_id;

            if (!pools[team][athleteKey]) pools[team][athleteKey] = [];

            const existing = pools[team][athleteKey].find(x => x.event === p.event);
            if (!existing || isBetter(p.mark, existing.mark, p.event)) {
                if (existing) {
                    pools[team][athleteKey] = pools[team][athleteKey].filter(x => x.event !== p.event);
                }
                pools[team][athleteKey].push(p);
            }
        });
        return pools;
    }, [filteredData, isBetter]);

    // Simulation Helpers and Core Logic
    const SCORING_RULES = [10, 8, 6, 4, 2, 1];
    
    // Treat Indoor/Outdoor differently: 4 event limit for Outdoor, 3 for Indoor.
    const EVENT_LIMIT = (filterSeason && filterSeason.toLowerCase().includes('indoor')) ? 3 : 4;

    const getMembers = (p) => {
        const name = p.athlete_name || "";
        if (p.isRelay) {
            // Relays often list members separated by commas or slashes
            return name.split(/[,/]/).map(n => n.trim()).filter(n => n && !n.toLowerCase().includes('relay'));
        }
        return [name];
    };

    const simulateSingleMeet = (allEntries, divideRelays = false) => {
        const eventGroups = {};
        allEntries.forEach(e => {
            if (!eventGroups[e.event]) eventGroups[e.event] = [];
            eventGroups[e.event].push(e);
        });

        const scores = {};
        Object.entries(eventGroups).forEach(([event, entries]) => {
            entries.sort((a, b) => isBetter(a.mark, b.mark, a.event) ? -1 : isBetter(b.mark, a.mark, a.event) ? 1 : 0);

            let scoringIndex = 0;
            const isRelayEvent = event.toLowerCase().includes('relay') || event.toLowerCase().includes('4x');

            for (let i = 0; i < entries.length; i++) {
                if (scoringIndex >= SCORING_RULES.length) break;

                const entry = entries[i];
                const team = entry.pvcTeam;

                // Any athlete can score as long as there is room on the podium (top 6)
                // Removed per-team entry limits as requested.
                let pts = SCORING_RULES[scoringIndex];
                if (divideRelays && isRelayEvent) pts /= 4;
                
                scores[team] = (scores[team] || 0) + pts;
                scoringIndex++;
            }
        });
        return scores;
    };



    const getGreedyEntries = (pool) => {
        const entries = [];
        const memberCounts = {};
        
        // Basic heuristic for getGreedyEntries without full opponent baseline:
        // Rank by mark quality relative to typical standards, but since we just want a rough greedy sort,
        // we'll sort relays lower if they share members. Actually, we shouldn't rely on isBetter for different events.
        // Let's just group by event, rank within event, and assign points.
        const groups = {};
        Object.values(pool).flat().forEach(e => {
            if (!groups[e.event]) groups[e.event] = [];
            groups[e.event].push(e);
        });
        
        const scored = [];
        Object.values(groups).forEach(evEntries => {
            evEntries.sort((a, b) => isBetter(a.mark, b.mark, a.event) ? -1 : isBetter(b.mark, a.mark, a.event) ? 1 : 0);
            evEntries.forEach((e, idx) => {
                let pts = idx < SCORING_RULES.length ? SCORING_RULES[idx] : 0.1; // 0.1 for participation
                const isRelayEvent = e.event.toLowerCase().includes('relay') || e.event.toLowerCase().includes('4x');
                if (isRelayEvent) pts /= 4;
                scored.push({ e, pts });
            });
        });
        
        scored.sort((a, b) => b.pts - a.pts);

        scored.forEach(({ e }) => {
            const members = getMembers(e);
            if (members.every(m => (memberCounts[m] || 0) < EVENT_LIMIT)) {
                entries.push(e);
                members.forEach(m => memberCounts[m] = (memberCounts[m] || 0) + 1);
            }
        });
        return entries;
    };

    // Core Optimization Logic (Nash Equilibrium Hill Climbing)
    const optimizeTeamStrategy = async ({
        teamName,
        gender,
        progressStart,
        progressRange,
        fixedOpponentLineups = null
    }) => {
        const isGender = (p) => {
            const g = p.event.toLowerCase().includes('girls');
            return gender === 'girls' ? g : !g;
        };

        const genderTeamPools = {};
        Object.entries(teamPools).forEach(([team, pool]) => {
            const newPool = {};
            Object.entries(pool).forEach(([key, athPerfs]) => {
                const valid = athPerfs.filter(isGender);
                if (valid.length > 0) newPool[key] = valid;
            });
            if (Object.keys(newPool).length > 0) genderTeamPools[team] = newPool;
        });

        const genderTargetPool = genderTeamPools[teamName] || {};
        const genderOpponentPools = { ...genderTeamPools };
        delete genderOpponentPools[teamName];

        const genderPossibleEntries = Object.values(genderTargetPool).flat();
        if (genderPossibleEntries.length === 0) return { avg: 0, entries: [], stats: [], scenarios: [] };

        // Generate Scenarios
        let scenarios = [];
        if (fixedOpponentLineups) {
            const sc = {};
            Object.entries(fixedOpponentLineups).forEach(([t, entries]) => {
                if (t !== teamName) {
                    sc[t] = entries.filter(isGender);
                }
            });
            scenarios = [sc];
        } else {
            for (let i = 0; i < simIterations; i++) {
                if (i % 10 === 0) {
                    setSimProgress(progressStart + Math.floor((i / simIterations) * (progressRange * 0.2)));
                    await new Promise(r => setTimeout(r, 0));
                }
                const sc = {};
                Object.entries(genderOpponentPools).forEach(([team, pool]) => {
                    const entries = [];
                    Object.values(pool).forEach(athPerfs => {
                        const sorted = [...athPerfs].sort((a, b) => isBetter(a.mark, b.mark, a.event) ? -1 : 1);
                        const topX = sorted.slice(0, 5);
                        for (let j = 0; j < EVENT_LIMIT && topX.length > 0; j++) {
                            const idx = Math.floor(Math.random() * topX.length);
                            entries.push(topX.splice(idx, 1)[0]);
                        }
                    });
                    sc[team] = entries;
                });
                scenarios.push(sc);
            }
        }

        const evaluateLineup = (lineup, divideRelays = false) => {
            const res = [];
            scenarios.forEach(oppEntries => {
                const fullMeet = [...lineup];
                Object.values(oppEntries).forEach(opps => fullMeet.push(...opps));
                res.push(simulateSingleMeet(fullMeet, divideRelays));
            });
            // Return average score for target team
            return res.reduce((s, r) => s + (r[teamName] || 0), 0) / scenarios.length;
        };

        // --- Robust Nash Equilibrium Hill Climbing (Cross-Relay Constraints) ---

        // 1. Initial Ranking (Greedy Score Estimate)
        const getBaselinePerformance = () => {
            const sc = {};
            Object.entries(genderTeamPools).forEach(([t, pool]) => {
                if (t === teamName) return;
                const poolEntries = Object.values(pool).flat();
                const groups = {};
                poolEntries.forEach(e => {
                    if (!groups[e.event]) groups[e.event] = [];
                    groups[e.event].push(e);
                });
                const topEntries = [];
                Object.entries(groups).forEach(([event, entries]) => {
                    const isRelayEvent = event.toLowerCase().includes('relay') || event.toLowerCase().includes('4x');
                    const sorted = [...entries].sort((a, b) => isBetter(a.mark, b.mark, a.event) ? -1 : 1);
                    topEntries.push(...sorted.slice(0, isRelayEvent ? 6 : 6));
                });
                sc[t] = topEntries;
            });
            return sc;
        };
        const baselineOpponents = getBaselinePerformance();

        const getEntryValue = (e) => {
            // How many points would this entry get against baseline opponents?
            const eventEntries = [e];
            Object.values(baselineOpponents).forEach(opps => {
                opps.forEach(o => { if (o.event === e.event) eventEntries.push(o); });
            });
            eventEntries.sort((a, b) => isBetter(a.mark, b.mark, a.event) ? -1 : isBetter(b.mark, a.mark, a.event) ? 1 : 0);
            const rank = eventEntries.indexOf(e);
            let points = rank < SCORING_RULES.length ? SCORING_RULES[rank] : 0;
            const isRelayEvent = e.event.toLowerCase().includes('relay') || e.event.toLowerCase().includes('4x');
            return isRelayEvent ? points / 4 : points;
        };

        const sortedPossible = [...genderPossibleEntries].sort((a, b) => getEntryValue(b) - getEntryValue(a));

        // 2. Greedy Start with Constraints
        let currentLineupList = [];
        let memberCounts = {};

        sortedPossible.forEach(e => {
            const members = getMembers(e);
            const canAdd = members.every(m => (memberCounts[m] || 0) < EVENT_LIMIT);
            if (canAdd) {
                currentLineupList.push(e);
                members.forEach(m => memberCounts[m] = (memberCounts[m] || 0) + 1);
            }
        });

        let currentScore = evaluateLineup(currentLineupList, true);

        // 3. Hill Climbing with Swap Logic
        let improved = true;
        let loops = 0;
        const maxLoops = 20;

        while (improved && loops < maxLoops) {
            improved = false;
            loops++;

            for (const toAdd of sortedPossible) {
                if (currentLineupList.includes(toAdd)) continue;

                // To add 'toAdd', we might need to remove its members' existing events
                const members = getMembers(toAdd);
                const conflicting = currentLineupList.filter(e => {
                    const eMembers = getMembers(e);
                    return members.some(m => eMembers.includes(m));
                });

                // Strategy: Try replacing each conflicting entry, or subsets if necessary
                // Simplest: Try removing ALL conflicting entries and see if score improves
                // More advanced: Try every combination? Too slow. 
                // Let's try: Remove minimum required to free up members in 'toAdd'.

                // For each member in toAdd that is at limit, we MUST remove one of their events.
                const membersAtLimit = members.filter(m => (memberCounts[m] || 0) >= EVENT_LIMIT);

                if (membersAtLimit.length === 0) {
                    const trialLineup = [...currentLineupList, toAdd];
                    const newScore = evaluateLineup(trialLineup, true);

                    if (newScore > currentScore + 0.01 || (Math.abs(newScore - currentScore) < 0.01 && !JSON.stringify(currentLineupList).includes(JSON.stringify(toAdd)))) {
                        currentLineupList = trialLineup;
                        currentScore = newScore;
                        memberCounts = {};
                        currentLineupList.forEach(le => getMembers(le).forEach(m => memberCounts[m] = (memberCounts[m] || 0) + 1));
                        improved = true;
                        break;
                    }
                } else {
                    let bestSwapScore = currentScore;
                    let bestSwapLineup = null;

                    const normToAddMembers = membersAtLimit.map(m => m.toLowerCase().trim());
                    const conflictingEntries = currentLineupList.filter(e => {
                        const em = getMembers(e).map(m => m.toLowerCase().trim());
                        return normToAddMembers.some(m => em.includes(m));
                    });

                    // 1-for-1 swaps
                    for (const toRemove of conflictingEntries) {
                        const trialLineup = currentLineupList.filter(e => e !== toRemove);
                        trialLineup.push(toAdd);

                        const trialCounts = {};
                        let valid = true;
                        trialLineup.forEach(le => {
                            getMembers(le).forEach(m => {
                                const nm = m.toLowerCase().trim();
                                trialCounts[nm] = (trialCounts[nm] || 0) + 1;
                                if (trialCounts[nm] > EVENT_LIMIT) valid = false;
                            });
                        });

                        if (valid) {
                            const newScore = evaluateLineup(trialLineup, true);
                            if (newScore > bestSwapScore + 0.01 || Math.abs(newScore - bestSwapScore) < 0.01) {
                                bestSwapScore = newScore;
                                bestSwapLineup = trialLineup;
                            }
                        }
                    }

                    // Option C: Joint Surgical Swap (Drop exactly 1 lowest event per member-at-limit)
                    // This specifically solves the "Relay Deadlock" where multiple members are full.
                    const isR = (e) => e.event.toLowerCase().includes('relay') || e.event.toLowerCase().includes('4x');
                    if (isR(toAdd)) {
                        const jointToRemove = new Set();
                        for (const m of getMembers(toAdd).map(nm => nm.toLowerCase().trim())) {
                            if ((memberCounts[m] || 0) >= EVENT_LIMIT) {
                                const mEntries = currentLineupList.filter(e => {
                                    const em = getMembers(e).map(nm => nm.toLowerCase().trim());
                                    return em.includes(m);
                                });
                                // Sacrifice the lowest value entry for this member
                                if (mEntries.length > 0) {
                                    mEntries.sort((a, b) => getEntryValue(a) - getEntryValue(b));
                                    jointToRemove.add(mEntries[0]);
                                }
                            }
                        }

                        if (jointToRemove.size > 0 && jointToRemove.size < 4) { // don't drop everything
                            const trialLineup = currentLineupList.filter(e => !jointToRemove.has(e));
                            trialLineup.push(toAdd);

                            const trialCounts = {};
                            let valid = true;
                            trialLineup.forEach(le => {
                                getMembers(le).forEach(m => {
                                    const nm = m.toLowerCase().trim();
                                    trialCounts[nm] = (trialCounts[nm] || 0) + 1;
                                    if (trialCounts[nm] > EVENT_LIMIT) valid = false;
                                });
                            });

                            if (valid) {
                                const newScore = evaluateLineup(trialLineup, true);
                                // For relays, we are slightly more lenient on lateral moves to favor participation
                                if (newScore > bestSwapScore + 0.01 || Math.abs(newScore - bestSwapScore) < 0.01) {
                                    bestSwapScore = newScore;
                                    bestSwapLineup = trialLineup;
                                }
                            }
                        }
                    }

                    if (bestSwapLineup && JSON.stringify(bestSwapLineup) !== JSON.stringify(currentLineupList)) {
                        currentLineupList = bestSwapLineup;
                        currentScore = bestSwapScore;
                        memberCounts = {};
                        currentLineupList.forEach(le => getMembers(le).forEach(m => memberCounts[m] = (memberCounts[m] || 0) + 1));
                        improved = true;
                        break;
                    }
                }
            }

            if (!fixedOpponentLineups) {
                setSimProgress(progressStart + (progressRange * 0.2) + Math.floor((loops / maxLoops) * (progressRange * 0.6)));
                await new Promise(r => setTimeout(r, 0));
            }
        }

        const bestRes = { avg: currentScore, entries: currentLineupList };

        // Identify what changed if we had a baseline
        let changeSummary = null;
        if (fixedOpponentLineups) {
            const oldList = fixedOpponentLineups[teamName] ? fixedOpponentLineups[teamName].filter(isGender) : [];
            const oldKeys = oldList.map(e => `${e.event}|${e.athlete_id}`).sort();
            const newKeys = currentLineupList.map(e => `${e.event}|${e.athlete_id}`).sort();

            const added = currentLineupList.filter(e => !oldKeys.includes(`${e.event}|${e.athlete_id}`));
            const removed = oldList.filter(e => !newKeys.includes(`${e.event}|${e.athlete_id}`));

            if (added.length > 0 || removed.length > 0) {
                changeSummary = {
                    added: added.map(e => ({ name: e.athlete_name, event: e.event })),
                    removed: removed.map(e => ({ name: e.athlete_name, event: e.event }))
                };
            }
        }

        // Calculate Stats
        if (!fixedOpponentLineups) {
            setSimProgress(progressStart + progressRange * 0.9);
            await new Promise(r => setTimeout(r, 0));
        }

        const statsByTeam = {};
        const entryScoresMap = new Map();
        bestRes.entries.forEach(e => entryScoresMap.set(e, []));

        scenarios.forEach((oppEntries, i) => {
            const fullMeet = [...bestRes.entries];
            Object.values(oppEntries).forEach(opps => fullMeet.push(...opps));
            const meetScores = simulateSingleMeet(fullMeet);
            Object.entries(meetScores).forEach(([team, score]) => {
                if (!statsByTeam[team]) statsByTeam[team] = [];
                statsByTeam[team].push(score);
            });

            const eventGroups = {};
            fullMeet.forEach(e => {
                if (!eventGroups[e.event]) eventGroups[e.event] = [];
                eventGroups[e.event].push(e);
            });

            const scoredEntries = new Set();
            Object.values(eventGroups).forEach(entries => {
                entries.sort((a, b) => isBetter(a.mark, b.mark, a.event) ? -1 : isBetter(b.mark, a.mark, a.event) ? 1 : 0);
                for (let r = 0; r < Math.min(entries.length, SCORING_RULES.length); r++) {
                    const entry = entries[r];
                    if (entryScoresMap.has(entry)) {
                        const pts = SCORING_RULES[r];
                        entryScoresMap.get(entry).push(pts);
                        scoredEntries.add(entry);
                    }
                }
            });

            bestRes.entries.forEach(e => {
                if (!scoredEntries.has(e)) {
                    entryScoresMap.get(e).push(0);
                }
            });
        });

        const enhancedEntries = bestRes.entries.map(e => {
            const scores = entryScoresMap.get(e) || [];
            if (scores.length === 0) return { ...e, pointsAvg: 0, pointsMin: 0, pointsMax: 0 };
            const sorted = [...scores].sort((a, b) => a - b);
            return {
                ...e,
                pointsAvg: sorted.reduce((a, b) => a + b, 0) / scores.length,
                pointsMin: sorted[0],
                pointsMax: sorted[sorted.length - 1]
            };
        });

        const finalStats = Object.entries(statsByTeam).map(([name, scores]) => {
            const sorted = scores.sort((a, b) => a - b);
            return {
                name,
                avg: sorted.reduce((a, b) => a + b, 0) / scenarios.length,
                min: sorted[0],
                max: sorted[sorted.length - 1],
                scores: sorted
            };
        }).sort((a, b) => b.avg - a.avg);

        return { avg: bestRes.avg, entries: enhancedEntries, stats: finalStats, changeSummary };
    };

    // Wrapper
    const optimizeForGender = async (gender, progressStart, progressRange) => {
        return optimizeTeamStrategy({
            teamName: targetTeam,
            gender,
            progressStart,
            progressRange
        });
    };

    const runRobustSimulation = async () => {
        if (filterYear === 'All' || filterSeason === 'All') {
            alert("Please select a Year and Season first.");
            return;
        }
        setIsRobustLoading(true);

        // Run in a timeout to allow UI to show loading state
        setTimeout(async () => {
            try {
                // 1. Run Optimization for Boys and Girls
                const boysRes = await optimizeForGender('boys', 0, 50);
                const girlsRes = await optimizeForGender('girls', 50, 50);

                setSimProgress(100);

                setRobustSimResults({
                    boys: boysRes,
                    girls: girlsRes
                });

            } catch (err) {
                console.error("Robust sim failed:", err);
                alert("An error occurred during simulation.");
            } finally {
                setIsRobustLoading(false);
            }
        }, 100);
    };

    const runStrategicSimulation = async () => {
        setIsRobustLoading(true);
        setStrategicLog([]);
        setSimProgress(0);

        setTimeout(async () => {
            try {
                // Initial Greedy Setup
                const initialLineups = {};
                Object.entries(teamPools).forEach(([team, pool]) => {
                    initialLineups[team] = getGreedyEntries(pool);
                });

                let currentLineups = JSON.parse(JSON.stringify(initialLineups));
                const log = [];

                // Helper to get score of a lineup state for THE CURRENT GENDER
                const getScoresForGender = (lineups, targetGender) => {
                    const isGen = (e) => (targetGender === 'girls' ? e.event.toLowerCase().includes('girls') : !e.event.toLowerCase().includes('girls'));
                    const allEntries = Object.values(lineups).flat().filter(isGen);
                    return simulateSingleMeet(allEntries);
                };

                const getLeaderboardString = (lineups, targetGender) => {
                    const scores = getScoresForGender(lineups, targetGender);
                    return Object.entries(scores)
                        .filter(([_, s]) => s > 0)
                        .sort((a, b) => b[1] - a[1])
                        .map(([t, s]) => `${t}: ${s.toFixed(0)}`)
                        .join(' | ');
                };

                // Split by gender for independent optimization
                const genders = ['boys', 'girls'];
                const finalResults = { boys: null, girls: null };

                for (const gender of genders) {
                    setSimProgress(gender === 'boys' ? 10 : 60);
                    await new Promise(r => setTimeout(r, 0));

                    const isGender = (e) => (gender === 'girls' ? e.event.toLowerCase().includes('girls') : !e.event.toLowerCase().includes('girls'));

                    // Optimization Loop: King of the Hill / Cascading
                    const maxGlobalRounds = 10;
                    let globalStable = false;

                    for (let globalRound = 1; globalRound <= maxGlobalRounds; globalRound++) {
                        if (globalStable) break;

                        const standings = getScoresForGender(currentLineups, gender);
                        const sortedTeams = Object.entries(standings)
                            .sort((a, b) => b[1] - a[1])
                            .map(x => x[0]);

                        const initialOrder = [...sortedTeams];
                        let roundLineupsSnapshot = JSON.stringify(currentLineups);
                        let rankingChanged = false;
                        let roundChanges = 0;

                        // Iterate down the ladder: 2nd vs 1st, 3rd vs 2nd...
                        for (let i = 0; i < sortedTeams.length - 1; i++) {
                            const defender = sortedTeams[i];
                            const challenger = sortedTeams[i + 1];

                            // Battle Logic: Challenger vs Defender (Static Background)
                            let battleStable = false;
                            let battleRounds = 0;

                            while (!battleStable && battleRounds < 5) {
                                battleRounds++;
                                let battleChanges = 0;

                                for (const team of [challenger, defender]) {
                                    const otherTeam = team === challenger ? defender : challenger;

                                    // Build static background
                                    const staticOpponents = {};
                                    Object.keys(currentLineups).forEach(t => {
                                        if (t !== challenger && t !== defender) {
                                            staticOpponents[t] = currentLineups[t];
                                        } else if (t === otherTeam) {
                                            staticOpponents[t] = currentLineups[t];
                                        }
                                    });

                                    const oldScore = getScoresForGender(currentLineups, gender)[team] || 0;
                                    const res = await optimizeTeamStrategy({
                                        teamName: team, gender, progressStart: 0, progressRange: 0,
                                        fixedOpponentLineups: { ...staticOpponents, [team]: currentLineups[team] }
                                    });

                                    const oldDef = JSON.stringify(currentLineups[team].filter(isGender).map(e => (e.event + e.athlete_id)).sort());
                                    const newDef = JSON.stringify(res.entries.map(e => (e.event + e.athlete_id)).sort());

                                    if (oldDef !== newDef) {
                                        const otherGenderEntries = currentLineups[team].filter(e => !isGender(e));
                                        currentLineups[team] = [...otherGenderEntries, ...res.entries];
                                        const newScore = getScoresForGender(currentLineups, gender)[team] || 0;

                                        if (Math.abs(newScore - oldScore) > 0.1) {
                                            const type = team === challenger ? "Title Match" : "Hold the Line";
                                            const leader = getLeaderboardString(currentLineups, gender);
                                            let detail = "";
                                            if (res.changeSummary) {
                                                const addStr = res.changeSummary.added.map(e => `+${e.name}(${e.event})`).join(', ');
                                                const remStr = res.changeSummary.removed.map(e => `-${e.name}(${e.event})`).join(', ');
                                                detail = ` [${addStr}${remStr ? ' | ' + remStr : ''}]`;
                                            }
                                            log.push(`[${gender.toUpperCase()} G${globalRound}] ${team} (${type}) vs ${otherTeam}.${detail} Leaderboard: ${leader}`);
                                            battleChanges++;
                                            roundChanges++;
                                        }
                                    }
                                }
                                if (battleChanges === 0) battleStable = true;
                            }

                            // Check if rank flipped
                            const currentStandings = getScoresForGender(currentLineups, gender);
                            const currentSorted = Object.entries(currentStandings)
                                .sort((a, b) => b[1] - a[1])
                                .map(x => x[0]);

                            if (JSON.stringify(currentSorted) !== JSON.stringify(initialOrder)) {
                                log.push(`[${gender.toUpperCase()} G${globalRound}] !!! RANKING CHANGE DETECTED !!! Restarting cascade...`);
                                rankingChanged = true;
                                break;
                            }
                            await new Promise(r => setTimeout(r, 0));
                        }

                        if (!rankingChanged) {
                            if (roundChanges === 0) {
                                log.push(`[${gender.toUpperCase()}] No further tactical adjustments possible. Equilibrium reached.`);
                                globalStable = true;
                            }
                        }
                    }

                    // Final Stats for Target Team
                    const finalRes = await optimizeTeamStrategy({
                        teamName: targetTeam,
                        gender: gender,
                        progressStart: (gender === 'boys' ? 40 : 90),
                        progressRange: 10,
                        fixedOpponentLineups: currentLineups
                    });
                    finalResults[gender] = finalRes;
                }

                setStrategicLog(log);
                setSimProgress(100);
                setRobustSimResults(finalResults);

            } catch (err) {
                console.error("Strategic sim failed:", err);
                alert("Error in Nash Equilibrium Mode");
            } finally {
                setIsRobustLoading(false);
            }
        }, 100);
    };

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

        return filterSeason === 'Outdoor' ? outdoor : indoor;
    }, [filterSeason]);

    const groupedData = useMemo(() => {
        const groups = {};

        filteredData.forEach(curr => {
            // Normalize the event name first to get the canonical version
            const normalizedFull = normalizeEvent(curr.event, filterSeason);
            const gender = normalizedFull.startsWith('Girls') ? 'Girls' : (normalizedFull.startsWith('Boys') ? 'Boys' : '');
            const baseName = normalizedFull.replace(/^(Girls|Boys)\s+/, '');
            const originalCanonical = baseName;

            // Map hurdles to combined key
            const scoringKey = (baseName === '100m Hurdles' || baseName === '110m Hurdles')
                ? '100m/110m Hurdles'
                : baseName;

            // Only include events on the scoring list
            if (!SCORING_EVENTS.includes(scoringKey)) return;

            // Use the gender-specific name for grouping/display
            const canonicalName = baseName; 

            const groupKey = `${gender} ${canonicalName} (${curr.derivedType} ${curr.derivedYear})`.trim();
            
            if (!groups[groupKey]) groups[groupKey] = {
                items: {},
                canonicalName: canonicalName,
                gender: gender,
                orderIdx: SCORING_EVENTS.indexOf(scoringKey)
            };

            const athleteKey = curr.isRelay ? curr.pvcTeam : `${curr.athlete_id}|${curr.pvcTeam}`;
            if (!groups[groupKey].items[athleteKey] || isBetter(curr.mark, groups[groupKey].items[athleteKey].mark, canonicalName)) {
                groups[groupKey].items[athleteKey] = { 
                    ...curr, 
                    event: `${gender} ${canonicalName}`.trim(),
                    originalCanonical: originalCanonical 
                };
            }
        });

        const finalGroups = {};
        
        // Sort keys by canonical order, then gender (Girls then Boys)
        const sortedKeys = Object.keys(groups).sort((a, b) => {
            const gA = groups[a];
            const gB = groups[b];
            
            if (gA.orderIdx !== gB.orderIdx) return gA.orderIdx - gB.orderIdx;
            
            // Same event, sort Girls before Boys
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
    }, [filteredData, isBetter, SCORING_EVENTS]);

    const optimizedData = useMemo(() => {
        if (!showSimulation || filterYear === 'All' || filterSeason === 'All' || Object.keys(groupedData).length === 0) {
            return groupedData;
        }

        const scoringRules = [10, 8, 6, 4, 2, 1];

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

        return finalGroups;
    }, [groupedData, showSimulation, filterYear, filterSeason, isBetter, EVENT_LIMIT]);

    const optimizedTeamScores = useMemo(() => {
        if (!showSimulation) return null;
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
    }, [optimizedData, showSimulation, filterYear, filterSeason]);

    const entryDecisions = useMemo(() => {
        if (!targetTeam || Object.keys(groupedData).length === 0) return null;

        const teamAthletes = {};

        Object.entries(groupedData).forEach(([groupTitle, results]) => {
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
    }, [groupedData, targetTeam]);

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

            <div className="analyzer-controls">
                <div className="filter-bar analyzer-filters">
                    <div className="filter-group">
                        <label>Year</label>
                        <select value={filterYear} onChange={e => setFilterYear(e.target.value)}>
                            <option value="All">All Years</option>
                            {years.map(y => <option key={y} value={y}>{y}</option>)}
                        </select>
                    </div>
                    <div className="filter-group">
                        <label>Season</label>
                        <select value={filterSeason} onChange={e => setFilterSeason(e.target.value)}>
                            <option value="All">All Seasons</option>
                            {seasons.map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                    </div>
                    <div className="filter-group">
                        <label>Competition</label>
                        <select value={competitionType} onChange={e => setCompetitionType(e.target.value)}>
                            <option value="PVC">PVC Small Schools</option>
                            <option value="States">Class C States</option>
                        </select>
                    </div>
                    <div className="filter-group">
                        <label>Optimize For</label>
                        <select value={targetTeam} onChange={e => setTargetTeam(e.target.value)}>
                            {Object.values(competitionType === 'PVC' ? getPVCSchools(filterYear, filterSeason) : getStateSchools(filterYear, filterSeason)).map(t => (
                                <option key={t} value={t}>{t}</option>
                            ))}
                        </select>
                    </div>
                    <div className="simulation-actions">
                        <button
                            className={`simulate-btn ${showSimulation ? 'active' : ''}`}
                            onClick={() => setShowSimulation(!showSimulation)}
                        >
                            {showSimulation ? 'Reset' : 'Simulate'}
                        </button>
                    </div>
                    <div className="record-count">{filteredData.length} Results</div>
                </div>
            </div>

            {entryDecisions && (entryDecisions.decisionAthletes.length > 0 || entryDecisions.straightforwardAthletes.length > 0) && (
                <div className="entry-decisions-dashboard" style={{ marginTop: '20px' }}>
                    <div className="dashboard-section-header" style={{ 
                        marginBottom: '16px', 
                        display: 'flex', 
                        alignItems: 'center', 
                        justifyContent: 'space-between',
                        padding: '12px 16px',
                        background: '#f8fafc',
                        borderRadius: '8px',
                        border: '1px solid #e2e8f0'
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#1a202c' }}>Entry Decisions: {targetTeam}</h3>
                            <span className="record-count" style={{ fontSize: '0.7rem' }}>Simple Performance Ranking</span>
                        </div>
                        <button 
                            onClick={() => setIsDashboardCollapsed(!isDashboardCollapsed)}
                            className="toggle-btn"
                            style={{ 
                                padding: '4px 12px', 
                                background: 'white', 
                                border: '1px solid #cbd5e0',
                                color: '#4a5568'
                            }}
                        >
                            {isDashboardCollapsed ? 'Expand Decisions' : 'Collapse Dashboard'}
                        </button>
                    </div>

                    {!isDashboardCollapsed && (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '20px' }}>
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
                    )}
                </div>
            )}

            {robustSimResults && (
                <div className="robust-results-overlay">
                    <div className="robust-card">
                        <div className="robust-header">
                            <h3>{strategicLog && strategicLog.length > 0 ? "Nash Equilibrium Report" : `Optimal Strategy: ${targetTeam}`}</h3>
                            <button className="close-btn" onClick={() => setRobustSimResults(null)}>X</button>
                        </div>

                        {strategicLog && strategicLog.length > 0 && (
                            <div className="strategic-log" style={{ background: '#1e293b', color: '#cbd5e1', padding: '12px', borderRadius: '6px', marginBottom: '20px', maxHeight: '350px', overflowY: 'auto', fontSize: '0.85rem', fontFamily: 'monospace' }}>
                                {strategicLog.map((entry, i) => (
                                    <div key={i} style={{ marginBottom: '4px' }}>{entry}</div>
                                ))}
                                <div style={{ color: '#4ade80', marginTop: '8px' }}>Nash Equilibrium Established</div>
                            </div>
                        )}

                        <div className="robust-stats" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '24px' }}>
                            {['boys', 'girls'].map(gender => {
                                const res = robustSimResults[gender];
                                const genderColor = gender === 'boys' ? '#3b82f6' : '#ec4899';
                                return (
                                    <div key={gender} style={{ padding: '16px', background: '#f8fafc', borderRadius: '8px', borderTop: `4px solid ${genderColor}` }}>
                                        <h4 style={{ margin: '0 0 12px 0', textTransform: 'capitalize', color: genderColor }}>{gender} Team</h4>
                                        <div className="stat-item">
                                            <span className="stat-label">Expected Score</span>
                                            <span className="stat-val" style={{ fontSize: '1.8rem' }}>{res ? res.avg.toFixed(1) : '-'}</span>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>

                        <div className="robust-recommendations" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                            {['boys', 'girls'].map(gender => {
                                const res = robustSimResults[gender];
                                return (
                                    <div key={gender}>
                                        <h4 style={{ borderBottom: '1px solid #eee', paddingBottom: '8px', marginBottom: '12px', textTransform: 'capitalize' }}>{gender} Strategy</h4>
                                        <div className="rec-grid">
                                            {res && res.entries.sort((a, b) => a.athlete_name.localeCompare(b.athlete_name)).map((en, i) => (
                                                <div key={i} className="rec-item">
                                                    <span className="rec-name">{en.athlete_name}</span>
                                                    <span className="rec-event">{en.event}</span>
                                                    <span className="rec-mark">{en.mark}</span>
                                                    <span className="rec-points" style={{ fontSize: '0.8rem', color: '#64748b', marginLeft: '16px' }}>
                                                        {en.pointsAvg ? `${en.pointsAvg.toFixed(1)} pts (${en.pointsMin}-${en.pointsMax})` : ''}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>

                        <div className="robust-distributions" style={{ marginTop: '24px' }}>
                            {['boys', 'girls'].map(gender => {
                                const stats = robustSimResults[gender]?.stats;
                                if (!stats || stats.length === 0) return null;

                                const genderDisplay = gender === 'boys' ? 'Boys' : 'Girls';
                                const genderColor = gender === 'boys' ? '#3b82f6' : '#ec4899';
                                const genderBg = gender === 'boys' ? '#eff6ff' : '#fdf2f8';
                                const globalMax = Math.max(...stats.map(t => t.max), 1);

                                return (
                                    <div key={gender} style={{ marginBottom: '32px' }}>
                                        <h4 style={{ borderBottom: `2px solid ${genderColor}`, paddingBottom: '8px', marginBottom: '16px', color: genderColor }}>
                                            {genderDisplay} Championship Distributions
                                        </h4>

                                        <div className="histogram-container" style={{ padding: '0 10px' }}>
                                            <div style={{ display: 'flex', marginBottom: '8px', fontSize: '0.7rem', color: '#94a3b8', borderBottom: '1px solid #f1f5f9', paddingBottom: '4px' }}>
                                                <div style={{ width: '130px' }}></div>
                                                <div style={{ flex: 1, position: 'relative', height: '15px' }}>
                                                    {[0, 0.25, 0.5, 0.75, 1].map(p => (
                                                        <span key={p} style={{ position: 'absolute', left: `${p * 100}%`, transform: 'translateX(-50%)' }}>
                                                            {(p * globalMax).toFixed(0)}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>

                                            {stats.slice(0, 8).map(stat => {
                                                const binCount = 50;
                                                const bins = Array(binCount).fill(0);
                                                const range = globalMax || 1;

                                                stat.scores.forEach(s => {
                                                    const binIdx = Math.min(Math.floor((s / range) * binCount), binCount - 1);
                                                    bins[binIdx]++;
                                                });

                                                const maxFreq = Math.max(...bins) || 1;
                                                const isTarget = stat.name === targetTeam;

                                                return (
                                                    <div key={stat.name} style={{ display: 'flex', alignItems: 'center', marginBottom: '8px', height: '30px' }}>
                                                        <div style={{
                                                            width: '130px',
                                                            fontSize: '0.75rem',
                                                            fontWeight: isTarget ? '700' : '500',
                                                            color: isTarget ? '#1e293b' : '#64748b',
                                                            whiteSpace: 'nowrap',
                                                            overflow: 'hidden',
                                                            textOverflow: 'ellipsis',
                                                            paddingRight: '12px'
                                                        }}>
                                                            {stat.name}
                                                        </div>
                                                        <div style={{
                                                            flex: 1,
                                                            height: '100%',
                                                            background: isTarget ? genderBg : '#f8fafc',
                                                            borderRadius: '4px',
                                                            position: 'relative',
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            border: isTarget ? `1px solid ${genderColor}44` : '1px solid #f1f5f9'
                                                        }}>
                                                            <div style={{
                                                                display: 'flex',
                                                                width: '100%',
                                                                height: '100%',
                                                                alignItems: 'flex-end',
                                                                opacity: isTarget ? 0.9 : 0.4,
                                                                padding: '0 2px'
                                                            }}>
                                                                {bins.map((f, i) => (
                                                                    <div key={i} style={{
                                                                        flex: 1,
                                                                        height: `${(f / maxFreq) * 100}%`,
                                                                        background: genderColor,
                                                                        margin: '0 0.5px',
                                                                        borderRadius: '2px 2px 0 0'
                                                                    }} />
                                                                ))}
                                                            </div>
                                                            <div style={{
                                                                position: 'absolute',
                                                                left: `${(stat.avg / globalMax) * 100}%`,
                                                                width: '3px',
                                                                height: '110%',
                                                                top: '-5%',
                                                                background: isTarget ? '#1e293b' : genderColor,
                                                                zIndex: 2,
                                                                borderRadius: '2px'
                                                            }} />
                                                        </div>
                                                        <div style={{ width: '40px', fontSize: '0.75rem', fontWeight: '700', textAlign: 'right', color: isTarget ? '#1e293b' : '#64748b', marginLeft: '8px' }}>
                                                            {stat.avg.toFixed(0)}
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>
            )}

            {showSimulation && optimizedTeamScores && (
                <div className="simulation-overlay">
                    {optimizedTeamScores.incomplete ? (
                        <div className="meet-leaderboard warn">
                            <p>Please select a specific Year and Season to view the Meet Simulation.</p>
                        </div>
                    ) : (
                        <div className="leaderboards-container">
                            {(() => {
                                const activeCanonicalNames = new Set();
                                Object.values(optimizedData).forEach(results => {
                                    if (results.length > 0 && results[0].originalCanonical) {
                                        const name = results[0].originalCanonical;
                                        // normalizeEvent splits hurdles by gender; map back to combined key for this check
                                        const scoringKey = (name === '100m Hurdles' || name === '110m Hurdles')
                                            ? '100m/110m Hurdles'
                                            : name;
                                        activeCanonicalNames.add(scoringKey);
                                    }
                                });

                                const missingEvents = SCORING_EVENTS.filter(canonical => {
                                    return !activeCanonicalNames.has(canonical);
                                });

                                if (missingEvents.length > 0) {
                                    return (
                                        <div className="missing-events-warning" style={{ gridColumn: '1 / -1', marginBottom: '1rem', padding: '1rem', background: '#fff3cd', borderRadius: '8px', border: '1px solid #ffeeba', color: '#856404' }}>
                                            Missing Events: No results found for: {missingEvents.join(', ')}.
                                        </div>
                                    );
                                }
                                return null;
                            })()}
                            <div className="meet-leaderboard boys">
                                <h3>Boys Team Standings</h3>
                                <div className="leaderboard-grid">
                                    {optimizedTeamScores.boys.map((ts, idx) => (
                                        <div key={ts.team} className="leaderboard-wrapper">
                                            <div
                                                className={`leaderboard-item rank-${idx + 1} ${expandedTeams[`${ts.team}-boys`] ? 'expanded' : ''}`}
                                                onClick={() => setExpandedTeams(prev => ({ ...prev, [`${ts.team}-boys`]: !expandedTeams[`${ts.team}-boys`] }))}
                                            >
                                                <span className="team-rank">{idx + 1}</span>
                                                <span className="team-name">{ts.team}</span>
                                                <span className="team-points">{ts.pts.toFixed(1)}</span>
                                                <span className="expand-icon">{expandedTeams[`${ts.team}-boys`] ? 'v' : '>'}</span>
                                            </div>
                                            {expandedTeams[`${ts.team}-boys`] && (
                                                <div className="team-breakdown">
                                                    {ts.breakdown.map((item, i) => (
                                                        <div key={i} className="breakdown-row">
                                                            <span
                                                                className="b-event clickable-event"
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    scrollToEvent(item.groupTitle);
                                                                }}
                                                                title={`Click to view results for ${item.event}`}
                                                            >
                                                                {item.event}
                                                            </span>
                                                            <span className="b-athlete">{item.athlete}</span>
                                                            <span className="b-pts">+{item.pts.toFixed(1)}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                    {optimizedTeamScores.boys.length === 0 && <p className="empty-scores">No results.</p>}
                                </div>
                            </div>
                            <div className="meet-leaderboard girls">
                                <h3>Girls Team Standings</h3>
                                <div className="leaderboard-grid">
                                    {optimizedTeamScores.girls.map((ts, idx) => (
                                        <div key={ts.team} className="leaderboard-wrapper">
                                            <div
                                                className={`leaderboard-item rank-${idx + 1} ${expandedTeams[`${ts.team}-girls`] ? 'expanded' : ''}`}
                                                onClick={() => setExpandedTeams(prev => ({ ...prev, [`${ts.team}-girls`]: !expandedTeams[`${ts.team}-girls`] }))}
                                            >
                                                <span className="team-rank">{idx + 1}</span>
                                                <span className="team-name">{ts.team}</span>
                                                <span className="team-points">{ts.pts.toFixed(1)}</span>
                                                <span className="expand-icon">{expandedTeams[`${ts.team}-girls`] ? 'v' : '>'}</span>
                                            </div>
                                            {expandedTeams[`${ts.team}-girls`] && (
                                                <div className="team-breakdown">
                                                    {ts.breakdown.map((item, i) => (
                                                        <div key={i} className="breakdown-row">
                                                            <span
                                                                className="b-event clickable-event"
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    scrollToEvent(item.groupTitle);
                                                                }}
                                                                title={`Click to view results for ${item.event}`}
                                                            >
                                                                {item.event}
                                                            </span>
                                                            <span className="b-athlete">{item.athlete}</span>
                                                            <span className="b-pts">+{item.pts.toFixed(1)}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                    {optimizedTeamScores.girls.length === 0 && <p className="empty-scores">No results.</p>}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}

            <div className="analyzer-results">
                {Object.keys(optimizedData).length > 0 ? (
                    Object.entries(optimizedData).map(([groupTitle, results]) => (
                        <div key={groupTitle} id={`event-${groupTitle.replace(/[^a-z0-9]/gi, '-')}`} className="event-section">
                            <h3 className="event-title">
                                {results[0].event}
                                <span className="event-meta">{results[0].derivedType} {results[0].derivedYear}</span>
                            </h3>
                            <table className="performance-table">
                                <thead>
                                    <tr>
                                        <th>Rank</th>
                                        <th>Name</th>
                                        <th>Team</th>
                                        <th>Mark</th>
                                        <th>Date</th>
                                        {showSimulation && <th>Points</th>}
                                    </tr>
                                </thead>
                                <tbody>
                                    {results.map((res, idx) => (
                                        <tr key={idx}>
                                            <td>{res.calculatedRank}</td>
                                            <td className="athlete-name-cell">{res.athlete_name}</td>
                                            <td>{res.pvcTeam}</td>
                                            <td className="mark-cell">{res.mark}</td>
                                            <td>{res.date ? res.date.split('T')[0] : 'N/A'}</td>
                                            {showSimulation && (
                                                <td className="points-cell">
                                                    {res.optimizedPts > 0 ? `+${res.optimizedPts.toFixed(1)}` : '-'}
                                                </td>
                                            )}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ))
                ) : (
                    <div className="empty-state">
                        <p>No results match your filters.</p>
                    </div>
                )}
            </div>
        </div>
    );
}

export default PostseasonSimulator;
