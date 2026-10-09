import React from 'react'
import { formatMoteList } from './requirementsView.js'

function MoteLine({ label, rows }) {
  return (
    <div>
      <span className="muted">{label}: </span>
      {formatMoteList(rows)}
    </div>
  )
}

export function UpgradePathCard({ item, onProgress, onTier }) {
  if (!item) return null
  return (
    <article className="requirement-card" data-testid="upgrade-path-card">
      <h3>
        {item.slot ? `${item.slot} · ` : ''}
        {item.name}
        {item.owned ? '' : ' · not owned'}
      </h3>
      <p>
        +{item.start_tier} → +{item.target_tier}
        {' · '}
        {item.xp_needed} XP
        {item.duplicate_xp ? ` · duplicates ${item.duplicate_xp} XP` : ''}
      </p>
      {item.tier_note ? <p className="note">{item.tier_note}</p> : null}
      {item.progress_note ? <p className="muted">{item.progress_note}</p> : null}
      {item.high_tier_note ? <p className="note">{item.high_tier_note}</p> : null}
      {item.path_ready ? (
        <>
          <MoteLine label="Motes this takes" rows={item.motes} />
          <MoteLine label="Using what you hold" rows={item.held_motes} />
          {(item.void_touched_planned || []).length ? (
            <div>
              <span className="muted">Void-Touched: </span>
              {item.void_touched_planned.map((step) => `+${step.tier} → +${step.to_tier}`).join(', ')}
              {(item.void_touched || []).length ? '' : ' (once that tier is reached)'}
            </div>
          ) : null}
          <MoteLine label="Still missing" rows={item.missing} />
          {(item.missing || []).map((row) => (
            <p key={`${row.name}-${row.count}`} className="muted">{row.hint}</p>
          ))}
        </>
      ) : null}
      <div className="requirement-controls">
        <label>
          Current +N
          <input
            type="number"
            min={0}
            max={10}
            aria-label={`Current tier for ${item.name}`}
            value={item.tier_source === 'unknown' ? '' : item.start_tier}
            onChange={(event) => onTier(item.name, event.target.value)}
          />
        </label>
        <label>
          Progress
          <input
            type="number"
            min={0}
            aria-label={`Progress for ${item.name}`}
            value={item.progress || 0}
            onChange={(event) => onProgress(item.name, event.target.value)}
          />
        </label>
      </div>
    </article>
  )
}

export function RequirementsPanel({
  plan,
  pos,
  pane,
  onPane,
  onProgress,
  onTier,
  sortByScore,
  onSortByScore,
  onManual,
  onIgnore,
}) {
  const items = sortByScore ? (plan?.by_score_per_mote || plan?.items || []) : (plan?.items || [])
  const totals = plan?.totals
  return (
    <div data-testid="requirements-panel">
      <div className="requirement-panes">
        <button type="button" className={pane === 'upgrades' ? 'primary' : ''} onClick={() => onPane('upgrades')}>
          Upgrades
        </button>
        <button type="button" className={pane === 'pos' ? 'primary' : ''} onClick={() => onPane('pos')}>
          Plane of Sky
        </button>
      </div>
      {pane === 'upgrades' ? (
        <>
          <p className="muted">{plan?.holdings_note}</p>
          <p className="note">{plan?.rules}</p>
          <p className="note">{plan?.damage_note}</p>
          {totals ? (
            <p data-testid="upgrade-totals">
              {totals.xp_needed} XP across these items
              {' · '}
              motes this takes: {formatMoteList(totals.motes)}
              {' · '}
              missing: {formatMoteList(totals.missing)}
              {' · '}
              Void-Touched used {totals.void_touched_used} of {totals.void_touched_held}
            </p>
          ) : (
            <p className="muted">Update Best in Slot to plan a path.</p>
          )}
          <label className="muted">
            <input type="checkbox" checked={!!sortByScore} onChange={(event) => onSortByScore(event.target.checked)} />
            {' '}
            Sort by Best in Slot score per mote
          </label>
          {items.map((item) => (
            <UpgradePathCard
              key={item.id || item.name}
              item={item}
              onProgress={onProgress}
              onTier={onTier}
            />
          ))}
        </>
      ) : (
        <PosPane pos={pos} onManual={onManual} onIgnore={onIgnore} />
      )}
    </div>
  )
}

