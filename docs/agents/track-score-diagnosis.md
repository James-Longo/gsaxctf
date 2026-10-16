# Track score mismatch: reader procedure

The code re-scores every track meet that prints official team scores
(`backend/track_verify.py`) and compares. You get one meet where they
disagree and find out **why**. The answer decides what gets fixed: the
parser, the scoring rules the checker knows, or nothing (the file's own
scores are wrong).

Your bundle directory has `meta.json`:

- `key`, `source_files` (under `backend/data/sub5_archive/`), `parsed`
  (our parse of the file: events -> rows with athlete, school, result,
  place, points)
- `verification`: the checker's best fit (`scoring_system`: `printed` =
  the points printed on each row summed per team, or a points table such as
  `10-8-6-4-2-1/3` = top 6 score, at most 3 per team) and the `worst` teams
  (official vs computed)

Read the source file (HTML: read it; PDF: `pdftotext -layout <file> -`) and
the parse. Do not edit anything except your diagnosis, do not run the
pipeline, do not use the web.

## What to find

Work from the worst teams: where do their points come from in the file, and
which of those rows or points are missing, extra or different in the parse?
Typical causes (name the one that fits, or describe a new one):

- `parse_missing_rows` rows / events / pages the parser lost
- `parse_wrong_school` rows filed under another team (or the official team
  name is not recognised as the same school)
- `parse_wrong_event` an event merged with another, or split
- `parse_points` printed points read wrong (column, ties "2.50")
- `scoring_divisions` the meet is scored in divisions / sections / several
  small meets inside one file (e.g. SMAA weekly meets scored as duals)
- `scoring_rules` other rules: places scored, per-team limits, relays,
  JV/exhibition not scoring, field-event ties
- `scores_block` the official scores are misread or belong to another meet
- `source_error` the file's own scores disagree with its own results
- `other`

## Diagnosis file

Write `<bundle>/diagnosis.json`:

```json
{
  "key": "2009_Indoor_smaachampsboys",
  "cause": "scoring_divisions",
  "confidence": "high | medium | low",
  "evidence": "Quote the file: the scores block header and two or three rows that show it.",
  "fix": "What would make the check pass: the parser change or the scoring rule, concretely.",
  "rows_affected": 40
}
```

Several causes: list the main one in `cause` and the rest in `evidence`.
Be exact and quote the file; say so when you can't tell.
