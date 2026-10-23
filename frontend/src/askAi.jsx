import { useEffect, useState } from 'react'
import {
  ASK_TIMEOUT_MS,
  CLI_STATE_TEXT,
  PASTE_HINT,
  formatCliAnswer,
  prepareAsk,
} from './askAi.js'

const INSTALL_NOTE = 'Windows runs irm https://x.ai/cli/install.ps1 | iex. macOS and Linux run curl -fsSL https://x.ai/cli/install.sh | bash. This app runs the command for this computer only after you confirm. It does not see your password.'

async function defaultCopy(text) {
  if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  throw new Error('clipboard unavailable')
}

function defaultOpen(url) {
  if (typeof window !== 'undefined') window.open(url, '_blank', 'noopener,noreferrer')
}

export function AskAiDialog({
  snapshot,
  onClose,
  status: statusProp = null,
  runError: runErrorProp = null,
  desktop = null,
  copyText = defaultCopy,
  openUrl = defaultOpen,
}) {
  const [question, setQuestion] = useState('')
  const [status, setStatus] = useState(statusProp || { state: 'unknown', detail: 'Checking the Grok Build CLI.' })
  const [hint, setHint] = useState('')
  const [manualPack, setManualPack] = useState('')
  const [runError, setRunError] = useState(runErrorProp)
  const [answer, setAnswer] = useState(null)
  const [busy, setBusy] = useState(false)
  const [runId, setRunId] = useState('')
  const [confirmInstall, setConfirmInstall] = useState(false)
  const [setupNote, setSetupNote] = useState('')

  useEffect(() => {
    if (statusProp) setStatus(statusProp)
  }, [statusProp])

  useEffect(() => {
    if (runErrorProp) setRunError(runErrorProp)
  }, [runErrorProp])

  useEffect(() => {
    if (statusProp || !desktop?.grokStatus) return undefined
    let cancelled = false
    desktop.grokStatus().then((next) => {
      if (!cancelled && next) setStatus(next)
    }).catch(() => {
      if (!cancelled) setStatus({ state: 'unknown', detail: 'Sign-in check failed. The copy button still works.' })
    })
    return () => { cancelled = true }
  }, [desktop, statusProp])

  useEffect(() => {
    if (!desktop?.onGrokResult) return undefined
    return desktop.onGrokResult((result) => {
      if (!result || (runId && result.id && result.id !== runId)) return
      setBusy(false)
      setRunId('')
      if (result.ok) setAnswer(formatCliAnswer(result))
      else {
        setAnswer(result.raw ? { label: result.friendly || '', body: result.raw } : null)
        setRunError({
          kind: result.kind || 'error',
          friendly: result.friendly || 'Grok stopped.',
          fallbackCopy: result.fallbackCopy !== false,
        })
      }
    })
  }, [desktop, runId])

  async function refreshStatus() {
    if (!desktop?.grokStatus) return
    try {
      const next = await desktop.grokStatus()
      if (next) setStatus(next)
    } catch (_) {
      setStatus({ state: 'unknown', detail: 'Sign-in check failed. The copy button still works.' })
    }
  }

  async function onCopy() {
    const prepared = prepareAsk(snapshot, question)
    setRunError(null)
    try {
      await copyText(prepared.pack)
      setManualPack('')
      setHint(prepared.hint || PASTE_HINT)
    } catch (_) {
      setManualPack(prepared.pack)
      setHint('The clipboard was not available. The pack is shown below so you can copy it. Then paste it into the Grok tab.')
    }
    openUrl(prepared.url)
  }

  async function onInstall() {
    if (!desktop?.grokInstall) return
    setSetupNote('')
    const result = await desktop.grokInstall(true)
    setConfirmInstall(false)
    setSetupNote(result?.detail || result?.command || 'Installer finished. Check again.')
    await refreshStatus()
  }

  async function onLogin() {
    if (!desktop?.grokLogin) return
    const result = await desktop.grokLogin()
    setSetupNote(result?.detail || 'Grok sign-in started.')
  }

  async function onAsk() {
    const prepared = prepareAsk(snapshot, question)
    if (!desktop?.askGrok) {
      setRunError({
        kind: 'not_installed',
        friendly: 'In-app answers need the desktop app and the Grok Build CLI. Copy context still works.',
        fallbackCopy: true,
      })
      return
    }
    setBusy(true)
    setAnswer(null)
    setRunError(null)
    try {
      const started = await desktop.askGrok({ prompt: prepared.pack, timeoutMs: ASK_TIMEOUT_MS })
      setRunId(started?.id || '')
    } catch (_) {
      setBusy(false)
      setRunError({
        kind: 'error',
        friendly: 'Grok could not be started. Copy the context and open Grok in the browser.',
        fallbackCopy: true,
      })
    }
  }

  async function onCancel() {
    if (desktop?.cancelGrok && runId) await desktop.cancelGrok(runId)
    setBusy(false)
  }

  const state = status?.state || 'unknown'
  const stateText = CLI_STATE_TEXT[state] || CLI_STATE_TEXT.unknown
  const showFallback = runError?.fallbackCopy

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Ask AI"
        data-testid="ask-ai-dialog"
      >
        <h2>
          Ask AI
          <span className="ask-ai-beta">Beta</span>
        </h2>
        <p className="muted" style={{ marginTop: 0 }} data-testid="ask-ai-status">
          {stateText} {status?.detail || ''}
        </p>
        <p className="note">
          Uses your own Grok account. This app does not see or store the sign-in, and it does not use a paid API key.
        </p>
        <label>
          Question
          <textarea
            className="ask-ai-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            data-testid="ask-ai-question"
          />
        </label>
        <div className="modal-actions" style={{ justifyContent: 'flex-start' }}>
          <button type="button" className="primary" data-testid="ask-ai-copy" onClick={onCopy}>
            Copy context &amp; open Grok
          </button>
          {state === 'ready' && (
            <button type="button" data-testid="ask-ai-run" onClick={onAsk} disabled={busy}>
              Ask in the app
              <span className="ask-ai-beta">Beta</span>
            </button>
          )}
          {busy && (
            <button type="button" data-testid="ask-ai-cancel" onClick={onCancel}>Cancel</button>
          )}
          {state === 'not_installed' && !confirmInstall && (
            <button type="button" data-testid="ask-ai-install" onClick={() => setConfirmInstall(true)}>
              Install Grok Build
            </button>
          )}
          {(state === 'not_signed_in' || state === 'unknown') && desktop?.grokLogin && (
            <button type="button" data-testid="ask-ai-login" onClick={onLogin}>Sign in with your Grok account</button>
          )}
          <button type="button" onClick={refreshStatus}>Check again</button>
        </div>
        {confirmInstall && (
          <div data-testid="ask-ai-install-confirm">
            <p>{INSTALL_NOTE}</p>
            <div className="modal-actions" style={{ justifyContent: 'flex-start' }}>
              <button type="button" className="primary" data-testid="ask-ai-install-go" onClick={onInstall}>
                Run the official installer
              </button>
              <button type="button" onClick={() => setConfirmInstall(false)}>Cancel</button>
            </div>
          </div>
        )}
        {setupNote ? <p className="note" data-testid="ask-ai-setup">{setupNote}</p> : null}
        {hint ? <p className="note" data-testid="ask-ai-hint">{hint}</p> : null}
        {showFallback ? (
          <p className="note" data-testid="ask-ai-fallback">Use Copy context &amp; open Grok.</p>
        ) : null}
        {runError?.friendly ? (
          <p data-testid="ask-ai-error">{runError.friendly}</p>
        ) : null}
        {answer?.label ? (
          <div data-testid="ask-ai-answer">
            <p className="note">{answer.label}</p>
            {answer.body ? <pre className="ask-ai-output">{answer.body}</pre> : null}
          </div>
        ) : null}
        {manualPack ? <pre className="ask-ai-output" data-testid="ask-ai-pack">{manualPack}</pre> : null}
        <div className="modal-actions">
          <button type="button" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}
