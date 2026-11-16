import { asset, fetchGz } from './utils'

/**
 * Summer series data (ui/public/data/summer.json.gz from backend/summer_track.py),
 * read once and shared by the Summer tab and the athlete profile.
 */

export const FIELD = /jump|vault|put|shot|discus|javelin|throw|turbo|softball|hammer/i
// throws the school store prints to the whole inch; other field marks to the quarter
const WHOLE_INCH = /discus|javelin|hammer|turbo|softball/i
// two-year groups, then the older USATF division names (2004-2008 Junior Olympic meets
// from sub5), then masters ranges ('40-49') last
const AGE_ORDER = ['8 & Under', '9-10', '11-12', '13-14', '15', '15-16', '17-18',
  'Bantam', 'Midget', 'Youth', 'Intermediate', 'Young']
export const ageRank = (a) => (AGE_ORDER.indexOf(a) + 1) || (/^\d{2}-\d{2}$/.test(a) ? 100 + parseInt(a) : 99)

// Summer event names in the school seasons' wording ("100 Meters" -> "100m Dash")
const eventLabel = (e) => e
  .replace(/^(\d+) Meters$/, (_, n) => +n <= 400 ? `${n}m Dash` : `${n}m Run`)
  .replace(/^(\d+)m Racewalk$/, '$1m Race Walk')
  .replace(/^(4x\d+) Relay$/, '$1m Relay')
  .replace(/^(\d+) Meters Steeplechase$/, '$1m Steeplechase')
  .replace(/^Shot Put Girls$/, 'Shot Put')

const pad2 = (n) => String(n).padStart(2, '0')
// A field mark in feet as the school store prints it ("14-03.25", "92-00"),
// and its length in inches. Results print feet or meters; a meter mark is
// converted from the stored value and rounded down (to the quarter inch, the
// whole inch for throws).
function feet(r) {
  const whole = WHOLE_INCH.test(r.event)
  const m = r.mark.match(/^(\d+)-(\d+)(\.\d+)?$/)
  if (m) return [`${m[1]}-${pad2(m[2])}${m[3] ? m[3].padEnd(3, '0') : whole ? '' : '.00'}`, +m[1] * 12 + +(m[2] + (m[3] || ''))]
  if (r.value && /^\d+(\.\d+)?m?$/.test(r.mark)) {
    const q = whole ? 1 : 4
    const ins = Math.floor(r.value / 0.0254 * q + 1e-6) / q
    const ft = Math.floor(ins / 12), rest = ins - ft * 12, ii = Math.floor(rest)
    return [`${ft}-${pad2(ii)}${whole ? '' : '.' + pad2(Math.round((rest - ii) * 100))}`, ins]
  }
  return [r.mark, r.value != null ? r.value / 0.0254 : null]
}

// Rows with their meet, school-style event names, field marks in feet, the
// runner they belong to (rid) and whether each is that runner's PR.
// One runner: the athletic.net id where printed; otherwise name, gender and
// club (a common name in another club is another kid). Rows without the id
// join the id'd runner with the same name, gender and club. The catalog
// (backend/athlete_catalog.summer_runners) keys runners the same way.
function parse(data) {
  const c = Object.fromEntries(data.cols.map((k, i) => [k, i]))
  const rows = data.rows.map((x, i) => {
    const r = Object.fromEntries(Object.entries(c).map(([k, j]) => [k, x[j]]))
    const m = data.meets[r.meet]
    r.i = i
    r.event = eventLabel(r.event)
    r.ev = `${r.gender} ${r.event}`
    r.field = FIELD.test(r.event)
    if (r.field) [r.mark, r.inches] = feet(r)
    r.date = m.date || ''
    r.year = r.date.slice(0, 4)
    r.meetName = m.name
    r.url = m.url
    return r
  })
  const key = (r) => `${r.name}|${r.gender}|${r.club}`
  const aidOf = {}
  rows.forEach(r => { if (r.aid && r.name) aidOf[key(r)] ||= r.aid })
  const runners = new Map()
  rows.forEach(r => {
    if (r.legs || !r.name) return
    r.rid = r.aid || aidOf[key(r)] || key(r)
    let a = runners.get(r.rid)
    if (!a) runners.set(r.rid, a = { id: r.rid, name: r.name, gender: r.gender, clubs: new Set(), rows: [] })
    a.clubs.add(r.club)
    a.rows.push(r.i)
  })
  // PR: the runner's best in the event (the earliest, on a tie); points events have none
  const best = {}
  const better = (a, b) => a.field ? a.value > b.value : a.value < b.value
  ;[...rows].sort((a, b) => a.date.localeCompare(b.date)).forEach(r => {
    if (!r.rid || r.value == null || /athlon/i.test(r.event)) return
    const k = `${r.rid}|${r.ev}`
    if (!best[k] || better(r, best[k])) best[k] = r
  })
  Object.values(best).forEach(r => { r.isPr = true })
  return { rows, runners, series_clubs: data.series_clubs || [] }
}

let loading = null
export const loadSummer = () => (loading ||= fetchGz(asset('/data/summer.json.gz')).then(parse))

// A runner's marks in the athlete profile's shape; points events (pentathlon)
// don't chart as a time or a distance.
export const profileRows = (summer, rid) => (summer?.runners.get(rid)?.rows || [])
  .map(i => summer.rows[i])
  .filter(r => r.value != null && !/athlon/i.test(r.event))
  .map(r => ({
    id: `summer|${r.i}`, event: r.event, mark: r.mark, date: r.date, year: r.year, season: 'Summer',
    meet_name: r.meetName, age: r.age, age_group: r.age_group, ageRank: ageRank(r.age_group),
    numericValue: r.field ? r.inches : r.value, isTime: !r.field,
  }))
