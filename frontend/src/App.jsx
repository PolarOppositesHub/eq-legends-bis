import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getItems,
  getMeta,
  postBis,
  postSimulate,
  exportXlsx,
  getZoneDetail,
  importInventory,
  upgradeSuggestions,
  getInventoryHelp,
} from './api.js'

const EMPTY_EQ = {}
const BUILDS_KEY = 'eq-legends-bis-saved-builds-v1'
const MAX_LEVEL = 50

function fmtStats(stats, keys) {
  if (!stats) return ''
  const parts = []
  for (const k of keys) {
    const v = stats[k]
    if (v === undefined || v === null || v === 0 || v === '') continue
    parts.push(`${k}:${Number.isInteger(v) ? v : Number(v)}`)
  }
  return parts.join(' · ')
}

const SHOW0 = ['AC','HP','MANA','END','STR','STA','AGI','DEX','WIS','INT','CHA','Haste','DMG','DLY']
const SHOW10 = SHOW0
const SHOW_UP = SHOW0

function loadBuilds() {
  try {
    const raw = localStorage.getItem(BUILDS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch (_) {
    return []
  }
}

function persistBuilds(builds) {
  localStorage.setItem(BUILDS_KEY, JSON.stringify(builds))
}

function AltRow({ a, upgrade }) {
  const tip = [
    a.haste ? `Haste +${a.haste}% (not stacked)` : null,
    (a.ratio_at_upgrade != null || a.ratio_plus10 != null)
      ? `Ratio@+${upgrade} ${Number(a.ratio_at_upgrade ?? a.ratio_plus10).toFixed(4)}`
      : null,
    fmtStats(a.stats_at_upgrade || a.stats_plus10 || a.stats_plus0, SHOW_UP) || null,
    a.zone ? `Zone: ${a.zone}` : null,
    a.why || null,
  ].filter(Boolean).join('\n')

  return (
    <li className="alt-row">
      <span className="alt-name" tabIndex={0} title="Hover for stats">
        {a.url ? (
          <a href={a.url} target="_blank" rel="noreferrer">{a.name}</a>
        ) : (
          a.name
        )}
      </span>
      {a.haste ? <span className="muted"> (haste +{a.haste}%)</span> : null}
      {(a.ratio_at_upgrade != null || a.ratio_plus10 != null) ? (
        <span className="muted"> · r@+{upgrade} {Number(a.ratio_at_upgrade ?? a.ratio_plus10).toFixed(3)}</span>
      ) : null}
      {tip ? <div className="alt-tip">{tip}</div> : null}
    </li>
  )
}

function ZoneModal({ detail, onClose }) {
  if (!detail) return null
  const ov = detail.overview || {}
  const drops = detail.drop_mobs || []
  const keys = detail.access_keys || ov.access_keys || []
  const walks = detail.walkthrough_urls || ov.walkthrough_urls || []
  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <h2>{detail.zone || 'Zone'} {detail.found === false ? '(not in research)' : ''}</h2>
        {detail.message ? <p className="warn-box">{detail.message}</p> : null}
        {ov.brief ? <p>{ov.brief}</p> : null}
        <p className="muted">
          Level requirement: {ov.level_requirement || '—'}
        </p>
        {keys.length > 0 && (
          <div style={{ marginBottom: '0.75rem' }}>
            <strong>Access keys</strong>
            <ul className="mob-list">
              {keys.map((k, i) => {
                if (typeof k === 'string') return <li key={i}>{k}</li>
                return (
                  <li key={i}>
                    {k.name || k.key || JSON.stringify(k)}
                    {k.required ? ' (required)' : ''}
                    {k.walkthrough_url ? (
                      <> — <a href={k.walkthrough_url} target="_blank" rel="noreferrer">walkthrough</a></>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          </div>
        )}
        {walks.length > 0 && (
          <div style={{ marginBottom: '0.75rem' }}>
            <strong>Walkthroughs</strong>
            <ul className="mob-list">
              {walks.map((u, i) => {
                const url = typeof u === 'string' ? u : (u.url || '')
                const label = typeof u === 'string' ? u : (u.label || u.title || url)
                return (
                  <li key={i}>
                    {url ? <a href={url} target="_blank" rel="noreferrer">{label}</a> : label}
                  </li>
                )
              })}
            </ul>
          </div>
        )}
        {detail.map_url ? (
          <p>
            <a href={detail.map_url} target="_blank" rel="noreferrer">Zone map</a>
            <span className="muted"> (spawn markers only when research has coords)</span>
          </p>
        ) : (
          <p className="muted">No map URL in zone-research.</p>
        )}
        <h3 style={{ fontSize: '0.95rem', color: 'var(--accent)' }}>Drop mobs</h3>
        {drops.length === 0 ? (
          <p className="muted">No drop mobs listed on this item.</p>
        ) : (
          <ul className="mob-list">
            {drops.map((m) => (
              <li key={m.name}>
                <strong>{m.name}</strong>
                {m.level != null && m.level !== '' ? ` · L${m.level}` : ' · level unknown'}
                {' · '}
                {m.spawn_known ? (m.spawn_notes || 'spawn known') : (
                  <span className="spawn-unknown">{m.spawn_notes || 'mob location unknown'}</span>
                )}
              </li>
            ))}
          </ul>
        )}
        <div className="modal-actions">
          <button type="button" className="primary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}

function HelpModal({ markdown, onClose }) {
  if (markdown == null) return null
  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <h2>Inventory import help</h2>
        <div className="help-md">{markdown || '(no help text found)'}</div>
        <div className="modal-actions">
          <button type="button" className="primary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [meta, setMeta] = useState(null)
  const [tab, setTab] = useState('bis')
  const [classes, setClasses] = useState([])
  const [mode, setMode] = useState('priority')
  const [priorityStat, setPriorityStat] = useState('INT')
  const [upgrade, setUpgrade] = useState(10)
  const [preferRanged, setPreferRanged] = useState(true)
  const [bis, setBis] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [race, setRace] = useState('Human')
  const [characterLevel, setCharacterLevel] = useState(MAX_LEVEL)
  const [equipment, setEquipment] = useState(EMPTY_EQ)
  const [slotItems, setSlotItems] = useState({})
  const [sim, setSim] = useState(null)
  const [exportMsg, setExportMsg] = useState('')

  const [zoneDetail, setZoneDetail] = useState(null)
  const [helpMd, setHelpMd] = useState(null)
  const [suggestions, setSuggestions] = useState(null)
  const [importMsg, setImportMsg] = useState('')

  const [builds, setBuilds] = useState(() => loadBuilds())
  const [buildName, setBuildName] = useState('')
  const [selectedBuildId, setSelectedBuildId] = useState('')

  useEffect(() => {
    getMeta()
      .then((m) => {
        setMeta(m)
        if (typeof m.prefer_ranged_damage_default === 'boolean') {
          setPreferRanged(m.prefer_ranged_damage_default)
        }
        const levels = m.character_levels || []
        if (levels.length) {
          const maxLv = Math.min(MAX_LEVEL, Math.max(...levels))
          setCharacterLevel(maxLv)
        }
      })
      .catch((e) => setError(String(e.message || e)))
  }, [])

  const toggleClass = (c) => {
    setClasses((prev) => {
      if (prev.includes(c)) return prev.filter((x) => x !== c)
      if (prev.length >= 3) return prev
      return [...prev, c]
    })
  }

  const runBis = useCallback(async () => {
    if (classes.length < 1) {
      setError('Pick at least one class (up to 3).')
      setBis(null)
      return
    }
    setLoading(true)
    setError('')
    try {
      const data = await postBis({
        classes,
        mode,
        priority_stat: priorityStat,
        alts: 5,
        upgrade,
        prefer_ranged_damage: preferRanged,
        character_level: characterLevel,
      })
      setBis(data)
      const eq = {}
      for (const s of data.slots || []) {
        if (s.name) eq[s.slot] = s.name
      }
      setEquipment(eq)
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setLoading(false)
    }
  }, [classes, mode, priorityStat, upgrade, preferRanged, characterLevel])

  useEffect(() => {
    if (meta && classes.length >= 1) runBis()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta, upgrade, preferRanged, characterLevel])

  const loadSlotOptions = useCallback(async () => {
    if (!meta || classes.length < 1) return
    const [c1, c2, c3] = [classes[0] || '', classes[1] || '', classes[2] || '']
    const map = {}
    await Promise.all(
      (meta.slots || []).map(async (slot) => {
        try {
          const res = await getItems({
            c1, c2, c3, slot, limit: 400, upgrade, prefer_ranged_damage: preferRanged,
          })
          map[slot] = res.items || []
        } catch (_) {
          map[slot] = []
        }
      })
    )
    setSlotItems(map)
  }, [meta, classes, upgrade, preferRanged])

  useEffect(() => {
    if (tab === 'sim') loadSlotOptions()
  }, [tab, loadSlotOptions])

  const runSim = useCallback(async () => {
    if (classes.length < 1) {
      setError('Pick at least one class (up to 3).')
      return
    }
    setLoading(true)
    setError('')
    try {
      const data = await postSimulate({
        classes,
        race,
        upgrade,
        character_level: characterLevel,
        equipment,
      })
      setSim(data)
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setLoading(false)
    }
  }, [classes, race, upgrade, characterLevel, equipment])

  useEffect(() => {
    if (tab === 'sim' && Object.keys(equipment).length) runSim()
  }, [tab, upgrade, race, characterLevel]) // eslint-disable-line react-hooks/exhaustive-deps

  const clearEquipment = () => {
    setEquipment({})
    setSim(null)
    setSuggestions(null)
  }

  const loadFromBis = () => {
    if (!bis?.slots?.length) {
      setError('Run BiS first, then Load from BiS.')
      return
    }
    const eq = {}
    for (const s of bis.slots) {
      if (s.name) eq[s.slot] = s.name
    }
    setEquipment(eq)
    setTab('sim')
  }

  const openZone = async (zone, dropsMobs = '') => {
    if (!zone) return
    try {
      const d = await getZoneDetail(zone, dropsMobs || '')
      setZoneDetail(d)
    } catch (e) {
      setZoneDetail({
        found: false,
        zone,
        message: String(e.message || e),
        drop_mobs: [],
        overview: {},
      })
    }
  }

  const onImportFile = async (file) => {
    if (!file) return
    setImportMsg('Reading…')
    try {
      const text = await file.text()
      const parsed = await importInventory(text)
      const eq = parsed.equipment || {}
      setEquipment(eq)
      setImportMsg(
        `Imported ${Object.keys(eq).length} worn slots` +
        (parsed.skipped_count ? ` · skipped ${parsed.skipped_count}` : '') +
        ` from ${file.name}`
      )
      setTab('sim')
      if (classes.length >= 1) {
        const sug = await upgradeSuggestions({
          classes,
          equipment: eq,
          upgrade,
          character_level: characterLevel,
          prefer_ranged_damage: preferRanged,
        })
        setSuggestions(sug)
      }
    } catch (e) {
      setImportMsg('')
      setError(String(e.message || e))
    }
  }

  const runUpgradeSuggestions = async () => {
    if (classes.length < 1) {
      setError('Pick at least one class for upgrade suggestions.')
      return
    }
    setLoading(true)
    try {
      const sug = await upgradeSuggestions({
        classes,
        equipment,
        upgrade,
        character_level: characterLevel,
        prefer_ranged_damage: preferRanged,
      })
      setSuggestions(sug)
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setLoading(false)
    }
  }

  const openHelp = async () => {
    try {
      const h = await getInventoryHelp()
      setHelpMd(h.markdown || '')
    } catch (e) {
      setHelpMd(`Help unavailable: ${e.message || e}`)
    }
  }

  const saveBuild = () => {
    const name = (buildName || '').trim()
    if (!name) {
      setError('Enter a name for the saved build.')
      return
    }
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const entry = {
      id,
      name,
      savedAt: new Date().toISOString(),
      classes,
      race,
      characterLevel,
      upgrade,
      preferRanged,
      equipment: { ...equipment },
      mode,
      priorityStat,
    }
    const next = [...builds.filter((b) => b.name !== name), entry]
    setBuilds(next)
    persistBuilds(next)
    setSelectedBuildId(id)
    setBuildName('')
    setImportMsg(`Saved build “${name}”`)
  }

  const loadBuild = (id) => {
    const b = builds.find((x) => x.id === id)
    if (!b) return
    setSelectedBuildId(id)
    setClasses(b.classes || [])
    setRace(b.race || 'Human')
    setCharacterLevel(Math.min(MAX_LEVEL, Math.max(1, b.characterLevel || MAX_LEVEL)))
    setUpgrade(b.upgrade ?? 10)
    setPreferRanged(!!b.preferRanged)
    setEquipment(b.equipment || {})
    if (b.mode) setMode(b.mode)
    if (b.priorityStat) setPriorityStat(b.priorityStat)
    setTab('sim')
    setImportMsg(`Loaded build “${b.name}”`)
  }

  const renameBuild = () => {
    const b = builds.find((x) => x.id === selectedBuildId)
    if (!b) return
    const name = (buildName || '').trim()
    if (!name) {
      setError('Enter a new name, then Rename.')
      return
    }
    const next = builds.map((x) => (x.id === b.id ? { ...x, name } : x))
    setBuilds(next)
    persistBuilds(next)
    setBuildName('')
    setImportMsg(`Renamed to “${name}”`)
  }

  const deleteBuild = () => {
    if (!selectedBuildId) return
    const next = builds.filter((x) => x.id !== selectedBuildId)
    setBuilds(next)
    persistBuilds(next)
    setSelectedBuildId('')
    setImportMsg('Deleted saved build')
  }

  const races = meta?.races?.races || []
  const priorityOptions = meta?.priority_stats || []
  const classButtons = useMemo(() => meta?.classes || [], [meta])
  const levelOptions = useMemo(() => {
    const fromMeta = (meta?.character_levels || []).filter((lv) => lv >= 1 && lv <= MAX_LEVEL)
    if (fromMeta.length) return fromMeta
    return Array.from({ length: MAX_LEVEL }, (_, i) => i + 1)
  }, [meta])

  const trioLabel = classes.length ? classes.join(' · ') : '(none selected)'

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>EQ Legends — BiS + Build Simulator</h1>
          <p>
            Local tool for Josh Monroe · data from <code>/workspace/eq-legends/decoded</code>
            {meta ? ` · ${meta.catalog_weapons} catalog weapons` : ''}
            {meta?.version ? ` · v${meta.version}` : ' · v1.0.3'}
          </p>
        </div>
        <div className="tabs">
          <button className={tab === 'bis' ? 'active' : ''} onClick={() => setTab('bis')}>BiS</button>
          <button className={tab === 'sim' ? 'active' : ''} onClick={() => setTab('sim')}>Simulator</button>
        </div>
      </header>

      <div className="trio-banner" aria-live="polite">
        <span className="label">Selected trio</span>
        <span className="trio-value">{trioLabel}</span>
      </div>

      <div className="panel">
        <div className="row">
          <div className="field" style={{ minWidth: '100%' }}>
            <label>Classes (pick up to 3)</label>
            <div className="class-picks">
              {classButtons.map((c) => {
                const on = classes.includes(c)
                const disabled = !on && classes.length >= 3
                return (
                  <button key={c} className={on ? 'on' : ''} disabled={disabled} onClick={() => toggleClass(c)}>
                    {c}
                  </button>
                )
              })}
            </div>
          </div>
          {tab === 'bis' && (
            <>
              <div className="field">
                <label>Mode</label>
                <select value={mode} onChange={(e) => setMode(e.target.value)}>
                  <option value="priority">Priority Stat</option>
                  <option value="max">Max All Stats</option>
                </select>
              </div>
              {mode === 'priority' && (
                <div className="field">
                  <label>Priority Stat</label>
                  <select value={priorityStat} onChange={(e) => setPriorityStat(e.target.value)}>
                    {priorityOptions.map((p) => (
                      <option key={p.key} value={p.key}>{p.label}</option>
                    ))}
                  </select>
                </div>
              )}
              <div className="field">
                <label>Upgrade +0…+10</label>
                <input
                  type="range"
                  min={0}
                  max={10}
                  value={upgrade}
                  onChange={(e) => setUpgrade(Number(e.target.value))}
                />
                <span className="muted">+{upgrade}</span>
              </div>
              <div className="field">
                <label>Character Level (max {MAX_LEVEL})</label>
                <select
                  value={characterLevel}
                  onChange={(e) => setCharacterLevel(Math.min(MAX_LEVEL, Number(e.target.value)))}
                >
                  {levelOptions.map((lv) => (
                    <option key={lv} value={lv}>{lv}</option>
                  ))}
                </select>
                <span className="muted" style={{ fontSize: '0.75rem' }}>DW vs 2H model</span>
              </div>
              <div className="field">
                <label>Prefer ranged damage</label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginTop: '0.35rem' }}>
                  <input
                    type="checkbox"
                    checked={preferRanged}
                    onChange={(e) => setPreferRanged(e.target.checked)}
                  />
                  <span className="muted">RANGE BiS by DMG/DLY ratio</span>
                </label>
              </div>
              <div className="field">
                <label>&nbsp;</label>
                <button className="primary" disabled={loading} onClick={runBis}>
                  {loading ? 'Calculating…' : 'Update BiS'}
                </button>
              </div>
              <div className="field">
                <label>&nbsp;</label>
                <button
                  disabled={loading || classes.length < 1}
                  onClick={async () => {
                    setExportMsg('Exporting XLSX…')
                    try {
                      const r = await exportXlsx(classes)
                      setExportMsg(r.ok ? `XLSX refreshed: ${r.path}` : `Export rc=${r.returncode} ${r.path || ''}`)
                    } catch (e) {
                      setExportMsg(String(e.message || e))
                    }
                  }}
                >
                  Export XLSX
                </button>
              </div>
            </>
          )}
          {tab === 'sim' && (
            <>
              <div className="field">
                <label>Race</label>
                <select value={race} onChange={(e) => setRace(e.target.value)}>
                  {races.map((r) => (
                    <option key={r.id} value={r.name}>{r.name}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Character Level (max {MAX_LEVEL})</label>
                <select
                  value={characterLevel}
                  onChange={(e) => setCharacterLevel(Math.min(MAX_LEVEL, Number(e.target.value)))}
                >
                  {levelOptions.map((lv) => (
                    <option key={lv} value={lv}>{lv}</option>
                  ))}
                </select>
                <span className="muted" style={{ fontSize: '0.75rem' }}>HP = gear only</span>
              </div>
              <div className="field">
                <label>Upgrade +0…+10</label>
                <input
                  type="range"
                  min={0}
                  max={10}
                  value={upgrade}
                  onChange={(e) => setUpgrade(Number(e.target.value))}
                />
                <span className="muted">+{upgrade}</span>
              </div>
              <div className="field">
                <label>&nbsp;</label>
                <button className="primary" disabled={loading} onClick={runSim}>
                  {loading ? 'Updating…' : 'Recalculate'}
                </button>
              </div>
            </>
          )}
        </div>
        <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span className="badge">Upgrade +{upgrade}</span>
          <span className="badge warn">Haste: only highest % counts</span>
          {preferRanged && <span className="badge">Prefer ranged damage</span>}
          {bis?.dual_wield_enabled && (
            <span className="badge">
              DW vs 2H @L{bis.character_level ?? characterLevel}
              {bis?.dual_wield_eval?.mode ? ` · ${bis.dual_wield_eval.mode}` : ''}
            </span>
          )}
          {bis?.haste_in_loadout?.[0] && (
            <span className="badge">
              BiS haste: {bis.haste_in_loadout[0].name} +{bis.haste_in_loadout[0].haste}%
            </span>
          )}
        </div>
      </div>

      {error && <div className="error" style={{ marginBottom: '1rem' }}>{error}</div>}
      {exportMsg && <div className="note" style={{ marginBottom: '1rem' }}>{exportMsg}</div>}
      {importMsg && <div className="note" style={{ marginBottom: '1rem' }}>{importMsg}</div>}

      {tab === 'bis' && !classes.length && (
        <div className="panel">
          <p className="muted" style={{ margin: 0 }}>Select 1–3 classes, then Update BiS.</p>
        </div>
      )}

      {tab === 'bis' && bis && (
        <>
          <div className="panel">
            <p className="muted" style={{ marginTop: 0 }}>
              Mode: <strong>{bis.mode}</strong>
              {bis.priority_stat ? <> · Priority: <strong>{bis.priority_stat}</strong></> : null}
              <> · Pool: {bis.pool_size} shared gear</>
              {bis.weapon_pool_size != null ? <> · Weapons pool: {bis.weapon_pool_size}</> : null}
              <> · Stats / ratios at <strong>+{bis.upgrade ?? upgrade}</strong></>
              <> · Level <strong>{bis.character_level ?? characterLevel}</strong></>
              <> · Weapons: any selected class · Armor: all selected classes</>
            </p>
            {bis.dual_wield_enabled && (
              <p className="note" style={{ marginTop: '0.5rem' }}>
                <strong>DW vs 2H working model</strong> (not exact): {bis.weapon_rule}
                {bis.dual_wield_eval?.model_note ? (
                  <> · {bis.dual_wield_eval.model_note}</>
                ) : null}
                {bis.dual_wield_eval?.dw_chance != null ? (
                  <> · DWChance={Number(bis.dual_wield_eval.dw_chance).toFixed(4)}
                    {' '}(skill≈{bis.dual_wield_eval.dw_skill})</>
                ) : null}
              </p>
            )}
            <div className="grid-slots">
              {bis.slots.map((s) => (
                <div className="slot-card" key={s.slot}>
                  <h3>{s.slot}{s.haste ? ` · Haste +${s.haste}%` : ''}</h3>
                  <div className="item-name">
                    {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.name || '—'}</a> : (s.name || '—')}
                  </div>
                  <div className="meta">
                    {s.zone ? (
                      <button
                        type="button"
                        className="zone-link"
                        onClick={() => openZone(s.zone, s.drops_mobs || '')}
                      >
                        {s.zone}
                      </button>
                    ) : (
                      'Unknown zone'
                    )}
                    {s.classes_str ? ` · ${s.classes_str}` : ''}
                    {s.is_weapon && (s.ratio_at_upgrade != null || s.ratio_plus10 != null)
                      ? ` · Ratio@+${upgrade} ${Number(s.ratio_at_upgrade ?? s.ratio_plus10).toFixed(4)}`
                      : ''}
                  </div>
                  <div className="why">{s.why}</div>
                  <div className="stats-line">+0 {fmtStats(s.stats_plus0, SHOW0) || '—'}</div>
                  <div className="stats-line">
                    +{upgrade} {fmtStats(s.stats_at_upgrade || (upgrade === 10 ? s.stats_plus10 : null), SHOW_UP) || fmtStats(s.stats_plus10, SHOW10) || '—'}
                  </div>
                  {s.alts?.length > 0 && (
                    <details className="alts" open>
                      <summary>Alternates ({s.alts.length})</summary>
                      <ul>
                        {s.alts.map((a) => (
                          <AltRow key={a.name} a={a} upgrade={upgrade} />
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {tab === 'sim' && (
        <div className="sim-grid">
          <div className="panel">
            <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Equipment</h2>
            <div className="builds-bar">
              <input
                type="text"
                placeholder="Build name"
                value={buildName}
                onChange={(e) => setBuildName(e.target.value)}
                style={{ minWidth: 140 }}
              />
              <button type="button" className="gold" onClick={saveBuild}>Save build</button>
              <select
                value={selectedBuildId}
                onChange={(e) => {
                  const id = e.target.value
                  setSelectedBuildId(id)
                  if (id) loadBuild(id)
                }}
              >
                <option value="">— saved builds —</option>
                {builds.map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </select>
              <button type="button" onClick={renameBuild} disabled={!selectedBuildId}>Rename</button>
              <button type="button" onClick={deleteBuild} disabled={!selectedBuildId}>Delete</button>
            </div>
            <p className="muted">
              Import <code>Inventory.txt</code> from in-game <code>/outputfile inventory</code>.
              Character level {characterLevel} is recorded only — HP/Mana/END are <strong>gear-only</strong>.
            </p>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem', alignItems: 'center' }}>
              <button type="button" onClick={clearEquipment}>Clear equipment</button>
              <button type="button" onClick={loadFromBis} disabled={!bis?.slots?.length}>
                Load from BiS
              </button>
              <label className="gold" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', padding: '0.45rem 0.85rem', borderRadius: 8, border: '1px solid #b8962e', background: 'var(--accent)', color: 'var(--accent-text)', fontWeight: 600, cursor: 'pointer' }}>
                Import Inventory.txt
                <input
                  type="file"
                  accept=".txt,text/plain"
                  style={{ display: 'none' }}
                  onChange={(e) => {
                    const f = e.target.files && e.target.files[0]
                    onImportFile(f)
                    e.target.value = ''
                  }}
                />
              </label>
              <button type="button" onClick={openHelp}>Help</button>
              <button type="button" className="primary" onClick={runUpgradeSuggestions} disabled={loading || classes.length < 1}>
                Suggest upgrades
              </button>
            </div>
            <div className="equip-list">
              {(meta?.slots || []).map((slot) => (
                <div className="equip-row" key={slot}>
                  <label>{slot}</label>
                  <select
                    className="slot-select"
                    value={equipment[slot] || ''}
                    onChange={(e) => {
                      const v = e.target.value
                      setEquipment((prev) => {
                        const next = { ...prev }
                        if (!v) delete next[slot]
                        else next[slot] = v
                        return next
                      })
                    }}
                    onBlur={runSim}
                  >
                    <option value="">— empty —</option>
                    {(slotItems[slot] || []).map((it) => (
                      <option key={it.name} value={it.name}>
                        {it.name}{it.haste ? ` (+${it.haste}% haste)` : ''}
                        {(it.ratio_at_upgrade != null || it.ratio_plus10 != null)
                          ? ` [r ${Number(it.ratio_at_upgrade ?? it.ratio_plus10).toFixed(2)}]`
                          : ''}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
            <div style={{ marginTop: '0.75rem' }}>
              <button className="primary" onClick={runSim} disabled={loading}>Apply / Recalculate</button>
            </div>
          </div>

          <div className="panel">
            <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Live Totals</h2>
            {sim ? (
              <>
                <div style={{ marginBottom: '0.75rem', display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                  <span className="badge">Haste applied: +{sim.haste?.applied_pct || 0}%</span>
                  {sim.haste?.applied_slot && (
                    <span className="badge">{sim.haste.applied_slot}: {sim.haste.candidates?.find(c => c.slot === sim.haste.applied_slot)?.name}</span>
                  )}
                  {(sim.haste?.candidates?.length || 0) > 1 && (
                    <span className="badge warn">Extra haste ignored</span>
                  )}
                  <span className="badge warn">HP/Mana/END/AC = gear-only (no racial/level pools)</span>
                  {sim.character_level != null && (
                    <span className="badge">Level {sim.character_level} (display only)</span>
                  )}
                </div>
                <div className="totals">
                  {['HP','MANA','END','AC','STR','STA','AGI','DEX','WIS','INT','CHA','SVF','SVC','SVM','SVP','SVD','SVV','ATK'].map((k) => (
                    <div className="tot" key={k}>
                      <div className="k">
                        {k === 'MANA' ? 'Mana' : k === 'END' ? 'Endurance' : k === 'HP' ? 'HP (gear)' : k}
                      </div>
                      <div className="v">{sim.totals?.[k] ?? 0}</div>
                    </div>
                  ))}
                  <div className="tot">
                    <div className="k">Haste</div>
                    <div className="v">{sim.haste?.applied_pct || 0}%</div>
                  </div>
                </div>
                {sim.weapons?.length > 0 && (
                  <div style={{ marginTop: '1rem' }}>
                    <h3 style={{ fontSize: '0.95rem' }}>Weapon ratios @ +{upgrade}</h3>
                    <ul className="muted">
                      {sim.weapons.map((w) => (
                        <li key={w.slot}>
                          <strong>{w.slot}</strong>: {w.name} — ratio {w.ratio != null ? Number(w.ratio).toFixed(4) : '—'}
                          {w.dmg ? ` (DMG ${w.dmg}` : ''}{w.dly ? ` / DLY ${w.dly})` : w.dmg ? ')' : ''}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {sim.warnings?.length > 0 && (
                  <div className="error" style={{ marginTop: '0.75rem' }}>
                    {sim.warnings.map((w, i) => <div key={i}>{w}</div>)}
                  </div>
                )}
                <p className="muted" style={{ marginTop: '0.75rem', fontSize: '0.82rem' }}>{sim.note}</p>
              </>
            ) : (
              <p className="muted">Load BiS, import Inventory.txt, or pick gear, then recalculate.</p>
            )}

            {suggestions?.suggestions?.length > 0 && (
              <div style={{ marginTop: '1.25rem' }}>
                <h3 style={{ fontSize: '0.95rem', color: 'var(--accent)' }}>Upgrade priorities</h3>
                <p className="muted" style={{ fontSize: '0.8rem' }}>{suggestions.note}</p>
                <ul className="upgrade-list">
                  {suggestions.suggestions.map((s) => (
                    <li key={`${s.slot}-${s.suggested}`}>
                      <div className="pri">P{s.priority} · {s.slot}</div>
                      <div>
                        {s.current ? <>Have <strong>{s.current}</strong> → </> : <>Empty → </>}
                        {s.suggested_url ? (
                          <a href={s.suggested_url} target="_blank" rel="noreferrer">{s.suggested}</a>
                        ) : (
                          <strong>{s.suggested}</strong>
                        )}
                      </div>
                      <div className="muted" style={{ fontSize: '0.78rem' }}>
                        {s.reason}
                        {s.suggested_zone ? (
                          <>
                            {' · '}
                            <button
                              type="button"
                              className="zone-link"
                              onClick={() => openZone(s.suggested_zone, '')}
                            >
                              {s.suggested_zone}
                            </button>
                          </>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      <footer className="muted" style={{ marginTop: '1.5rem', fontSize: '0.8rem' }}>
        Item stats from decoded JSON only. Zone details from zone-research (never invented).
        Race attrs/resists: eqlegendstools (verified; matches eqlwiki).
        HP/Mana/END/AC racial &amp; level pools = not applied (no verified formula).
        Excel export: <code>.venv/bin/python scripts/export_xlsx.py</code>
      </footer>

      <ZoneModal detail={zoneDetail} onClose={() => setZoneDetail(null)} />
      <HelpModal markdown={helpMd} onClose={() => setHelpMd(null)} />
    </div>
  )
}
