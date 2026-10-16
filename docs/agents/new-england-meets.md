# New England championships: agent procedure

sub5.com posts most Maine meets but only some New England championships, and
none of the open USATF New England meets where Maine high schoolers often
run unattached (John Hassett's 4:25.20 mile, USATF NE Indoor 2017). These
meets count for Maine athletes' marks and school records. Their volume is
small, so a reader collects them by hand: find the official results, copy
**only the Maine athletes** into the parse format, and save one file per
meet (per sex when the results are split).

## Sources, in this order

1. The meet's own results page or host site (NEISTA / New England
   Interscholastic, USATF New England, the host college).
2. TFRRS (tfrrs.org), athletic.net, directathletics, the timing company's
   site (Hy-Tek "results.htm" pages).
3. MileSplit only to confirm a single row you already found elsewhere: never
   page through it, never bulk-download from it, stop if it blocks you.

Never sign in, never work around a paywall, captcha or bot block. If a meet's
results can't be found, record that (see "Not found") and move on.

## What to collect

For every Maine athlete or relay in the meet: event, sex, place, name as
printed, school (full Maine school name; "Unattached" entries: see below), grade if
printed, mark exactly as printed (convert metric field marks only when the
results print feet-inches too; otherwise keep the metric mark with its "m"),
round (Prelims / Finals). Relays: school, mark, legs if printed. Status rows
(DNF, DQ, NH, FOUL): keep with the status as the mark.

**Unattached runners.** A Maine high schooler entered "Unattached" (common
at USATF meets) is filed under their school when we can tell which: look the
name up in our athlete index (read the committed copy:
`git show HEAD:ui/public/data/athletes.json.gz | gunzip`, fields
`name`, `primary_team`, `teams`, `years`). If exactly one Maine high-school
runner of that name was active that year, write that school and add
`"unattached": true` to the row. If none or several match, keep "Unattached"
and say so in `notes`.

A Maine athlete: school in Maine (the results usually print "ME" or a Maine
school name). When unsure whether a school is in Maine, leave it out and say
so in `notes`.

## Write

`backend/data/parsed_results/<year>/<season>/ne-<slug>.json`, where
`<season>` is `Indoor` or `Outdoor`, `<year>` the indoor year in January
(a December meet belongs to the next year) or the outdoor year, and
`<slug>` short and unique, e.g. `ne-usatf-indoor-2017`,
`ne-interscholastic-outdoor-2010`.

```json
{
  "meet_name": "2017 USATF New England Indoor Championships",
  "date": "2017-02-19",
  "venue": "Harvard Gordon Track, Cambridge MA",
  "meet_level": "hs",
  "parser": "ne-manual",
  "source": {"site": "tfrrs.org", "url": "<the results page>"},
  "events": [
    {"event": "Boys 1 Mile Run", "gender": "Boys", "is_relay": false,
     "results": [
       {"place": 5, "athlete": "John Hassett", "school": "Unattached", "grade": "",
        "result": "4:25.20", "type": "Finals"}
     ]}
  ],
  "team_rankings": [],
  "notes": "anything unsure"
}
```

`meet_level` is `hs` for interscholastic meets and for open meets (the
store only keeps the Maine high-school rows you write). Event names: the
standard names ("55 Meter Dash", "1 Mile Run", "4x800 Meter Relay", "High
Jump" ...), prefixed with the sex as above.

Check the file with `python3 -c "import json;json.load(open('<path>'))"`.

## Not found

Append one line per meet you could not find to
`backend/data/ne_meets_not_found.txt`: `<year> <season> <meet>: <where you looked>`.

## Report

One line per meet: file written (Maine rows) or not found.
