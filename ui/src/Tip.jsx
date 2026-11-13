import { useEffect, useId, useRef } from 'react'

// A hover hint that also opens on keyboard focus and long-press: a
// popover="hint" opened by its trigger's interestfor attribute (polyfilled in
// main.jsx where missing). The trigger is a <button> styled as plain text
// (class "tip"), unless `styled` keeps the button's own look, as for buttons
// that also act on click. With no `tip`, renders the children as before.
// A button is an atomic inline, so a line may break before it where the old
// span ran on from the text: `glue` puts a word joiner there to keep it on
// (not on phones, where table cells break anywhere: there the span broke too).
const anchors = typeof CSS !== 'undefined' && CSS.supports('position-area: block-start')

export default function Tip({ tip, children, className = '', styled = false, glue = false, style, ...rest }) {
  const id = useId()
  const pop = useRef(null)
  const btn = useRef(null)
  const anchor = `--tip${id.replace(/[^\w-]/g, '')}`

  // Without CSS anchor positioning, place the open hint above its trigger
  // (below when there's no room), kept inside the viewport.
  useEffect(() => {
    const el = pop.current
    if (anchors || !el) return
    const place = (e) => {
      if (e.newState !== 'open' || !btn.current) return
      const r = btn.current.getBoundingClientRect()
      const h = el.offsetHeight, w = el.offsetWidth
      const top = r.top - h - 6 >= 0 ? r.top - h - 6 : r.bottom + 6
      const left = Math.min(Math.max(4, r.left + r.width / 2 - w / 2), window.innerWidth - w - 4)
      Object.assign(el.style, { inset: 'auto', margin: '0', top: `${top}px`, left: `${left}px` })
    }
    el.addEventListener('toggle', place)
    return () => el.removeEventListener('toggle', place)
  }, [tip])

  if (!tip) {
    return rest.onClick
      ? <button type="button" className={className} style={style} {...rest}>{children}</button>
      : <span className={className || undefined} style={style}>{children}</span>
  }
  return (
    <>
      {glue && <span className="tip-glue">{'\u2060'}</span>}
      <button type="button" ref={btn} className={`${styled ? '' : 'tip '}${className}`.trim()}
        interestfor={id} aria-describedby={id} style={{ ...style, anchorName: anchor }} {...rest}>
        {children}
      </button>
      <span popover="hint" id={id} role="tooltip" ref={pop} className="tip-pop"
        style={{ positionAnchor: anchor }}>{tip}</span>
    </>
  )
}
