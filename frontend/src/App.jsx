import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  searchItems,
  getItemDetail,
  itemImageUrl,
  ensureItemImage,
  getPriorityDefaults,
} from './api.js'

const EMPTY_EQ = {}
const BUILDS_KEY = 'eq-legends-bis-saved-builds-v1'
const MAX_LEVEL = 50
const EMPTY_TIERS = ['', '', '']

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

const SHOW0 = ['AC','HP','MANA','END','STR','STA','AGI','DEX','WIS','INT','CHA','Haste','DMG','DLY','HP_REGEN','MANA_REGEN','END_REGEN']
const SHOW10 = SHOW0
const SHOW_UP = SHOW0

const DELTA_KEYS = [
  'AC', 'HP', 'MANA', 'END', 'STR', 'STA', 'AGI', 'DEX', 'WIS', 'INT', 'CHA',
  'Haste', 'DMG', 'DLY', 'HP_REGEN', 'MANA_REGEN', 'END_REGEN',
  'SVF', 'SVC', 'SVM', 'SVP', 'SVD',
]

function hideImg(e) {
  e.target.style.display = 'none'
}

function padTier(arr) {
  const next = Array.isArray(arr) ? [...arr] : []
  while (next.length < 3) next.push('')
  return next.slice(0, 3).map((v) => (v == null ? '' : String(v)))
}

function nonemptyStats(arr) {
  return padTier(arr).filter((s) => s && String(s).trim())
}

function computeStatDeltas(wornStats, bisStats) {
  const out = []
  for (const k of DELTA_KEYS) {
    const a = Number((wornStats && wornStats[k]) || 0)
    const b = Number((bisStats && bisStats[k]) || 0)
    const d = b - a
    if (Math.abs(d) < 1e-9) continue
    out.push({ stat: k, worn: a, bis: b, delta: d })
  }
  return out
}

function formatSignedDelta(d) {
  const n = d.delta
  const shown = Number.isInteger(n) ? n : Math.round(n * 10) / 10
  const sign = shown > 0 ? '+' : ''
  return `${d.stat} ${sign}${shown}`
}

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

function itemTipStatsText(item, upgrade) {
  if (!item) return ''
  const stats = item.stats_at_upgrade || item.stats_plus10 || item.stats_plus0
  const tipParts = [
    item.haste ? `Haste +${item.haste}% (not stacked)` : null,
    (item.ratio_at_upgrade != null || item.ratio_plus10 != null)
      ? `Ratio@+${upgrade} ${Number(item.ratio_at_upgrade ?? item.ratio_plus10).toFixed(4)}`
      : null,
    fmtStats(stats, SHOW_UP) || null,
    item.zone ? `Zone: ${item.zone}` : null,
    item.why || null,
  ].filter(Boolean)
  return tipParts.join('\n')
}

