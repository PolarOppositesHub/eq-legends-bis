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

export function CurrenciesPanel({
  character,
  onCharacter,
  view,
  status,
  onAnchor,
  onUse,
  onCondense,
  onUndo,
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
      {view ? (
        <>
          <p className="note" data-testid="currencies-pending">{view.pending_label}</p>
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
              Set currency storage
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
            <button type="submit">Set count</button>
          </form>
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
                    {row.item_xp != null ? <span className="muted"> · {row.item_xp} item XP</span> : null}
                    {row.autosold_note ? <span className="badge">{row.autosold_note}</span> : null}
                    {row.condense?.warning ? <span className="note">{row.condense.warning}</span> : null}
                    {row.condense?.needs_confirmed ? <span className="note">{row.condense.note}</span> : null}
                  </td>
                  <CountCells row={row} />
                  <td>
                    {row.condense ? (
                      <button type="button" data-testid="currencies-condense" data-currency={row.name} onClick={() => onCondense && onCondense(row.name)}>
                        Condense
                      </button>
                    ) : null}
                    <button type="button" onClick={() => setLedgerName(row.name)}>Ledger</button>
                  </td>
                </tr>
              ))}
              {runes.map((row) => (
                <tr key={row.name} data-currency={row.name}>
                  <td>
                    {row.name}
                    <span className="muted"> · need not tracked in this version</span>
                  </td>
                  <CountCells row={row} />
                  <td>
                    <button type="button" onClick={() => setLedgerName(row.name)}>Ledger</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {ledgerName ? (
            <section data-testid="currencies-ledger">
              <h3>{ledgerName}</h3>
              {ledger.length ? ledger.map((entry) => (
                <p key={entry.id}>
                  {entry.reverted ? 'reverted ' : ''}{entry.delta > 0 ? `+${entry.delta}` : entry.delta} · {entry.evidence}
                  {entry.reverted ? null : (
                    <button type="button" data-testid="currencies-undo" onClick={() => onUndo && onUndo(entry.id)}>Undo</button>
                  )}
                </p>
              )) : <p className="muted">No ledger entries.</p>}
            </section>
          ) : null}
        </>
      ) : (
        <p className="muted">Enter a character to open that ledger.</p>
      )}
    </div>
  )
}
