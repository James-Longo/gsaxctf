# Site update routine: agent procedure

This is how the site gets updated. It replaces the weekly GitHub Action
(whose schedule is off; a manual run remains as a fallback). It runs as a
Claude scheduled task in the desktop app on James's computer, because two
steps need an agent: Five K Sport results are read in a browser, and QAQC
problems are settled by reading the results.

Code steps are `python3 -m backend.routine <step>` (backend/routine.py).
Work from the repository root. Never run destructive git commands. Do not
deploy if any step below fails; report instead.

**Scope: the week's results only.** The routine ingests the recent results of
the season(s) in progress and reruns what is downstream of them, nothing else.
Older seasons are another process's work (James, 2026-10-26: "for the monday
updates, i just want to ingest recent results and rerun anything that's
downstream of them. i'll have another process work on older data"). So:

- the scrape reads only the current season's sub5 index (`routine scrape`
  does this); an older file sub5 newly links is left for the other process;
- a parser fix made for a new file re-parses only that week's files; older
  files with the same layout are listed in the report as leads, not re-parsed;
- a school string in a new file is settled with a per-meet rule
  (`FILE_RULES` / `FILE_CODES` scoped to that file's stem and year), never a
  global alias, and after the catalog rebuild `store_drift` must show no
  change outside the current season's team-seasons; a change there means the
  rule leaked: narrow it, or leave the string unidentified and report it;
- no full re-sync (`scraper_v2 --resync-only`) unless a current-season fix
  needs one, and then the same drift rule applies;
- no database audit, and no rebuild of past seasons' predictions.

## 1. Plan

`python3 -m backend.routine plan` prints what is in season (from the
results' own season windows), whether Five K Sport applies (cross country),
how many Five K Sport files are pending, and whether the XC postseason
predictions are due.

Start from a clean, current checkout: `git status` (only data changes from a
previous unfinished run are acceptable) and `git pull --ff-only`.

## 2. Scrape and parse

1. `python3 -m backend.routine scrape` -- sub5 index pages for the season(s)
   in progress; new result files are downloaded, parsed and synced into the store; the
   manifest, meet links and athlete catalog are rebuilt. A new youth/USATF
   or college meet is listed in `backend/data/meet_scope.json` (see
   `docs/agents/missing-meets.md`, "Not school track") and the sync rerun.
2. If cross country is in season and Five K Sport files are pending: follow
   `docs/agents/fiveksport.md` with the built-in browser (tall viewport,
   OPEN_VIEWER_JS, EXTRACT_JS, `save`), then
   `python3 -m backend.fiveksport sync <year>`.

## 3. QAQC

`python3 -m backend.routine qaqc` verifies every meet's team scores against
the official scores in the file and reports the meets added since the last
run (verified / mismatch / no rankings). The first run only records a
baseline.

`routine qaqc` lists every meet added since its last recorded run. Read only
this week's meets of the season in progress (the files the scrape, Five K
Sport and MileSplit steps added); older meets in the list are not this
routine's work.

For each **mismatch** in the new meets (most are rare, so read each one):
1. Open the source file (`backend/data/sub5_archive/<year>/<season>/...`)
   and the parse (`backend/data/parsed_results/...`).
2. Decide: parser error (fix the parser if it is a pattern, with a test in
   backend/tests/test_parsers.py, re-parse only this week's files that have
   the pattern) or source error (the official scores disagree with the
   file's own results; leave it and note it in the report).

**Odd sections** (`odd_sections` in the same report; qaqc check 16): an event
at one new meet whose *median* mark belongs to another event, such as a
"Girls 200" field with 800 times (`looks_like` names the nearest event), or
`no event (mark format?)` when the marks fit no event. Score verification
misses these when a file prints no team scores. Each flag is judged on the
whole field, so one runner's great or bad day never trips it. Real fields
do look unusual, though (kids' meets, beginner middle school throws, New
England finals), so never drop or relabel rows because of a flag alone:
1. Read the source around that event. If the source shows the event the
   parse gave it (a genuinely slow or strong field), it is fine; say so in
   the report.
2. Otherwise fix the cause like a mismatch: the parser (missed event or
   gender header, meters read as feet-inches, columns crossed), or a
   transcription for a one-off layout. Field relay team totals ("Brewer A"
   in shot put) are expected at relay meets; the catalog, record boards and
   predictor already leave them out.

`unreadable_times` lists marks such as "7:70" (seconds over 59), always a
parse or source error: find the right time in the source.

**Parse confidence** (backend/meet_ledger.py): after the QAQC steps,
`python3 -m backend.meet_ledger signoff --auto` signs off the new files whose
team scores verify exactly with every school identified and nothing
flagged. `python3 -m backend.meet_ledger review 20` then lists what still
needs a reader, worst first. A `changed` file (signed off, but its source or
parse has moved since) comes first: compare the new parse with the source;
if it is right, sign it off again, and if the parse got worse, fix the
parser. Report the counts per confidence level.

**Gender conflicts**: `python3 -m backend.athlete_catalog stats` reports
`gender_conflicts`, runners whose results are filed under both genders
(the catalog keeps them one runner; the store id has no gender). A new one
usually means a race the parser read as the wrong sex: its `other` races in
`gender_conflicts` (backend/data/athlete_catalog.json.gz) name the meet.
Check new ones in this run's meets against the source file and fix the
parser if it is a pattern.

**MileSplit validation** (`docs/agents/missing-meets.md`, one Sonnet agent,
one season at a time):
1. *Gaps*: `python3 -m backend.milesplit list <year> <season>` for the
   season in progress, then `python3 -m backend.meet_ledger build` and
   `missing <year> <season>`. Each missing high-school or middle-school meet
   is filled in the order of the procedure: sub5, the Internet Archive, the
   host, MileSplit (or marked as one we hold, with `match`).
2. *New school records*: every record-board change this run (a new best in
   an event for any team, `ui/src/records.js`) is checked against the
   meet's MileSplit page. A disagreement is settled by the procedure's
   "MileSplit wins" rule and reported.
3. *Mismatches*: a meet whose team scores still mismatch after the step
   above is checked against MileSplit the same way.

Five K Sport files are verified by `fiveksport sync` (every high-school
results file with a team sheet must say `verified`).

**Athlete identity**: `python3 -m backend.athlete_catalog build` and `apply`
settle every spelling pair by rule (same team, never in one race, nothing in
the results against it; see the module docstring). Nothing is reviewed by a
person. Report the stats line.

## 4. Postseason predictions

`python3 -m backend.routine sims` publishes the XC postseason predictions while
the season's championship meets (backend/data/xc_groups.json) are still
ahead, and once more the Monday after the last one: a meet that has been run
shows its result beside its prediction. Past seasons' predictions are not
rebuilt here (they follow corrections to older data). Track predictions are
computed in the browser and need nothing here.
Owen's Predictor is rebuilt by the resync and by `athlete_catalog apply`;
check it as listed in the "What new data feeds" table.

Each season, before the first championship meet, check
backend/data/xc_groups.json against the coaches' schedule (dates, venues,
conference membership and divisions) and record the source in its
`sources`.

## 5. Check, publish, report

1. `python3 -m backend.routine check` -- production build and tests.
   Before it, rebuild every product the run's new data feeds (table in
   `docs/agents/missing-meets.md`, "What new data feeds").
2. `python3 -m backend.store_drift 25` lists team-seasons that lost results
   since the last commit. Every one must be a current-season team-season
   with its reason traced (rows moved to the right school, a duplicate
   removed). A drop in an older season means a change leaked outside this
   week's results (see Scope): undo it before publishing.
3. Commit any code fixes made in step 3 with their own message first.
4. `python3 -m backend.routine publish --yes -m "data: routine update <date>"`
   commits the data and pushes. The push is the deploy: GitHub Pages
   rebuilds the site (.github/workflows/deploy-pages.yml). Confirm it with
   `gh run watch $(gh run list --workflow deploy-pages.yml -L1 --json databaseId -q '.[0].databaseId')`.
5. Report to James (the run's final message): new meets and performances,
   QAQC results (mismatches, odd sections and unreadable times, and what was
   done), Five K Sport files added, the athlete catalog stats line,
   predictions published or skipped, leads for the older-data process
   (older files with a pattern fixed this week, old files sub5 newly links),
   Pages deploy result. Keep it short.