function AltRow({ a, upgrade, onShowTip, onHideTip }) {
  const statsText = itemTipStatsText(a, upgrade)
  const show = (e) => {
    const el = e.currentTarget
    const r = el.getBoundingClientRect()
    onShowTip({
      name: a.name,
      statsText,
      x: Math.min(r.left, window.innerWidth - 320),
      y: r.bottom + 6,
      image: itemImageUrl(a.name),
    })
  }
  return (
    <li className="alt-row">
      <span className="alt-name-wrap">
        <span
          className="alt-name"
          tabIndex={0}
          onMouseEnter={show}
          onFocus={show}
          onMouseLeave={onHideTip}
          onBlur={onHideTip}
        >
          {a.url ? (
            <a href={a.url} target="_blank" rel="noreferrer">{a.name}</a>
          ) : (
            a.name
          )}
        </span>
      </span>
      {a.haste ? <span className="muted"> (haste +{a.haste}%)</span> : null}
      {(a.ratio_at_upgrade != null || a.ratio_plus10 != null) ? (
        <span className="muted"> · r@+{upgrade} {Number(a.ratio_at_upgrade ?? a.ratio_plus10).toFixed(3)}</span>
      ) : null}
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

function TierSelects({ label, values, options, onChange }) {
  const vals = padTier(values)
  return (
    <div className="priority-tier">
      <div className="priority-tier-label">{label}</div>
      <div className="priority-tier-selects">
        {[0, 1, 2].map((i) => (
          <select
            key={i}
            value={vals[i] || ''}
            onChange={(e) => onChange(i, e.target.value)}
          >
            <option value="">—</option>
            {options.map((p) => (
              <option key={p.key} value={p.key}>{p.label}</option>
            ))}
          </select>
        ))}
      </div>
    </div>
  )
}

export default function App() {
  const [meta, setMeta] = useState(null)
  const [tab, setTab] = useState('bis')
  const [classes, setClasses] = useState([])
  const [mode, setMode] = useState('priority')
  const [primaryStats, setPrimaryStats] = useState(() => [...EMPTY_TIERS])
  const [secondaryStats, setSecondaryStats] = useState(() => [...EMPTY_TIERS])
  const [tertiaryStats, setTertiaryStats] = useState(() => [...EMPTY_TIERS])
  const [maximizeHpRegen, setMaximizeHpRegen] = useState(false)
  const [upgrade, setUpgrade] = useState(10)
  const [preferRanged, setPreferRanged] = useState(true)
  const [bis, setBis] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [race, setRace] = useState('Human')
  const [characterLevel, setCharacterLevel] = useState(MAX_LEVEL)
  const [equipment, setEquipment] = useState(EMPTY_EQ)
  const [slotItems, setSlotItems] = useState({})
  const [bisOverrides, setBisOverrides] = useState({})
  const [sim, setSim] = useState(null)
  const [exportMsg, setExportMsg] = useState('')

  const [zoneDetail, setZoneDetail] = useState(null)
  const [helpMd, setHelpMd] = useState(null)
  const [suggestions, setSuggestions] = useState(null)
  const [importMsg, setImportMsg] = useState('')
  const [importMeta, setImportMeta] = useState(null)

  const [builds, setBuilds] = useState(() => loadBuilds())
  const [buildName, setBuildName] = useState('')
  const [selectedBuildId, setSelectedBuildId] = useState('')

  const [searchQ, setSearchQ] = useState('')
  const [searchSlot, setSearchSlot] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [searchLoading, setSearchLoading] = useState(false)
  const [itemDetail, setItemDetail] = useState(null)
  const [hoverTip, setHoverTip] = useState(null)
  const hoverTipClearRef = useRef(null)
  const skipPriorityDefaultsRef = useRef(false)
  const ensuredImagesRef = useRef(new Set())

  const priorityStat = nonemptyStats(primaryStats)[0] || 'INT'

  const showHoverTip = useCallback((tip) => {
    if (hoverTipClearRef.current) {
      clearTimeout(hoverTipClearRef.current)
      hoverTipClearRef.current = null
    }
    setHoverTip(tip)
    if (tip?.name && !ensuredImagesRef.current.has(tip.name)) {
      ensuredImagesRef.current.add(tip.name)
      ensureItemImage(tip.name).catch(() => {})
    }
  }, [])

  const hideHoverTip = useCallback(() => {
    if (hoverTipClearRef.current) clearTimeout(hoverTipClearRef.current)
    hoverTipClearRef.current = setTimeout(() => setHoverTip(null), 80)
  }, [])

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

  useEffect(() => {
    if (skipPriorityDefaultsRef.current) {
      skipPriorityDefaultsRef.current = false
      return
    }
    if (!classes.length) {
      setPrimaryStats([...EMPTY_TIERS])
      setSecondaryStats([...EMPTY_TIERS])
      setTertiaryStats([...EMPTY_TIERS])
      return
    }
    let cancelled = false
    getPriorityDefaults(classes)
      .then((d) => {
        if (cancelled) return
        setPrimaryStats(padTier(d.primary_stats))
        setSecondaryStats(padTier(d.secondary_stats))
        setTertiaryStats(padTier(d.tertiary_stats))
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [classes])

  const toggleClass = (c) => {
    setClasses((prev) => {
      if (prev.includes(c)) return prev.filter((x) => x !== c)
      if (prev.length >= 3) return prev
      return [...prev, c]
    })
  }

  const setTierAt = (setter, index, value) => {
    setter((prev) => {
      const next = padTier(prev)
      next[index] = value
      return next
    })
  }

  const bisRequestBody = useCallback(() => ({
    classes,
    mode,
    priority_stat: priorityStat,
    primary_stats: nonemptyStats(primaryStats),
    secondary_stats: nonemptyStats(secondaryStats),
    tertiary_stats: nonemptyStats(tertiaryStats),
    maximize_hp_regen: maximizeHpRegen,
    alts: 5,
    upgrade,
    prefer_ranged_damage: preferRanged,
    character_level: characterLevel,
  }), [
    classes, mode, priorityStat, primaryStats, secondaryStats, tertiaryStats,
    maximizeHpRegen, upgrade, preferRanged, characterLevel,
  ])

  const runBis = useCallback(async () => {
    if (classes.length < 1) {
      setError('Pick at least one class (up to 3).')
      setBis(null)
      return
    }
    setLoading(true)
    setError('')
    try {
      const data = await postBis(bisRequestBody())
      setBis(data)
      setBisOverrides({})
      const eq = {}
      const names = []
      for (const s of data.slots || []) {
        if (s.name) {
          eq[s.slot] = s.name
          names.push(s.name)
        }
        for (const a of s.alts || []) {
          if (a?.name) names.push(a.name)
        }
      }
      setEquipment(eq)
      // Best-effort icon cache so list/hover images appear without waiting on hover
      for (const name of names) {
        if (!name || ensuredImagesRef.current.has(name)) continue
        ensuredImagesRef.current.add(name)
        ensureItemImage(name).catch(() => {})
      }
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setLoading(false)
    }
  }, [classes, bisRequestBody])

  useEffect(() => {
    if (meta && classes.length >= 1) runBis()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta, upgrade, preferRanged, characterLevel, mode, maximizeHpRegen])

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

  useEffect(() => {
    if (tab === 'upgrades' && classes.length >= 1 && !suggestions) {
      runUpgradeSuggestions()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, classes])

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
    setImportMeta(null)
    setBisOverrides({})
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
    setBisOverrides({})
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

  const suggestionBody = useCallback((eq) => ({
    classes,
    equipment: eq,
    upgrade,
    character_level: characterLevel,
    prefer_ranged_damage: preferRanged,
    mode,
    priority_stat: priorityStat,
    primary_stats: nonemptyStats(primaryStats),
    secondary_stats: nonemptyStats(secondaryStats),
    tertiary_stats: nonemptyStats(tertiaryStats),
    maximize_hp_regen: maximizeHpRegen,
    fetch_quest_guides: true,
  }), [
    classes, upgrade, characterLevel, preferRanged, mode, priorityStat,
    primaryStats, secondaryStats, tertiaryStats, maximizeHpRegen,
  ])

  const onImportFile = async (file) => {
    if (!file) return
    setImportMsg('Reading…')
    try {
      const text = await file.text()
      const parsed = await importInventory(text)
      const eq = parsed.equipment || {}
      setEquipment(eq)
      setImportMeta({
        unmatched_count: parsed.unmatched_count || 0,
        unmatched: parsed.unmatched || [],
        all_items: parsed.all_items || [],
      })
      setImportMsg(
        `Imported ${Object.keys(eq).length} worn slots` +
        (parsed.skipped_count ? ` · skipped ${parsed.skipped_count}` : '') +
        (parsed.unmatched_count ? ` · unmatched ${parsed.unmatched_count}` : '') +
        ` from ${file.name}`
      )
      setTab('upgrades')
      if (classes.length >= 1) {
        const sug = await upgradeSuggestions(suggestionBody(eq))
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
      const sug = await upgradeSuggestions(suggestionBody(equipment))
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
      primaryStats: padTier(primaryStats),
      secondaryStats: padTier(secondaryStats),
      tertiaryStats: padTier(tertiaryStats),
      maximizeHpRegen,
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
    skipPriorityDefaultsRef.current = true
    setSelectedBuildId(id)
    setClasses(b.classes || [])
    setRace(b.race || 'Human')
    setCharacterLevel(Math.min(MAX_LEVEL, Math.max(1, b.characterLevel || MAX_LEVEL)))
    setUpgrade(b.upgrade ?? 10)
    setPreferRanged(!!b.preferRanged)
    setEquipment(b.equipment || {})
    if (b.mode) setMode(b.mode)
    if (b.primaryStats) setPrimaryStats(padTier(b.primaryStats))
    else if (b.priorityStat) setPrimaryStats([b.priorityStat, '', ''])
    if (b.secondaryStats) setSecondaryStats(padTier(b.secondaryStats))
    if (b.tertiaryStats) setTertiaryStats(padTier(b.tertiaryStats))
    if (typeof b.maximizeHpRegen === 'boolean') setMaximizeHpRegen(b.maximizeHpRegen)
    setBisOverrides({})
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

  const runSearch = async () => {
    setSearchLoading(true)
    setError('')
    try {
      const params = { q: searchQ || '', limit: 80 }
      if (searchSlot) params.slot = searchSlot
      const res = await searchItems(params)
      setSearchResults(res)
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setSearchLoading(false)
    }
  }

  const openItemDetail = async (name) => {
    if (!name) return
    try {
      const d = await getItemDetail(name)
      setItemDetail(d)
    } catch (e) {
      setError(String(e.message || e))
    }
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

  const equipCompareRows = useMemo(() => {
    if (suggestions?.equipment_compare?.length) {
      return suggestions.equipment_compare
    }
    if (!bis?.slots?.length) return []
    return bis.slots.map((row) => {
      const slot = row.slot
      const bisName = (row.name || '').trim()
      const bis_options = []
      if (bisName) {
        bis_options.push({
          name: bisName,
          why: row.why,
          url: row.url || '',
          stats_at_upgrade: row.stats_at_upgrade || row.stats_plus10 || {},
        })
      }
      for (const a of row.alts || []) {
        if (a?.name) {
          bis_options.push({
            name: a.name,
            why: a.why,
            url: a.url || '',
            stats_at_upgrade: a.stats_at_upgrade || a.stats_plus10 || {},
          })
        }
      }
      const wornName = (equipment[slot] || '').trim()
      const pool = slotItems[slot] || []
      const wornItem = pool.find((it) => (it.name || '').toLowerCase() === wornName.toLowerCase())
      const wornStats = wornItem
        ? (wornItem.stats_at_upgrade || wornItem.stats_plus10 || {})
        : {}
      const bisStats = row.stats_at_upgrade || row.stats_plus10 || {}
      return {
        slot,
        worn: { name: wornName || null, stats: wornStats },
        bis_options,
        selected_bis: bisName || null,
        deltas: bisName ? computeStatDeltas(wornStats, bisStats) : [],
      }
    })
  }, [suggestions, bis, equipment, slotItems])

  const resolveCompareDeltas = (row) => {
    const slot = row.slot
    const selected = bisOverrides[slot] || row.selected_bis || ''
    const wornName = equipment[slot] || row.worn?.name || ''
    const wornStats = row.worn?.stats || {}
    const pool = slotItems[slot] || []
    let effectiveWorn = wornStats
    if (wornName && (!effectiveWorn || !Object.keys(effectiveWorn).length)) {
      const found = pool.find((it) => (it.name || '').toLowerCase() === String(wornName).toLowerCase())
      if (found) effectiveWorn = found.stats_at_upgrade || found.stats_plus10 || {}
    }
    if (!selected) return []
    if (selected === row.selected_bis && row.deltas?.length && !bisOverrides[slot]) {
      return row.deltas.filter((d) => Math.abs(d.delta) >= 1e-9)
    }
    const opt = (row.bis_options || []).find((o) => o.name === selected)
    let bisStats = opt?.stats_at_upgrade || opt?.stats_plus10 || null
    if (!bisStats && bis?.slots) {
      const slotRow = bis.slots.find((s) => s.slot === slot)
      if (slotRow && slotRow.name === selected) {
        bisStats = slotRow.stats_at_upgrade || slotRow.stats_plus10 || {}
      } else {
        const alt = (slotRow?.alts || []).find((a) => a.name === selected)
        bisStats = alt?.stats_at_upgrade || alt?.stats_plus10 || {}
      }
    }
    if (!bisStats && pool.length) {
      const found = pool.find((it) => it.name === selected)
      bisStats = found?.stats_at_upgrade || found?.stats_plus10 || {}
    }
    return computeStatDeltas(effectiveWorn, bisStats || {})
  }

  const navItems = [
    { id: 'bis', label: 'Best in Slot' },
    { id: 'sim', label: 'Simulator' },
    { id: 'upgrades', label: 'Upgrade Priority' },
    { id: 'search', label: 'Item Search' },
  ]

  const unmatchedNames = (importMeta?.unmatched || [])
    .map((u) => (typeof u === 'string' ? u : (u.name || u.base_name || '')))
    .filter(Boolean)
  const allItemNames = (importMeta?.all_items || [])
    .map((u) => (typeof u === 'string' ? u : (u.name || u.base_name || '')))
    .filter(Boolean)

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>EQ Legends — BiS + Build Simulator</h1>
          <p>
            Local tool for Josh Monroe · data from <code>/workspace/eq-legends/decoded</code>
            {meta ? ` · ${meta.catalog_weapons} catalog weapons` : ''}
            {meta?.version ? ` · v${meta.version}` : ' · v1.0.5'}
          </p>
        </div>
        <span className="ui-build-badge" title="Frontend UI build">UI 1.0.5</span>
      </header>

      <div className="app-shell">
        <nav className="side-nav" aria-label="Main">
          <div className="side-nav-heading">Menu</div>
          {navItems.map((n) => (
            <button
              key={n.id}
              type="button"
              className={tab === n.id ? 'active' : ''}
              onClick={() => setTab(n.id)}
            >
              {n.label}
            </button>
          ))}
        </nav>

        <div className="main-pane">
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
                      <option value="ai">AI Choice</option>
                    </select>
                    <span className="muted mode-hint">
                      Priority Stat · Max All Stats · AI Choice
                    </span>
                  </div>
                  {mode === 'priority' && (
                    <div className="field" style={{ minWidth: '100%' }}>
                      <label>Priority tiers (empty allowed)</label>
                      <div className="priority-tiers">
                        <TierSelects
                          label="Primary"
                          values={primaryStats}
                          options={priorityOptions}
                          onChange={(i, v) => setTierAt(setPrimaryStats, i, v)}
                        />
                        <TierSelects
                          label="Secondary"
                          values={secondaryStats}
                          options={priorityOptions}
                          onChange={(i, v) => setTierAt(setSecondaryStats, i, v)}
                        />
                        <TierSelects
                          label="Tertiary"
                          values={tertiaryStats}
                          options={priorityOptions}
                          onChange={(i, v) => setTierAt(setTertiaryStats, i, v)}
                        />
                      </div>
                      <p className="note priority-defaults-note">
                        Defaults from selected classes — change any dropdown
                      </p>
                    </div>
                  )}
                  <div className="field">
                    <label>HP regen</label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginTop: '0.35rem' }}>
                      <input
                        type="checkbox"
                        checked={maximizeHpRegen}
                        onChange={(e) => setMaximizeHpRegen(e.target.checked)}
                      />
                      <span className="muted">Maximize HP regen</span>
                    </label>
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
            {(tab === 'bis' || tab === 'sim') && (
              <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <span className="badge">Upgrade +{upgrade}</span>
                <span className="badge warn">Haste: only highest % counts</span>
                {preferRanged && <span className="badge">Prefer ranged damage</span>}
                {maximizeHpRegen && <span className="badge">Maximize HP regen</span>}
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
            )}
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
            <div className="panel">
              <p className="muted" style={{ marginTop: 0 }}>
                Mode: <strong>{bis.mode}</strong>
                {bis.priority_stat ? <> · Priority: <strong>{bis.priority_stat}</strong></> : null}
                {(bis.primary_stats || []).length ? (
                  <> · Primary: <strong>{(bis.primary_stats || []).join(', ')}</strong></>
                ) : null}
                {(bis.secondary_stats || []).length ? (
                  <> · Secondary: <strong>{(bis.secondary_stats || []).join(', ')}</strong></>
                ) : null}
                {(bis.tertiary_stats || []).length ? (
                  <> · Tertiary: <strong>{(bis.tertiary_stats || []).join(', ')}</strong></>
                ) : null}
                {bis.maximize_hp_regen ? <> · <strong>HP regen maximized</strong></> : null}
                <> · Pool: {bis.pool_size} gear (any selected class)</>
                {bis.weapon_pool_size != null ? <> · Weapons pool: {bis.weapon_pool_size}</> : null}
                <> · Stats / ratios at <strong>+{bis.upgrade ?? upgrade}</strong></>
                <> · Level <strong>{bis.character_level ?? characterLevel}</strong></>
                <> · Weapons &amp; armor: any selected class (multi-class preferred on ties)</>
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
                      {s.name ? (
                        <img
                          className="item-icon"
                          src={itemImageUrl(s.name)}
                          alt=""
                          onError={hideImg}
                        />
                      ) : null}
                      {s.name ? (
                        <span
                          className="bis-item-name"
                          tabIndex={0}
                          onMouseEnter={(e) => {
                            const r = e.currentTarget.getBoundingClientRect()
                            showHoverTip({
                              name: s.name,
                              statsText: itemTipStatsText(s, upgrade),
                              x: Math.min(r.left, window.innerWidth - 320),
                              y: r.bottom + 6,
                              image: itemImageUrl(s.name),
                            })
                          }}
                          onFocus={(e) => {
                            const r = e.currentTarget.getBoundingClientRect()
                            showHoverTip({
                              name: s.name,
                              statsText: itemTipStatsText(s, upgrade),
                              x: Math.min(r.left, window.innerWidth - 320),
                              y: r.bottom + 6,
                              image: itemImageUrl(s.name),
                            })
                          }}
                          onMouseLeave={hideHoverTip}
                          onBlur={hideHoverTip}
                        >
                          {s.url ? (
                            <a href={s.url} target="_blank" rel="noreferrer">{s.name}</a>
                          ) : (
                            s.name
                          )}
                        </span>
                      ) : (
                        '—'
                      )}
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
                            <AltRow
                              key={a.name}
                              a={a}
                              upgrade={upgrade}
                              onShowTip={showHoverTip}
                              onHideTip={hideHoverTip}
                            />
                          ))}
                        </ul>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {tab === 'search' && (
            <div className="panel item-search">
              <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Item Search</h2>
              <div className="item-search-bar">
                <input
                  type="text"
                  placeholder="Search items…"
                  value={searchQ}
                  onChange={(e) => setSearchQ(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') runSearch() }}
                />
                <select value={searchSlot} onChange={(e) => setSearchSlot(e.target.value)}>
                  <option value="">All slots</option>
                  {(meta?.slots || []).map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <button type="button" className="primary" disabled={searchLoading} onClick={runSearch}>
                  {searchLoading ? 'Searching…' : 'Search'}
                </button>
              </div>
              {searchResults && (
                <p className="muted" style={{ marginTop: '0.65rem' }}>
                  {searchResults.total} match{searchResults.total === 1 ? '' : 'es'}
                  {searchResults.catalog_size != null ? ` · catalog ${searchResults.catalog_size}` : ''}
                </p>
              )}
              <div className="item-search-layout">
                <ul className="item-search-list">
                  {(searchResults?.items || []).map((it) => (
                    <li key={it.name}>
                      <button type="button" className="item-search-result" onClick={() => openItemDetail(it.name)}>
                        <img
                          className="item-icon"
                          src={itemImageUrl(it.name)}
                          alt=""
                          onError={hideImg}
                        />
                        <div>
                          <div className="item-search-name">
                            {it.url ? (
                              <a href={it.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                                {it.name}
                              </a>
                            ) : it.name}
                          </div>
                          <div className="muted" style={{ fontSize: '0.78rem' }}>
                            {it.classes_str || (it.classes || []).join(', ') || '—'}
                            {it.zone ? ` · ${it.zone}` : ''}
                          </div>
                          <div className="stats-line">
                            {fmtStats(it.stats_plus10 || it.stats_plus0, SHOW_UP) || '—'}
                          </div>
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
                {itemDetail && (
                  <div className="item-detail-panel">
                    <div className="item-name">
                      <img
                        className="item-icon"
                        src={itemImageUrl(itemDetail.name)}
                        alt=""
                        onError={hideImg}
                      />
                      {itemDetail.url ? (
                        <a href={itemDetail.url} target="_blank" rel="noreferrer">{itemDetail.name}</a>
                      ) : itemDetail.name}
                    </div>
                    <div className="meta">
                      {(itemDetail.slots || []).join(', ') || itemDetail.slot || '—'}
                      {itemDetail.zone ? ` · ${itemDetail.zone}` : ''}
                    </div>
                    <div className="muted" style={{ fontSize: '0.8rem', marginTop: '0.35rem' }}>
                      {itemDetail.classes_str || (itemDetail.classes || []).join(', ')}
                    </div>
                    <div className="stats-line" style={{ marginTop: '0.5rem' }}>
                      +0 {fmtStats(itemDetail.stats_plus0, SHOW0) || '—'}
                    </div>
                    <div className="stats-line">
                      +10 {fmtStats(itemDetail.stats_plus10, SHOW10) || '—'}
                    </div>
                    {itemDetail.tooltipLines?.length > 0 && (
                      <pre className="help-md" style={{ marginTop: '0.65rem', fontSize: '0.75rem' }}>
                        {(itemDetail.tooltipLines || []).join('\n')}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            </div>
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

                {importMeta && (importMeta.unmatched_count > 0 || unmatchedNames.length > 0 || allItemNames.length > 0) && (
                  <div className="import-unmatched">
                    <p className="muted" style={{ marginTop: 0 }}>
                      Unmatched: <strong>{importMeta.unmatched_count ?? unmatchedNames.length}</strong>
                      {allItemNames.length ? ` · all items listed: ${allItemNames.length}` : ''}
                    </p>
                    {unmatchedNames.length > 0 && (
                      <details open>
                        <summary>Unmatched names</summary>
                        <ul className="mob-list">
                          {unmatchedNames.map((n, i) => <li key={`${n}-${i}`}>{n}</li>)}
                        </ul>
                      </details>
                    )}
                    {allItemNames.length > 0 && (
                      <details>
                        <summary>All imported item names</summary>
                        <ul className="mob-list">
                          {allItemNames.map((n, i) => <li key={`all-${n}-${i}`}>{n}</li>)}
                        </ul>
                      </details>
                    )}
                  </div>
                )}

                <div className="equip-compare-head">
                  <span>Slot</span>
                  <span>Worn</span>
                  <span>BiS</span>
                  <span>Deltas</span>
                </div>
                <div className="equip-list equip-compare">
                  {(meta?.slots || []).map((slot) => {
                    const row = equipCompareRows.find((r) => r.slot === slot) || {
                      slot,
                      worn: { name: equipment[slot] || null, stats: {} },
                      bis_options: [],
                      selected_bis: null,
                      deltas: [],
                    }
                    let bisOptions = row.bis_options || []
                    if (!bisOptions.length && (slotItems[slot] || []).length) {
                      bisOptions = (slotItems[slot] || []).slice(0, 40).map((it) => ({
                        name: it.name,
                        stats_at_upgrade: it.stats_at_upgrade || it.stats_plus10,
                      }))
                    }
                    const selectedBis = bisOverrides[slot] || row.selected_bis || ''
                    const deltas = resolveCompareDeltas({ ...row, bis_options: bisOptions })

                    return (
                      <div className="equip-compare-row" key={slot}>
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
                          {equipment[slot] && !(slotItems[slot] || []).some((it) => it.name === equipment[slot]) && (
                            <option value={equipment[slot]}>{equipment[slot]} (imported)</option>
                          )}
                        </select>
                        <select
                          className="slot-select"
                          value={selectedBis}
                          onChange={(e) => {
                            const v = e.target.value
                            setBisOverrides((prev) => {
                              const next = { ...prev }
                              if (!v) delete next[slot]
                              else next[slot] = v
                              return next
                            })
                          }}
                        >
                          <option value="">— BiS —</option>
                          {bisOptions.map((opt) => (
                            <option key={opt.name} value={opt.name}>{opt.name}</option>
                          ))}
                        </select>
                        <div className="equip-deltas">
                          {deltas.length === 0 ? (
                            <span className="muted">—</span>
                          ) : (
                            deltas.map((d) => (
                              <span
                                key={d.stat}
                                className={`delta-chip ${d.delta > 0 ? 'up' : 'down'}`}
                              >
                                {formatSignedDelta(d)}
                              </span>
                            ))
                          )}
                        </div>
                      </div>
                    )
                  })}
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
                    <p className="muted" style={{ fontSize: '0.8rem' }}>
                      {suggestions.suggestions.length} upgrades ranked — open the{' '}
                      <button type="button" className="zone-link" onClick={() => setTab('upgrades')}>
                        Upgrade Priority
                      </button>{' '}
                      menu for the full rundown (zone, mobs, quest steps).
                    </p>
                    <ul className="upgrade-list">
                      {suggestions.suggestions.slice(0, 5).map((s) => (
                        <li key={`${s.slot}-${s.suggested}`}>
                          <div className="pri">#{s.rank || s.priority} · {s.slot}</div>
                          <div>
                            {s.current ? <>Have <strong>{s.current}</strong> → </> : <>Empty → </>}
                            <strong>{s.suggested}</strong>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'upgrades' && (
            <div className="panel upgrade-priority-panel">
              <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Upgrade Priority</h2>
              <p className="muted" style={{ marginTop: 0 }}>
                Ordered list of what to upgrade next for your selected trio — driven by the BiS list.
                Each entry shows how to get the piece: zone + drop mobs and/or quest steps (from item DB + eqlwiki; never invented).
              </p>
              <div className="row" style={{ marginBottom: '0.85rem' }}>
                <button type="button" className="primary" onClick={runUpgradeSuggestions} disabled={loading || classes.length < 1}>
                  {loading ? 'Building list…' : 'Refresh upgrade list'}
                </button>
                <label className="gold" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', padding: '0.45rem 0.85rem', borderRadius: 8, border: '1px solid #b8962e', background: 'var(--accent)', color: 'var(--accent-text)', fontWeight: 600 }}>
                  Import Inventory.txt
                  <input
                    type="file"
                    accept=".txt,text/plain"
                    style={{ display: 'none' }}
                    onChange={(e) => {
                      onImportFile(e.target.files?.[0])
                      e.target.value = ''
                    }}
                  />
                </label>
                <button type="button" onClick={openHelp}>Help</button>
              </div>
              {classes.length < 1 && (
                <p className="muted">Pick 1–3 classes above, optionally import Inventory.txt, then refresh.</p>
              )}
              {importMsg ? <div className="note" style={{ marginBottom: '0.75rem' }}>{importMsg}</div> : null}
              {suggestions?.note ? <p className="muted" style={{ fontSize: '0.82rem' }}>{suggestions.note}</p> : null}
              {!suggestions?.suggestions?.length && classes.length >= 1 && !loading && (
                <p className="muted">
                  No gaps yet — either you already match BiS, or click Refresh (empty slots count as upgrades).
                </p>
              )}
              <ol className="upgrade-priority-list">
                {(suggestions?.suggestions || []).map((s) => {
                  const obtain = s.obtain || {}
                  const guide = obtain.quest_guide || {}
                  const steps = guide.steps || []
                  const components = guide.components || []
                  const dropMobs = (obtain.zone_detail && obtain.zone_detail.drop_mobs) || []
                  return (
                    <li key={`${s.rank}-${s.slot}-${s.suggested}`} className="upgrade-priority-card">
                      <div className="upgrade-priority-head">
                        <span className="pri">#{s.rank || '—'} · {s.slot}</span>
                        {s.suggested_image_url ? (
                          <img className="item-icon" src={itemImageUrl(s.suggested)} alt="" onError={hideImg} />
                        ) : null}
                        <div className="upgrade-priority-title">
                          {s.current ? (
                            <span>Have <strong>{s.current}</strong> → </span>
                          ) : (
                            <span>Empty → </span>
                          )}
                          {s.suggested_url ? (
                            <a href={s.suggested_url} target="_blank" rel="noreferrer">{s.suggested}</a>
                          ) : (
                            <strong>{s.suggested}</strong>
                          )}
                        </div>
                      </div>
                      <p className="why" style={{ marginTop: '0.35rem' }}>{s.reason}</p>
                      {(s.deltas || []).length > 0 && (
                        <div className="equip-deltas" style={{ marginTop: '0.35rem' }}>
                          {s.deltas.slice(0, 10).map((d) => (
                            <span key={d.stat} className={d.delta > 0 ? 'delta-pos' : 'delta-neg'}>
                              {formatSignedDelta(d)}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="obtain-block">
                        <h4>How to get it</h4>
                        {obtain.how === 'drop' || s.suggested_drops_mobs || s.suggested_zone ? (
                          <div className="obtain-section">
                            <div>
                              <span className="muted">Zone: </span>
                              {s.suggested_zone ? (
                                <button
                                  type="button"
                                  className="zone-link"
                                  onClick={() => openZone(s.suggested_zone, s.suggested_drops_mobs || '')}
                                >
                                  {s.suggested_zone}
                                </button>
                              ) : (
                                <span className="muted">unknown</span>
                              )}
                            </div>
                            {(s.suggested_drops_mobs || dropMobs.length > 0) && (
                              <div style={{ marginTop: '0.35rem' }}>
                                <span className="muted">Drops from: </span>
                                {dropMobs.length > 0 ? (
                                  <ul className="mob-list" style={{ margin: '0.25rem 0 0' }}>
                                    {dropMobs.map((m) => (
                                      <li key={m.name}>
                                        <strong>{m.name}</strong>
                                        {m.level != null && m.level !== '' ? ` · L${m.level}` : ''}
                                        {m.spawn_notes ? ` · ${m.spawn_notes}` : ''}
                                      </li>
                                    ))}
                                  </ul>
                                ) : (
                                  <span>{s.suggested_drops_mobs}</span>
                                )}
                              </div>
                            )}
                          </div>
                        ) : null}
                        {(s.suggested_quest_name || obtain.quest_name) && (
                          <div className="obtain-section" style={{ marginTop: '0.55rem' }}>
                            <div>
                              <span className="muted">Quest: </span>
                              <strong>{s.suggested_quest_name || obtain.quest_name}</strong>
                              {guide.url ? (
                                <>
                                  {' · '}
                                  <a href={guide.url} target="_blank" rel="noreferrer">eqlwiki</a>
                                </>
                              ) : null}
                            </div>
                            {components.length > 0 && (
                              <table className="quest-components" style={{ marginTop: '0.4rem' }}>
                                <thead>
                                  <tr>
                                    <th>Item</th>
                                    <th>Who</th>
                                    <th>Where</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {components.map((c, i) => (
                                    <tr key={`${c.item}-${i}`}>
                                      <td>{c.item}</td>
                                      <td>{c.who}</td>
                                      <td>{c.where}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                            {steps.length > 0 ? (
                              <ol className="quest-steps">
                                {steps.map((step, i) => (
                                  <li key={i}>{step}</li>
                                ))}
                              </ol>
                            ) : (
                              <p className="muted" style={{ fontSize: '0.8rem', marginTop: '0.35rem' }}>
                                {guide.note || guide.error || 'Quest steps not in local DB — open eqlwiki link if shown.'}
                              </p>
                            )}
                          </div>
                        )}
                        {!s.suggested_zone && !s.suggested_drops_mobs && !s.suggested_quest_name && !obtain.quest_name && (
                          <p className="muted" style={{ fontSize: '0.8rem' }}>
                            No zone/drop/quest source recorded for this item in the decoded catalog.
                          </p>
                        )}
                      </div>
                    </li>
                  )
                })}
              </ol>
            </div>
          )}

          <footer className="muted" style={{ marginTop: '1.5rem', fontSize: '0.8rem' }}>
            Item stats from decoded JSON only. Zone details from zone-research (never invented).
            Quest steps from eqlwiki when available (cached; never invented).
            Race attrs/resists: eqlegendstools (verified; matches eqlwiki).
            HP/Mana/END/AC racial &amp; level pools = not applied (no verified formula).
            Excel export: <code>.venv/bin/python scripts/export_xlsx.py</code>
          </footer>
        </div>
      </div>

      <ZoneModal detail={zoneDetail} onClose={() => setZoneDetail(null)} />
      <HelpModal markdown={helpMd} onClose={() => setHelpMd(null)} />
      {hoverTip ? (
        <div
          className="hover-tip"
          style={{ left: hoverTip.x, top: hoverTip.y }}
          role="tooltip"
        >
          {hoverTip.image ? (
            <img
              className="item-icon"
              src={hoverTip.image}
              alt=""
              onError={hideImg}
            />
          ) : null}
          <div className="hover-tip-body">
            <div className="hover-tip-name">{hoverTip.name}</div>
            {hoverTip.statsText ? (
              <pre className="hover-tip-stats">{hoverTip.statsText}</pre>
            ) : (
              <div className="muted">No stats</div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
