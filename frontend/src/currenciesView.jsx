import React, { useState } from 'react'

const MOTE_GRADES = [
  'Mote of Infinitesimal Potential',
  'Mote of Minor Potential',
  'Mote of Lesser Potential',
  'Mote of Potential',
  'Mote of Major Potential',
  'Mote of Greater Potential',
  'Mote of Superior Potential',
  'Mote of Grand Potential',
  'Mote of Ascendant Potential',
  'Mote of Infinite Potential',
]

function CountCells({ row }) {
  return (
    <>
      <td>{row.bags}</td>
      <td>{row.storage}</td>
      <td>{row.total}</td>
    </>
  )
}

function currencyRows(view) {
  return [
    ...(view?.motes || []),
    ...(view?.void_touched ? [view.void_touched] : []),
    ...(view?.wind_runes || []),
  ]
}

function CountAdjust({ row, onAdjust }) {
  return (
    <span className="currencies-adjust">
      <button
        type="button"
        aria-label={`Decrease ${row.name}`}
        disabled={!row.anchored}
        onClick={() => onAdjust && onAdjust(row.name, -1)}
      >
        −
      </button>
      <button
        type="button"
        aria-label={`Increase ${row.name}`}
        disabled={!row.anchored}
        onClick={() => onAdjust && onAdjust(row.name, 1)}
      >
        +
      </button>
    </span>
  )
}

