import React, { useEffect, useMemo, useState } from 'react'
import { pickLoadingSaying } from './uiSettings.js'

/**
 * Full-screen busy overlay with progress bar + EQ-flavored tip.
 * jobs: [{ id, label }] — first label is the primary status line.
 */
export default function LoadingOverlay({ open, jobs = [], funnyTips = true, progress = null }) {
  const [sayingIdx, setSayingIdx] = useState(() => Date.now())
  const active = open && (jobs.length > 0 || progress != null)

  useEffect(() => {
    if (!active || !funnyTips) return undefined
    const t = setInterval(() => setSayingIdx((n) => n + 1), 2800)
    return () => clearInterval(t)
  }, [active, funnyTips])

  const primary = jobs[0]?.label || 'Working…'
  const secondary = jobs.slice(1).map((j) => j.label).filter(Boolean)
  const pct = progress == null ? null : Math.max(0, Math.min(100, Number(progress)))
  const saying = useMemo(() => pickLoadingSaying(sayingIdx), [sayingIdx])

  if (!active) return null

  return (
    <div className="load-overlay" role="alertdialog" aria-busy="true" aria-live="polite">
      <div className="load-card">
        <div className="load-title">Please wait</div>
        <div className="load-status">{primary}</div>
        {secondary.length > 0 && (
          <ul className="load-queue">
            {secondary.map((label, i) => (
              <li key={`${label}-${i}`}>{label}</li>
            ))}
          </ul>
        )}
        <div className="load-bar-track" aria-hidden="true">
          <div
            className={`load-bar-fill${pct == null ? ' indeterminate' : ''}`}
            style={pct != null ? { width: `${pct}%` } : undefined}
          />
        </div>
        {pct != null && <div className="load-pct">{Math.round(pct)}%</div>}
        {funnyTips && <p className="load-saying">{saying}</p>}
      </div>
    </div>
  )
}
