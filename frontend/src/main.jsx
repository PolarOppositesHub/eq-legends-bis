import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles.css'
import { applyThemeToDocument, loadUiSettings } from './uiSettings.js'

const bootSettings = loadUiSettings()
applyThemeToDocument(bootSettings.theme)
if (typeof document !== 'undefined') {
  document.documentElement.setAttribute('data-reduce-motion', bootSettings.reduceMotion ? '1' : '0')
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
