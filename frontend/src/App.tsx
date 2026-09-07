import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ClassesResp, ItemRow, RacesResp } from './api'

const DEFAULT: string[] = []  // 1.0.1: no default classes

function fmtStats(s?: Record<string, number>, keys?: string[]) {
  if (!s) return ''
  const use = keys || ['AC', 'HP', 'MANA', 'STR', 'STA', 'AGI', 'DEX', 'WIS', 'INT', 'CHA', 'Haste']
  return use
    .filter((k) => s[k] != null && Number(s[k]) !== 0)
    .map((k) => `${k}:${Math.round(Number(s[k]))}`)
    .join(' ')
}

export default function App() {
  const [meta, setMeta] = useState<ClassesResp | null>(null)
  const [races, setRaces] = useState<RacesResp | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [mode, setMode] = useState<'priority' | 'max'>('priority')
  const [stat, setStat] = useState('INT')
  const [upgrade, setUpgrade] = useState(10)
  const [race, setRace] = useState('Human')
  const [bySlot, setBySlot] = useState<Record<string, ItemRow[]>>({})
  const [equipped, setEquipped] = useState<Record<string, string>>({})
  const [sim, setSim] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [exportMsg, setExportMsg] = useState<string | null>(null)
  const [viewSlot, setViewSlot] = useState('HEAD')
  const [preferRanged, setPreferRanged] = useState(true)
  const [charLevel, setCharLevel] = useState(60)

  useEffect(() => {
    Promise.all([api.classes(), api.races()])
      .then(([c, r]) => {
        setMeta(c)
        // 1.0.1: do not force default_trio into UI
        setSelected([])
        setRaces(r)
        if (r.races?.some((x) => x.name === 'Human')) setRace('Human')
        else if (r.races?.[0]) setRace(r.races[0].name)
      })
      .catch((e) => setErr(String(e)))
  }, [])

  const loadItems = useCallback(async () => {
    if (selected.length < 1) return
    setLoading(true)
    setErr(null)
    try {
      const params = new URLSearchParams()
      params.set('classes', selected.join(','))
      params.set('mode', mode)
      params.set('stat', stat)
      params.set('upgrade', String(upgrade))
      params.set('usable_by', 'any')
      params.set('limit', '20')
      params.set('include_loadout', 'true')
      params.set('prefer_ranged', preferRanged ? '1' : '0')
      const data = await api.items(params)
      setBySlot(data.by_slot || {})
      const eq: Record<string, string> = {}
      if (data.suggested_loadout) {
        for (const [slot, row] of Object.entries(data.suggested_loadout)) {
          if (row?.name) eq[slot] = row.name
        }
      }
      setEquipped(eq)
      if (data.by_slot && !data.by_slot[viewSlot]) {
        const first = Object.keys(data.by_slot)[0]
        if (first) setViewSlot(first)
      }
    } catch (e) {
      setErr(String(e))
    } finally {
      setLoading(false)
    }
  }, [selected, mode, stat, upgrade, viewSlot, preferRanged])

  useEffect(() => {
    loadItems()
  }, [loadItems])

  const runSim = useCallback(async (eqMap: Record<string, string>) => {
    try {
      const body = {
        classes: selected,
        race,
        upgrade,
        character_level: charLevel,
        equipped: Object.fromEntries(
          Object.entries(eqMap)
            .filter(([, name]) => !!name)
            .map(([slot, name]) => [slot, { name }]),
        ),
      }
      const result = await api.simulate(body)
      setSim(result)
    } catch (e) {
      setErr(String(e))
    }
  }, [selected, race, upgrade, charLevel])

  useEffect(() => {
    if (Object.keys(equipped).length) runSim(equipped)
  }, [equipped, runSim])

  const toggleClass = (cls: string) => {
    setSelected((prev) => {
      if (prev.includes(cls)) {
        return prev.filter((c) => c !== cls)
      }
      if (prev.length >= 3) return prev
      return [...prev, cls]
    })
  }

  const slots = meta?.slots || []
  const raceNote = races?.note || ''
  const ranked = bySlot[viewSlot] || []

  const totalsOrder = useMemo(
    () => ['HP', 'MANA', 'END', 'AC', 'STR', 'STA', 'AGI', 'DEX', 'WIS', 'INT', 'CHA', 'SVM', 'SVF', 'SVC', 'SVP', 'SVD', 'Haste'],
    [],
  )

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>EQ Legends BiS + Build Sim</h1>
          <p>Local planner · decoded JSON stats only · single worn haste</p>
        </div>
        <div className="row">
          <button className="primary" disabled={loading} onClick={() => loadItems()}>
            {loading ? 'Loading…' : 'Refresh BiS'}
          </button>
          <button
            onClick={async () => {
              setExportMsg('Exporting…')
              try {
                const r = await api.exportXlsx(selected)
                setExportMsg(
                  r.ok
                    ? `XLSX refreshed: ${r.path}`
                    : `Export finished with code ${r.returncode}. See ${r.path || 'logs'}`,
                )
              } catch (e) {
                setExportMsg(String(e))
              }
            }}
          >
            Export XLSX
          </button>
        </div>
      </header>

      {err && <div className="warn">{err}</div>}
      {exportMsg && <div className="note">{exportMsg}</div>}

      <div className="panel">
        <h2>Classes (pick 1–3)</h2>
        <div className="class-chips">
          {(meta?.classes || DEFAULT).map((cls) => {
            const on = selected.includes(cls)
            const disabled = !on && selected.length >= 3
            return (
              <button
                key={cls}
                type="button"
                className={`chip ${on ? 'on' : ''} ${disabled ? 'disabled' : ''}`}
                onClick={() => toggleClass(cls)}
              >
                {cls}
              </button>
            )
          })}
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <div>
            <label>Mode</label>
            <select value={mode} onChange={(e) => setMode(e.target.value as 'priority' | 'max')}>
              <option value="priority">Priority Stat</option>
              <option value="max">Max All</option>
            </select>
          </div>
          <div>
            <label>Priority Stat</label>
            <select
              value={stat}
              disabled={mode !== 'priority'}
              onChange={(e) => setStat(e.target.value)}
            >
              {(meta?.priority_stats || [{ key: 'INT', label: 'INT' }]).map((s) => (
                <option key={s.key} value={s.key}>{s.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label>Upgrade display</label>
            <select value={upgrade} onChange={(e) => setUpgrade(Number(e.target.value))}>
              {Array.from({ length: 11 }, (_, i) => (
                <option key={i} value={i}>{`+${i}`}</option>
              ))}
            </select>
          </div>
          <div>
            <label>Race</label>
            <select value={race} onChange={(e) => setRace(e.target.value)}>
              {(races?.races || []).map((r) => (
                <option key={r.id} value={r.name}>{r.name}</option>
              ))}
              {!races?.races?.length && <option value="">(none)</option>}
            </select>
          </div>
        </div>
        <div className="note">
          {meta?.notes?.weapons} {meta?.notes?.haste}
          {raceNote ? ` · Race: ${raceNote}` : ''}
          {!races?.bases_available ? ' · Race bases unavailable — using zeros.' : ''}
        </div>
      </div>

      <div className="grid grid-2">
        <div className="panel">
          <h2>Build simulator</h2>
          {sim?.warnings?.map((w: string, i: number) => (
            <div className="warn" key={i}>{w}</div>
          ))}
          <div className="row" style={{ marginBottom: 8, gap: 8 }}>
            <button type="button" onClick={() => { setEquipped({}); setSim(null) }}>Clear equipment</button>
            <button
              type="button"
              onClick={() => {
                const eq: Record<string, string> = {}
                for (const [slot, rows] of Object.entries(bySlot)) {
                  if (rows?.[0]?.name) eq[slot] = rows[0].name
                }
                setEquipped(eq)
              }}
            >
              Load from BiS
            </button>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <input type="checkbox" checked={preferRanged} onChange={(e) => setPreferRanged(e.target.checked)} />
              Prefer ranged damage
            </label>
            <label>
              Level{' '}
              <select value={charLevel} onChange={(e) => setCharLevel(Number(e.target.value))}>
                {Array.from({ length: 60 }, (_, i) => i + 1).map((lv) => (
                  <option key={lv} value={lv}>{lv}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="slots">
            {slots.map((slot) => {
              const opts = bySlot[slot] || []
              const name = equipped[slot] || ''
              const chosen = opts.find((o) => o.name === name)
              const stats = upgrade >= 10 ? chosen?.stats_plus10 : chosen?.stats_plus0
              return (
                <div className="slot-card" key={slot}>
                  <div className="slot-name">{slot}</div>
                  <select
                    value={name}
                    onChange={(e) => setEquipped((prev) => ({ ...prev, [slot]: e.target.value }))}
                  >
                    <option value="">— empty —</option>
                    {opts.map((o) => (
                      <option key={o.name} value={o.name}>
                        {o.name}{o.is_weapon && o.ratio10 != null ? ` (r${Number(o.ratio10).toFixed(2)})` : ''}
                        {o.haste ? ` +${o.haste}%h` : ''}
                      </option>
                    ))}
                    {name && !opts.some((o) => o.name === name) && (
                      <option value={name}>{name}</option>
                    )}
                  </select>
                  <div className="item-name">{name || <span className="muted">empty</span>}</div>
                  <div className="stats-mini">{fmtStats(stats)}{chosen?.haste ? ` Haste:+${chosen.haste}%` : ''}</div>
                </div>
              )
            })}
          </div>
        </div>

        <div>
          <div className="panel">
            <h2>Totals ({`+${upgrade}`} gear-only HP · race attrs)</h2>
            <div className="totals">
              {totalsOrder.map((k) => (
                <div className={`tot ${k === 'Haste' ? 'haste' : ''}`} key={k}>
                  <div className="k">{k}</div>
                  <div className="v">{sim?.totals?.[k] ?? 0}</div>
                </div>
              ))}
            </div>
            <div className="note" style={{ marginTop: 10 }}>
              Applied worn haste: <strong>{sim?.haste?.applied ?? 0}%</strong>
              {sim?.haste?.items?.length > 1 ? ' (multiple equipped — only highest counts)' : ''}
            </div>
          </div>

          <div className="panel">
            <h2>BiS by slot</h2>
            <div className="row" style={{ marginBottom: 8 }}>
              <select value={viewSlot} onChange={(e) => setViewSlot(e.target.value)}>
                {slots.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <span className="muted">Usable by any selected · weapons ratio-only</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Why</th>
                    <th>+0 / +10</th>
                    <th>Zone</th>
                  </tr>
                </thead>
                <tbody>
                  {ranked.map((row) => (
                    <tr key={row.name}>
                      <td>
                        {row.url ? <a href={row.url} target="_blank" rel="noreferrer">{row.name}</a> : row.name}
                        <div>
                          {row.is_weapon && <span className="badge ratio">ratio {row.ratio10 != null ? Number(row.ratio10).toFixed(3) : '—'}</span>}
                          {!!row.haste && <span className="badge haste">+{row.haste}% haste</span>}
                        </div>
                      </td>
                      <td>{row.why}</td>
                      <td className="mono">
                        <div>{fmtStats(row.stats_plus0)}</div>
                        <div className="muted">{fmtStats(row.stats_plus10)}</div>
                      </td>
                      <td>{row.zone}</td>
                    </tr>
                  ))}
                  {!ranked.length && (
                    <tr><td colSpan={4} className="muted">No items for this slot / trio.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