export function CurrenciesPanel({
  character,
  onCharacter,
  view,
  status,
  onAnchor,
  onUse,
  onCondense,
  onUndo,
  onAdjust,
  onSetAll,
}) {
  const [anchorCurrency, setAnchorCurrency] = useState(MOTE_GRADES[0])
  const [anchorCount, setAnchorCount] = useState('0')
  const [useCurrency, setUseCurrency] = useState(MOTE_GRADES[0])
  const [useQty, setUseQty] = useState('0')
  const [useOpen, setUseOpen] = useState(false)
  const [ledgerName, setLedgerName] = useState('')
  const motes = view?.motes || []
  const runes = view?.wind_runes || []
  const voidTouched = view?.void_touched
  const names = [
    ...motes.map((row) => row.name),
    voidTouched?.name,
    ...runes.map((row) => row.name),
  ].filter(Boolean)
  const ledger = (view?.ledger && ledgerName && view.ledger[ledgerName]) || []
  const rows = currencyRows(view)
  const needsAnchor = rows.some((row) => row.anchored === false)

  return (
    <div className="panel currencies" data-testid="currencies-panel">
      <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Currencies</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Bags from the last inventory import plus currency storage is the total.
        This ledger does not plan Void-Touched spending or reorder which item it is used on.
        Wind Rune need is not tracked in this version.
      </p>
      <label className="currencies-character">
        Character
        <input
          aria-label="Currency character"
          value={character || ''}
          onChange={(event) => onCharacter && onCharacter(event.target.value)}
        />
      </label>
      {status === 'loading' ? <p className="muted">Reading the ledger…</p> : null}
      {view?.warning ? <p className="note" data-testid="currencies-warning">{view.warning}</p> : null}
      {view?.log_loaded === false ? (
        <p className="note" data-testid="currencies-no-log">No log is loaded.</p>
      ) : null}
      {view ? (
        <>
          <p className="note" data-testid="currencies-pending">{view.pending_label}</p>
          {view.last_pickup_label ? (
            <p className="note" data-testid="currencies-last-pickup">{view.last_pickup_label}</p>
          ) : null}
          {needsAnchor ? (
            <p className="note" data-testid="currencies-anchor-banner">
              Set a starting count to start tracking; new loot from the log is added after it.
            </p>
          ) : null}
          <button type="button" data-testid="currencies-used-open" onClick={() => setUseOpen(true)}>
            I used
          </button>
          {useOpen ? (
            <form
              className="currencies-used"
              data-testid="currencies-used-form"
              onSubmit={(event) => {
                event.preventDefault()
                if (onUse) onUse(useCurrency, useQty)
                setUseOpen(false)
              }}
            >
              <label>
                Grade
                <select aria-label="I used currency" value={useCurrency} onChange={(event) => setUseCurrency(event.target.value)}>
                  {names.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </label>
              <label>
                Count
                <input aria-label="I used count" type="number" min="0" value={useQty} onChange={(event) => setUseQty(event.target.value)} />
              </label>
              <button type="submit">Record</button>
            </form>
          ) : null}
          {voidTouched ? (
            <section className="currencies-void" data-testid="currencies-void">
              <h3>Void-Touched Potential</h3>
              <p>Held {voidTouched.held_label}</p>
              <p>Earned this week {voidTouched.earned_label}</p>
              <p data-testid="currencies-reset">{voidTouched.countdown_label}</p>
            </section>
          ) : null}
          <form
            className="currencies-anchor"
            onSubmit={(event) => {
              event.preventDefault()
              if (onAnchor) onAnchor(anchorCurrency, anchorCount)
            }}
          >
            <label>
              Starting count
              <select aria-label="Anchor currency" value={anchorCurrency} onChange={(event) => setAnchorCurrency(event.target.value)}>
                {names.map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
            </label>
            <input
              aria-label="Anchor count"
              type="number"
              min="0"
              value={anchorCount}
              onChange={(event) => setAnchorCount(event.target.value)}
            />
            <button type="submit">Starting count</button>
            <button
              type="button"
              data-testid="currencies-set-all"
              onClick={() => {
                if (!onSetAll) return
                const counts = {}
                for (const row of rows) counts[row.name] = Number(row.storage) || 0
                onSetAll(counts)
              }}
            >
              Set all counts
            </button>
          </form>
          <p className="muted">Combine into next grade turns lower motes into one higher mote. Some XP is lost.</p>
          <table className="currencies-table">
            <thead>
              <tr>
                <th>Currency</th>
                <th>Bags</th>
                <th>Currency storage</th>
                <th>Total</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {motes.map((row) => (
                <tr key={row.name} data-currency={row.name}>
                  <td>
                    {row.name}
                    <CountAdjust row={row} onAdjust={onAdjust} />
                    {row.item_xp != null ? <span className="muted"> · {row.item_xp} item XP</span> : null}
                    {row.seen_label ? <span className="note" data-testid="currencies-seen">{row.seen_label}</span> : null}
                    {row.autosold_note ? <span className="badge">{row.autosold_note}</span> : null}
                    {row.condense?.warning ? <span className="note">{row.condense.warning}</span> : null}
                    {row.condense?.needs_confirmed ? <span className="note">{row.condense.note}</span> : null}
                  </td>
                  <CountCells row={row} />
                  <td>
                    {row.condense ? (
                      <button
                        type="button"
                        data-testid="currencies-condense"
                        data-currency={row.name}
                        title="Turns lower motes into one higher mote. Some XP is lost."
                        onClick={() => onCondense && onCondense(row.name)}
                      >
                        Combine into next grade
                      </button>
                    ) : null}
                    <button type="button" title="Every change to this count: looted, given, used, or set by you." onClick={() => setLedgerName(row.name)}>History</button>
                  </td>
                </tr>
              ))}
              {runes.map((row) => (
                <tr key={row.name} data-currency={row.name}>
                  <td>
                    {row.name}
                    <CountAdjust row={row} onAdjust={onAdjust} />
                    {row.seen_label ? <span className="note" data-testid="currencies-seen">{row.seen_label}</span> : null}
                    <span className="muted"> · Plane of Sky need is on Requirements</span>
                  </td>
                  <CountCells row={row} />
                  <td>
                    <button type="button" title="Every change to this count: looted, given, used, or set by you." onClick={() => setLedgerName(row.name)}>History</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {ledgerName ? (
            <section data-testid="currencies-ledger">
              <h3>History · {ledgerName}</h3>
              <p className="muted">Every change to this count: looted, given, used, or set by you.</p>
              {ledger.length ? ledger.map((entry) => (
                <p key={entry.id}>
                  {entry.reverted ? 'reverted ' : ''}{entry.delta > 0 ? `+${entry.delta}` : entry.delta} · {entry.evidence}
                  {entry.reverted ? null : (
                    <button type="button" data-testid="currencies-undo" onClick={() => onUndo && onUndo(entry.id)}>Undo</button>
                  )}
                </p>
              )) : <p className="muted">No history yet.</p>}
            </section>
          ) : null}
        </>
      ) : (
        <p className="muted">Enter a character to open that ledger.</p>
      )}
    </div>
  )
}
