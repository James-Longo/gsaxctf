// Compare each team's computed records with its official record board
// (src/officialBoards.js), the same way the Records tab builds them.
//
//   npm --prefix ui run check:boards
//
// Prints every board event that doesn't match. Exits 1 when the results beat
// the board (the board sheet needs updating) or the board holds a mark from
// 2003 on that the results lack (a missing meet); board marks from before
// 2003, when the results start, are expected.
import fs from 'node:fs'
import path from 'node:path'
import zlib from 'node:zlib'
import { fileURLToPath } from 'node:url'
import { computeRecords, coopTeams, mergeBoard } from '../src/records.js'
import { OFFICIAL_BOARDS, BOARD_EVENTS } from '../src/officialBoards.js'
import { storeAthleteId } from '../src/utils.js'

const DATA = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'public', 'data')
const readGz = (f) => JSON.parse(zlib.gunzipSync(fs.readFileSync(f)).toString('utf8'))

const manifest = JSON.parse(fs.readFileSync(path.join(DATA, 'manifest.json'), 'utf8'))
const athletes = readGz(path.join(DATA, 'athletes.json.gz'))
const runnerOf = {}
for (const a of athletes) for (const id of a.members || []) runnerOf[id] = a.id
const names = new Map(athletes.map(a => [a.id, a.name]))
const runnerId = (p) => runnerOf[p.athlete_id] || p.athlete_id
const nameOf = (id) => names.get(id)

// a team's rows for one season type, enriched as App.jsx loadTeamData does
function teamRows(team, season) {
  const out = []
  for (const key of (team.seasons || []).filter(k => k.endsWith(`_${season}`))) {
    const year = key.slice(0, key.indexOf('_'))
    for (const p of readGz(path.join(DATA, 'teams', team.slug, `${key}.json.gz`))) {
      out.push({ ...p, team: p.team || team.name, year: p.year || year, season: p.season || season,
        athlete_id: p.athlete_id || storeAthleteId(p.athlete_name || '', team.name, year, season, p.event) })
    }
  }
  return out
}

const fmt = (e) => e ? `${(e.legs && e.legs.length > 1) ? e.legs.join(', ') : e.name} ${e.mark} (${e.date || e.year})` : '-'
let failures = 0
for (const [teamName, seasons] of Object.entries(OFFICIAL_BOARDS)) {
  const team = manifest.teams.find(t => t.name === teamName)
  for (const [season, board] of Object.entries(seasons)) {
    const squads = [team, ...coopTeams(teamName, manifest.teams)]
    const rows = squads.flatMap(t => teamRows(t, season))
    const records = mergeBoard(
      computeRecords(rows, { season, runnerId, nameOf })
        .filter(r => BOARD_EVENTS[season]?.has(`${r.gender}|${r.event}`)),
      board)
    const off = records.filter(r => r.board && r.board.status !== 'match')
    console.log(`${teamName} ${season}: ${records.length - off.length}/${records.length} match the board`)
    for (const r of off) {
      const { row, status, site } = r.board
      const expected = status === 'board' && +String(row.year).slice(0, 4) < 2003
      if (!expected) failures++
      const here = status === 'beats' ? r.record[0] : site
      console.log(`  ${expected ? 'ok  ' : 'FAIL'} ${r.gender} ${r.event}: board ${row.name} ${row.mark} (${row.year}); ` +
        `results ${status === 'beats' ? 'beat it' : 'best'}: ${fmt(here)}`)
    }
  }
}
process.exit(failures ? 1 : 0)
