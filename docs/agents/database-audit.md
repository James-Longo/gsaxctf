# Database audit: agent procedure

The parsers make the first read of every result file. This is the second
read: a reader checks the parse against the source, row by row, for every
file that is not yet `certain` (backend/meet_ledger.py). The most recent year
goes first: 2026 is made perfect, then 2025, and so on back. The routine
runs it after each week's new results are in (docs/agents/update-routine.md,
step 6).

    python3 -m backend.db_audit progress          certain / left per year
    python3 -m backend.db_audit queue --n 20      the next files, newest first
    python3 -m backend.db_audit show <path>       the source text, then the parse
    python3 -m backend.db_audit record <path> --verdict <v> --by "<who>" --notes "<evidence>"

## Orchestrator (the routine)

1. First apply what earlier reviews found: `python3 -m backend.db_audit fixes`
   lists the `fixed` verdicts whose fix hasn't reached the parse yet (parser
   patterns, school codes, transcription overrides still to write). Do them
   (step 4's rules), rebuild, and those files come back to the queue for a
   final `confirmed`. Then `python3 -m backend.meet_ledger build` and
   `db_audit queue --n 60`.
2. Split the list into 3 batches of 20 and give each to a **Sonnet** reviewer
   with the reviewer instructions below (Agent tool, model "sonnet"). Run at
   most 3 at a time.
3. Spot-check 3 verdicts per batch against `show`. A batch with a wrong
   `confirmed` is rerun.
4. Apply what the reviewers report for the code: parser patterns (fix with a
   test, re-parse only the files concerned, compare kept rows per canonical
   event; docs/agents/track-score-diagnosis.md and backend/tools/README.md),
   per-meet school codes (backend/school_catalog_seed.py FILE_RULES with
   evidence, or backend/data/milesplit_codes.json for ms- files), then rebuild
   what the changes feed (docs/agents/missing-meets.md, "What new data feeds").
5. Report: files audited per verdict, `db_audit progress` for the current and
   last two years, the parser fixes, and the `james` items.

## Reviewer instructions

For each file in your list, run `python3 -m backend.db_audit show <path>` and
compare the parse with the source, every row:

- every result row in the source is in the parse, and nothing else is (no
  headers, team-score lines or page furniture read as runners);
- place, name, school, grade and mark agree (the parse may reorder "Last,
  First", expand a school code, and drop a points column: those are fine);
- each race is the right event, gender, distance and division; varsity and JV,
  boys and girls, classes and heats are not merged or swapped;
- the school's catalog id (after "->") is the school the source means; "?" is
  an unidentified school;
- team scores in the parse are the ones the source prints.

Then record one verdict with the evidence in `--notes` (quote the source lines
that settle it):

- **confirmed**: the parse matches the source. Warnings that the source
  explains are fine: a mark flagged as implausible that the source prints
  (real athletes do have great and bad days), team scores the sheet's own
  rows don't reproduce. Say which.
- **fixed**: the parse was wrong. For a one-off error, write a transcription
  override, `backend/data/transcribed/<year>/<season>/<stem>.json`, in the
  format of docs/agents/track-transcribe.md: copy every row of the parse and
  change only the wrong ones, listing each change in its `notes`. The file
  returns to the queue once the store is rebuilt, for a final `confirmed`.
  For an error that looks like a parser pattern, or a school code that needs
  a per-meet rule, do not edit code: describe it in `--notes` (the layout,
  the lines, what it should be) and in your final reply.
- **source-error**: the parse matches the source, and the source itself is
  wrong (times out of place order, team scores that don't add up, a runner
  listed twice). Quote the lines.
- **james**: something only James can settle (a school string two schools
  could be, a meet that may not be a school meet). Say exactly what to ask.

Rules: never drop or change a row because a flag says so; never guess a
school (a string that two schools could be stays "?" and goes to `james`);
college results are excluded anyway; a wrong `confirmed` is worse than a
`james`. Do not edit parsers, the school catalog or the store. Final reply:
counts per verdict, then one line per parser pattern or school code found
(file, lines, what it should be).
