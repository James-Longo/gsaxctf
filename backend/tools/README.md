# Maintenance tools

## reparse/ (re-parse safety, see memory reparse-safety.md)
- `run_all.py <outdir>`: parse every Indoor/Outdoor archive file with the current code into
  `<outdir>/<year>/<season>/<stem>.json` (12 workers, ~25 min). Run with `python3 -I`.
  .htm/.pdf pairs both land on `<stem>.json`, so ~24 files show false diffs.
- `compare2.py <before> <after>`: compare rows the sync KEEPS per canonical event
  (event_canon.canonical_event). Use this, not raw row counts.
- `apply3.py`: write changed parses into parsed_results. Files whose stored parse equals the
  baseline are copied straight over; the rest are re-parsed under their real output names and
  compared per event with the committed parse.
- `drift_by_meet.py`: lost/gained rows per meet, HEAD store vs working store, net loss outside meet_scope.
- `bisect_one.py`: parse one file with a given code root (e.g. a `git archive HEAD backend` copy with
  patches applied one at a time).
- `scan_bounds.py`: track rows outside predictor BOUNDS, by meet.

Never force-reparse a whole season folder: some stored parses came from older parser paths. (2011
Outdoor winthrop_april28 / leavitt_may11 parsed worse from e0da7ae68 on, when the column parser began
winning RaceTab files with only their running events; fixed by reading RaceTab "Team ... Time" relay
and "Mark" field headers.) The tools resolve the repo from their own path, so they also work in a
git worktree.

## mislabel_2026-10-17/
Diagnoses and proposed patches from the 2026-10-17 mislabeled-event agents. All but the ones listed below were applied in
9be6c3ac9 / 12c6b04dc (sections_a_1 included: it was reverted once by mistake, then restored after bisecting).
NOT applied, on purpose: sections_a_2 and sections_b_7 (age-group rows now go to the summer data),
sections_a_5 (James keeps field-relay team totals), sections_b_3 ("- TM" relay flag),
ne_relays_4 (name-only is_team_label extension), sections_b_1 (narrower column split),
sections_b_6 (ne_relays_1 covers it).
