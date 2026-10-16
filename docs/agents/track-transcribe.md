# Track transcription: reader procedure

Some indoor/outdoor result files are one-off layouts no parser reads: a
coach's score sheet (top 3-5 per event, surname and school code, "HH: K.
Pierpont TA 16.5; Biasin TA 16.8"), a grid with events side by side, a
newspaper-style paragraph. You copy one such file, by hand, into the
parse format. The pipeline then uses your copy instead of a parser
(`load_transcription` in `backend/scraper_v2.py`), so it must hold exactly
what the file says.

You get a source file (under `backend/data/sub5_archive/<year>/<season>/`).
Read all of it (HTML: read it; PDF: `pdftotext -layout <file> -`). Do not
edit anything but your transcription, do not run the pipeline, do not use
the web.

## Write

`backend/data/transcribed/<year>/<season>/<stem>.json` (stem = the source
file name without its extension):

```json
{
  "source": "backend/data/sub5_archive/2005/Outdoor/massabesic5_19g.htm",
  "meet_name": "Thornton Academy, Bonny Eagle, Biddeford at Massabesic",
  "date": "2005-05-19",
  "school_codes": {"TA": "Thornton Academy", "BE": "Bonny Eagle", "M": "Massabesic", "B": "Biddeford"},
  "events": [
    {"event": "100 Meter Hurdles", "gender": "Girls", "is_relay": false,
     "results": [
       {"place": 1, "athlete": "K. Pierpont", "school": "Thornton Academy", "result": "16.5", "grade": ""},
       {"place": 2, "athlete": "Biasin", "school": "Thornton Academy", "result": "16.8", "grade": ""}
     ]},
    {"event": "4x400 Meter Relay", "gender": "Girls", "is_relay": true,
     "results": [
       {"place": 1, "school": "Thornton Academy", "result": "4:24.1", "athletes": []}
     ]}
  ],
  "team_rankings": [
    {"gender": "Girls", "teams": [{"rank": 1, "team": "Thornton Academy", "score": 116},
                                  {"rank": 2, "team": "Massabesic", "score": 80}]}
  ],
  "notes": "Anything you could not read or had to decide: say which row and why."
}
```

## Rules

- **Every result row in the file**, in the file's order, nothing invented.
  A row with no mark is left out; a row marked DQ/DNF/NH/FOUL/ND/NT keeps
  that status as its `result` with `place` null.
- **Names as printed.** A surname alone stays a surname ("Biasin"); an
  initial stays ("K. Pierpont"). Fix only obvious line-wrap damage
  ("ers/FAL" for "Piers/FAL") and say so in `notes`.
- **Schools:** the full name when the file says what a code means (a
  legend, the title "Westbrook, Sanford at Thornton Academy", a team score
  line) or when it is unambiguous among the meet's teams; put each code you
  expanded in `school_codes`. A code you cannot tie to a team stays as
  printed and goes in `notes`. Never guess between two schools.
- **Events:** the standard names: "100 Meter Dash", "200 Meter Dash",
  "400 Meter Dash", "800 Meter Run", "1600 Meter Run", "3200 Meter Run",
  "1 Mile Run", "2 Mile Run", "100 Meter Hurdles" (girls HH), "110 Meter
  Hurdles" (boys HH), "300 Meter Hurdles", "55 Meter Dash", "55 Meter
  Hurdles", "1600 Meter Race Walk", "4x100 Meter Relay", "4x400 Meter
  Relay", "4x800 Meter Relay", "High Jump", "Long Jump", "Triple Jump",
  "Pole Vault", "Shot Put", "Discus", "Javelin". A "1600 relay" is the
  4x400, a "3200 relay" the 4x800, a "400 relay" the 4x100. Anything else:
  the file's own name.
- **Gender** per event: from the file (title, "Girls" header, file name
  "...g.htm" / "...girls..."). Both sexes in one file: two events.
- **Marks** exactly as printed, normalised only in form: times "13.4",
  "2:38.5", "11:06.8"; field marks feet-inches "16-03", "35-02.5",
  "97-05" (from 16' 3", 35' 2.5", 97' 5). A typo you can read for sure
  ("6;21.1") is written correctly and listed in `notes`; a mark you can't
  read for sure is left as printed and listed.
- **Spreadsheet marks.** A field mark printed with a dot is feet.inches
  when the sheet shows it ("117.11" can only be 117' 11"): write
  "117-11". Times a spreadsheet mangled ("00:11.58" for 11.58, "16:48min"
  for 16.48) are written as the time they mean, listed in `notes`. A row
  whose mark you cannot read at all ("1min.3sec", an 800 in "23.8") is
  left out and listed.
- **A row with no name** (an unnamed tie, "3 way tie @ 4'6") is left out.
- **Date** from the file (title, header). None in the file: the date in
  the file name if it has one (also when the sheet's date contradicts
  the file name and the sheet looks copied from another meet's template) ("thornton5_16g" = May 16 of the folder
  year), and say so in `notes`; otherwise null.
- **Official team scores** when the file prints them, in `team_rankings`;
  none printed: `[]`.

Final reply: one line with the number of events and rows written and the
main thing you could not settle.
