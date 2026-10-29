# XC course registry review: agent procedure

The XC course table (`backend/xc_course_model.py`, published as
`ui/public/data/xc_courses.json.gz`) folds venue spellings together by rule:
"Thornton" and "Thornton Academy", "Mt. Ararat XC course" and "Mt. Ararat".
A rule cannot tell when two different names are one place, or one name two
places. That takes reading the evidence, and this pass does it once. After
it, only new venue names need a look (the "What new data feeds" checklist in
`docs/agents/missing-meets.md` asks for each one to be mapped).

James can't answer course questions. Decide from evidence; don't queue
questions for him.

## Input

`python3 -m backend.xc_course_review` writes `backend/data/xc_course_review.json`:
batches of venues, each with:

- `courses`: the published course labels at that venue (venue + distance,
  sometimes an era) with factor, standard error, races and seasons
- `raw_names`: every venue string the store holds for it, with row counts
- `top_teams`: the teams that race there most (the host is usually first)
- `meets`: each meet with its sub5 index venue and its file-header venue
- `pairs`: candidate same-course pairs decided in this batch (a pair lives in
  the batch of its first venue), with evidence: `header` (one meet's index
  venue and header venue disagree) or `factor` (factors agree within 3.8%,
  one side has one or two races, and the venues share regular teams; weak
  on its own)
- `partners`: short cards for pair partners that live in another batch
- `flagged`: the venues that need a decision (in a pair, or a course with
  one or two races, which is usually a spelling or a distance label that
  belongs to another course); the rest of the batch is context

The batches are independent: one reviewer per batch.

## Leads found while building the list (2026-10-29)

- Likely one course, two names: Gull Crest Field / Cape Elizabeth;
  Fort Foster / Kittery / Traip Academy; Norway (Roberts Farm) / Oxford Hills
  (see `xc_course_changes.json`); East Corinth / Central; Saxl Park / Bangor;
  Center Drive School / Orrington; Royal River Park / Yarmouth (?);
  Pownal Road Recreation Field / Freeport (?); Mt A XC - Highland Green GC /
  Mt. Ararat (a new course, or the same one?).
- Likely two courses at one school: Brunswick's Spring Brook Farm and
  Crystal Spring Farm; Mt. Blue High School and Mt. Blue State Park (already
  kept apart, factors differ 6-7%).
- The index overrides the header: `2013/XC/traip_sept27` is now York (index)
  where its file says Traip; `Vaughan Woods Course (Marshwood)` (2013) is now
  Marshwood. Check that both headers agree.
- Middle-school course names (`<school> MS XC Course`) are kept apart from
  the school's high-school course by rule. Where high-school meets are run on
  them (Gray New Gloucester MS 2024-26, OOB MS 2023/2025, Massabesic MS
  2026), decide whether the loop is the high-school course.
- Distance labels after merges: GSA (Blue Hill) is now labelled 2.92 mi and
  Mattanawcook Academy 2.98 mi, because the larger-evidence node won. Check
  each course's real distance from headers; only the label changes.
- Era boundaries moved with the 2013-14 data: Waterville (5K, 2003-2016) and
  Maranacook (5K, 2004-2018). Quarry Road (Waterville) starts 2018. Confirm
  or add the change to `xc_course_changes.json` with a source.
- `Hyde School (Bath)` split into 2006-2008 (1.02) and 2015+ (1.10) once
  "Hyde XC" folded in: check whether Hyde changed course.

## Evidence, best first

1. The result file's own header (`backend/data/sub5_archive/<year>/XC/`):
   "LOC: Roberts Farm", "Gull Crest Field, Cape Elizabeth". For MileSplit
   files, the course field of the meet page.
2. The sub5 index row (meet name and LOCATION column).
3. Who hosts: a dual meet's host is the venue school; the meet name often
   says "at ...".
4. A public source about the course (school athletics page, land trust,
   news item), cited with its URL.
5. Factors. Agreement supports a merge but never proves it (many courses
   rate near 1.00); a disagreement beyond 3.8% says two courses, or a
   course change (see `backend/data/xc_course_changes.json`).

## Decisions and where they go

| Decision | Write it to |
|---|---|
| Two names, one course | `backend/data/xc_course_aliases.json`: the full lowercased venue string as printed → the display name of the course it belongs to |
| A venue string that names no place (meet label, file name) | the same file, mapped to `""` (excluded), or to the real venue when the file says it |
| One meet's venue is wrong | `backend/manual_fixes.json` `venue_corrections`: `{"file": "<year>/XC/<stem>", "venue": ..., "source": "<the header line or URL>"}` |
| A course changed layout in a known season | `backend/data/xc_course_changes.json`, with its source |
| Confirmed distinct (two places at one school, e.g. Brunswick's Spring Brook Farm and Crystal Spring Farm) | a `distinct` note in the batch's sign-off, so it isn't asked again |

A middle-school course name ("Gray New Gloucester MS XC Course") stays
separate from the high-school course unless the evidence says the two are
the same loop. Merge it with an alias if it is.

Record each batch's decisions with their evidence in
`backend/data/audit_log.json` (same shape as the older-data loop's entries).

## After each batch

Rebuild and check, as in `docs/agents/missing-meets.md` ("What new data
feeds"):

1. `python3 -m backend.scraper_v2 --resync-only` (only if `venue_corrections` changed)
2. `python3 -m backend.xc_course_model`: every merged pair now has one
   label; compare factors with the published table and explain moves over 2%
3. `python3 -m backend.routine sims`: every meet in `backend/data/xc_groups.json`
   still names a course that exists
4. Commit the named files and push.
