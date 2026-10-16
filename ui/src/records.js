import { parseMark, isDistanceEvent } from './utils.js'

// Record board: a team's best mark ever per event and gender, for one season
// type (Indoor or Outdoor). Pure functions so the board (RecordBoard.jsx) and
// checks run from node compute the same thing.
//
// Rules:
//  - status marks (DQ, DNF, DNS, NH, ND, NT, FOUL, FS, FAIL, ...) never count
//  - one runner counts once: rows are grouped by the athlete catalog's runner
//    id (runnerId), so a runner's name spellings share one entry and a prelim
//    and final from one meet can't fill two places
//  - relays rank every performance (a relay "athlete" is its leg list)
//  - team entries in individual events (field relays' team totals) don't count
//  - metric field marks ("12.34m") are converted to inches before comparing
//  - hand times ("12.3h") count as written; the store has no wind or
//    exhibition flags, so nothing is excluded for those

const STATUS = /^[A-Z]+$/

// Comparable value of a mark: inches (higher is better) for field events,
// seconds (lower is better) for running events, or null when the mark is a
// status or unparseable.
export function markValue(mark, event) {
  const s = String(mark || '').trim().toUpperCase()
  if (!s || STATUS.test(s)) return null
  const field = isDistanceEvent(event) || /jump|vault|put|throw|discus|javelin/i.test(event || '')
  if (field) {
    const metric = s.match(/^(\d+(?:\.\d+)?)\s*M$/)
    if (metric) return parseFloat(metric[1]) * 39.3701
  }
  // a time is [h:][m:]s[.ff][h]; anything else ("12.19.94") is a typo we
  // can't read with confidence
  if (!field && !/^(\d+:){0,2}\d+(\.\d+)?H?$/.test(s)) return null
  const p = parseMark(s, field)
  if (!p.valid || !(p.value > 0)) return null
  if (field !== !p.isTime) return null
  return p.value
}

// "Boys 55 Meter Dash" -> { gender: 'Boys', event: '55 Meter Dash' }
export function splitGender(event) {
  const m = String(event || '').match(/^(Boys|Girls|Mixed)\s+(.*)$/)
  return m ? { gender: m[1], event: m[2] } : { gender: '', event: event || '' }
}

export const isRelay = (event) => /relay/i.test(event || '')

// Relay meets run field events as team totals (three throwers' shot puts
// added up), and some results files list those under the plain event name
// with the team as the athlete: "GSA A", "George Stevens A", "A GSA". Such a
// row is not an individual mark. A name is a team entry when it names a
// relay or school, or carries a team letter (A-D) beside an abbreviation or
// a word of the team's name.
export function isTeamEntry(name, team = '') {
  const n = String(name || '').trim()
  if (!n) return true
  if (team && n.toLowerCase() === team.toLowerCase()) return true
  if (/\b(relay|academy|school)\b/i.test(n)) return true
  const words = n.split(/\s+/)
  const letter = /^[A-D]$/.test(words[0]) || /^[A-D]$/.test(words[words.length - 1])
  if (!letter || words.length < 2) return false
  const teamWords = team.toLowerCase().split(/\s+/).filter(Boolean)
  const initials = teamWords.map(w => w[0]).join('')
  return words.some(w => /^[A-Z]{2,5}$/.test(w) || w.toLowerCase() === initials ||
    (w.length > 2 && teamWords.includes(w.toLowerCase())))
}

// Board order: sprints and distance by length, hurdles, race walk, relays,
// then field events in the order meets run them.
const FIELD_ORDER = ['High Jump', 'Pole Vault', 'Long Jump', 'Triple Jump', 'Shot Put', 'Discus', 'Javelin']
function eventLength(ev) {
  const mile = ev.match(/^(\d+)\s+Mile/i)
  if (mile) return +mile[1] * 1609.34
  const d = ev.match(/(\d+)\s*x\s*(\d+)\s*(Meter|Yard)/i)
  if (d) return +d[1] * +d[2] * (/yard/i.test(d[3]) ? 0.9144 : 1)
  const m = ev.match(/^(\d+)\s*(Meter|Yard)/i)
  if (m) return +m[1] * (/yard/i.test(m[2]) ? 0.9144 : 1)
  return 99999
}
export function eventSortKey(ev) {
  const f = FIELD_ORDER.findIndex(x => ev.startsWith(x))
  if (f >= 0) return [4, f, ev]
  const cat = isRelay(ev) ? 3 : /walk/i.test(ev) ? 2 : /hurdle/i.test(ev) ? 1 : 0
  return [cat, eventLength(ev), ev]
}
const cmpKeys = (a, b) => {
  for (let i = 0; i < a.length; i++) {
    if (a[i] < b[i]) return -1
    if (a[i] > b[i]) return 1
  }
  return 0
}

