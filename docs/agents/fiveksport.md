# Five K Sport results: agent procedure

Five K Sport (5K Sports Race Management) times western and coastal Maine cross
country meets: WMC schools, Poland, Maine Coast, Falmouth, Greely. sub5.com
does not carry most of them. Results are posted on
`https://fiveksport.com/race-results-{year}` as Word documents shared from the
timer's personal OneDrive.

This needs an agent with a **browser tool**. Plain HTTP downloads of the
OneDrive files are refused ("The request is blocked"), and we do not work
around that block. A browser opening the share link the way any visitor does
works fine, and needs no person in the loop: no clicking through menus, no
downloads, no clipboard, and the browser pane does not have to be on screen.

Code: `backend/fiveksport.py`. Archive: `backend/data/fiveks_archive/`
(`index.json` + `{year}/XC/*.txt`). Tests: `python3 backend/tests/test_fiveksport.py`.

## Steps

1. **List what to fetch.**
   `python3 -m backend.fiveksport pending {year}` prints JSON rows
   `{label, url, file_id, page_meet, status, ...}`. `status` is `new` (not
   archived) or `recheck` (archived before the completeness check existed; the
   row carries `archived_content_sha`). The season page itself is fetched over
   plain HTTP (its robots.txt allows it). An empty list means nothing to do.

2. **Fetch each file in the browser.** Results files before team-score files
   (team sheets are paired to results by content). With the built-in browser
   (`mcp__Claude_Browser__*`):
   1. `resize_window` to **1000 x 3000** on the tab, once per turn (the app
      clears an emulated size when a turn ends). Word only lays out pages that
      fit the viewport; with the pane hidden or small (800 x 220 was seen) it
      lays out page 1 and stops.
   2. `navigate` to the row's `url`, **exactly as printed**. Never retype or
      shorten a URL; a wrong link lands on an OneDrive "Error" page.
   3. wait ~5 s. The tab title becomes the document name
      (e.g. "Poland Boys Results.docx").
   4. `javascript_tool`: run `OPEN_VIEWER_JS` from `backend/fiveksport.py`. The
      OneDrive page loads the Word viewer into a cross-site frame whose text
      cannot be read; this re-targets the viewer's own form so the viewer
      becomes the whole tab. Expect `{ok: true, filename: ...}`.
   5. wait ~8 s. The tab is now `word-edit.officeapps.live.com` titled "Word".
   6. `javascript_tool`: run `EXTRACT_JS` (takes 5-30 s). It scrolls until the
      laid-out pages stop changing, opens Word's own **Document stats** dialog
      (which counts the whole file whether or not the pane is visible), and
      returns `{rendered_pages, empty_pages, doc_stats, sha256, content_sha,
      text}`. `doc_stats` must not be null; if it is, run it again.

   Steps 2-6 batch well in one `browser_batch` call; three files per batch is
   fine.

3. **Save.**
   - `status: recheck` and `content_sha` equals `archived_content_sha`: the
     document is unchanged. Save **without** the text:
     `{file_id, url, label, year, page_meet, content_sha, doc_stats, rendered_pages}`.
     `save` checks the archived copy against Word's count.
   - Otherwise write a JSON file merging the inventory row with the
     `EXTRACT_JS` output **copied verbatim**, then
     `python3 -m backend.fiveksport save < that.json`.

   `save` refuses:
   - text whose `sha256` doesn't match (one character changed in transit:
     extract again, don't hand-edit);
   - text that doesn't account for Word's character count (truncated
     extraction: reload with the tall viewport and extract again);
   - a payload with no `doc_stats`.

   It prints the archived path, `duplicate of …` (the same document already
   archived under another link) or `unchanged, complete`.

4. **Parse, verify, sync.**
   `python3 -m backend.fiveksport sync {year}` reads the archive with the
   Five K Sport reader, writes `parsed_results/{year}/XC/fiveks-*.json`, runs
   team-score verification, and adds the meets to the store through the normal
   sync (school catalog, double-ingest guard). Every high-school results file
   with a paired team sheet must say `verified`. If a re-extraction changed a
   file's rows, `parse` un-marks that meet so the sync adds the new rows.

5. **Report** what was added, anything refused, and any `mismatch`. A mismatch
   is either a reader bug or a source error; read the archived `.txt` by hand
   to tell which (see "Truncated extraction" below for the one seen so far).

## Rules learned the hard way

