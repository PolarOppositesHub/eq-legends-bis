import {
  CREDITS,
  LEVEL_LOADOUT_NOTE,
  WHATS_NEW_POINTS,
  WHATS_NEW_TITLE,
} from './parserView.js'

export function CreditsDialog({ onClose }) {
  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Credits"
        data-testid="credits-dialog"
      >
        <h2>Credits</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          EQ Legends BiS shows sourced data. It does not invent stats, mobs, or log lines.
          Parser numbers come only from the combat log on this PC.
        </p>
        {CREDITS.map((entry) => (
          <section key={entry.id} className="help-section" data-credit={entry.id}>
            <h3>{entry.title}</h3>
            <p>{entry.body}</p>
            <p>
              <a href={entry.href} target="_blank" rel="noopener noreferrer">{entry.href}</a>
              {entry.licenseHref ? (
                <>
                  {' · '}
                  <a href={entry.licenseHref} target="_blank" rel="noopener noreferrer">{entry.licenseLabel}</a>
                </>
              ) : null}
            </p>
          </section>
        ))}
        <p className="note">{LEVEL_LOADOUT_NOTE}</p>
        <div className="modal-actions">
          <button type="button" className="primary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}

export function WhatsNewDialog({ onClose }) {
  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={WHATS_NEW_TITLE}
        data-testid="whats-new-dialog"
      >
        <h2>{WHATS_NEW_TITLE}</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          This note shows once. Parser, Best in Slot, and the other tabs stay on this PC.
        </p>
        <ul className="parser-notes">
          {WHATS_NEW_POINTS.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <div className="modal-actions">
          <button type="button" className="primary" onClick={onClose}>Got it</button>
        </div>
      </div>
    </div>
  )
}
