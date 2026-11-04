# Grade review: agent procedure

A result with no printed grade gets `grade_est` from the runner's class year
(`athlete_catalog.settle_class`). A class year settles by rule when every
printed grade names the same year, when one meet alone disagrees (the rest
outvote it), or when the runner has four different high-school years (the
last is senior year), and every season fits grades 3-12 (3-8 at a middle
school). Otherwise the runner is a case in
`backend/data/grade_review_queue.json` (rebuilt by `athlete_catalog apply`,
so by every resync), and a Sonnet agent decides it.

## A case

`issue` is `grades disagree` or `grade out of range`. `votes` counts printed
grades per class year they imply (grade 11 in fall 2019 XC or spring 2020
track is class of 2021). `graded` lists every row with a printed grade;
`ungraded` counts the rest by year, season and team.

## Deciding

Decide each case from its rows, opening the source file
(`backend/data/parsed_results/...`, the meet name is the file) or MileSplit
page only when the rows don't settle it. Use common sense:

- **A misprint**: one class year has most of the rows and the others are a
  stray row or a meet that printed everyone a year off (check the meet's
  other runners: if the whole sheet is off, it is the sheet). Decide that
  year.
- **Two runners on one profile**: the same name at one school in two eras
  (a career longer than a school's grades, class years far apart, marks of
  two different levels). Decide both class years; each row gets the grade
  that fits its season. Say "two runners" in the reason; identity is fixed
  separately.
- **Repeated a grade or reclassified**: grades that go 9, 10, 10, 11 across
  seasons with every source agreeing are real. Decide the class year of the
  latest seasons.
- **Can't tell**: two or three rows, split evenly, no source to break the
  tie. Decide `unsure`; the case comes back if new printed grades arrive.

Write `{"decisions": [{"id": ..., "decision": "class", "class_of": [2021],
"reason": "..."}]}` (`"decision": "unsure"` with no `class_of` when unsure),
one short reason each naming the evidence. Import with
`python3 -m backend.athlete_catalog class-import <files> --by "sonnet grade review YYYY-MM-DD"`;
the next `build` and `apply` fill the grades. A decision holds while the
runner's most-printed class year is among its years.

## Pacing

The Monday routine reviews the cases among the season in progress's
runners. The backlog of older careers belongs to the older-data process,
in batches of about 40 cases per agent.
