import { useEffect, useRef } from 'react'
import { mergeProjection } from './syncSettings.js'

function desktop() {
  if (typeof window === 'undefined') return null
  return window.eqDesktop || null
}

/** Push local character data, then apply whatever the other PC has added. */
export function SyncBridge({ snapshot, onApply, enabled = true }) {
  const json = JSON.stringify(snapshot || { characters: {} })
  const first = useRef(true)
  const onApplyRef = useRef(onApply)
  onApplyRef.current = onApply
  useEffect(() => {
    if (!enabled) return undefined
    let cancel = false
    const delay = first.current ? 400 : 10000
    first.current = false
    const handle = setTimeout(async () => {
      try {
        const response = await fetch('/api/sync/capture', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: json,
        })
        if (cancel) return
        if (!response.ok) {
          let message = `Sync could not save changes (${response.status}).`
          try {
            const failed = await response.json()
            if (typeof failed?.detail === 'string' && failed.detail) message = failed.detail
          } catch (_) { /* keep the status text */ }
          if (desktop()?.isDesktop && typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('eq-sync-error', { detail: message }))
          }
          return
        }
        const body = await response.json()
        if (cancel) return
        const merged = mergeProjection(JSON.parse(json), body.projection)
        if (merged && onApplyRef.current) onApplyRef.current(merged)
        desktop()?.syncTouch?.()
      } catch (err) {
        if (desktop()?.isDesktop && typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('eq-sync-error', {
            detail: String(err?.message || err || 'Sync could not save changes.'),
          }))
        }
      }
    }, delay)
    return () => {
      cancel = true
      clearTimeout(handle)
    }
  }, [json, enabled])
  return null
}