- **Truncated extraction (2026-10-15).** Falmouth boys 2025 is two pages (62
  finishers). The first archive held 43: the viewer reported "Page 1 of 1"
  before it had laid out page 2, and the old page-count check believed it.
  Team-score verification caught it, because Windham's 5th-7th runners were
  missing. The completeness gate is now Word's own Document stats count
  ("characters, no spaces"). Calibrated on all 16 archived files: the
  extracted text matches it exactly, or is short by the 5 characters of a
  "Page 1" header field the viewer sometimes doesn't render. A lost result
  line is 25+ characters. The status bar ("Page x of N", "W words") stays empty
  while the browser pane is hidden, so it is not used.
- **The rendered text is not byte-stable.** The "Page N" header field and a
  "Page Break" marker appear on some loads and not others. `sha256` (the exact
  text) only proves the copy reached `save` intact. Document identity is
  `content_sha`: non-blank lines other than those markers. Both the browser
  and `fiveksport.content_sha` compute it.
- **Multi-page sheets repeat the header** on every page. The reader only takes
  rows whose time cell is a real finish time (the phone-number line once
  sliced into a fake row).
- **A file's identity comes from its own header, never from the page.** The
  site reuses links. One "Girls Results" file appears under three meets (a
  high-school meet, a middle-school meet and a Nordic race). Poland's 9/18 and
  9/30 entries link the same files, which are dated 9/30 inside. Files are
  keyed by OneDrive item id, so a reused link is fetched once.
- **The timer overwrites last year's Word files.** In October 2026 the 2025
  page's Poland and Maine Coast links already held the 2026 documents, so the
  2025 Poland results are lost. Archive each season promptly; run this weekly
  in season. A saved document that matches an archived one becomes a
  `duplicate_of` alias. If a link already archived later holds a different
  race, `save` keeps the earlier document under `{file_id}@{date}`.
- **Middle-school races sit under high-school headings.** A document titled
  "... Middle School ..." is archived with `level: ms` (so it isn't refetched)
  and never synced.
- **Team-score sheets have no header** (no meet, date or gender). `save` pairs
  each one to the single archived results file of that season that contains its
  runners (names compared on their first 14 characters, because results cut
  names to the column width). If no results file matches, it is archived as
  `level: unpaired` and never synced.
- **Deliberately skipped files.** A payload with `skip: "<reason>"` (plus
  `sha256`/`content_sha` and a short `head`) records a file that was read and
  deliberately not archived, so it isn't fetched again. This was used for
  2025-linked sheets that turned out to be 2026 middle-school or orphaned team
  sheets. Plain `save` handles these cases too (as `ms` or `unpaired`), so
  `skip` is optional.
- **Results layout:** fixed width with a `=====` ruler under
  `Place TmPl No. Name Yr School Time`. Columns are cut by ruler position, so a
  blank team-place or year cell stays blank. (The generic parser let the bib
  number slide into team place.)
- **Team-score layout:** `N. Team` then `p1 p2 p3 p4 p5 (p6) (p7) = total`,
  with team places; the bracketed displacers don't count toward the total.
- **Distances are not printed.** High-school races default to 5K, like sub5
  files with no distance.
- **2024 is gone.** That season's page links files on `nebula.wsimg.com`, which
  now answer `410 invalid-access-key-id`. 2025 onward is on OneDrive.

## Archive state (2026-10-15)

| Season | High-school results archived and synced | Verified against team sheet |
|---|---|---|
| 2025 | Greely boys and girls (9/26), Falmouth boys and girls (10/10) | all 4 |
| 2026 | Poland Regional boys and girls (9/30), Maine Coast boys (9/18) | Poland 2 of 2; Maine Coast has no team sheet linked |

Known gaps:
- 2025 Poland Regional and 2025 Maine Coast: their links now hold 2026
  documents; the 2025 races are lost.
- 2026 Maine Coast HS **girls** results and HS **boys** team scores are not
  linked anywhere; the page's links for them point at middle-school files.
- 2026 Poland Regional (9/30) is in the store but dropped by the course model's
  outlier-season check: its runners ran ~14% slower than the 2006-2018
  "Poland" course predicts (the same Traip runners were ~3% slower than at
  Freeport). The header names only the town, and the historical "Poland" key
  pools several Poland-hosted meets, so the 2026 course is likely a different
  layout or distance. Undecided: give it its own course key.

## Running it as a routine

The weekly GitHub Action cannot do step 2. Five K Sport needs a scheduled
**Claude routine** (an agent with a browser tool) that runs steps 1-5 for the
current season and reports what it added. The routine must run where a
browser tool exists: a desktop-app scheduled task, or a cloud session linked
to a computer with the desktop app open. The browser pane does not need to be
visible (step 2.1 covers that). The sub5 scrape can stay in the Action or move
into the same routine.
