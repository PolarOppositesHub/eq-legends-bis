import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import OverlayApp from './OverlayApp.jsx'
import './styles.css'
import { overlayIdFromSearch } from './overlayView.js'
import { applyThemeToDocument, loadUiSettings } from './uiSettings.js'

const bootSettings = loadUiSettings()
applyThemeToDocument(bootSettings.theme)
if (typeof document !== 'undefined') {
  document.documentElement.setAttribute('data-reduce-motion', bootSettings.reduceMotion ? '1' : '0')
}

const overlayId = overlayIdFromSearch(window.location.search)
if (overlayId) document.documentElement.setAttribute('data-overlay', overlayId)

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {overlayId ? <OverlayApp /> : <App />}
  </React.StrictMode>
)
