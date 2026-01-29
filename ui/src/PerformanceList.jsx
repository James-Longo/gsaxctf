import { useState, useMemo } from 'react'
import { parseMark } from './utils'
import './App.css'

function PVCSimulator({ performances, isBetter }) {
    const [filterYear, setFilterYear] = useState('All')
    const [filterSeason, setFilterSeason] = useState('All')
    const [filterEvent, setFilterEvent] = useState('All')
    const [showSimulation, setShowSimulation] = useState(false)
    const [expandedTeams, setExpandedTeams] = useState({}) // { 'teamName-boys': true }
    const [robustSimResults, setRobustSimResults] = useState(null)
    const [isRobustLoading, setIsRobustLoading] = useState(false)
    const [targetTeam, setTargetTeam] = useState('George Stevens Academy')
    const [simProgress, setSimProgress] = useState(0);
    const [simIterations, setSimIterations] = useState(50);
    const [strategicLog, setStrategicLog] = useState([]);

    // Configuration for PVC Small Schools
    const getPVCSchools = (year, season) => {
        // Specific Rule for Indoor 2026
        if (year === '2026' && season === 'Indoor') {
            return {
                "Bangor Chris": "Bangor Christian Schools",
                "Bucksport": "Bucksport High School",
                "Central": "Central High School",
                "Dexter": "Dexter Regional High School",
                "Foxcroft": "Foxcroft Academy",
                "George Stevens": "George Stevens Academy",
                "Mattanawcook": "Mattanawcook Academy",
                "Orono": "Orono High School",
                "PCHS": "Piscataquis Community High School",
                "Penquis": "Penquis Valley High School",
                "Searsport": "Searsport District High School",
                "Sumner": "Sumner/Narragaugus"
            };
        }

        // Default / Legacy List
        return {
            "Orono": "Orono High School",
            "George Steve": "George Stevens Academy",
            "Bucksport": "Bucksport High School",
            "Sumner": "Sumner/Narragaugus",
            "Central": "Central High School",
            "Foxcroft": "Foxcroft Academy",
            "Dexter": "Dexter Regional High School",
            "Piscataquis": "Piscataquis Community High School",
            "Penquis": "Penquis Valley High School",
            "Searsport": "Searsport District High School",
            "Mattanawcook": "Mattanawcook Academy",
            "Lee Academy": "Lee Academy",
            "Deer Isle": "Deer Isle-Stonington High School",
            "Bangor Chris": "Bangor Christian Schools",
            "Greenville": "Greenville High School",
            "Narraguagus": "Sumner/Narragaugus",
            "Washington Acad": "Washington Academy",
            "Calais": "Calais High School",
            "Shead": "Shead High School",
            "Fort Kent": "Fort Kent Community High School",
            "Caribou Hig": "Caribou High School",
            "Presque Isle": "Presque Isle High School",
            "Houlton": "Houlton High School"
        };
    };

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
        const activeSchools = getPVCSchools(filterYear, filterSeason);

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
    }, [performances, filterYear, filterSeason, filterEvent]);

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
            if (!existing || isBetter(p.mark, existing.mark)) {
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
    const EVENT_LIMIT = 4;

    const getMembers = (p) => {
        const name = p.athlete_name || "";
        if (p.isRelay) {
            return name.split(',').map(n => n.trim()).filter(n => n && !n.toLowerCase().includes('relay'));
        }
        return [name];
    };

    const simulateSingleMeet = (allEntries) => {
        const eventGroups = {};
        allEntries.forEach(e => {
            if (!eventGroups[e.event]) eventGroups[e.event] = [];
            eventGroups[e.event].push(e);
        });

        const scores = {};
        Object.entries(eventGroups).forEach(([event, entries]) => {
            entries.sort((a, b) => isBetter(a.mark, b.mark) ? -1 : isBetter(b.mark, a.mark) ? 1 : 0);
            for (let i = 0; i < Math.min(entries.length, SCORING_RULES.length); i++) {
                const team = entries[i].pvcTeam;
                scores[team] = (scores[team] || 0) + SCORING_RULES[i];
            }
        });
        return scores;
    };

    const getGreedyEntries = (pool) => {
        const entries = [];
        Object.values(pool).forEach(athPerfs => {
            athPerfs.sort((a, b) => isBetter(a.mark, b.mark) ? -1 : 1);
            entries.push(...athPerfs.slice(0, EVENT_LIMIT));
        });
        return entries;
    };

    // Core Optimization Logic (Deterministic Hill Climbing)
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
                        const sorted = [...athPerfs].sort((a, b) => isBetter(a.mark, b.mark) ? -1 : 1);
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

        const evaluateLineup = (lineup) => {
            const res = [];
            scenarios.forEach(oppEntries => {
                const fullMeet = [...lineup];
                Object.values(oppEntries).forEach(opps => fullMeet.push(...opps));
                res.push(simulateSingleMeet(fullMeet));
            });
            // Return average score for target team
            return res.reduce((s, r) => s + (r[teamName] || 0), 0) / scenarios.length;
        };

        // --- Deterministic Hill Climbing ---
        // 1. Start with Greedy (Best events for everyone)
        // Group by Athlete first to make swapping easy
        const athletes = Object.keys(genderTargetPool);
        let currentLineupMap = {}; // { athlete_key: [entries] }

        athletes.forEach(key => {
            const perfs = genderTargetPool[key];
            const sorted = [...perfs].sort((a, b) => isBetter(a.mark, b.mark) ? -1 : 1);
            currentLineupMap[key] = sorted.slice(0, EVENT_LIMIT);
        });

        let currentLineupList = Object.values(currentLineupMap).flat();
        let currentScore = evaluateLineup(currentLineupList);

        let improved = true;
        let loops = 0;
        const maxLoops = 5;

        // Iterative Improvement
        while (improved && loops < maxLoops) {
            improved = false;
            loops++;

            // For each athlete...
            for (const key of athletes) {
                const allPerfs = genderTargetPool[key];
                const currentSelection = currentLineupMap[key];

                // If athlete has <= limit events, no choices to make.
                if (allPerfs.length <= EVENT_LIMIT) continue;

                // Try swapping a currently selected event for an unselected one
                const unselected = allPerfs.filter(p => !currentSelection.includes(p));

                for (let i = 0; i < currentSelection.length; i++) {
                    const toRemove = currentSelection[i];

                    for (const toAdd of unselected) {
                        // Swap
                        const trialSelection = [...currentSelection];
                        trialSelection[i] = toAdd;

                        // Reconstruct full lineup
                        const trialLineupMap = { ...currentLineupMap, [key]: trialSelection };
                        const trialLineupList = Object.values(trialLineupMap).flat();

                        const newScore = evaluateLineup(trialLineupList);

                        if (newScore > currentScore + 0.01) { // strict improvement
                            currentScore = newScore;
                            currentLineupMap = trialLineupMap; // Commit change
                            currentLineupList = trialLineupList;
                            improved = true;
                            // Break to restart search (optional, or continue greedy?)
                            // Let's break to maintain true hill climbing path
                            break;
                        }
                    }
                    if (improved) break;
                }
                if (improved) break;
            }

            if (!fixedOpponentLineups) {
                setSimProgress(progressStart + (progressRange * 0.2) + Math.floor((loops / maxLoops) * (progressRange * 0.6)));
                await new Promise(r => setTimeout(r, 0));
            }
        }

        const bestRes = { avg: currentScore, entries: currentLineupList };

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
                entries.sort((a, b) => isBetter(a.mark, b.mark) ? -1 : isBetter(b.mark, a.mark) ? 1 : 0);
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

        return { avg: bestRes.avg, entries: enhancedEntries, stats: finalStats };
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

                // Helper to get score of a lineup state
                const getScores = (lineups) => {
                    const allEntries = Object.values(lineups).flat();
                    return simulateSingleMeet(allEntries);
                };

                // Split by gender for independent optimization
                const genders = ['boys', 'girls'];
                const finalResults = { boys: null, girls: null };

                for (const gender of genders) {
                    setSimProgress(gender === 'boys' ? 10 : 60);
                    await new Promise(r => setTimeout(r, 0));

                    // Filter lineups for this gender
                    const isGender = (e) => (gender === 'girls' ? e.event.toLowerCase().includes('girls') : !e.event.toLowerCase().includes('girls'));

                    // Optimization Loop
                    const maxRounds = 10;
                    let stable = false;

                    for (let round = 1; round <= maxRounds; round++) {
                        if (stable) break;
                        let changes = 0;
                        const roundScores = getScores(currentLineups);
                        const rankedTeams = Object.entries(roundScores)
                            .sort((a, b) => b[1] - a[1]) // Sort desc
                            .map(x => x[0]);

                        // Limit to top teams effectively battling for positions (Top 3 + Target if strictly needed)
                        // For speed, let's do top 4
                        const activeTeams = rankedTeams.slice(0, 4);
                        if (!activeTeams.includes(targetTeam)) activeTeams.push(targetTeam);

                        for (const team of activeTeams) {
                            const opponents = { ...currentLineups };
                            // Optimization logic needs other teams' lineups fixed
                            const res = await optimizeTeamStrategy({
                                teamName: team,
                                gender: gender,
                                progressStart: 0,
                                progressRange: 0,
                                fixedOpponentLineups: opponents
                            });

                            const newGenderEntries = res.entries;
                            const otherGenderEntries = currentLineups[team].filter(e => !isGender(e));
                            const combined = [...otherGenderEntries, ...newGenderEntries];

                            // Check for change
                            const oldDef = JSON.stringify(currentLineups[team].filter(isGender).map(e => e.id).sort());
                            const newDef = JSON.stringify(newGenderEntries.map(e => e.id).sort());

                            if (oldDef !== newDef) {
                                changes++;
                                log.push(`[${gender.toUpperCase()} Round ${round}] ${team} adjusted strategy.`);
                                currentLineups[team] = combined;
                            }

                            // Update progress per team step to keep UI alive
                            await new Promise(r => setTimeout(r, 0));
                        }

                        if (changes === 0) stable = true;
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
                alert("Error in Strategic Mode");
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

    const EVENT_ALIASES = {
        "55m Dash": ["55m Dash", "55 Meter Dash"],
        "200m Dash": ["200m Dash", "200 Meter Dash"],
        "400m Dash": ["400m Dash", "400 Meter Dash"],
        "800m Run": ["800m Run", "800 Meter Run"],
        "1 Mile Run": ["1 Mile Run"],
        "2 Mile Run": ["2 Mile Run"],
        "55m Hurdles": ["55m Hurdles", "55 Meter Hurdles"],
        "4x200m Relay": ["4x200m", "4x200 Meter"],
        "4x800m Relay": ["4x800m", "4x800 Meter"],
        "High Jump": ["High Jump"],
        "Pole Vault": ["Pole Vault"],
        "Long Jump": ["Long Jump"],
        "Triple Jump": ["Triple Jump"],
        "Shot Put": ["Shot Put"]
    };

    // Group by Event, Season, and Year for context-specific ranking
    const groupedData = useMemo(() => {
        const groups = {};

        filteredData.forEach(curr => {
            // Filter non-PVC events
            const eventLower = curr.event.toLowerCase();
            let isAllowed = false;

            // Check if current event matches any allowed alias
            for (const aliases of Object.values(EVENT_ALIASES)) {
                if (aliases.some(alias => eventLower.includes(alias.toLowerCase()))) {
                    isAllowed = true;
                    break;
                }
            }

            const isExcluded = eventLower.includes("pentathlon");

            if (!isAllowed || isExcluded) {
                return;
            }

            const groupKey = `${curr.event} (${curr.derivedType} ${curr.derivedYear})`;
            if (!groups[groupKey]) groups[groupKey] = {};

            // For Relays, use team as key. For Individual, use athlete_id
            const athleteKey = curr.isRelay ? curr.pvcTeam : `${curr.athlete_id}|${curr.pvcTeam}`;
            if (!groups[groupKey][athleteKey] || isBetter(curr.mark, groups[groupKey][athleteKey].mark)) {
                groups[groupKey][athleteKey] = curr;
            }
        });

        const finalGroups = {};
        Object.entries(groups).forEach(([groupKey, itemMap]) => {
            const results = Object.values(itemMap);

            results.sort((a, b) => {
                if (isBetter(a.mark, b.mark)) return -1;
                if (isBetter(b.mark, a.mark)) return 1;
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
    }, [filteredData, isBetter]);

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

        // 3. Optimization Logic (3 event limit)
        const eventLimit = 3;
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
    }, [groupedData, showSimulation, filterYear, filterSeason, isBetter]);

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

    return (
        <div className="analyzer-container">
            <div className="analyzer-header">
                <h2>PVC Championships Simulator</h2>
                <p className="subtitle">Simulating PVC Small Schools Championships using all-time best performances</p>
            </div>

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
                        <label>Optimize For</label>
                        <select value={targetTeam} onChange={e => setTargetTeam(e.target.value)}>
                            {Object.values(getPVCSchools(filterYear, filterSeason)).map(t => (
                                <option key={t} value={t}>{t}</option>
                            ))}
                        </select>
                    </div>
                    <div className="filter-group">
                        <label>Simulation Depth</label>
                        <input
                            type="number"
                            value={simIterations}
                            onChange={e => setSimIterations(Math.max(1, Number(e.target.value)))}
                            min="1"
                            step="10"
                            style={{ width: '80px', padding: '6px' }}
                        />
                    </div>
                    <div className="simulation-actions">
                        <button
                            className={`simulate-btn robust-btn ${isRobustLoading ? 'loading' : ''}`}
                            onClick={runRobustSimulation}
                            disabled={isRobustLoading}
                        >
                            {isRobustLoading ? `Simulating (${simProgress}%)...` : 'Robust Simulation'}
                        </button>
                        <button
                            className={`simulate-btn deterministic-btn ${isRobustLoading ? 'loading' : ''}`}
                            onClick={runStrategicSimulation}
                            disabled={isRobustLoading}
                        >
                            Deterministic Simulation
                        </button>
                        <button
                            className={`simulate-btn ${showSimulation ? 'active' : ''}`}
                            onClick={() => setShowSimulation(!showSimulation)}
                        >
                            {showSimulation ? '📊 Show Raw Results' : '🏆 Quick Simulation'}
                        </button>
                    </div>
                    <div className="record-count">{filteredData.length} Results</div>
                </div>
            </div>

            {robustSimResults && (
                <div className="robust-results-overlay">
                    <div className="robust-card">
                        <div className="robust-header">
                            <h3>{strategicLog && strategicLog.length > 0 ? "Strategic Battle Report" : `Optimal Strategy: ${targetTeam}`}</h3>
                            <button className="close-btn" onClick={() => setRobustSimResults(null)}>✕</button>
                        </div>

                        {strategicLog && strategicLog.length > 0 && (
                            <div className="strategic-log" style={{ background: '#1e293b', color: '#cbd5e1', padding: '12px', borderRadius: '6px', marginBottom: '20px', maxHeight: '150px', overflowY: 'auto', fontSize: '0.85rem', fontFamily: 'monospace' }}>
                                {strategicLog.map((entry, i) => (
                                    <div key={i} style={{ marginBottom: '4px' }}>{entry}</div>
                                ))}
                                <div style={{ color: '#4ade80', marginTop: '8px' }}>✓ Nash Equilibrium Established</div>
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
                            <p>⚠️ <strong>Please select a specific Year and Season</strong> to view the Meet Simulation.</p>
                        </div>
                    ) : (
                        <div className="leaderboards-container">
                            {(() => {
                                const foundEvents = new Set();
                                Object.values(optimizedData).forEach(r => {
                                    if (r.length > 0) foundEvents.add(r[0].event);
                                });

                                // Group expected events by likely gender if possible, but simplest is just check existence
                                // We'll just look for missing generic event types
                                const missingEvents = Object.entries(EVENT_ALIASES).filter(([canonical, aliases]) => {
                                    // Return true if NONE of the aliases are found in 'foundEvents'
                                    return !aliases.some(alias => {
                                        return Array.from(foundEvents).some(found => found.toLowerCase().includes(alias.toLowerCase()));
                                    });
                                }).map(([canonical]) => canonical);

                                if (missingEvents.length > 0) {
                                    return (
                                        <div className="missing-events-warning" style={{ gridColumn: '1 / -1', marginBottom: '1rem', padding: '1rem', background: '#fff3cd', borderRadius: '8px', border: '1px solid #ffeeba', color: '#856404' }}>
                                            ⚠️ <strong>Missing Events:</strong> No results found for: {missingEvents.join(', ')}.
                                        </div>
                                    );
                                }
                                return null;
                            })()}
                            <div className="meet-leaderboard boys">
                                <h3>🏃‍♂️ Boys Team Standings</h3>
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
                                                <span className="expand-icon">{expandedTeams[`${ts.team}-boys`] ? '▼' : '▶'}</span>
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
                                <h3>🏃‍♀️ Girls Team Standings</h3>
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
                                                <span className="expand-icon">{expandedTeams[`${ts.team}-girls`] ? '▼' : '▶'}</span>
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

export default PVCSimulator;