const dateKey = (p) => (p.date && p.date !== 'Unknown' ? p.date.slice(0, 10) : `${p.year || ''}`)

// performances: one team's rows (already enriched: team, year, season, date).
// Returns [{ gender, event, record: [entry], top: [entry] }] sorted for display,
// where an entry is { name, mark, value, date, year, meet, grade, runner, legs }.
// `record` holds every entry tied with the best mark; `top` is the best `topN`
// (one per runner, relays per performance).
// nameOf(runner) gives the catalog's name for a runner, so a record shows one
// name however the meet spelled it.
export function computeRecords(performances, { season, runnerId = (p) => p.athlete_id, nameOf = () => null, fromYear = null, topN = 10 } = {}) {
  const groups = new Map()
  for (const p of performances) {
    if (season && p.season !== season) continue
    if (fromYear && +p.year < +fromYear) continue
    const value = markValue(p.mark, p.event)
    if (value == null) continue
    const { gender, event } = splitGender(p.event)
    if (!isRelay(event) && isTeamEntry(p.athlete_name, p.team)) continue
    const key = `${gender}|${event}`
    if (!groups.has(key)) groups.set(key, { gender, event, field: isDistanceEvent(p.event) || /jump|vault|put|throw|discus|javelin/i.test(p.event), rows: [] })
    groups.get(key).rows.push({ p, value })
  }
  const out = []
  for (const g of groups.values()) {
    const better = (a, b) => (g.field ? b.value - a.value : a.value - b.value) || dateKey(a.p).localeCompare(dateKey(b.p))
    g.rows.sort(better)
    const relay = isRelay(g.event)
    const seen = new Set()
    const top = []
    for (const { p, value } of g.rows) {
      // a relay once per race: a mixed relay can sit in both the boys' and
      // the girls' results file of one meet
      const who = relay ? `${p.athlete_name}|${p.mark}|${dateKey(p)}` : runnerId(p)
      if (seen.has(who)) continue
      seen.add(who)
      top.push({
        name: (!relay && nameOf(runnerId(p))) || p.athlete_name, mark: p.mark, value, date: dateKey(p), year: p.year,
        meet: p.meet_name, grade: p.grade, runner: runnerId(p),
        legs: relay ? String(p.athlete_name || '').split(/\s*,\s*/).filter(Boolean) : null,
      })
    }
    const best = top[0].value
    const record = top.filter(e => Math.abs(e.value - best) < 1e-6)
    out.push({ gender: g.gender, event: g.event, record, top: top.slice(0, Math.max(topN, record.length)) })
  }
  const gOrder = { Boys: 0, Girls: 1, Mixed: 2, '': 3 }
  out.sort((a, b) => (gOrder[a.gender] - gOrder[b.gender]) || cmpKeys(eventSortKey(a.event), eventSortKey(b.event)))
  return out
}

// Co-op squads a school hosts are stored under their own team folder, named
// by the co-op label with the slash dropped ("George Stevens/Blue Hill
// Harbor" -> "George StevensBlue Hill Harbor"). A school's records include
// them: a folder whose name is the school's short name followed directly by
// another school's ("StevensBlue", "Central/Dexter"), never a separate school
// that merely shares a first word ("Bangor Christian").
const GENERIC = /\s+(high school|academy|regional high school|community high school|junior senior high school|school|schools|institute)$/i
export function coopTeams(teamName, manifestTeams = []) {
  const short = String(teamName || '').replace(GENERIC, '').trim()
  if (!short || short === teamName) return []
  const esc = short.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(`^${esc}(?:[A-Z]|/)`)
  return manifestTeams.filter(t => t.name !== teamName && t.level !== 'ms' && re.test(t.name))
}
