// Read an athletic.net meet's "all results" page (…/TrackAndField/meet/<id>/results/all) as it
// is already rendered in the browser: no requests of its own. Paste into the page (javascript_tool);
// the returned capture goes to backend/data/summer/raw/an-<meet id>.tsv via backend/summer_grab.py.
// Format: backend/summer_track.py parse_capture ('#meet' line, '## <title>\t<url>' per event,
// '<cells joined by " | ">\t<athlete id>\t<team id>' per row).
(() => {
  const T = e => (e ? e.textContent : '').replace(/\s+/g, ' ').trim();
  const idOf = (a, kind) => { const m = a && (a.getAttribute('href') || '').match(new RegExp('/' + kind + '/(\\d+)')); return m ? m[1] : ''; };
  const meet = T(document.querySelector('h1, .meet-name, [class*=meetName]')) || document.title.split(' - ')[0];
  const body = document.body.textContent.replace(/\s+/g, ' ');
  const dm = body.match(/(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), ([A-Z][a-z]{2} \d{1,2}, \d{4})/);
  const vm = dm && body.slice(body.indexOf(dm[0]) + dm[0].length).match(/^\s*(.*?, [A-Z]{2} US)/);
  const blocks = [...document.querySelectorAll('div.event-block')];
  // full club names by team id (relay rows print them cut short: "Running Passion Select -...")
  const clubs = {};
  for (const a of document.querySelectorAll('a.team-name')) {
    const t = T(a);
    if (!/\.\.\.$/.test(t)) clubs[idOf(a, 'team')] = t;
  }
  const out = ['#meet\t' + meet + '\t' + (dm ? dm[1] : '') + '\t' + (vm ? vm[1].trim() : '')];
  let skipped = [];
  for (const b of blocks) {
    const head = b.querySelector('h4');
    const ev = T(head.querySelector('a'));
    const age = T(head.querySelector('.text-primary'));
    const round = T(head.querySelector('small span:last-child')).replace(/^-\s*/, '');
    if (round && !/^Finals?$/.test(round)) { skipped.push(ev + ' ' + age + ' ' + round); continue; }
    // the event link says the sex: …/results/m/1/200m, /f/…, /x/… (mixed)
    const sx = (head.querySelector('a').getAttribute('href').match(/\/results\/([mfx])\//) || [])[1];
    const sex = { m: 'Mens', f: 'Womens', x: 'Mixed' }[sx] || '';
    const evName = ev.replace(/^Mixed /, '');
    const relay = /relay|4x/i.test(ev);
    out.push('## ' + meet + ' - ' + sex + ' ' + age + ' ' + evName + ' Results\t' + new URL(head.querySelector('a').getAttribute('href'), location.href).href);
    for (const tr of b.querySelectorAll(':scope > div.table-responsive > table > tbody > tr')) {
      const tds = [...tr.children].filter(x => x.tagName === 'TD');
      if (!tds.length) continue;
      const place = T(tds[0]).replace(/\.$/, '');
      const teamA = tr.querySelector('a.team-name');
      const tid = idOf(teamA, 'team');
      if (relay) {
        const legs = [...tr.querySelectorAll('td.w-100 a[href*="/athlete/"]')].map(T);
        const markTd = tds[tds.length - 3];
        const letter = (T(teamA).match(/ - ([A-Z])\b/) || [])[1];
        const club = (clubs[tid] || T(teamA).replace(/\s*-?\.\.\.$/, '').replace(/ - [A-Z]$/, '')) + (letter ? ' - ' + letter : '');
        out.push([place, club, T(markTd), legs.join(', ')].join(' | ') + '\t\t' + tid);
      } else {
        const a = tr.querySelector('a[href*="/athlete/"]');
        const ageTd = tds[1];
        const markA = tr.querySelector('a[href*="/result/"]');
        const mark = T(markA) || T(tds[4]);
        out.push([place, T(a), clubs[tid] || T(teamA), mark, 'Yr: ' + T(ageTd)].join(' | ') + '\t' + idOf(a, 'athlete') + '\t' + tid);
      }
    }
  }
  const text = out.join('\n');
  const rows = out.filter(l => !l.startsWith('#')).length;
  return '<<CAPTURE>>\n' + text + '\n<<END>>\n' + 'events ' + blocks.length + ' rows ' + rows + ' skipped ' + JSON.stringify(skipped) + '\n' + ' '.repeat(Math.max(0, 60000 - text.length));
})()
