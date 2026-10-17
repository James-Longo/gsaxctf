# Missing meets and MileSplit validation: agent procedure

sub5.com is the main source, but its archive has holes. The worst are the
seasons around its 2013-2016 WordPress move: 2013-2014 cross country,
2014-2015 indoor and outdoor are a tenth of a normal season, and GSA's
2014-15 outdoor records (Finn Davis-Batt's 159-01 javelin, Zeya Lorio's
5:43.65 1600) exist in no file we have. This procedure fills such holes and
uses MileSplit as the check of last resort.

## The meet ledger

`backend/meet_ledger.py` keeps the answer to "which meets exist, and do we
have each one?". It is rebuilt from what we hold (every file in
parsed_results), the meet lists sites publish (`backend/data/meet_listings/`)
and the not-found logs:

- `python3 -m backend.milesplit list <year> <season>` reads MileSplit's
  meet list for a season (a handful of pages) into
  `meet_listings/milesplit-<year>-<season>.json`.
- `python3 -m backend.meet_ledger build` matches listings to stored meets
  (MileSplit id, else date and name) and prints meets / files / missing /
  not found per season; `python3 -m backend.meet_ledger missing <year>
  <season>` lists what is left to find.
- When a listed meet is one we already hold under a name the matcher can't
  see (a sub5 file named after its venue), set `"match": "<file stem>"` on
  that listing entry, with a `note`; a wrong first guess at `kind` (hs, ms,
  youth, college, open) is corrected there too with `"kind_checked": true`.
  Re-listing keeps both.

Work a season from its `missing` list, in the source order below.

## Sources, in this order

1. **sub5 itself.** The season's index page (backend/scraper_v2.py lists
   the URLs).
2. **The Internet Archive** (web.archive.org). Older captures of sub5's
   upload folders hold files sub5 later dropped. List them with the CDX API,
   for example
   `https://web.archive.org/cdx/search/cdx?url=sub5.com/wp/wp-content/uploads/2015/*&fl=timestamp,original,statuscode&collapse=urlkey`,
   and fetch the original bytes with the `id_` form:
   `https://web.archive.org/web/<timestamp>id_/<original url>`. A file
   recovered this way is a sub5 file: save it under
   `backend/data/sub5_archive/<year>/<season>/<original file name>` so the
   normal parser reads it. Keep only track and cross-country results
   (high school and middle school); skip road races, adult series and
   records lists. Go easy on the Archive: one request at a time.
3. **The meet host or timer** (school sites, Hy-Tek "results.htm" pages,
   timing companies such as Lancer, Five K Sport, Granite State Race
   Services).
4. **MileSplit** (me.milesplit.com), last. Use it when a meet is not in any
   source above, and to settle a disagreement (below).

## MileSplit rules

- Read results pages one at a time, as a person would, with the built-in
  browser or plain requests. No crawling of whole sites, no parallel
  fetches, and stop for the day if the site slows or blocks you.
- Never sign in, never work around the MileSplit Pro paywall, a captcha or
  a bot block. Results that sit behind Pro are "not found".
- A meet that exists only on MileSplit: transcribe the full results (every
  school, not only GSA) into
  `backend/data/parsed_results/<year>/<season>/ms-<slug>.json` in the parse
  format of `docs/agents/new-england-meets.md`, with
  `"parser": "milesplit-manual"` and `"source": {"site": "milesplit", "url": ...}`.
  Team scores, when MileSplit prints them, go in `team_rankings`.
  `python3 -m backend.milesplit write <slug> <year> <season>` does this
  for the layouts seen so far (see its docstring); check each file it
  writes (every individual row has athlete, school and result; relay legs
  in `athletes`) and extend it when a new layout prints NO EVENTS or ROW?.
  Progress goes in `backend/data/milesplit_progress.txt`.
- Before you write, check the meet is not already stored under another name
  (same date, same schools): `ls backend/data/parsed_results/<year>/<season>/`
  and the `date` field of the candidates.

## Discrepancies: MileSplit wins

When our parse and MileSplit disagree on a row (mark, name, school, place)
and the source file can't settle it (the sub5 file itself says what we
stored), MileSplit's version is taken: it is often corrected after the meet
(timing fixes, misassigned schools), and coaches check against it.

- Write the corrected meet as a transcription:
  `backend/data/transcribed/<year>/<season>/<stem>.json` (same format as
  `docs/agents/track-transcribe.md`; the stem is the source file's), which
  replaces the parse on the next sync. Copy every row from the parse and
  change only the rows MileSplit corrects.
- Record each change in that file's `notes`: the row before, the row after,
  and the MileSplit URL.
- A difference that is plainly MileSplit's mistake (a mark that doesn't fit
  the place order, a runner in two heats at once) is left alone and noted.

## What new data feeds (rerun before publishing)

Added or corrected results reach the site through several built products.
After ingesting, rebuild each one the new data touches, and check it:

| Product | Rebuild | Check |
|---|---|---|
| Team store, manifest, meet links | `python3 -m backend.scraper_v2 --resync-only` | `python3 -m backend.store_drift 25`: every big drop explained |
| School catalog (when seeds, rules or new school names change) | `python3 -m backend.build_school_catalog`, then the resync | new schools resolve to the right level (middle school vs high school) |
| Athlete catalog (who is the same runner) | `python3 -m backend.athlete_catalog build` and `apply` | same-team spelling pairs in the new meets (see the roster review) |
| Team-score verification, QAQC, ledger sign-offs | `python3 -m backend.routine qaqc`, `python3 -m backend.track_verify`, `python3 -m backend.meet_ledger build` and `signoff --auto` | mismatches in the new meets read and settled |
| XC course table (`ui/public/data/xc_courses.json.gz`) | `python3 -m backend.xc_course_model` | every new venue name mapped to its existing course in `backend/data/xc_course_aliases.json` (keys are the full lowercased venue as printed, e.g. "old town xc course"); compare factors with the published table and explain big moves |
| XC postseason forecast (in season) | `python3 -m backend.routine sims` | duplicate runners in each field, every team's top seven against its roster |
| Record boards, athlete pages, PRs | computed in the browser from the store | spot-check a team's board for marks that are new |
| Owen's Predictor (`ui/public/data/predictor.json.gz`) | `python3 -m backend.predictor_data`; the resync and `athlete_catalog apply` run it too | open the Predictor tab, pick an event pair the new meets cover, and confirm the athlete count grew and the line still fits the cloud (a fit that goes flat means marks outside `BOUNDS` in `backend/predictor_data.py` got through, or the bounds need widening for a real mark) |

A new source brings new names: venue strings (course aliases), school
spellings and mascots (school catalog), runner spellings (athlete catalog).
Each one is a place the new data can split from the old.

## Not found

Append one line per meet you looked for and could not find to
`backend/data/missing_meets_not_found.txt`:
`<year> <season> <meet>: <where you looked>`.

## Report

Per season: files recovered from the Archive, meets transcribed from
MileSplit, rows corrected from MileSplit (with the meet), and not found.
