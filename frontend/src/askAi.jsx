import { useState } from 'react'
import {
  askPlaceholder,
  askPlaceLabel,
  buildAskPrompt,
  deliverAsk,
  isGrokUrl,
} from './askAi.js'

/**
 * One Ask AI button. The question is typed next to it.
 * The attached context follows the open page.
 */
export function AskAiControl({ tab, snapshot }) {
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [answer, setAnswer] = useState('')
  const [toast, setToast] = useState('')
  const [paste, setPaste] = useState('')
  const [open, setOpen] = useState(false)
  const label = askPlaceLabel(tab)

  async function onAsk() {
    const built = buildAskPrompt(tab, question, snapshot)
    if (busy) return
    if (!built.ok) {
      setToast('Type a question first.')
      setAnswer('')
      setPaste('')
      setOpen(true)
      return
    }
    setBusy(true)
    setAnswer('')
    setToast('')
    setPaste('')
    try {
      const result = await deliverAsk({
        prompt: built.prompt,
        askLocal: askLocalGrok,
        openUrl: (url) => {
          if (!isGrokUrl(url) || typeof window === 'undefined') return undefined
          window.open(url, '_blank', 'noopener,noreferrer')
          return undefined
        },
        copyText: async (text) => {
          const clipboard = typeof navigator !== 'undefined' ? navigator.clipboard : null
          if (!clipboard || typeof clipboard.writeText !== 'function') return false
          await clipboard.writeText(text)
          return true
        },
      })
      if (result.mode === 'answer') {
        setAnswer(result.text)
        setToast('')
        setOpen(true)
      } else if (result.toast || result.prompt) {
        setToast(result.toast || '')
        setPaste(result.prompt || '')
        setOpen(true)
      } else {
        setOpen(false)
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="ask-ai" data-testid="ask-ai">
      <input
        type="text"
        className="ask-ai-question"
        data-testid="ask-ai-question"
        placeholder={askPlaceholder(tab)}
        aria-label="Question for Ask AI"
        title={label}
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            onAsk()
          }
        }}
      />
      <button
        type="button"
        className="header-text-btn"
        data-testid="ask-ai-button"
        title={label}
        disabled={busy}
        onClick={onAsk}
      >
        {busy ? 'Asking…' : 'Ask AI'}
      </button>
      {open ? (
        <div className="modal-backdrop" onClick={() => setOpen(false)} role="presentation">
          <div
            className="modal"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Ask AI"
            data-testid="ask-ai-dialog"
          >
            <h2>Ask AI</h2>
            <p className="muted" style={{ marginTop: 0 }}>{label}</p>
            {toast ? <p className="note" role="status" data-testid="ask-ai-toast">{toast}</p> : null}
            {answer ? <pre className="ask-ai-answer" data-testid="ask-ai-answer">{answer}</pre> : null}
            {paste ? (
              <textarea className="ask-ai-paste" data-testid="ask-ai-paste" readOnly value={paste} rows={8} />
            ) : null}
            {!toast && !answer && !paste ? <p className="muted">Asking…</p> : null}
            <div className="modal-actions">
              <button type="button" className="primary" onClick={() => setOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

async function askLocalGrok(prompt) {
  const desktop = typeof window !== 'undefined' ? window.eqDesktop : null
  if (!desktop || typeof desktop.askGrok !== 'function') return { mode: 'browser', reason: 'not-installed' }
  return desktop.askGrok({ prompt })
}
