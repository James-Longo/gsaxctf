# Athlete roster review: agent procedure

The athlete catalog (`backend/athlete_catalog.py`) merges obvious spelling
variants by itself and queues the uncertain pairs. The pair reviewer
(`athlete-review.md`) sees two names at a time. This procedure gives one
reviewer a whole roster -- one school, one gender, every season -- so a
name can be judged against everyone else on the team: a brother who
arrives the year another runner graduates, three spellings of one girl
across four seasons, a freshman who is plainly someone new.

Use a **Sonnet** model, one roster per reviewer.

## Steps (orchestrator)

1. `python3 -m backend.athlete_catalog build` (refreshes the queue).
2. `python3 -m backend.athlete_catalog roster-export --out <dir> "me-hs-gsa|Boys" ...`
   writes `<dir>/me-hs-gsa_Boys.json` per roster.
3. One Sonnet reviewer per roster file with the instructions below. Each
   writes `<dir>/decisions_<roster file name>`.
4. Spot-check 5 decisions per roster against the results; a roster with a
   clearly wrong decision is rerun.
5. `python3 -m backend.athlete_catalog review-import <dir>/decisions_*.json --by "sonnet roster review <date>"`
   (imports `decisions`; `suggested` pairs are read by the orchestrator, who
   adds the sound ones to the queue logic or to a later review).
6. `build` then `apply`.

## Reviewer instructions

The roster file has:

- `names`: every name printed for this team, each with its `career`, one
  line per season: grades, number of results, first and last date, best mark
  in its most-raced events (`"5000 Meter Run CC 19:42.50 x6"`), and the
  team label when more than one.
- `queued_pairs`: pairs the code thinks may be one runner, each with the
  relation (nickname, typo_last, initial ...), evidence, and both sides'
  results.

**Decide every queued pair** with the rules in
`docs/agents/athlete-review.md` (section "Reviewer instructions": evidence
for different and for same, middle school and high school, and "when
unsure, say unsure"). Use the whole roster: who else has that surname, which
seasons each name covers, whether a variant fills a gap in one career.

**Surname-only ("Sanborn") and initial ("J Smith") names: work them out
from the roster.** The code has already merged the ones where only one
runner fits. What reaches you has two or more candidates (siblings, a
father and son decades apart) or a gap in the seasons. Decide by context:
which candidate was on the team that season, in that grade band, running
that event at that level (a 6-02 high jump is the high jumper, not his
distance-running brother; a 2:05 800 is the 800 runner). One row is enough
when only one candidate fits it. Say `unsure` only when two candidates both
fit, or none does. This rule replaces "a single initial-only row is unsure"
in athlete-review.md.

**Then read the roster for misses**: two names on this roster that are one
runner but are not in `queued_pairs` (a nickname the code doesn't know, a
swapped first/last, a hyphenated surname printed half). List them under
`suggested`, only with real evidence (one career's gap filled, same events
and marks, consistent grades, never in the same race).

Write `decisions_<roster file name>` next to the roster file:

```json
{"roster": "me-hs-gsa|Boys",
 "decisions": [
   {"pair": "<pair string, copied exactly>", "decision": "same|different|unsure",
    "reason": "one sentence citing the deciding evidence"}
 ],
 "suggested": [
   {"a": "<name as printed>", "b": "<name as printed>", "reason": "the evidence"}
 ]}
```

A wrong merge (two people joined) is worse than a missed one: when unsure,
say unsure. Final reply: one line with counts of same / different / unsure /
suggested.
