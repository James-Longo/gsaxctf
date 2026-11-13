import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { watchScrollRegions } from './scrollRegions'

// Hover hints (src/Tip.jsx) use popover + interestfor; load each polyfill
// only where the browser lacks it, popover first (interestfor opens popovers).
;(async () => {
  if (!Object.hasOwn(HTMLElement.prototype, 'popover')) await import('@oddbird/popover-polyfill')
  if (!('interestForElement' in HTMLButtonElement.prototype)) await import('interestfor')
})().catch(err => console.error('Polyfill load failed:', err))

watchScrollRegions(document.getElementById('root'))

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