function Chip({ met, children }) {
  return <span className={met ? 'chip chip-have' : 'chip chip-need'}>{children}</span>
}

export function PosPane({ pos, onManual, onIgnore }) {
  const classes = pos?.classes || []
  const tests = pos?.tests || []
  return (
    <div data-testid="pos-pane">
      <p className="muted">{pos?.attribution}</p>
      <p className="note">{pos?.granted_note}</p>
      <p className="note">{pos?.locked_note}</p>
      {!classes.length ? <p className="muted">Plane of Sky test data is not loaded.</p> : null}
      {classes.map((row) => {
        const mine = tests.filter((test) => test.class === row.class && !test.ignored)
        return (
          <details key={row.class} className="pos-class" open={!!row.goal}>
            <summary>
              {row.class}
              {' · '}
              {row.done} done, {row.remaining} remaining
              {row.granted ? ' · Unlocked (granted)' : ''}
              {row.token_unverified ? ' · token UNVERIFIED' : ''}
              {row.goal ? ' · goal' : ''}
            </summary>
            {row.token_unverified ? (
              <p className="note">
                The bypass component is complete. Whether a Primary Class Unlock Token set that row is UNVERIFIED, so Obtain rows are not counted as turn-ins.
              </p>
            ) : null}
            {row.granted && !row.token_unverified ? (
              <p className="note">
                The autocomplete component is complete, so Obtain rows are not counted as turn-ins.
              </p>
            ) : null}
            <ul className="pos-tests">
              {mine.map((test) => (
                <li key={test.quest}>
                  <strong>{test.quest}</strong>
                  {test.done ? ` · done (${test.source})` : ' · not done'}
                  {test.linked_bis?.length ? ' · BiS reward' : ''}
                  <button type="button" onClick={() => onManual(test.quest, test.source === 'manual' && test.done ? 'not_done' : 'done')}>
                    {test.done ? 'Mark not done' : 'Mark done'}
                  </button>
                  <button type="button" onClick={() => onIgnore(test.quest)}>Ignore</button>
                  <div>
                    {(test.runes || []).map((rune) => (
                      <Chip key={rune.name} met={rune.met}>
                        {rune.name} {rune.have}/{rune.need}
                      </Chip>
                    ))}
                    {(test.items || []).map((item) => (
                      <Chip key={item.name} met={item.met}>
                        {item.name} {item.have}/{item.need}
                      </Chip>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </details>
        )
      })}
      {(pos?.unmatched_achievements || []).length ? (
        <div>
          <h3>Unmatched achievement lines</h3>
          <ul>
            {pos.unmatched_achievements.map((row, index) => (
              <li key={`${row.text}-${index}`}>{row.text} — {row.reason}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

export function WishListPanel({ names, plan, ownedNames, isOwned, onUnpin }) {
  const byName = new Map((plan?.items || []).map((item) => [String(item.name || '').toLowerCase(), item]))
  const ownedList = ownedNames || []
  return (
    <div data-testid="wish-list-panel">
      <p className="muted">
        Pinned items for this character. Owned uses the last inventory import. The mote path uses the same rules as Requirements.
      </p>
      {!names.length ? <p>Nothing is pinned.</p> : null}
      {names.map((name) => {
        const item = byName.get(name.toLowerCase())
        const owned = typeof isOwned === 'function'
          ? !!isOwned(name)
          : ownedList.some((entry) => String(entry).toLowerCase() === name.toLowerCase())
        return (
          <article key={name} className="requirement-card">
            <h3>
              {name}
              {owned ? ' · owned' : ' · not owned'}
            </h3>
            <button type="button" onClick={() => onUnpin(name)}>Unpin</button>
            {item ? (
              <>
                <p>{item.xp_needed} XP to +{item.target_tier}</p>
                <MoteLine label="Motes this takes" rows={item.motes} />
                <MoteLine label="Still missing" rows={item.missing} />
                {item.tier_note ? <p className="note">{item.tier_note}</p> : null}
              </>
            ) : (
              <p className="muted">Open Wish list after Best in Slot has run to see the mote path.</p>
            )}
          </article>
        )
      })}
    </div>
  )
}
