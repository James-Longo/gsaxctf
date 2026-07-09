import React, { useState, useRef, useEffect, useMemo } from 'react'

/**
 * SearchSelect - type-ahead replacement for long <select> lists.
 *
 * options: [{ value, label, group?, secondary? }]
 *   group     - optional section header (options must be pre-sorted by group)
 *   secondary - dim text right of the label (e.g. team name, result count)
 * minSearch  - require N typed chars before listing (for huge option sets)
 */
export default function SearchSelect({ value, onChange, options, placeholder = 'Search...', minSearch = 0 }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [hi, setHi] = useState(0)
  const rootRef = useRef(null)
  const listRef = useRef(null)

  const selected = options.find(o => String(o.value) === String(value))

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (q.length < minSearch) return q.length === 0 && minSearch === 0 ? options.slice(0, 300) : []
    const starts = []
    const contains = []
    for (const o of options) {
      const l = o.label.toLowerCase()
      if (l.startsWith(q)) starts.push(o)
      else if (l.includes(q)) contains.push(o)
      if (starts.length + contains.length >= 300) break
    }
    return [...starts, ...contains]
  }, [options, query, minSearch])

  useEffect(() => { setHi(0) }, [query, open])

  useEffect(() => {
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  useEffect(() => {
    if (!listRef.current) return
    const el = listRef.current.querySelector('.ss-hi')
    if (el) el.scrollIntoView({ block: 'nearest' })
  }, [hi])

  const pick = (o) => {
    onChange(o.value)
    setOpen(false)
    setQuery('')
  }

  const onKey = (e) => {
    if (!open && (e.key === 'ArrowDown' || e.key === 'Enter')) { setOpen(true); return }
    if (e.key === 'ArrowDown') { e.preventDefault(); setHi(h => Math.min(h + 1, filtered.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHi(h => Math.max(h - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); if (filtered[hi]) pick(filtered[hi]) }
    else if (e.key === 'Escape') { setOpen(false); setQuery('') }
  }

  const rows = []
  let lastGroup = null
  filtered.forEach((o, i) => {
    if (o.group && o.group !== lastGroup) {
      rows.push(<li key={`g-${o.group}`} className="ss-group">{o.group}</li>)
      lastGroup = o.group
    }
    rows.push(
      <li key={o.value}
          className={`ss-opt${i === hi ? ' ss-hi' : ''}${String(o.value) === String(value) ? ' ss-sel' : ''}`}
          onMouseDown={(e) => { e.preventDefault(); pick(o) }}
          onMouseEnter={() => setHi(i)}>
        <span>{o.label}</span>
        {o.secondary && <span className="ss-2nd">{o.secondary}</span>}
      </li>
    )
  })

  return (
    <div className="searchselect" ref={rootRef}>
      <input
        value={open ? query : (selected ? selected.label : '')}
        placeholder={selected ? selected.label : placeholder}
        onChange={e => { setQuery(e.target.value); if (!open) setOpen(true) }}
        onFocus={() => { setOpen(true); setQuery('') }}
        onKeyDown={onKey}
      />
      <span className="ss-caret">▾</span>
      {open && (
        <ul className="ss-list" ref={listRef}>
          {rows.length ? rows : (
            <li className="ss-empty">
              {query.trim().length < minSearch
                ? `Type ${minSearch}+ characters to search`
                : 'No matches'}
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
