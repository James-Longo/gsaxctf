# Athlete identity review: agent procedure

The athlete catalog (`backend/athlete_catalog.py`) decides which printed names
are the same runner. It works in two layers, like the scraper and parser:

1. **Code** (`build`) merges spellings automatically when the evidence is
   clean: case, punctuation, word order, a rare-letter typo, a name cut off at
   a column width, a dropped leading letter, and never when the two spellings
   ran in the same race. Everything uncertain goes to a review queue.
2. **Review** (this procedure): an agent reads each queued pair's actual
   results side by side and decides **same**, **different** or **unsure**.
   Decisions are stored in `backend/data/athlete_decisions.json`, are
   permanent, and override the code layer. This is athlete-identity QAQC.

Use a **Sonnet** model for reviewers (cheaper; the task is reading tables, not
deep reasoning), about 20 pairs per reviewer.

## Steps (orchestrator)

1. `python3 -m backend.athlete_catalog build` (refreshes the queue).
2. `python3 -m backend.athlete_catalog review-export --batches N --size 20 --out <dir>`
   writes `batch_001.json` ... Each pair has both spellings' results (season,
   date, meet, event, mark, grade, team) and the code layer's evidence.
3. One Sonnet reviewer per batch, with the reviewer instructions below. Each
   writes `<dir>/decisions_NNN.json`.
4. Spot-check: read 5 of each reviewer's decisions yourself against the
   results. If any is clearly wrong, discard that batch and rerun it.
5. `python3 -m backend.athlete_catalog review-import <dir>/decisions_*.json --by "sonnet review <date>"`
   ("unsure" is recorded too: agents don't see the pair again, and it is
   listed for James by `review-export --unsure`.)
6. `python3 -m backend.athlete_catalog build` then `apply` (PR flags and the
   athlete registry follow the new decisions).

James can overrule any decision by editing `athlete_decisions.json` (set
`decision` and `by`), or by importing a file with `--by "James Longo"`.

## Reviewer instructions

You decide whether two printed names at one school are the same runner.
Read the batch file. For each pair, compare side A and side B.

**Strong evidence they are DIFFERENT people**
- They ran in the same race (same meet, same event, same day). A runner
  cannot finish one race twice. (The code layer already rejects these, but
  check same-meet different-event too: plausible for one runner, but for a
  sibling pair it is a sign of two people.)
- Grades that cannot belong to one person (one is a senior the same season
  the other is a freshman; class years more than one apart with several
  graded rows each).
- Different first names that are both ordinary names (Hayley / Hailey can be
  a typo; William / Liam with the same surname can be brothers). Same
  surname, both common first names, overlapping seasons: lean different
  unless the results line up perfectly as one career.

**Evidence they are the SAME runner**
- One spelling fills a gap in the other's career: same events, marks in line
  with the weeks before and after, consistent grade progression.
- The odd spelling appears once or twice, in a meet where the usual spelling
  is absent.
- Typical variants: a letter swapped or doubled, a nickname (Will/William),
  an initial (J Smith), a dropped middle or second surname, a name cut off,
  first and last reversed.

**Middle school and high school.** A school's middle-school and high-school
runners can share one team. A career spanning grades 7 through 12 on one team
is normal, not a sign of two people. Check that grades increase by one per
academic year (fall cross country belongs to the following spring's year).

**When unsure, say unsure.** A wrong merge (two people joined) is worse than a
missed one, and both "same" and "different" are permanent.

- Say **different** only with positive evidence of two people: they ran the
  same race, their grades cannot be one person's, or they overlap in time
  with unrelated events and marks. Seasons that simply don't overlap (John
  2019-21, Jack from 2022) are not evidence of two people -- that is unsure.
- Say **same** for an initial-only or one-token name ("R Barry", "Sanborn")
  only when several of its results line up with the full name's career. A
  single initial-only row is unsure.

Write `decisions_NNN.json`:

```json
{"decisions": [
  {"pair": "<the pair string, copied exactly>", "decision": "same|different|unsure",
   "reason": "one sentence citing the deciding evidence"}
]}
```

Copy each `pair` string exactly. Decide every pair in the batch.
