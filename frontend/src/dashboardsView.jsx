import React, { useEffect, useState } from 'react'
import { openParserStream } from './parserApi.js'
import {
  getDashboardConsidered,
  getDashboardLeveling,
  getDashboardLoot,
  getDashboardMob,
  getDashboardOverlay,
  getDashboardOverview,
  getDashboardRaids,
  postDashboardFavourite,
  postDashboardLockout,
  postDashboardMoteGrade,
  postDashboardWishes,
} from './parserApi.js'
import {
  MULTI_CLASS_CAVEAT,
  XP_HONESTY,
  conLine,
  dropRateLabel,
  formatHours,
  formatLevelsPerHour,
  toastText,
  toastsFromStream,
} from './dashboardsView.js'

function useDashboard(loader, character, wishes, deps) {
  const [body, setBody] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    let cancelled = false
    const name = (character || '').trim()
    if (!name) {
      setBody(null)
      setError('')
      return undefined
    }
    setLoading(true)
    const run = async () => {
      try {
        if (Array.isArray(wishes)) await postDashboardWishes(name, wishes)
        const next = await loader(name)
        if (!cancelled) {
          setBody(next)
          setError('')
        }
      } catch (err) {
        if (!cancelled) setError(String(err.message || err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    run()
    return () => {
      cancelled = true
    }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  return { body, error, loading, reload: () => setBody((current) => current) }
}

function EmptyCharacter() {
  return (
    <p className="muted" data-testid="dashboard-need-character">
      Choose a character on Currencies, or import that character, so these pages can use the combat log under that name.
    </p>
  )
}

function StatList({ stats }) {
  const entries = stats && typeof stats === 'object' ? Object.entries(stats) : []
  if (!entries.length) return <span className="muted">unknown</span>
  return (
    <span>
      {entries.map(([key, value]) => `${key} ${value}`).join(' · ')}
    </span>
  )
}

function Sparkline({ curve }) {
  const buckets = curve?.available ? curve.buckets || [] : []
  if (!buckets.length) {
    return <p className="muted" data-testid="dps-curve-empty">{curve?.reason || 'No DPS curve is stored for this fight.'}</p>
  }
  const values = buckets.map((row) => Number(row.you) || 0)
  const max = Math.max(...values, 1)
  const width = 280
  const height = 64
  const step = buckets.length === 1 ? width : width / (buckets.length - 1)
  const points = values.map((value, index) => {
    const x = index * step
    const y = height - (value / max) * (height - 4) - 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg className="dps-spark" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Your damage over the fight" data-testid="dps-curve">
      <polyline fill="none" stroke="currentColor" strokeWidth="2" points={points} />
    </svg>
  )
}

export function OverviewPanel({ character, wishes }) {
  const { body, error, loading } = useDashboard(
    (name) => getDashboardOverview(name),
    character,
    wishes,
    [character, (wishes || []).join('|')],
  )
  if (!(character || '').trim()) return <div className="panel"><h2>Overview</h2><EmptyCharacter /></div>
  const mob = body?.current_mob || {}
  const dps = body?.dps || {}
  return (
    <div className="panel dashboard-panel" data-testid="overview-panel">
      <h2>Overview</h2>
      <p className="note" data-testid="overview-caveat">{body?.caveat || MULTI_CLASS_CAVEAT}</p>
      {loading ? <p className="muted">Loading the log…</p> : null}
      {error ? <p className="error">{error}</p> : null}
      <div className="dashboard-grid">
        <section className="dashboard-card" data-testid="card-current-mob">
          <h3>Current mob</h3>
          <p>{mob.status === 'fighting' ? (mob.names || []).join(', ') || 'unknown' : 'No fight open'}</p>
          <p className="muted">{mob.zone || 'zone unknown'}</p>
          {(mob.last_targets || []).length ? (
            <p className="muted">Recent: {(mob.last_targets || []).join(', ')}</p>
          ) : null}
        </section>
        <section className="dashboard-card" data-testid="card-dps">
          <h3>DPS</h3>
          <p>{dps.your_dps == null ? 'unknown' : `${Number(dps.your_dps).toFixed(1)} DPS`}</p>
          <p className="muted">{(dps.targets || []).join(', ') || 'no targets'}</p>
          <Sparkline curve={dps.curve} />
        </section>
        <section className="dashboard-card" data-testid="card-leveling">
          <h3>Leveling</h3>
          <p>{formatLevelsPerHour(body?.leveling?.levels_per_hour)}</p>
          <p className="muted">Time to level {formatHours(body?.leveling?.hours_to_level)}</p>
          <p className="muted">
            {(body?.leveling?.classes || []).join(' / ') || 'classes unknown'}
            {body?.leveling?.level != null ? ` · ${body.leveling.level}` : ''}
          </p>
        </section>
        <section className="dashboard-card" data-testid="card-drops">
          <h3>Recent drops</h3>
          <ul className="dashboard-list">
            {(body?.recent_loots || []).map((row, index) => (
              <li key={`${row.item}-${index}`}>{row.item || row.coin_text || 'unknown'}{row.from ? ` from ${row.from}` : ''}</li>
            ))}
          </ul>
          {(body?.recent_loots || []).length ? null : <p className="muted">No loot yet.</p>}
        </section>
        <section className="dashboard-card" data-testid="card-kills">
          <h3>Recent kills</h3>
          <ul className="dashboard-list">
            {(body?.recent_kills || []).map((row, index) => (
              <li key={`${row.mob}-${index}`}>{row.mob || 'unknown'}</li>
            ))}
          </ul>
          {(body?.recent_kills || []).length ? null : <p className="muted">No kills yet.</p>}
        </section>
        <section className="dashboard-card" data-testid="card-zones">
          <h3>Zones</h3>
          <ul className="zone-strip">
            {(body?.zones || []).map((row) => (
              <li key={`${row.zone}-${row.ts}`}>{row.zone}{row.instance?.tier ? ` · ${row.instance.tier}` : ''}</li>
            ))}
          </ul>
          {(body?.zones || []).length ? null : <p className="muted">No zone yet.</p>}
        </section>
      </div>
    </div>
  )
}

export function LootPanel({ character, wishes }) {
  const [grade, setGrade] = useState('')
  const [tick, setTick] = useState(0)
  const { body, error, loading } = useDashboard(
    (name) => getDashboardLoot(name),
    character,
    wishes,
    [character, (wishes || []).join('|'), tick],
  )
  useEffect(() => {
    if (body && body.mote_notable_grade != null && grade === '') setGrade(String(body.mote_notable_grade))
  }, [body, grade])
  if (!(character || '').trim()) return <div className="panel"><h2>Loot</h2><EmptyCharacter /></div>
  const saveGrade = async () => {
    const trimmed = grade.trim()
    await postDashboardMoteGrade(trimmed === '' ? null : Number(trimmed))
    setTick((n) => n + 1)
  }
  const star = async (item, starred) => {
    await postDashboardFavourite({ character, kind: 'item', name: item, starred: !starred })
    setTick((n) => n + 1)
  }
  return (
    <div className="panel dashboard-panel" data-testid="loot-panel">
      <h2>Loot</h2>
      <p className="muted">Drop rate is your loot lines divided by your kills of that mob. A mob you have not killed stays unknown.</p>
      {loading ? <p className="muted">Loading loot…</p> : null}
      {error ? <p className="error">{error}</p> : null}
      <div className="row">
        <label>
          Notable mote grade
          <input
            type="number"
            min="1"
            max="10"
            value={grade}
            placeholder="blank skips motes"
            data-testid="mote-grade"
            onChange={(event) => setGrade(event.target.value)}
          />
        </label>
        <button type="button" onClick={saveGrade}>Save grade</button>
      </div>
      <h3>Your drop rates</h3>
      <table className="data-table" data-testid="drop-rates">
        <thead>
          <tr><th>Mob</th><th>Loots</th><th>Kills</th><th>Rate</th></tr>
        </thead>
        <tbody>
          {(body?.drop_rates || []).map((row) => {
            const label = dropRateLabel(row.loots, row.kills)
            return (
              <tr key={row.mob}>
                <td>{row.mob}</td>
                <td>{row.loots}</td>
                <td>{row.kills}</td>
                <td>{row.rate_text || label.text}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <h3>History</h3>
      <ul className="dashboard-list" data-testid="loot-ledger">
        {(body?.loot || []).map((row, index) => {
          const knowledge = row.knowledge || {}
          return (
            <li key={`${row.item}-${row.ts}-${index}`}>
              <button
                type="button"
                className={row.favourite ? 'star on' : 'star'}
                aria-label={row.favourite ? 'Unstar item' : 'Star item'}
                onClick={() => star(row.item, row.favourite)}
              >
                {row.favourite ? '★' : '☆'}
              </button>
              <strong>{row.item || 'unknown'}</strong>
              {row.from ? <span> from {row.from}</span> : null}
              {row.mode ? <span className="muted"> · {row.mode}</span> : null}
              {(row.notable || []).length ? <span className="badge">Notable: {row.notable.join(', ')}</span> : null}
              <div className="muted">
                {knowledge.known ? <StatList stats={knowledge.stats} /> : (knowledge.note || 'unknown')}
              </div>
              {(knowledge.quests || []).length ? (
                <div className="quest-flags">
                  {(knowledge.quests || []).map((flag) => (
                    <span key={flag.quest} className="badge">{flag.quest}</span>
                  ))}
                </div>
              ) : null}
            </li>
          )
        })}
      </ul>
      {(body?.loot || []).length ? null : <p className="muted">No loot in the log yet.</p>}
    </div>
  )
}

export function LevelingPanel({ character, payload }) {
  const remote = useDashboard(
    (name) => getDashboardLeveling(name),
    character,
    null,
    [character, payload ? 'fixed' : 'live'],
  )
  const body = payload || remote.body
  const error = payload ? '' : remote.error
  const loading = payload ? false : remote.loading
  if (!payload && !(character || '').trim()) {
    return <div className="panel"><h2>Leveling & AA</h2><EmptyCharacter /></div>
  }
  const band = body?.zone_band || {}
  return (
    <div className="panel dashboard-panel" data-testid="leveling-panel">
      <h2>Leveling & AA</h2>
      <p className="note" data-testid="leveling-caveat">{body?.caveat || MULTI_CLASS_CAVEAT}</p>
      <p className="muted">{body?.honesty || XP_HONESTY}</p>
      {loading ? <p className="muted">Loading experience…</p> : null}
      {error ? <p className="error">{error}</p> : null}
      <div className="dashboard-grid">
        <section className="dashboard-card">
          <h3>Pace</h3>
          <p data-testid="xp-pace">{formatLevelsPerHour(body?.levels_per_hour)}</p>
          <p className="muted" data-testid="time-to-level">Time to level {formatHours(body?.hours_to_level)}</p>
          <p className="muted">
            {body?.bar_known ? `Bar ${body.progress_pct == null ? 'unknown' : `${Number(body.progress_pct).toFixed(1)}%`}` : 'Bar unknown. A percent-less experience line is in this level.'}
          </p>
          {body?.xp_lines_without_percent ? (
            <p className="muted">{body.xp_lines_without_percent} experience line(s) had no percent and were not counted as 0.</p>
          ) : null}
        </section>
        <section className="dashboard-card">
          <h3>AA</h3>
          <p data-testid="aa-pace">{body?.aa_per_hour == null ? 'unknown' : `${Number(body.aa_per_hour).toFixed(2)} points / hour`}</p>
          <p className="muted">{body?.aa_total == null ? 'Total unknown' : `You now have ${body.aa_total}`}</p>
          <p className="muted">{body?.aa_note}</p>
        </section>
        <section className="dashboard-card">
          <h3>Zone band</h3>
          <p>{band.zone || 'zone unknown'}</p>
          <p className="muted" data-testid="zone-band">
            {band.status === 'sourced' ? band.level_requirement : 'unknown'}
          </p>
          {band.note ? <p className="muted">{band.note}</p> : null}
        </section>
      </div>
      <h3>Level history</h3>
      <ul className="dashboard-list" data-testid="level-history">
        {(body?.history || []).map((row, index) => (
          <li key={`${row.start_ts}-${index}`}>
            {row.classes || 'classes unknown'} · {row.start_level ?? '?'} → {row.end_level ?? '?'}
            {row.classes_note ? <span className="muted"> · {row.classes_note}</span> : null}
          </li>
        ))}
      </ul>
      <h3>New at this level</h3>
      <p className="muted">Sourced spells only. A spell with no cast level on file is left out.</p>
      <ul className="dashboard-list" data-testid="new-at-level">
        {(body?.new_at_level || []).map((row) => (
          <li key={`${row.class}-${row.name}`}>{row.name} · {row.class} · L{row.level}</li>
        ))}
      </ul>
      {(body?.new_at_level || []).length ? null : <p className="muted">Nothing sourced for this level.</p>}
    </div>
  )
}

export function RaidsPanel({ character, onSelectMob }) {
  const [mob, setMob] = useState('')
  const [note, setNote] = useState('')
  const [tick, setTick] = useState(0)
  const [page, setPage] = useState(null)
  const { body, error, loading } = useDashboard(
    (name) => getDashboardRaids(name),
    character,
    null,
    [character, tick],
  )
  if (!(character || '').trim()) return <div className="panel"><h2>Raid targets</h2><EmptyCharacter /></div>
  const week = body?.lockout_week || {}
  const save = async () => {
    if (!mob.trim()) return
    await postDashboardLockout({ character, mob: mob.trim(), note, clear: false })
    setTick((n) => n + 1)
  }
  const openMob = async (name) => {
    const detail = await getDashboardMob(character, name)
    setPage(detail)
    if (onSelectMob) onSelectMob(name)
  }
  return (
    <div className="panel dashboard-panel" data-testid="raids-panel">
      <h2>Raid targets</h2>
      <p className="note" data-testid="lockout-week">{week.note}</p>
      <p data-testid="lockout-countdown">{week.countdown_label || 'unknown'}</p>
      <p className="muted">{body?.unverified_note}</p>
      {loading ? <p className="muted">Loading kills…</p> : null}
      {error ? <p className="error">{error}</p> : null}
      <h3>Kills</h3>
      <ul className="dashboard-list" data-testid="raid-kills">
        {(body?.kills || []).map((row, index) => (
          <li key={`${row.mob}-${row.ts}-${index}`}>
            <button type="button" className="linkish" onClick={() => openMob(row.mob)}>{row.mob}</button>
            <span className="muted"> · {row.difficulty === 'unknown' ? 'difficulty unknown' : row.difficulty}</span>
            <span className="muted"> · {row.zone || 'zone unknown'}</span>
          </li>
        ))}
      </ul>
      {(body?.kills || []).length ? null : <p className="muted">No named, mini-boss, or raid kill is in the log yet.</p>}
      <h3>Your lockouts</h3>
      <p className="muted">These are UNVERIFIED. The app does not invent a reset time for them.</p>
      <ul className="dashboard-list" data-testid="user-lockouts">
        {(body?.user_lockouts || []).map((row) => (
          <li key={row.mob}>
            {row.mob} · {row.status || 'UNVERIFIED'}
            {row.note ? ` · ${row.note}` : ''}
          </li>
        ))}
      </ul>
      <div className="row">
        <input value={mob} placeholder="Mob name" aria-label="Lockout mob" onChange={(event) => setMob(event.target.value)} />
        <input value={note} placeholder="Your note" aria-label="Lockout note" onChange={(event) => setNote(event.target.value)} />
        <button type="button" onClick={save}>Save lockout</button>
      </div>
      {page ? (
        <section data-testid="mob-page">
          <h3>{page.name}</h3>
          <p>Your drop rate {page.drop_rate_text || 'unknown'}</p>
          <p className="muted">{page.wiki_level ? `Wiki level ${page.wiki_level}` : page.wiki_level_note}</p>
          <h4>Considered</h4>
          <ul>
            {(page.your_considers || []).map((row, index) => (
              <li key={`${row.ts}-${index}`}>{conLine(row)}{row.zone ? ` · ${row.zone}` : ''}</li>
            ))}
          </ul>
          <h4>Looted</h4>
          <ul>
            {(page.your_loots || []).map((row, index) => (
              <li key={`${row.item}-${index}`}>{row.item || 'unknown'}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}

export function RecentlyConsidered({ character, onSelectMob }) {
  const { body } = useDashboard(
    (name) => getDashboardConsidered(name),
    character,
    null,
    [character],
  )
  const rows = body?.considered || []
  if (!rows.length) return null
  return (
    <section className="dashboard-card" data-testid="recently-considered">
      <h3>Recently considered</h3>
      <ul className="dashboard-list">
        {rows.map((row, index) => (
          <li key={`${row.mob}-${row.ts}-${index}`}>
            <button type="button" className="linkish" onClick={() => onSelectMob && onSelectMob(row.mob)}>
              {conLine(row)}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function DashboardToasts() {
  const [toast, setToast] = useState(null)
  useEffect(() => {
    const stream = openParserStream({
      toast: (data) => {
        const next = toastsFromStream(data, { live: true })
        if (next[0]) setToast(next[0])
      },
    })
    return () => stream.close()
  }, [])
  useEffect(() => {
    if (!toast) return undefined
    const timer = setTimeout(() => setToast(null), 8000)
    return () => clearTimeout(timer)
  }, [toast])
  if (!toast) return null
  return (
    <div className="live-toast" role="status" data-testid="live-toast">
      {toast.kind === 'level' ? 'Level up' : 'Notable loot'}
      <strong>{toastText(toast)}</strong>
    </div>
  )
}

export function overlayCardText(payload) {
  if (!payload) return 'Loading…'
  if (payload.kind === 'con') return conLine(payload.consider)
  const pct = payload.latest && payload.latest.pct != null ? `${payload.latest.pct}%` : 'no percent'
  return `${formatLevelsPerHour(payload.levels_per_hour)} · last ${pct}`
}

export { getDashboardOverlay }
