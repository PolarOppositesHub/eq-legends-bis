import { SHORTCUTS } from './shortcuts.js'

export function ShortcutsDialog({ onClose }) {
  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        data-testid="shortcuts-dialog"
      >
        <h2>Keyboard shortcuts</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Press ? to open this list. Press g, then a letter, to open a page.
          Shortcuts do nothing while you are typing in a field, or while a dialog is open.
        </p>
        <ul className="shortcut-list" data-testid="shortcut-list">
          {SHORTCUTS.map((row) => (
            <li key={row.tab}>
              <kbd>g</kbd>
              {' '}
              <kbd>{row.key}</kbd>
              <span>{row.label}</span>
            </li>
          ))}
        </ul>
        <div className="modal-actions">
          <button type="button" className="primary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}
