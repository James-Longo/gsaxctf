# Site update routine: agent procedure

This is how the site gets updated. It replaces the weekly GitHub Action
(whose schedule is off; a manual run remains as a fallback). It runs as a
Claude scheduled task in the desktop app on James's computer, because two
steps need an agent: Five K Sport results are read in a browser, and QAQC
problems are settled by reading the results.

Code steps are `python3 -m backend.routine <step>` (backend/routine.py).
Work from the repository root. Never run destructive git commands. Do not
deploy if any step below fails; report instead.

## 1. Plan

`python3 -m backend.routine plan` prints what is in season (from the
results' own season windows), whether Five K Sport applies (cross country),
how many Five K Sport files are pending, whether the XC postseason forecast
is due, and the athlete review queue size.

Start from a clean, current checkout: `git status` (only data changes from a
previous unfinished run are acceptable) and `git pull --ff-only`.

## 2. Scrape and parse

1. `python3 -m backend.routine scrape` -- sub5 index pages for every season;
   new result files are downloaded, parsed and synced into the store; the
   manifest, meet links and athlete catalog are rebuilt.
2. If cross country is in season and Five K Sport files are pending: follow
   `docs/agents/fiveksport.md` with the built-in browser (tall viewport,
   OPEN_VIEWER_JS, EXTRACT_JS, `save`), then
   `python3 -m backend.fiveksport sync <year>`.

## 3. QAQC

`python3 -m backend.routine qaqc` verifies every meet's team scores against
the official scores in the file and reports the meets added since the last
run (verified / mismatch / no rankings). The first run only records a
baseline.

For each **mismatch** in the new meets (most are rare, so read each one):
1. Open the source file (`backend/data/sub5_archive/<year>/<season>/...`)
   and the parse (`backend/data/parsed_results/...`).
2. Decide: parser error (fix the parser if it is a pattern, with a test in
   backend/tests/test_parsers.py, re-parse that season) or source error
   (the official scores disagree with the file's own results; leave it and
   note it in the report).

Five K Sport files are verified by `fiveksport sync` (every high-school
results file with a team sheet must say `verified`).

**Athlete identity** (`docs/agents/athlete-review.md`): review up to
**10 batches of 20 pairs** per run, newest runners first, with Sonnet
reviewers, spot-check them, then import and run
`python3 -m backend.athlete_catalog build` and `apply`. The decisions file is
internal and stays on this computer. Pairs marked unsure are listed for James
in the report, not re-reviewed.

## 4. Postseason forecasts

`python3 -m backend.routine sims` publishes the XC postseason forecast while
the season's championship meets (backend/data/xc_groups.json) are still
ahead. Track forecasts are computed in the browser and need nothing here.

Each season, before the first championship meet, check
backend/data/xc_groups.json against the coaches' schedule (dates, venues,
conference membership and divisions) and record the source in its
`sources`.

## 5. Check, publish, report

1. `python3 -m backend.routine check` -- production build and tests.
2. Commit any code fixes made in step 3 with their own message first.
3. `python3 -m backend.routine publish --yes -m "data: routine update <date>"`
   commits the data and pushes. The push is the deploy: GitHub Pages
   rebuilds the site (.github/workflows/deploy-pages.yml). Confirm it with
   `gh run watch $(gh run list --workflow deploy-pages.yml -L1 --json databaseId -q '.[0].databaseId')`.
4. Report to James (the run's final message): new meets and performances,
   QAQC results (mismatches and what was done), Five K Sport files added,
   athlete review counts and the unsure list, forecast published or skipped,
   Pages deploy result. Keep it short.
