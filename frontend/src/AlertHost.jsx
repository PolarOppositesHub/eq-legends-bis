import { useEffect } from 'react'
import { openParserStream } from './parserApi.js'
import { alertSoundRoute } from './overlayView.js'

function speak(text) {
  if (!text || typeof window === 'undefined' || !window.speechSynthesis) return
  const utter = new SpeechSynthesisUtterance(text)
  window.speechSynthesis.speak(utter)
}

async function playFile(filePath) {
  if (!filePath || !window.eqDesktop?.readSoundFile) return
  const dataUrl = await window.eqDesktop.readSoundFile(filePath)
  if (!dataUrl) return
  const audio = new Audio(dataUrl)
  audio.play().catch(() => {})
}

function playAlert(alert) {
  const route = alertSoundRoute(alert)
  if (route.visibleOverlay || route.host !== 'hidden-window') return
  if (route.file) {
    playFile(route.file)
    return
  }
  if (!route.speak) return
  speak(alert?.message || alert?.name || 'Alert')
}

/** Hidden window. Sound stays here so a covered overlay is not the player. */
export default function AlertHost() {
  useEffect(() => {
    const stream = openParserStream({
      alert: (data) => {
        const alerts = Array.isArray(data?.alerts) ? data.alerts : []
        const last = alerts[alerts.length - 1]
        if (last) playAlert(last)
      },
    })
    return () => stream.close()
  }, [])
  return <div data-testid="alert-host" data-alert-host="hidden-window" hidden />
}
