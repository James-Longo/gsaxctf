# Track meet audit: reader procedure

You are checking one indoor or outdoor track meet: does the site store what
the results file says? You get a bundle directory with:

- `meta.json`: the meet key (`YEAR_SEASON_STEM`), the source file path(s)
  under `backend/data/sub5_archive/`, and the code checks' verdict
  (`verification`: verified / verified_close / mismatch / no_rankings).
- `stored.json`: every row the site stores for this meet, grouped by event
  (`Boys 100 Meter Dash`, ...): athlete, team folder, mark, grade, date.

Read the source file yourself (HTML: read the text; PDF: run
`pdftotext -layout <file> -`). Do not run the pipeline, edit any file other
than your findings, or fetch anything from the web.

## What to compare

For every event in the source (and every stored event):

1. **Rows**: every finisher with a mark should be stored once. Missing rows,
   extra rows (stored but not in the file), duplicated rows.
2. **Marks**: same mark (times to the printed precision; field marks
   feet-inches with fractions, e.g. `16-6 3/4` must not become `16-6`).
3. **Names**: same person (First Last order is fine; spelling exactly).
4. **School**: the team folder is the school the file names for the row
   (codes like `WIND` = Windham; check the file's own team list / scores).
5. **Event and gender**: right event, right sex (a boys' race stored as
   girls' is a finding); relays stored as relays.
6. **Date and level**: the meet date; a middle-school meet stored as high
   school (or the reverse) is a finding.
7. Rows that are not results at all (headers, team names as athletes,
   splits, seed marks) stored as performances.

By design, not findings: prelim and final marks are both stored (each is a
real race; the site picks the best); status rows (DQ, DNF, NH, FOUL, NM) are
stored with the status as the mark and the site's lists skip them;
exhibition (`x`) rows may be stored; a mark equal in prelims and finals is
stored once. A prelim mark stored *instead of* a final is a finding, and so
is a final (or a DQ'd athlete's status row) that is missing. Ignore display
formatting (e.g. `9:50.70` vs `9:50.7`).

## Findings file

Write `<bundle>/findings.json`:

```json
{
  "key": "2016_Outdoor_BucksportMeet",
  "verdict": "clean | minor | major | unreadable",
  "rows_in_file": 212,
  "rows_stored": 212,
  "findings": [
    {"kind": "missing_row | extra_row | duplicate_row | wrong_mark | wrong_name |
              wrong_school | wrong_event | wrong_gender | wrong_date | wrong_level |
              not_a_result | other",
     "event": "Boys Long Jump",
     "rows": 1,
     "file": "Ramsay, Ian  GSA  16-6 3/4",
     "stored": "Ian Ramsay  George_Stevens_Academy  16-6",
     "pattern": "inch fractions dropped"}
  ],
  "notes": "one or two sentences on anything systematic"
}
```

`rows` is how many rows the finding covers (group identical problems:
"every GSA row in this file is filed under Windsor" is one finding with
rows = 40, not 40 findings). `pattern` names the cause when it is clear.
Verdict: clean = no findings; minor = a few rows; major = a whole event,
team, or more than 5% of rows wrong; unreadable = you could not read the
source.

Be exact and quote the file. Don't guess: if you can't tell which is right,
say so in `notes`.

## After the audit

A pattern shared by many files is a parser fix. A file in a one-off layout
that no parser reads (a coach's score sheet, an event grid) is transcribed
by hand instead: `docs/agents/track-transcribe.md`, written to
`backend/data/transcribed/`, which the pipeline prefers over any parse.

**Sign off what is right.** Which files to audit comes from
`python3 -m backend.meet_ledger review [N] [--season <year>/<season>]`
(changed sign-offs first, then suspect, then unverified). A file whose
stored rows you have checked against the source, row by row, and found
complete and correct (after any fix and re-parse) is signed off:
`python3 -m backend.meet_ledger signoff <parsed path> --by "<reviewer> <date>" --evidence "<what you compared>"`.
It is then never audited again unless its source or its parse changes.
