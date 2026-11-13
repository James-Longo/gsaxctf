// Tables wider than the screen scroll sideways inside .table-container. A
// container that overflows becomes a named, focusable region so keyboard
// users can scroll it (Tab to it, then arrow keys); one that fits stays out
// of the tab order. Watches every .table-container the app renders.
const watched = new WeakSet()

const HEADINGS = 'h1, h2, h3, h4, h5, h6'

// the nearest heading before the table names the region: one inside the
// container above its table (Records boards), else the last one before the
// container, skipping the site banner and other tables' containers
function headingBefore(el) {
  const table = el.querySelector('table')
  const inside = [...el.querySelectorAll(HEADINGS)]
    .filter(h => table && (h.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING))
  if (inside.length) return inside[inside.length - 1]
  for (let n = el; n && n !== document.body; n = n.parentElement) {
    for (let s = n.previousElementSibling; s; s = s.previousElementSibling) {
      if (s.matches('header, .table-container')) continue
      if (s.matches(HEADINGS)) return s
      const hs = [...s.querySelectorAll(HEADINGS)].filter(h => !h.closest('header, .table-container'))
      if (hs.length) return hs[hs.length - 1]
    }
  }
  return null
}

let n = 0
function update(el) {
  if (el.scrollWidth > el.clientWidth + 1) {
    if (el.hasAttribute('tabindex')) return
    el.setAttribute('tabindex', '0')
    el.setAttribute('role', 'region')
    const h = headingBefore(el)
    if (h) {
      if (!h.id) h.id = `table-heading-${++n}`
      el.setAttribute('aria-labelledby', h.id)
    } else {
      // no heading: the page's name from the sidebar (e.g. Results)
      const page = document.querySelector('nav [aria-current="page"]:not(.sport-switch *)')
      el.setAttribute('aria-label', page?.textContent.trim() || 'Table')
    }
  } else if (el.hasAttribute('tabindex')) {
    for (const a of ['tabindex', 'role', 'aria-labelledby', 'aria-label']) el.removeAttribute(a)
  }
}

const sizes = new ResizeObserver(entries => {
  for (const e of entries) update(e.target.closest('.table-container') || e.target)
})

let queued = false
function scan() {
  queued = false
  for (const el of document.querySelectorAll('.table-container')) {
    if (watched.has(el)) { update(el); continue }
    watched.add(el)
    sizes.observe(el)
    const table = el.querySelector('table')
    if (table) sizes.observe(table)
  }
}

export function watchScrollRegions(root) {
  new MutationObserver(() => {
    if (!queued) { queued = true; requestAnimationFrame(scan) }
  }).observe(root, { childList: true, subtree: true })
  scan()
}
