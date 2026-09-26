import {
  categoryLabel,
  chartValue,
  formatParseText,
  lootModeLabel,
  spellBucketAmount,
  spellStats,
  timelinePeak,
} from './parserDepth.js'
import { formatDamage, formatFightTime, formatRate } from './parserView.js'

function rateText(value) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${formatRate(value)}%`
}

function numText(value) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return formatDamage(value)
}

export function ParserItemName({ name, itemNameProps }) {
  const label = typeof name === 'string' ? name.trim() : ''
  if (!label) return null
  if (!itemNameProps || typeof itemNameProps.openMenu !== 'function') return label
  return (
    <button
      type="button"
      className="zone-link"
      data-parser-item={label}
      onMouseEnter={(e) => itemNameProps.preview && itemNameProps.preview(label, e)}
      onMouseMove={(e) => {
        if (itemNameProps.menuOpen) return
        if (itemNameProps.moveTip) itemNameProps.moveTip(e)
      }}
      onMouseLeave={() => itemNameProps.hideTip && itemNameProps.hideTip()}
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        itemNameProps.openMenu(label, e)
      }}
    >
      {label}
    </button>
  )
}

export function SpellPage({ row, timeline, onClose }) {
  const stats = spellStats(row)
  if (!stats) return null
  const buckets = Array.isArray(timeline?.buckets) ? timeline.buckets : []
  const bin = timeline?.bin_seconds || 1
  let peak = 0
  let peakT = 0
  for (const bucket of buckets) {
    const amount = spellBucketAmount(bucket) / bin
    if (amount >= peak) {
      peak = amount
      peakT = Number(bucket.t) || 0
    }
  }
  return (
    <section className="parser-spell-page" data-testid="parser-spell-page">
      <div className="parser-detail-head">
        <h3 className="parser-subhead">{stats.name || 'Spell'}</h3>
        <button type="button" onClick={onClose}>Close</button>
      </div>
      <p className="note">
        {stats.source ? `${stats.source}` : 'Unknown source'}
        {stats.target ? ` on ${stats.target}` : ''}
        {' · '}
        {stats.heal ? (stats.overTime ? 'Heal over time' : 'Direct heal') : categoryLabel(stats.category)}
      </p>
      <dl className="parser-spell-stats">
        <div><dt>Hits</dt><dd>{formatDamage(stats.hits)}</dd></div>
        {stats.heal ? null : <div><dt>Misses</dt><dd>{formatDamage(stats.misses)}</dd></div>}
        {stats.heal ? null : <div><dt>Hit %</dt><dd>{rateText(stats.hitPct)}</dd></div>}
        <div><dt>Crits</dt><dd>{formatDamage(stats.crits)}</dd></div>
        <div><dt>Crit %</dt><dd>{rateText(stats.critPct)}</dd></div>
        <div><dt>{stats.heal ? 'Actual' : 'Damage'}</dt><dd>{numText(stats.total)}</dd></div>
        <div><dt>Average</dt><dd>{stats.avg == null ? '—' : formatRate(stats.avg)}</dd></div>
        {stats.heal ? null : <div><dt>Max</dt><dd>{numText(stats.max)}</dd></div>}
        {stats.heal ? <div><dt>Full</dt><dd>{numText(stats.full)}</dd></div> : null}
        {stats.heal ? <div><dt>Overheal</dt><dd data-testid="parser-spell-overheal">{numText(stats.overheal)}</dd></div> : null}
      </dl>
      {buckets.length ? (
        <p className="note" data-testid="parser-spell-peak">
          Peak {formatRate(peak)} per second at {formatDamage(peakT)}s. Amounts come from the log.
        </p>
      ) : (
        <p className="muted">No per-second amounts for this name in the log range.</p>
      )}
      {buckets.length ? (
        <TimelineChart
          buckets={buckets}
          binSeconds={bin}
          series={[{ id: 'spell', label: stats.name, stroke: 'var(--gold)', value: (bucket) => spellBucketAmount(bucket) / bin }]}
        />
      ) : null}
    </section>
  )
}

export function AbilityList({ abilities, onOpenSpell }) {
  const rows = Array.isArray(abilities) ? abilities : []
  if (!rows.length) return <p className="muted">No attacks or spells for this source.</p>
  return (
    <table className="parser-table parser-abilities" data-testid="parser-abilities">
      <thead>
        <tr>
          <th>Attack / spell</th>
          <th>Type</th>
          <th>Damage</th>
          <th>Hits</th>
          <th>Miss</th>
          <th>Crit</th>
          <th>Crit %</th>
          <th>Avg</th>
          <th>Max</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((ability) => {
          const stats = spellStats(ability)
          return (
            <tr key={`${ability.category}:${ability.ability}`}>
              <td>
                <button
                  type="button"
                  className="zone-link"
                  data-testid="parser-spell"
                  data-spell={ability.ability}
                  onClick={(e) => {
                    e.stopPropagation()
                    if (onOpenSpell) onOpenSpell(ability)
                  }}
                >
                  {ability.ability}
                </button>
              </td>
              <td>{categoryLabel(ability.category)}</td>
              <td>{formatDamage(ability.damage)}</td>
              <td>{formatDamage(ability.hits)}</td>
              <td>{formatDamage(ability.misses)}</td>
              <td>{formatDamage(ability.crits)}</td>
              <td>{rateText(stats?.critPct)}</td>
              <td>{stats?.avg == null ? '—' : formatRate(stats.avg)}</td>
              <td>{formatDamage(ability.max_hit)}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export function TimelineChart({ buckets, binSeconds = 1, series, summary }) {
  const rows = Array.isArray(buckets) ? buckets : []
  const lines = Array.isArray(series) ? series : []
  const width = 640
  const height = 180
  const pad = 8
  let maxY = 1
  for (const row of rows) {
    for (const line of lines) {
      const value = Number(line.value(row)) || 0
      if (value > maxY) maxY = value
    }
  }
  const span = Math.max(rows.length ? Number(rows[rows.length - 1].t) || 0 : 0, binSeconds, 1)
  const pathFor = (line) => rows.map((row) => {
    const x = pad + ((Number(row.t) || 0) / span) * (width - pad * 2)
    const y = height - pad - ((Number(line.value(row)) || 0) / maxY) * (height - pad * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <div className="parser-chart" data-testid="parser-timeline-chart">
      {summary ? <p className="note" data-testid="parser-timeline-summary">{summary}</p> : null}
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={summary || 'DPS over time'}>
        <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} stroke="var(--border)" />
        {lines.map((line) => (
          <polyline
            key={line.id}
            fill="none"
            stroke={line.stroke}
            strokeWidth="2"
            points={pathFor(line)}
            data-series={line.id}
          />
        ))}
      </svg>
      <p className="parser-legend">
        {lines.map((line) => (
          <span key={line.id} data-series={line.id}>{line.label}</span>
        ))}
        <span>Each point is damage in that {binSeconds === 1 ? 'second' : `${binSeconds}s`} divided by the bin, so the axis is DPS.</span>
      </p>
    </div>
  )
}

export function FightTimeline({ timeline, scope, status }) {
  if (status === 'loading') return <p className="muted">Reading the log range for this fight…</p>
  if (status === 'missing') return <p className="muted">This fight has no log byte range to chart.</p>
  const buckets = Array.isArray(timeline?.buckets) ? timeline.buckets : []
  if (!timeline?.available && status === 'ready') {
    return <p className="muted">{timeline?.reason || 'The log file for this fight is not available.'}</p>
  }
  if (!buckets.length) return <p className="muted">No timed damage in this fight.</p>
  const bin = timeline.bin_seconds || 1
  const peak = timelinePeak(buckets, scope, bin)
  const outgoingLabel = scope === 'pets' ? 'Pets' : (scope === 'self' ? 'You' : 'Outgoing')
  const summary = `Peak ${outgoingLabel} ${formatRate(peak.outgoing)} DPS at ${formatDamage(peak.outgoingT)}s. Incoming peak ${formatRate(peak.incoming)} DPS at ${formatDamage(peak.incomingT)}s.`
  return (
    <TimelineChart
      buckets={buckets}
      binSeconds={bin}
      summary={summary}
      series={[
        {
          id: 'outgoing',
          label: outgoingLabel,
          stroke: 'var(--gold)',
          value: (bucket) => chartValue(bucket, scope, bin).outgoing,
        },
        {
          id: 'incoming',
          label: 'Incoming',
          stroke: 'var(--danger)',
          value: (bucket) => chartValue(bucket, scope, bin).incoming,
        },
      ]}
    />
  )
}

export function HealingPanel({ healing, names, onOpenSpell }) {
  const rows = (healing?.rows || []).filter((row) => !names || names.has(String(row.source || '').toLowerCase()))
  if (!rows.length) return <p className="muted">No heals in this scope.</p>
  const sum = (key, pred) => rows.reduce((total, row) => (
    !pred || pred(row) ? total + (Number(row[key]) || 0) : total
  ), 0)
  return (
    <div data-testid="parser-healing">
      <p className="parser-totals">
        Actual {formatDamage(sum('actual'))}
        {' · full '}
        {formatDamage(sum('full'))}
        {' · overheal '}
        {formatDamage(sum('overheal'))}
        {' · direct '}
        {formatDamage(sum('actual', (row) => !row.over_time))}
        {' · over time '}
        {formatDamage(sum('actual', (row) => !!row.over_time))}
      </p>
      <div className="parser-table-wrap">
        <table className="parser-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Target</th>
              <th>Spell</th>
              <th>Type</th>
              <th>Actual</th>
              <th>Full</th>
              <th>Overheal</th>
              <th>Hits</th>
              <th>Crits</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.source}:${row.target}:${row.spell}:${row.over_time ? 1 : 0}`}>
                <td>{row.source}</td>
                <td>{row.target}</td>
                <td>
                  <button type="button" className="zone-link" data-testid="parser-spell" onClick={() => onOpenSpell && onOpenSpell(row)}>
                    {row.spell}
                  </button>
                </td>
                <td>{row.over_time ? 'Over time' : 'Direct'}</td>
                <td>{formatDamage(row.actual)}</td>
                <td>{formatDamage(row.full)}</td>
                <td>{formatDamage(row.overheal)}</td>
                <td>{formatDamage(row.hits)}</td>
                <td>{formatDamage(row.crits)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function TankingPanel({ tanking, names }) {
  const keep = (name) => !names || names.has(String(name || '').toLowerCase())
  const incoming = (tanking?.incoming || []).filter((row) => keep(row.target))
  const avoidance = (tanking?.avoidance || []).filter((row) => keep(row.target))
  const runes = (tanking?.runes || []).filter((row) => keep(row.source))
  const selfDamage = (tanking?.self_damage || []).filter((row) => keep(row.target))
  if (!incoming.length && !avoidance.length && !runes.length && !selfDamage.length) {
    return <p className="muted">No damage taken in this scope.</p>
  }
  return (
    <div data-testid="parser-tanking">
      {incoming.length ? (
        <>
          <h4 className="parser-subhead">Damage taken</h4>
          <div className="parser-table-wrap">
            <table className="parser-table">
              <thead>
                <tr>
                  <th>Target</th>
                  <th>Source</th>
                  <th>Ability</th>
                  <th>Type</th>
                  <th>Damage</th>
                  <th>Hits</th>
                  <th>Max</th>
                </tr>
              </thead>
              <tbody>
                {incoming.map((row) => (
                  <tr key={`${row.target}:${row.source}:${row.category}:${row.ability}`}>
                    <td>{row.target}</td>
                    <td>{row.source || 'unknown'}</td>
                    <td>{row.ability}</td>
                    <td>{categoryLabel(row.category)}</td>
                    <td>{formatDamage(row.damage)}</td>
                    <td>{formatDamage(row.hits)}</td>
                    <td>{formatDamage(row.max_hit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
      {avoidance.length ? (
        <>
          <h4 className="parser-subhead">Avoidance</h4>
          <ul className="parser-allow-list">
            {avoidance.map((row) => (
              <li key={`${row.target}:${row.kind}`}>{row.target}: {row.kind} {formatDamage(row.count)}</li>
            ))}
          </ul>
        </>
      ) : null}
      {runes.length ? (
        <>
          <h4 className="parser-subhead">Runes</h4>
          <p className="note">The log prints absorption gained. It does not say how much of the rune was later used.</p>
          <ul className="parser-allow-list">
            {runes.map((row) => (
              <li key={row.source}>{row.source}: {formatDamage(row.absorption)} across {formatDamage(row.count)}</li>
            ))}
          </ul>
        </>
      ) : null}
      {selfDamage.length ? (
        <>
          <h4 className="parser-subhead">Self damage</h4>
          <p className="note">You hurt yourself is kept out of DPS.</p>
          <ul className="parser-allow-list">
            {selfDamage.map((row) => (
              <li key={row.target}>{row.target}: {formatDamage(row.damage)} ({formatDamage(row.hits)})</li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  )
}

export function DeathsPanel({ deaths, names }) {
  const rows = (Array.isArray(deaths) ? deaths : []).filter((row) => !names || names.has(String(row.who || '').toLowerCase()))
  if (!rows.length) return <p className="muted">No deaths in this scope.</p>
  return (
    <div data-testid="parser-deaths">
      {rows.map((row, index) => (
        <article key={`${row.ts}:${row.who}:${index}`} className="parser-death" data-testid="parser-death">
          <h4>{row.who}{row.killer ? ` slain by ${row.killer}` : ''}</h4>
          <p className="note">{formatFightTime(row.ts)} · {row.kind || 'death'}</p>
          <p className="muted">Last {Array.isArray(row.incoming) ? row.incoming.length : 0} incoming events</p>
          <ol className="parser-death-log">
            {(row.incoming || []).map((event, eventIndex) => (
              <li key={`${event.ts}:${eventIndex}`}>
                {formatFightTime(event.ts)}
                {' '}
                {event.source || 'unknown'}
                {' '}
                {event.ability || event.kind || 'event'}
                {event.amount ? ` ${formatDamage(event.amount)}` : ''}
                {event.avoidance ? ` (${event.avoidance})` : ''}
                {event.critical ? ' critical' : ''}
              </li>
            ))}
          </ol>
        </article>
      ))}
    </div>
  )
}

export function ResistsPanel({ resists, names }) {
  const rows = (Array.isArray(resists) ? resists : []).filter((row) => {
    if (!names) return true
    return names.has(String(row.source || '').toLowerCase()) || names.has(String(row.target || '').toLowerCase())
  })
  if (!rows.length) return <p className="muted">No resists in this scope.</p>
  return (
    <div className="parser-table-wrap" data-testid="parser-resists">
      <table className="parser-table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Target</th>
            <th>Spell</th>
            <th>Count</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.source}:${row.target}:${row.spell}`}>
              <td>{row.source || 'unknown'}</td>
              <td>{row.target || 'unknown'}</td>
              <td>{row.spell}</td>
              <td>{formatDamage(row.count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function LootPanel({ loot, status, page, pages, onPage, fightOnly, onFightOnly, itemNameProps }) {
  if (status === 'loading') return <p className="muted">Loading loot…</p>
  const events = loot?.rows || []
  return (
    <div data-testid="parser-loot">
      <div className="parser-toolbar">
        <button type="button" className={fightOnly ? 'on' : undefined} aria-pressed={!!fightOnly} onClick={() => onFightOnly && onFightOnly(true)}>
          This fight
        </button>
        <button type="button" className={!fightOnly ? 'on' : undefined} aria-pressed={!fightOnly} onClick={() => onFightOnly && onFightOnly(false)}>
          All saved
        </button>
      </div>
      {!events.length ? <p className="muted">No loot in this view.</p> : null}
      {events.length ? (
        <div className="parser-table-wrap">
          <table className="parser-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Item</th>
                <th>Qty</th>
                <th>From</th>
                <th>How</th>
              </tr>
            </thead>
            <tbody>
              {events.map((row, index) => (
                <tr key={`${row.ts}:${row.item}:${index}`}>
                  <td>{formatFightTime(row.ts)}</td>
                  <td><ParserItemName name={row.item} itemNameProps={itemNameProps} /></td>
                  <td>{formatDamage(row.qty)}</td>
                  <td>{row.from || row.npc || '—'}</td>
                  <td>{lootModeLabel(row.mode)}{row.is_mote ? ' · mote' : ''}{row.is_wind_rune ? ' · wind rune' : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {Array.isArray(loot?.gives) && loot.gives.length ? (
        <>
          <h4 className="parser-subhead">Turn-ins</h4>
          <ul className="parser-allow-list">
            {loot.gives.map((row, index) => (
              <li key={`${row.ts}:${index}`}>
                {formatFightTime(row.ts)} · {formatDamage(row.qty)} <ParserItemName name={row.item} itemNameProps={itemNameProps} /> to {row.npc}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {Array.isArray(loot?.merges) && loot.merges.length ? (
        <>
          <h4 className="parser-subhead">Merges</h4>
          <p className="note">The log names the result. It does not name which mote was used.</p>
          <ul className="parser-allow-list">
            {loot.merges.map((row, index) => (
              <li key={`${row.ts}:${index}`}>
                {formatFightTime(row.ts)} · <ParserItemName name={row.result_item} itemNameProps={itemNameProps} />
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <p className="note">
        Page {page} of {pages}
        <button type="button" disabled={page <= 1} onClick={() => onPage && onPage(page - 1)}>Previous</button>
        <button type="button" disabled={page >= pages} onClick={() => onPage && onPage(page + 1)}>Next</button>
      </p>
    </div>
  )
}

export function MultiAttackTable({ multi, names }) {
  const rows = (multi?.sources || []).filter((row) => !names || names.has(String(row.source || '').toLowerCase()))
  if (!rows.length) return null
  return (
    <div data-testid="parser-multi">
      <h4 className="parser-subhead">Multi-attack estimate</h4>
      <p className="note">{multi?.note || 'Estimate from swings that share a timestamp second.'}</p>
      <div className="parser-table-wrap">
        <table className="parser-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Rounds</th>
              <th>Double</th>
              <th>Triple</th>
              <th>Flurry</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.source}>
                <td>{row.source}</td>
                <td>{formatDamage(row.rounds)}</td>
                <td>{formatRate((Number(row.double_rate) || 0) * 100)}%</td>
                <td>{formatRate((Number(row.triple_rate) || 0) * 100)}%</td>
                <td>{formatRate((Number(row.flurry_rate) || 0) * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ProcsTable({ procs, names, itemNameProps }) {
  const items = (procs?.items || []).filter((row) => !names || names.has(String(row.source || '').toLowerCase()))
  if (!items.length) return null
  return (
    <div data-testid="parser-procs">
      <h4 className="parser-subhead">Procs</h4>
      <p className="note">{formatRate(procs?.per_minute)} per minute over the fight. Count {formatDamage(procs?.count)}.</p>
      <ul className="parser-allow-list">
        {items.map((row) => (
          <li key={`${row.source}:${row.item}`}>
            {row.source}: <ParserItemName name={row.item} itemNameProps={itemNameProps} /> × {formatDamage(row.count)}
          </li>
        ))}
      </ul>
    </div>
  )
}

export function copyPreviewText(detail, sources) {
  return formatParseText(detail, sources)
}
