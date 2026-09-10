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
  spellIconUrl,
  ensureItemImage,
  getPriorityDefaults,
  listQuests,
  getQuestDetail,
  listMobs,
  getMobDetail,
} from './api.js'
import LoadingOverlay from './LoadingOverlay.jsx'
import {
  APP_HELP,
  THEME_OPTIONS,
  applyThemeToDocument,
  loadUiSettings,
  saveUiSettings,
} from './uiSettings.js'

const EMPTY_EQ = {}
const BUILDS_KEY = 'eq-legends-bis-saved-builds-v1'
const MAX_LEVEL = 50
const EMPTY_TIERS = ['', '', '']

function slotLabel(slot) {
  if (slot === 'ANY1') return 'ANY1 (Any Slot)'
  if (slot === 'ANY2') return 'ANY2 (Any Slot)'
  return slot
}

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
const SHOW_REWARD = [
  'AC', 'HP', 'MANA', 'END', 'STR', 'STA', 'AGI', 'DEX', 'WIS', 'INT', 'CHA',
  'Haste', 'DMG', 'DLY', 'ATK', 'HP_REGEN', 'MANA_REGEN', 'END_REGEN',
  'SVF', 'SVC', 'SVM', 'SVP', 'SVD',
]

const SCALABLE_STAT_KEYS = new Set([
  'AC', 'HP', 'MANA', 'STR', 'STA', 'AGI', 'DEX', 'WIS', 'INT', 'CHA', 'END', 'ATK',
  'SVM', 'SVF', 'SVC', 'SVD', 'SVP', 'SVV',
  'HP_REGEN', 'MANA_REGEN', 'END_REGEN',
])
const UPGRADE_LEVELS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

function clampUpgrade(n) {
  const v = Number(n)
  if (!Number.isFinite(v)) return 0
  return Math.max(0, Math.min(10, Math.trunc(v)))
}

/** Match backend decode_local.scale_item_stat / engine.scale_stats_to_level. */
function scaleItemStat(base, level) {
  const o = Number(base)
  if (!Number.isFinite(o)) return base
  if (!o || !level) return Number.isInteger(o) ? o : o
  const a = Math.floor(o * (1 + level / 10))
  if (o > 0) return Math.max(a, o + level)
  if (o < -10) return Math.ceil(o * Math.max(0, 10 - level) / 10)
  return Math.min(0, o + level)
}

function scaleStatsToLevel(stats0, level) {
  const lvl = clampUpgrade(level)
  const out = {}
  for (const [k, v] of Object.entries(stats0 || {})) {
    if (k === 'DMG') {
      const base = Number(v)
      if (!Number.isFinite(base)) continue
      out[k] = lvl === 0 ? base : Math.floor(base * (1 + lvl / 10))
    } else if (k === 'DLY' || k === 'FIRE_DMG' || k === 'COLD_DMG' || k === 'Haste') {
      out[k] = Number(v) || 0
    } else if (SCALABLE_STAT_KEYS.has(k)) {
      out[k] = scaleItemStat(v, lvl)
    } else {
      const n = Number(v)
      out[k] = Number.isFinite(n) ? n : v
    }
  }
  return out
}

function itemStatsAtLevel(item, level) {
  if (!item) return {}
  const s0 = item.stats_plus0
  if (s0 && typeof s0 === 'object' && Object.keys(s0).length) {
    return scaleStatsToLevel(s0, level)
  }
  const lvl = clampUpgrade(level)
  if (lvl >= 10) return item.stats_plus10 || item.stats_at_upgrade || {}
  if (lvl === 0) return item.stats_plus0 || item.stats_at_upgrade || {}
  return item.stats_at_upgrade || item.stats_plus10 || item.stats_plus0 || {}
}

function upgradesFromImportHints(equipmentMap, hints, wornRows) {
  const out = {}
  const hintMap = hints || {}
  const wornBySlot = {}
  for (const row of wornRows || []) {
    const slot = row?.planner_slot
    if (slot && row.upgrade_from_name != null && row.upgrade_from_name !== '') {
      wornBySlot[slot] = clampUpgrade(row.upgrade_from_name)
    }
  }
  for (const slot of Object.keys(equipmentMap || {})) {
    if (hintMap[slot] != null && hintMap[slot] !== '') {
      out[slot] = clampUpgrade(hintMap[slot])
    } else if (wornBySlot[slot] != null) {
      out[slot] = wornBySlot[slot]
    } else {
      out[slot] = 0
    }
  }
  return out
}

function SlotUpgradeSelect({ value, onChange, title }) {
  return (
    <select
      className="slot-upgrade-select"
      value={clampUpgrade(value)}
      title={title || 'Enchant level +0…+10'}
      aria-label={title || 'Enchant level'}
      onChange={(e) => onChange(clampUpgrade(e.target.value))}
      onClick={(e) => e.stopPropagation()}
    >
      {UPGRADE_LEVELS.map((n) => (
        <option key={n} value={n}>+{n}</option>
      ))}
    </select>
  )
}

const DELTA_KEYS = [
  'AC', 'HP', 'MANA', 'END', 'STR', 'STA', 'AGI', 'DEX', 'WIS', 'INT', 'CHA',
  'Haste', 'DMG', 'DLY', 'HP_REGEN', 'MANA_REGEN', 'END_REGEN',
  'SVF', 'SVC', 'SVM', 'SVP', 'SVD',
]

function hideImg(e) {
  e.target.style.display = 'none'
}

/** Prefer tip to the right of the cursor; clamp into the viewport. */
function tipCoordsFromPointer(e, tipW = 320, tipH = 220) {
  const pad = 22
  const cx = e?.clientX
  const cy = e?.clientY
  const rect = e?.currentTarget?.getBoundingClientRect?.()
  let x = (typeof cx === 'number' && cx > 0 ? cx : (rect ? rect.right : 0)) + pad
  let y = typeof cy === 'number' && cy > 0 ? cy - 8 : (rect ? rect.top : 0)
  if (x + tipW > window.innerWidth - 8) {
    x = Math.max(8, (typeof cx === 'number' && cx > 0 ? cx : x) - tipW - pad)
  }
  if (y + tipH > window.innerHeight - 8) {
    y = Math.max(8, window.innerHeight - tipH - 8)
  }
  if (y < 8) y = 8
  if (x < 8) x = 8
  return { x, y }
}

/** User-facing BiS reason — hide DW/ratio formulas from UI (API still has full why). */
function displayWhy(itemOrWhy) {
  if (itemOrWhy && typeof itemOrWhy === 'object') {
    if (itemOrWhy.why_ui) return String(itemOrWhy.why_ui)
    return displayWhy(itemOrWhy.why)
  }
  if (!itemOrWhy) return ''
  const w = String(itemOrWhy)
  if (/HandMod|DWChance\s*=|Skill\s*\/\s*400|DB\s*=|min\(DLY|eqlwiki Game_Mechanics|working Legends model|expected-dmg|DW main score|DW offhand|2H occupies|best DW pair/i.test(w)) {
    if (/2H occupies/i.test(w)) return 'Two-handed weapon (occupies both hands)'
    if (/DW offhand|offhand with/i.test(w)) return 'Dual-wield offhand'
    if (/DW main|dual.?wield|best DW pair/i.test(w)) return 'Best dual-wield pair'
    if (/2H expected|best 2H|two.?hand/i.test(w)) return 'Best two-handed weapon'
    if (/best ratio/i.test(w)) return 'Best weapon ratio'
    return 'Weapon pick'
  }
  if (/best ratio/i.test(w)) return 'Best weapon ratio'
  // Drop softcap plumbing tags from the visible line
  return w
    .replace(/;\s*AC→softcap/gi, '')
    .replace(/;\s*past AC softcap/gi, '')
    .replace(/;\s*AC softcap-aware/gi, '')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

function ItemIcon({ name, className = 'item-icon' }) {
  const [src, setSrc] = useState('')
  const [failed, setFailed] = useState(false)
  const [loading, setLoading] = useState(Boolean(name))
  const tries = useRef(0)

  useEffect(() => {
    if (!name) return undefined
    let cancelled = false
    tries.current = 0
    setFailed(false)
    setLoading(true)
    setSrc('')

    const paint = (bust = false) => {
      const base = itemImageUrl(name)
      setSrc(bust ? `${base}&_=${Date.now()}` : base)
      setFailed(false)
      setLoading(false)
    }

    const load = async () => {
      try {
        await ensureItemImage(name)
        if (cancelled) return
        paint()
      } catch (_) {
        if (cancelled) return
        // One retry after a short delay (wiki/network race on first BiS paint).
        if (tries.current < 1) {
          tries.current += 1
          await new Promise((r) => setTimeout(r, 450))
          if (cancelled) return
          try {
            await ensureItemImage(name)
            if (cancelled) return
            paint()
            return
          } catch (__) {
            /* fall through — GET also fetches/serves */
          }
        }
        // Soft-fallback: still try the GET endpoint (it runs ensure server-side).
        if (!cancelled) paint()
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [name])

  if (!name) return null
  if (failed) {
    return <span className={`${className} item-icon-placeholder`} title="No image" aria-hidden />
  }
  if (loading || !src) {
    return <span className={`${className} item-icon-placeholder`} title="Loading image…" aria-hidden />
  }
  return (
    <img
      className={className}
      src={src}
      alt=""
      onError={() => {
        // File existed at ensure time but GET failed — one more ensure then give up.
        if (tries.current >= 3) {
          setFailed(true)
          return
        }
        tries.current += 1
        ensureItemImage(name)
          .then(() => setSrc(`${itemImageUrl(name)}&_=${Date.now()}`))
          .catch(() => {
            // Last chance: bust cache on GET without ensure JSON.
            if (tries.current >= 3) setFailed(true)
            else setSrc(`${itemImageUrl(name)}&_=${Date.now()}&retry=${tries.current}`)
          })
      }}
    />
  )
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
  const whyLine = displayWhy(item)
  const tipParts = [
    item.haste ? `Haste +${item.haste}% (highest item only; stacks with spell haste)` : null,
    (item.ratio_at_upgrade != null || item.ratio_plus10 != null)
      ? `Ratio@+${upgrade} ${Number(item.ratio_at_upgrade ?? item.ratio_plus10).toFixed(4)}`
      : null,
    fmtStats(stats, SHOW_UP) || null,
    item.zone ? `Zone: ${item.zone}` : null,
    whyLine || null,
  ].filter(Boolean)
  return tipParts.join('\n')
}

function tipCoordsRightOfCursor(e, tipW = 320, tipH = 220) {
  /** Always prefer the tip to the right of the cursor (buff / item tips). */
  const pad = 18
  const cx = typeof e?.clientX === 'number' ? e.clientX : 0
  const cy = typeof e?.clientY === 'number' ? e.clientY : 0
  let x = cx + pad
  let y = cy - 12
  if (x + tipW > window.innerWidth - 8) {
    x = Math.max(8, window.innerWidth - tipW - 8)
  }
  if (y + tipH > window.innerHeight - 8) {
    y = Math.max(8, window.innerHeight - tipH - 8)
  }
  if (y < 8) y = 8
  if (x < 8) x = 8
  return { x, y }
}

function BuffIcon({ icon, name, className = 'buff-icon' }) {
  const [src, setSrc] = useState(icon ? spellIconUrl(icon) : '')
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    setSrc(icon ? spellIconUrl(icon) : '')
    setFailed(false)
  }, [icon])
  if (!icon || failed || !src) {
    return <span className={`${className} buff-icon-placeholder`} title={name || ''} aria-hidden="true" />
  }
  return (
    <img
      className={className}
      src={src}
      alt=""
      width={32}
      height={32}
      onError={() => setFailed(true)}
    />
  )
}

function buffTipText(buff) {
  if (buff?.hover_text) return buff.hover_text
  const parts = []
  if (buff?.tooltip) parts.push(buff.tooltip)
  const effects = buff?.effects || {}
  const lines = Object.entries(effects)
    .filter(([, v]) => Number(v) !== 0)
    .map(([k, v]) => {
      const n = Number(v)
      if (k === 'HASTE') return `Haste +${n}%`
      return `${k} ${n > 0 ? '+' : ''}${n}`
    })
  if (lines.length) parts.push(`Effects:\n${lines.map((l) => `  ${l}`).join('\n')}`)
  const meta = []
  if (buff?.classes?.length) meta.push(buff.classes.join(', '))
  if (buff?.level != null) meta.push(`L${buff.level}`)
  if (meta.length) parts.push(meta.join(' · '))
  return parts.join('\n\n') || 'No buff details in catalog.'
}

function CastBuffsIconStrip({ castBuffs, onShowTip, onMoveTip, onHideTip }) {
  if (!castBuffs || castBuffs.mode === 'off') return null
  const buffs = castBuffs.active || []
  if (!buffs.length) {
    return (
      <div className="cast-buff-strip">
        <span className="muted" style={{ fontSize: '0.8rem' }}>
          Quick Buff: no spells castable for this trio at L{castBuffs.character_level ?? '—'}.
        </span>
      </div>
    )
  }
  return (
    <div className="cast-buff-strip" aria-label="Active cast buffs">
      {buffs.map((b) => {
        const show = (e) => {
          const { x, y } = tipCoordsRightOfCursor(e)
          onShowTip({
            name: b.name,
            statsText: buffTipText(b),
            x,
            y,
            image: b.icon_url || spellIconUrl(b.icon),
            icon: b.icon,
            kind: 'buff',
          })
        }
        return (
          <button
            type="button"
            className="cast-buff-icon-btn"
            key={b.id}
            title={b.name}
            aria-label={b.name}
            onMouseEnter={show}
            onMouseMove={show}
            onFocus={show}
            onMouseLeave={onHideTip}
            onBlur={onHideTip}
          >
            <BuffIcon icon={b.icon} name={b.name} className="buff-icon buff-icon-lg" />
          </button>
        )
      })}
    </div>
  )
}

function AltRow({ a, upgrade, onShowTip, onMoveTip, onHideTip }) {
  const statsText = itemTipStatsText(a, upgrade)
  const show = (e) => {
    const { x, y } = tipCoordsFromPointer(e)
    onShowTip({
      name: a.name,
      statsText,
      x,
      y,
      image: itemImageUrl(a.name),
    })
  }
  return (
    <li className="alt-row">
      <span
        className="alt-name-wrap"
        tabIndex={0}
        onMouseEnter={show}
        onMouseMove={onMoveTip}
        onFocus={show}
        onMouseLeave={onHideTip}
        onBlur={onHideTip}
      >
        <ItemIcon name={a.name} />
        <span className="alt-name">
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
  const [wornUpgrades, setWornUpgrades] = useState({})
  const [bisUpgrades, setBisUpgrades] = useState({})
  const [preferRanged, setPreferRanged] = useState(true)
  const [bis, setBis] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [race, setRace] = useState('Human')
  const [characterLevel, setCharacterLevel] = useState(MAX_LEVEL)
  const [castBuffsMode, setCastBuffsMode] = useState('off') // off | quick
  const [assumeMaxAas, setAssumeMaxAas] = useState(true)
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
  const [uiSettings, setUiSettings] = useState(() => loadUiSettings())
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [appHelpOpen, setAppHelpOpen] = useState(false)
  const [loadJobs, setLoadJobs] = useState([])
  const loadJobsRef = useRef([])
  const [eqInstallFolder, setEqInstallFolder] = useState('')
  const [eqInventoryInfo, setEqInventoryInfo] = useState(null)
  const [bagsQ, setBagsQ] = useState('')
  const [bagsLoc, setBagsLoc] = useState('')
  const [questQ, setQuestQ] = useState('')
  const [questResults, setQuestResults] = useState(null)
  const [questLoading, setQuestLoading] = useState(false)
  const [questDetail, setQuestDetail] = useState(null)
  const [questDetailLoading, setQuestDetailLoading] = useState(false)
  const [selectedQuestName, setSelectedQuestName] = useState('')
  const [questListCollapsed, setQuestListCollapsed] = useState(false)
  const [questRewardUpgrade, setQuestRewardUpgrade] = useState(0)
  const [mobQ, setMobQ] = useState('')
  const [mobKind, setMobKind] = useState('all')
  const [mobResults, setMobResults] = useState(null)
  const [mobLoading, setMobLoading] = useState(false)
  const [mobDetail, setMobDetail] = useState(null)
  const [mobDetailLoading, setMobDetailLoading] = useState(false)
  const [selectedMobName, setSelectedMobName] = useState('')
  const [mobListCollapsed, setMobListCollapsed] = useState(false)

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
    // Item icons only — buff tips already carry icon_url / kind:'buff'.
    if (tip?.kind === 'buff' || tip?.skipItemImage) return
    if (tip?.name && !ensuredImagesRef.current.has(tip.name)) {
      ensuredImagesRef.current.add(tip.name)
      ensureItemImage(tip.name)
        .then(() => {
          setHoverTip((t) =>
            t && t.name === tip.name
              ? { ...t, image: `${itemImageUrl(tip.name)}&_=${Date.now()}` }
              : t
          )
        })
        .catch(() => {})
    }
  }, [])

  const moveHoverTip = useCallback((e) => {
    const { x, y } = tipCoordsFromPointer(e)
    setHoverTip((t) => (t ? { ...t, x, y } : t))
  }, [])

  const hideHoverTip = useCallback(() => {
    if (hoverTipClearRef.current) clearTimeout(hoverTipClearRef.current)
    hoverTipClearRef.current = setTimeout(() => setHoverTip(null), 80)
  }, [])

  const beginLoad = useCallback((id, label) => {
    const job = { id, label }
    loadJobsRef.current = [...loadJobsRef.current.filter((j) => j.id !== id), job]
    setLoadJobs(loadJobsRef.current)
  }, [])

  const endLoad = useCallback((id) => {
    loadJobsRef.current = loadJobsRef.current.filter((j) => j.id !== id)
    setLoadJobs(loadJobsRef.current)
  }, [])

  const patchUiSettings = useCallback((patch) => {
    setUiSettings((prev) => {
      const next = { ...prev, ...patch }
      saveUiSettings(next)
      if (patch.theme != null) applyThemeToDocument(next.theme)
      if (typeof document !== 'undefined') {
        document.documentElement.setAttribute('data-reduce-motion', next.reduceMotion ? '1' : '0')
      }
      return next
    })
  }, [])

  useEffect(() => {
    applyThemeToDocument(uiSettings.theme)
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-reduce-motion', uiSettings.reduceMotion ? '1' : '0')
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    beginLoad('meta', 'Loading catalog metadata…')
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
      .finally(() => endLoad('meta'))
  }, [beginLoad, endLoad])

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
    beginLoad('bis', 'Calculating Best in Slot…')
    setError('')
    try {
      const data = await postBis(bisRequestBody())
      setBis(data)
      setBisOverrides({})
      const names = []
      for (const s of data.slots || []) {
        if (s.name) names.push(s.name)
        for (const a of s.alts || []) {
          if (a?.name) names.push(a.name)
        }
      }
      // Do not overwrite Simulator worn gear here — BiS mode/upgrades must leave
      // imported equipment alone. Use "Load from BiS" to copy BiS into worn slots.
      beginLoad('images', 'Fetching item icons…')
      const pending = []
      for (const name of names) {
        if (!name || ensuredImagesRef.current.has(name)) continue
        ensuredImagesRef.current.add(name)
        pending.push(ensureItemImage(name).catch(() => {}))
      }
      if (pending.length) await Promise.all(pending)
      endLoad('images')
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      endLoad('bis')
      endLoad('images')
      setLoading(false)
    }
  }, [classes, bisRequestBody, beginLoad, endLoad])

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

  const suggestionBody = useCallback((eq, slotUpgradesOverride) => ({
    classes,
    equipment: eq,
    upgrade,
    slot_upgrades: slotUpgradesOverride || wornUpgrades,
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
    classes, upgrade, wornUpgrades, characterLevel, preferRanged, mode, priorityStat,
    primaryStats, secondaryStats, tertiaryStats, maximizeHpRegen,
  ])

  const runSim = useCallback(async (equipmentOverride, wornUpgradesOverride) => {
    if (classes.length < 1) {
      setError('Pick at least one class (up to 3).')
      return
    }
    const eq =
      equipmentOverride && typeof equipmentOverride === 'object' && !equipmentOverride.nativeEvent
        ? equipmentOverride
        : equipment
    const slotUpg = wornUpgradesOverride && typeof wornUpgradesOverride === 'object'
      ? wornUpgradesOverride
      : wornUpgrades
    setLoading(true)
    beginLoad('sim', 'Updating Simulator totals…')
    setError('')
    try {
      const data = await postSimulate({
        classes,
        race,
        upgrade,
        slot_upgrades: slotUpg,
        character_level: characterLevel,
        equipment: eq,
        cast_buffs: castBuffsMode,
        assume_max_aas: assumeMaxAas,
      })
      setSim(data)
      // Also refresh upgrade priorities (replaces separate Suggest upgrades button).
      try {
        beginLoad('upgrades', 'Refreshing upgrade priorities…')
        const sug = await upgradeSuggestions(suggestionBody(eq, slotUpg))
        setSuggestions(sug)
      } catch (_) {
        /* sim totals still useful if upgrade ranking fails */
      } finally {
        endLoad('upgrades')
      }
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      endLoad('sim')
      setLoading(false)
    }
  }, [classes, race, upgrade, wornUpgrades, characterLevel, equipment, castBuffsMode, assumeMaxAas, suggestionBody, beginLoad, endLoad])

  useEffect(() => {
    // Recalc on Cast Buffs / level / race / per-slot upgrade changes even with
    // empty worn slots so Quick Buff totals and icon strip update immediately.
    if (tab !== 'sim' || classes.length < 1) return undefined
    const t = setTimeout(() => { runSim() }, 220)
    return () => clearTimeout(t)
  }, [tab, upgrade, wornUpgrades, race, characterLevel, castBuffsMode, assumeMaxAas, classes]) // eslint-disable-line react-hooks/exhaustive-deps

  const applyUpgradeToAllSlots = useCallback(() => {
    const slots = meta?.slots || Object.keys(equipment)
    const next = {}
    for (const slot of slots) next[slot] = clampUpgrade(upgrade)
    setWornUpgrades(next)
    setBisUpgrades(next)
    setImportMsg(`Set all slot upgrades to +${clampUpgrade(upgrade)}`)
  }, [meta, equipment, upgrade])

  const clearEquipment = () => {
    setEquipment({})
    setWornUpgrades({})
    setBisUpgrades({})
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
    const upg = {}
    for (const s of bis.slots) {
      if (s.name) {
        eq[s.slot] = s.name
        upg[s.slot] = clampUpgrade(upgrade)
      }
    }
    setEquipment(eq)
    setWornUpgrades(upg)
    setBisUpgrades({ ...upg })
    setBisOverrides({})
    setTab('sim')
  }

  const resetToImportedWorn = () => {
    const eq = importMeta?.equipment
    if (!eq || !Object.keys(eq).length) {
      setError('Import Inventory.txt first to restore worn gear from that file.')
      return
    }
    const restored = { ...eq }
    const restoredUpg = { ...(importMeta.wornUpgrades || {}) }
    setEquipment(restored)
    setWornUpgrades(restoredUpg)
    setBisOverrides({})
    setImportMsg(`Restored ${Object.keys(restored).length} worn slots from last Inventory.txt import`)
    setTab('sim')
    if (classes.length >= 1) {
      runSim(restored, restoredUpg)
    }
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

  const isDesktopApp = typeof window !== 'undefined' && !!window.eqDesktop?.isDesktop

  useEffect(() => {
    if (!window.eqDesktop?.getSettings) return undefined
    let cancelled = false
    window.eqDesktop.getSettings().then((s) => {
      if (cancelled || !s) return
      if (s.eqInstallFolder) setEqInstallFolder(s.eqInstallFolder)
      if (s.lastInventoryName) {
        setEqInventoryInfo({
          name: s.lastInventoryName,
          path: s.lastInventoryPath || '',
          mtimeMs: s.lastInventoryMtimeMs || null,
        })
      }
    }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  const applyInventoryText = useCallback(async (text, sourceLabel, opts = {}) => {
    beginLoad('import', 'Importing Inventory.txt…')
    try {
      const parsed = await importInventory(text)
      if (parsed && parsed.ok === false) {
        setImportMsg('')
        setError((parsed.warnings && parsed.warnings[0]) || parsed.note || 'Inventory import failed.')
        return false
      }
      const eq = parsed.equipment || {}
      const wornUpg = upgradesFromImportHints(eq, parsed.upgrade_hints, parsed.worn)
      setEquipment(eq)
      setWornUpgrades(wornUpg)
      setImportMeta({
        unmatched_count: parsed.unmatched_count || 0,
        unmatched: parsed.unmatched || [],
        all_items: parsed.all_items || [],
        worn: parsed.worn || [],
        equipment: eq,
        wornUpgrades: wornUpg,
        upgrade_hints: parsed.upgrade_hints || {},
        skipped_count: parsed.skipped_count || 0,
        source: sourceLabel || '',
      })
      const wornN = Object.keys(eq).length
      const hinted = Object.values(wornUpg).filter((n) => n > 0).length
      setImportMsg(
        `Imported ${wornN} worn slots` +
        (hinted ? ` · ${hinted} at imported +N` : ' · all unmarked names treated as +0') +
        (parsed.skipped_count ? ` · skipped ${parsed.skipped_count} bag/nested lines` : '') +
        (sourceLabel ? ` from ${sourceLabel}` : '') +
        (parsed.unmatched_count ? ` · ${parsed.unmatched_count} names not in item catalog (see debug)` : '')
      )
      if (opts.switchTab) setTab(opts.switchTab)
      if (classes.length >= 1) {
        try {
          const sug = await upgradeSuggestions(suggestionBody(eq, wornUpg))
          setSuggestions(sug)
        } catch (_) {
          /* import succeeded; upgrade list can be refreshed via Apply / Recalculate */
        }
        try {
          await runSim(eq, wornUpg)
        } catch (_) {
          /* runSim sets its own error */
        }
      }
      return true
    } finally {
      endLoad('import')
    }
  }, [classes, suggestionBody, runSim, beginLoad, endLoad])

  const onImportFile = async (file) => {
    if (!file) return
    const lower = (file.name || '').toLowerCase()
    if (lower.endsWith('.exe') || lower.endsWith('.dll') || lower.endsWith('.bin')) {
      setImportMsg('')
      setError(
        'Pick Inventory.txt from in-game /outputfile inventory — not inventory.exe or other binaries.'
      )
      return
    }
    setImportMsg('Reading…')
    try {
      const text = await file.text()
      await applyInventoryText(text, file.name, { switchTab: 'sim' })
    } catch (e) {
      setImportMsg('')
      setError(String(e.message || e))
    }
  }

  const pickEqInstallFolder = async () => {
    if (!window.eqDesktop?.pickEqInstallFolder) {
      setError('EQ install folder setup requires the desktop app.')
      return null
    }
    setError('')
    const res = await window.eqDesktop.pickEqInstallFolder()
    if (!res?.ok) {
      if (!res?.canceled) setError(res?.message || 'Could not set EQ install folder.')
      return null
    }
    setEqInstallFolder(res.path || res.eqInstallFolder || '')
    setImportMsg(`EQ install folder set: ${res.path || res.eqInstallFolder}`)
    return res.path || res.eqInstallFolder || ''
  }

  const updateInventoryFromEqFolder = async (opts = {}) => {
    if (!window.eqDesktop?.findLatestInventory || !window.eqDesktop?.readInventoryFile) {
      setError('Auto-update from EQ folder requires the desktop app. Use Import Inventory.txt instead.')
      return
    }
    setError('')
    setImportMsg('Looking for latest Inventory.txt…')
    try {
      let folder = (eqInstallFolder || '').trim()
      if (!folder) {
        folder = await pickEqInstallFolder()
        if (!folder) {
          setImportMsg('')
          return
        }
      }
      const found = await window.eqDesktop.findLatestInventory(folder)
      if (!found?.ok) {
        setImportMsg('')
        setError(found?.message || 'No Inventory.txt found in the EQ install folder.')
        return
      }
      const read = await window.eqDesktop.readInventoryFile(found.path)
      if (!read?.ok) {
        setImportMsg('')
        setError(read?.message || 'Could not read Inventory.txt.')
        return
      }
      setEqInventoryInfo({
        name: found.name,
        path: found.path,
        mtimeMs: found.mtimeMs,
        count: found.count,
      })
      await applyInventoryText(read.text, found.name, { switchTab: opts.switchTab })
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
      wornUpgrades: { ...wornUpgrades },
      bisUpgrades: { ...bisUpgrades },
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
    setWornUpgrades(b.wornUpgrades || {})
    setBisUpgrades(b.bisUpgrades || {})
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
      if (res?.warning) setError(String(res.warning))
    } catch (e) {
      setSearchResults(null)
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

  // Load full catalog size (and empty-query page) when opening Item Search.
  useEffect(() => {
    if (tab !== 'search') return undefined
    let cancelled = false
    const t = setTimeout(async () => {
      setSearchLoading(true)
      try {
        const params = { q: searchQ || '', limit: 80 }
        if (searchSlot) params.slot = searchSlot
        const res = await searchItems(params)
        if (!cancelled) {
          setSearchResults(res)
          if (res?.warning) setError(String(res.warning))
        }
      } catch (e) {
        if (!cancelled) {
          setSearchResults(null)
          setError(String(e.message || e))
        }
      } finally {
        if (!cancelled) setSearchLoading(false)
      }
    }, 180)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [tab, searchQ, searchSlot])

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
    const slots = meta?.slots || bis?.slots?.map((s) => s.slot) || []
    const sugBySlot = {}
    for (const row of suggestions?.equipment_compare || []) {
      if (row?.slot) sugBySlot[row.slot] = row
    }
    const bisBySlot = {}
    for (const row of bis?.slots || []) {
      if (row?.slot) bisBySlot[row.slot] = row
    }

    return slots.map((slot) => {
      const sug = sugBySlot[slot]
      const bisRow = bisBySlot[slot]
      const pool = slotItems[slot] || []
      const wornName = (equipment[slot] || '').trim()
      const wornLevel = clampUpgrade(wornUpgrades[slot] ?? upgrade)
      const bisLevel = clampUpgrade(bisUpgrades[slot] ?? upgrade)
      const wornItem = pool.find((it) => (it.name || '').toLowerCase() === wornName.toLowerCase())
      let wornStats = wornItem ? itemStatsAtLevel(wornItem, wornLevel) : {}
      // Suggestions may include worn stats for imported names missing from the slot pool.
      if ((!wornStats || !Object.keys(wornStats).length) && sug?.worn?.stats) {
        const sugWornName = (sug.worn?.name || '').trim().toLowerCase()
        if (!wornName || sugWornName === wornName.toLowerCase()) {
          wornStats = sug.worn.stats || {}
        }
      }

      const bis_options = []
      const pushOpt = (o) => {
        if (!o?.name) return
        if (bis_options.some((x) => x.name === o.name)) return
        bis_options.push({
          name: o.name,
          why: o.why,
          url: o.url || '',
          stats_plus0: o.stats_plus0,
          stats_plus10: o.stats_plus10,
          stats_at_upgrade: o.stats_at_upgrade || o.stats_plus10 || {},
        })
      }
      if (sug?.bis_options?.length) {
        for (const o of sug.bis_options) pushOpt(o)
      }
      if (bisRow) {
        pushOpt({
          name: bisRow.name,
          why: bisRow.why,
          url: bisRow.url || '',
          stats_plus0: bisRow.stats_plus0,
          stats_plus10: bisRow.stats_plus10,
          stats_at_upgrade: bisRow.stats_at_upgrade || bisRow.stats_plus10 || {},
        })
        for (const a of bisRow.alts || []) pushOpt(a)
      }
      if (!bis_options.length && pool.length) {
        for (const it of pool.slice(0, 40)) {
          pushOpt({
            name: it.name,
            stats_plus0: it.stats_plus0,
            stats_plus10: it.stats_plus10,
            stats_at_upgrade: it.stats_at_upgrade || it.stats_plus10 || {},
          })
        }
      }

      const selectedBis = (sug?.selected_bis || bisRow?.name || '').trim() || null
      const selectedOpt = bis_options.find((o) => o.name === selectedBis)
      const poolBis = selectedBis
        ? pool.find((it) => (it.name || '').toLowerCase() === selectedBis.toLowerCase())
        : null
      let bisStats = {}
      if (poolBis) bisStats = itemStatsAtLevel(poolBis, bisLevel)
      else if (selectedOpt) {
        bisStats = selectedOpt.stats_plus0
          ? itemStatsAtLevel(selectedOpt, bisLevel)
          : (selectedOpt.stats_at_upgrade || {})
      } else if (bisRow && bisRow.name === selectedBis) {
        bisStats = bisRow.stats_plus0
          ? itemStatsAtLevel(bisRow, bisLevel)
          : (bisRow.stats_at_upgrade || bisRow.stats_plus10 || {})
      }

      return {
        slot,
        worn: { name: wornName || null, stats: wornStats, upgrade: wornLevel },
        bis_options,
        selected_bis: selectedBis,
        bis_upgrade: bisLevel,
        deltas: selectedBis ? computeStatDeltas(wornStats, bisStats) : [],
      }
    })
  }, [suggestions, bis, equipment, slotItems, meta, wornUpgrades, bisUpgrades, upgrade])

  const resolveCompareDeltas = (row) => {
    const slot = row.slot
    const selected = bisOverrides[slot] || row.selected_bis || ''
    const wornName = (equipment[slot] || row.worn?.name || '').trim()
    const wornLevel = clampUpgrade(wornUpgrades[slot] ?? upgrade)
    const bisLevel = clampUpgrade(bisUpgrades[slot] ?? upgrade)
    const pool = slotItems[slot] || []
    let effectiveWorn = {}
    if (wornName) {
      const found = pool.find((it) => (it.name || '').toLowerCase() === wornName.toLowerCase())
      if (found) {
        effectiveWorn = itemStatsAtLevel(found, wornLevel)
      } else if (
        row.worn?.name
        && String(row.worn.name).toLowerCase() === wornName.toLowerCase()
        && row.worn?.stats
      ) {
        effectiveWorn = row.worn.stats
      }
    }
    if (!selected) return []
    // Same item + same level on both sides → no delta chips.
    if (
      wornName
      && wornName.toLowerCase() === String(selected).toLowerCase()
      && wornLevel === bisLevel
    ) return []
    const opt = (row.bis_options || []).find((o) => o.name === selected)
    let bisStats = null
    const poolBis = pool.find((it) => (it.name || '').toLowerCase() === String(selected).toLowerCase())
    if (poolBis) {
      bisStats = itemStatsAtLevel(poolBis, bisLevel)
    } else if (opt?.stats_plus0) {
      bisStats = itemStatsAtLevel(opt, bisLevel)
    } else if (opt) {
      bisStats = opt.stats_at_upgrade || opt.stats_plus10 || null
    }
    if (!bisStats && bis?.slots) {
      const slotRow = bis.slots.find((s) => s.slot === slot)
      if (slotRow && slotRow.name === selected) {
        bisStats = slotRow.stats_plus0
          ? itemStatsAtLevel(slotRow, bisLevel)
          : (slotRow.stats_at_upgrade || slotRow.stats_plus10 || {})
      } else {
        const alt = (slotRow?.alts || []).find((a) => a.name === selected)
        bisStats = alt
          ? (alt.stats_plus0 ? itemStatsAtLevel(alt, bisLevel) : (alt.stats_at_upgrade || alt.stats_plus10 || {}))
          : {}
      }
    }
    if ((!bisStats || !Object.keys(bisStats).length) && pool.length) {
      const found = pool.find((it) => (it.name || '').toLowerCase() === String(selected).toLowerCase())
      bisStats = found ? itemStatsAtLevel(found, bisLevel) : {}
    }
    return computeStatDeltas(effectiveWorn, bisStats || {}).filter((d) => Math.abs(d.delta) >= 1e-9)
  }

  const openQuestHub = useCallback((questName) => {
    const n = (questName || '').trim()
    if (!n) return
    setSelectedQuestName(n)
    setQuestQ(n)
    setTab('quests')
  }, [])

  const loadQuestDetail = useCallback(async (questName) => {
    const n = (questName || '').trim()
    if (!n) return
    setQuestDetailLoading(true)
    setSelectedQuestName(n)
    setError('')
    try {
      const inv = importMeta?.all_items || []
      const d = await getQuestDetail({
        name: n,
        fetch: true,
        inventory_items: inv,
      })
      setQuestDetail(d)
    } catch (e) {
      setQuestDetail(null)
      setError(String(e.message || e))
    } finally {
      setQuestDetailLoading(false)
    }
  }, [importMeta])

  useEffect(() => {
    if (tab !== 'quests') return undefined
    let cancelled = false
    const t = setTimeout(async () => {
      setQuestLoading(true)
      try {
        const res = await listQuests({ q: questQ || '', limit: 120 })
        if (!cancelled) setQuestResults(res)
      } catch (e) {
        if (!cancelled) {
          setQuestResults(null)
          setError(String(e.message || e))
        }
      } finally {
        if (!cancelled) setQuestLoading(false)
      }
    }, 220)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [tab, questQ])

  useEffect(() => {
    if (tab !== 'quests' || !selectedQuestName) return
    loadQuestDetail(selectedQuestName)
  }, [tab, selectedQuestName, loadQuestDetail])

  const loadMobDetail = useCallback(async (mobName) => {
    const n = (mobName || '').trim()
    if (!n) return
    setMobDetailLoading(true)
    setSelectedMobName(n)
    setError('')
    try {
      const d = await getMobDetail({ name: n, fetch: true })
      setMobDetail(d)
    } catch (e) {
      setMobDetail(null)
      setError(String(e.message || e))
    } finally {
      setMobDetailLoading(false)
    }
  }, [])

  useEffect(() => {
    if (tab !== 'mobs') return undefined
    let cancelled = false
    const t = setTimeout(async () => {
      setMobLoading(true)
      try {
        const res = await listMobs({
          q: mobQ || '',
          kind: mobKind && mobKind !== 'all' ? mobKind : '',
          limit: 120,
        })
        if (!cancelled) setMobResults(res)
      } catch (e) {
        if (!cancelled) {
          setMobResults(null)
          setError(String(e.message || e))
        }
      } finally {
        if (!cancelled) setMobLoading(false)
      }
    }, 220)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [tab, mobQ, mobKind])

  useEffect(() => {
    if (tab !== 'mobs' || !selectedMobName) return
    loadMobDetail(selectedMobName)
  }, [tab, selectedMobName, loadMobDetail])

  const navItems = [
    { id: 'bis', label: 'Best in Slot' },
    { id: 'sim', label: 'Simulator' },
    { id: 'upgrades', label: 'Upgrade Priority' },
    { id: 'bags', label: 'Search My Bags' },
    { id: 'quests', label: 'Quest Hub' },
    { id: 'mobs', label: 'Mobs' },
    { id: 'search', label: 'Item Search' },
  ]

  const unmatchedNames = (importMeta?.unmatched || [])
    .map((u) => (typeof u === 'string' ? u : (u.name || u.base_name || '')))
    .filter(Boolean)
  const allImportedItems = importMeta?.all_items || []
  const wornSlotCount = Object.keys(importMeta?.equipment || equipment || {}).length

  const bagHits = useMemo(() => {
    const q = (bagsQ || '').trim().toLowerCase()
    const tokens = q.split(/[^a-z0-9']+/i).filter((t) => t && !['of', 'the', 'a', 'an', 'and'].includes(t))
    const locFilter = (bagsLoc || '').trim().toLowerCase()
    return allImportedItems.filter((row) => {
      const name = String(row?.base_name || row?.name || row || '').trim()
      const nameLc = name.toLowerCase()
      if (!name || nameLc === 'empty') return false
      const loc = String(row?.location || '').toLowerCase()
      if (locFilter && !loc.includes(locFilter)) return false
      if (!tokens.length) return true
      return tokens.every((t) => nameLc.includes(t) || loc.includes(t))
    })
  }, [allImportedItems, bagsQ, bagsLoc])

  return (
    <div className="app">
      <LoadingOverlay
        open={loadJobs.length > 0}
        jobs={loadJobs}
        funnyTips={uiSettings.funnyLoadingTips !== false}
      />
      <header className="app-header">
        <div>
          <h1>EQ Legends — BiS + Build Simulator</h1>
          <p>
            Local BiS planner & simulator
            {meta?.catalog_weapons ? ` · ${meta.catalog_weapons} catalog weapons` : ''}
            {meta?.version ? ` · v${meta.version}` : ''}
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="icon-btn"
            title="Help"
            aria-label="Open help"
            onClick={() => setAppHelpOpen(true)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="12" cy="12" r="9" />
              <path d="M9.5 9.5a2.5 2.5 0 1 1 3.6 2.2c-.8.4-1.1.8-1.1 1.8" />
              <circle cx="12" cy="17" r="0.8" fill="currentColor" stroke="none" />
            </svg>
          </button>
          <button
            type="button"
            className="icon-btn"
            title="Settings"
            aria-label="Open settings"
            onClick={() => setSettingsOpen(true)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="12" cy="12" r="3.2" />
              <path d="M12 2.8v2.2M12 19v2.2M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M2.8 12h2.2M19 12h2.2M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6" />
            </svg>
          </button>
          <span className="ui-build-badge" title="App version">{meta?.version ? `Version ${meta.version}` : "Version …"}</span>
        </div>
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
                    <span className="muted" style={{ fontSize: '0.75rem' }}>Pools use race+class+STA (EQLT)</span>
                  </div>
                  <div className="field">
                    <label>Cast Buffs</label>
                    <select value={castBuffsMode} onChange={(e) => setCastBuffsMode(e.target.value)}>
                      <option value="off">Off</option>
                      <option value="quick">Quick Buff (at Character Level)</option>
                    </select>
                    <span className="muted" style={{ fontSize: '0.75rem' }}>
                      Trio casters → best stacking lines castable at level {characterLevel}
                    </span>
                  </div>
                  <div className="field">
                    <label className="check">
                      <input type="checkbox" checked={assumeMaxAas} onChange={(e) => setAssumeMaxAas(e.target.checked)} />
                      Max AAs (sheet)
                    </label>
                  </div>
                  <div className="field">
                    <label>Default upgrade +0…+10</label>
                    <input
                      type="range"
                      min={0}
                      max={10}
                      value={upgrade}
                      onChange={(e) => setUpgrade(Number(e.target.value))}
                    />
                    <span className="muted">+{upgrade}</span>
                    <button
                      type="button"
                      style={{ marginTop: '0.35rem' }}
                      onClick={applyUpgradeToAllSlots}
                      title="Copy this default onto every Worn and BiS slot"
                    >
                      Apply to all slots
                    </button>
                    <span className="muted" style={{ fontSize: '0.72rem' }}>
                      Each row has its own +N; import sets Worn from Inventory.txt
                    </span>
                  </div>
                  <div className="field">
                    <label>&nbsp;</label>
                    <button className="primary" disabled={loading} onClick={runSim}>
                      {loading ? 'Updating…' : 'Apply / Recalculate'}
                    </button>
                  </div>
                </>
              )}
            </div>
            {(tab === 'bis' || tab === 'sim') && (
              <div
                className={uiSettings.compactBadges !== false ? 'badge-row-compact' : undefined}
                style={{ marginTop: '0.75rem', display: 'flex', gap: '0.45rem', flexWrap: 'wrap' }}
              >
                <span className="badge">Default +{upgrade}</span>
                {tab === 'sim' && (
                  <span className="badge">
                    Per-slot +N
                  </span>
                )}
                <span className="badge warn">Haste: highest item + spell (cap 175/185)</span>
                {preferRanged && <span className="badge">Prefer ranged</span>}
                {maximizeHpRegen && <span className="badge">Max HP regen</span>}
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
              {bis.dual_wield_enabled ? (
                <p className="note" style={{ marginTop: '0.5rem' }}>
                  Dual-wield classes: primary/secondary chosen as the best DW pair or two-hander
                  (formulas stay in the API only).
                </p>
              ) : null}
              <p className="note" style={{ marginTop: '0.5rem' }}>
                ANY1/ANY2 are the two worn Any Slots — BiS scored on stats only (weapon damage ignored);
                filled after dedicated slots from leftover gear.
              </p>
              <div className="grid-slots">
                {bis.slots.map((s) => (
                  <div className="slot-card" key={s.slot}>
                    <h3>{slotLabel(s.slot)}{s.haste ? ` · Haste +${s.haste}%` : ''}</h3>
                    <div className="item-name">
                      {s.name ? <ItemIcon name={s.name} /> : null}
                      {s.name ? (
                        <span
                          className="bis-item-name"
                          tabIndex={0}
                          onMouseEnter={(e) => {
                            const { x, y } = tipCoordsFromPointer(e)
                            showHoverTip({
                              name: s.name,
                              statsText: itemTipStatsText(s, upgrade),
                              x,
                              y,
                              image: itemImageUrl(s.name),
                            })
                          }}
                          onMouseMove={moveHoverTip}
                          onFocus={(e) => {
                            const { x, y } = tipCoordsFromPointer(e)
                            showHoverTip({
                              name: s.name,
                              statsText: itemTipStatsText(s, upgrade),
                              x,
                              y,
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
                    {displayWhy(s) ? <div className="why">{displayWhy(s)}</div> : null}
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
                              onMoveTip={moveHoverTip}
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

          {tab === 'bags' && (
            <div className="panel item-search">
              <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Search My Bags</h2>
              <p className="muted" style={{ marginTop: 0 }}>
                Search occupied slots from your last Inventory.txt import (worn, bags, bank, nested — empty slots hidden).
              </p>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem', alignItems: 'center' }}>
                {isDesktopApp && (
                  <>
                    <button
                      type="button"
                      onClick={pickEqInstallFolder}
                      title="Point once at your EverQuest Legends install folder"
                    >
                      {eqInstallFolder ? 'Change EQ folder' : 'Set EQ folder'}
                    </button>
                    <button
                      type="button"
                      className="primary"
                      onClick={() => updateInventoryFromEqFolder({ switchTab: 'bags' })}
                      title="Find the newest *-Inventory.txt in your EQ install folder and import it"
                    >
                      Update from EQ folder
                    </button>
                  </>
                )}
                <label className="gold" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', padding: '0.45rem 0.85rem', borderRadius: 8, border: '1px solid #b8962e', background: 'var(--accent)', color: 'var(--accent-text)', fontWeight: 600, cursor: 'pointer' }}>
                  Import Inventory.txt
                  <input
                    type="file"
                    accept=".txt,text/plain"
                    style={{ display: 'none' }}
                    onChange={async (e) => {
                      const f = e.target.files && e.target.files[0]
                      e.target.value = ''
                      if (!f) return
                      const lower = (f.name || '').toLowerCase()
                      if (lower.endsWith('.exe') || lower.endsWith('.dll') || lower.endsWith('.bin')) {
                        setError('Pick Inventory.txt — not a binary.')
                        return
                      }
                      setImportMsg('Reading…')
                      try {
                        const text = await f.text()
                        await applyInventoryText(text, f.name, { switchTab: 'bags' })
                      } catch (err) {
                        setImportMsg('')
                        setError(String(err.message || err))
                      }
                    }}
                  />
                </label>
              </div>
              {isDesktopApp && (
                <p className="muted" style={{ marginTop: 0, fontSize: '0.8rem' }}>
                  {eqInstallFolder
                    ? <>EQ folder: <code>{eqInstallFolder}</code>
                      {eqInventoryInfo?.name ? <> · last dump <code>{eqInventoryInfo.name}</code></> : null}
                      </>
                    : 'Set EQ folder once, then Update pulls the newest *-Inventory.txt after /outputfile inventory.'}
                </p>
              )}
              {!allImportedItems.length ? (
                <p className="muted">
                  No inventory imported yet — use Update from EQ folder or Import Inventory.txt.
                </p>
              ) : (
                <>
                  <div className="item-search-bar">
                    <input
                      type="text"
                      placeholder="Find an item in your bags…"
                      value={bagsQ}
                      onChange={(e) => setBagsQ(e.target.value)}
                    />
                    <input
                      type="text"
                      placeholder="Location filter (e.g. General, Bank)"
                      value={bagsLoc}
                      onChange={(e) => setBagsLoc(e.target.value)}
                      style={{ maxWidth: 220 }}
                    />
                  </div>
                  <p className="muted" style={{ marginTop: '0.65rem' }}>
                    {bagHits.length} match{bagHits.length === 1 ? '' : 'es'}
                    {' · '}
                    {allImportedItems.filter((r) => {
                      const n = String(r?.base_name || r?.name || '').trim().toLowerCase()
                      return n && n !== 'empty'
                    }).length}{' '}
                    items with contents
                  </p>
                  <ul className="item-search-list">
                    {bagHits.slice(0, 500).map((row, i) => {
                      const name = row?.base_name || row?.name || String(row)
                      const loc = row?.location || '—'
                      const count = row?.count || ''
                      return (
                        <li key={`${loc}-${name}-${i}`}>
                          <div className="item-search-result" style={{ cursor: 'default' }}>
                            <div>
                              <div className="item-search-name">{name}</div>
                              <div className="muted" style={{ fontSize: '0.78rem' }}>
                                {loc}{count ? ` · ×${count}` : ''}
                                {row?.in_catalog === false
                                  ? ' · not in item catalog'
                                  : (row?.catalog_source === 'eqlwiki' && !row?.has_stats
                                    ? ' · eqlwiki name (no stats yet)'
                                    : '')}
                                {row?.planner_slot ? ` · worn ${row.planner_slot}` : ''}
                              </div>
                            </div>
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                </>
              )}
            </div>
          )}

          {tab === 'quests' && (
            <div className="panel item-search">
              <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Quest Hub</h2>
              <p className="muted" style={{ marginTop: 0 }}>
                Single-click a quest for a preview. Double-click (or use the side arrow) to maximize the walkthrough.
                Steps come from eqlwiki when available.
              </p>
              <div className={`quest-hub-layout${questListCollapsed ? ' list-collapsed' : ''}`}>
                <div className="quest-hub-list-col">
                  <div className="item-search-bar">
                    <input
                      type="text"
                      placeholder="Search quests…"
                      value={questQ}
                      onChange={(e) => setQuestQ(e.target.value)}
                    />
                  </div>
                  {questResults && (
                    <p className="muted" style={{ marginTop: '0.65rem', marginBottom: '0.35rem' }}>
                      {questLoading ? 'Searching…' : `${questResults.total} quest${questResults.total === 1 ? '' : 's'}`}
                      {questResults.catalog_size != null ? ` · index ${questResults.catalog_size}` : ''}
                    </p>
                  )}
                  {questResults?.note ? (
                    <p className="muted" style={{ fontSize: '0.78rem' }}>{questResults.note}</p>
                  ) : null}
                  <ul className="item-search-list quest-hub-list">
                    {(questResults?.quests || []).map((q) => (
                      <li key={q.name}>
                        <button
                          type="button"
                          className="item-search-result"
                          title="Click to preview · Double-click to maximize walkthrough"
                          onClick={() => setSelectedQuestName(q.name)}
                          onDoubleClick={() => {
                            setSelectedQuestName(q.name)
                            setQuestListCollapsed(true)
                          }}
                          style={selectedQuestName === q.name ? { outline: '1px solid var(--accent)' } : undefined}
                        >
                          <div>
                            <div className="item-search-name">{q.name}</div>
                            <div className="muted" style={{ fontSize: '0.78rem' }}>
                              {q.item_count ? `${q.item_count} linked item${q.item_count === 1 ? '' : 's'}` : '—'}
                              {(q.sample_items || [])[0] ? ` · e.g. ${q.sample_items[0]}` : ''}
                            </div>
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
                <button
                  type="button"
                  className="quest-hub-rail"
                  title={questListCollapsed ? 'Show quest list' : 'Maximize walkthrough (hide list)'}
                  aria-label={questListCollapsed ? 'Expand quest list' : 'Collapse quest list'}
                  onClick={() => setQuestListCollapsed((v) => !v)}
                >
                  <span className="quest-hub-rail-arrow" aria-hidden="true">
                    {questListCollapsed ? '›' : '‹'}
                  </span>
                </button>
                <div className="item-detail-panel quest-hub-detail">
                  {!selectedQuestName && (
                    <p className="muted">Select a quest to view steps, prerequisites, and inventory checks.</p>
                  )}
                  {questDetailLoading && <p className="muted">Loading quest…</p>}
                  {questDetail && !questDetailLoading && (
                    <>
                      <div className="item-name">
                        <strong>{questDetail.quest || selectedQuestName}</strong>
                        {questDetail.url ? (
                          <>
                            {' · '}
                            <a href={questDetail.url} target="_blank" rel="noreferrer">eqlwiki</a>
                          </>
                        ) : null}
                      </div>
                      {questDetail.inventory?.imported ? (
                        <p className="muted" style={{ fontSize: '0.82rem' }}>
                          Inventory check: have {questDetail.inventory.have_count || 0} / need{' '}
                          {(questDetail.inventory.have_count || 0) + (questDetail.inventory.need_count || 0)} component
                          {(questDetail.inventory.have_count || 0) + (questDetail.inventory.need_count || 0) === 1 ? '' : 's'}
                        </p>
                      ) : (
                        <p className="muted" style={{ fontSize: '0.82rem' }}>
                          Import Inventory.txt to mark which turn-in items you already have.
                        </p>
                      )}
                      <h3 style={{ fontSize: '0.95rem', marginBottom: '0.35rem' }}>Rewards</h3>
                      {(questDetail.rewards || []).length ? (
                        <>
                          {(questDetail.rewards || []).some((r) => r.in_catalog && (r.stats_plus0 || r.stats_by_upgrade)) ? (
                            <div className="quest-reward-upgrade">
                              <label htmlFor="quest-reward-upgrade">Upgrade +0…+10</label>
                              <input
                                id="quest-reward-upgrade"
                                type="range"
                                min={0}
                                max={10}
                                value={questRewardUpgrade}
                                onChange={(e) => setQuestRewardUpgrade(Number(e.target.value))}
                              />
                              <span className="muted">+{questRewardUpgrade}</span>
                            </div>
                          ) : null}
                          <ul className="quest-rewards">
                            {(questDetail.rewards || []).map((r, i) => {
                              const by = r.stats_by_upgrade || {}
                              const stats = by[String(questRewardUpgrade)]
                                || by[questRewardUpgrade]
                                || r.stats_at_upgrade
                                || r.stats_plus0
                              const ratioBy = r.ratio_by_upgrade || {}
                              const ratio = ratioBy[String(questRewardUpgrade)]
                                ?? ratioBy[questRewardUpgrade]
                                ?? r.ratio_at_upgrade
                              return (
                                <li key={`${r.name}-${i}`} className="quest-reward">
                                  <div className="quest-reward-head">
                                    {r.image_url || r.name ? (
                                      <img
                                        className="item-icon"
                                        src={itemImageUrl(r.name)}
                                        alt=""
                                        onError={hideImg}
                                      />
                                    ) : null}
                                    <div>
                                      <div className="item-search-name">
                                        {r.url ? (
                                          <a href={r.url} target="_blank" rel="noreferrer">{r.name}</a>
                                        ) : (
                                          r.name
                                        )}
                                      </div>
                                      <div className="muted" style={{ fontSize: '0.78rem' }}>
                                        {(r.slots || []).join(', ') || r.slot || 'item'}
                                        {r.classes_str ? ` · ${r.classes_str}` : ''}
                                      </div>
                                    </div>
                                  </div>
                                  {r.in_catalog === false ? (
                                    <p className="muted" style={{ fontSize: '0.78rem', margin: '0.25rem 0 0' }}>
                                      {r.note || 'No catalog stats for this reward name.'}
                                    </p>
                                  ) : (
                                    <div className="stats-line" style={{ marginTop: '0.35rem' }}>
                                      +{questRewardUpgrade}{' '}
                                      {fmtStats(stats, SHOW_REWARD) || '—'}
                                      {ratio != null ? (
                                        <span className="muted"> · Ratio {Number(ratio).toFixed(4)}</span>
                                      ) : null}
                                    </div>
                                  )}
                                </li>
                              )
                            })}
                          </ul>
                        </>
                      ) : (
                        <p className="muted" style={{ fontSize: '0.8rem' }}>
                          {questDetail.rewards_note || 'No item rewards linked in the decoded catalog for this quest.'}
                        </p>
                      )}
                      <h3 style={{ fontSize: '0.95rem', marginBottom: '0.35rem' }}>Prerequisites</h3>
                      {(questDetail.prerequisites || []).length ? (
                        <ul className="mob-list">
                          {(questDetail.prerequisites || []).map((p, i) => {
                            const openable = p.kind === 'quest' && p.in_hub !== false
                            return (
                              <li key={`${p.name}-${i}`}>
                                {openable ? (
                                  <button
                                    type="button"
                                    className="zone-link"
                                    onClick={() => {
                                      setSelectedQuestName(p.name)
                                      setQuestQ(p.name)
                                      setQuestListCollapsed(true)
                                    }}
                                  >
                                    {p.name}
                                  </button>
                                ) : (
                                  <span>{p.name}</span>
                                )}
                                {p.mentioned_as && String(p.mentioned_as).toLowerCase() !== String(p.name || '').toLowerCase() ? (
                                  <span className="muted"> (as {p.mentioned_as})</span>
                                ) : null}
                                {p.kind === 'quest' && p.in_hub === false ? (
                                  <span className="muted"> · not in Quest Hub index</span>
                                ) : null}
                                {p.source ? <span className="muted"> · {p.source}</span> : null}
                              </li>
                            )
                          })}
                        </ul>
                      ) : (
                        <p className="muted" style={{ fontSize: '0.8rem' }}>
                          {questDetail.prerequisites_note || 'No prerequisites listed in available sources.'}
                        </p>
                      )}
                      {(questDetail.components || []).length > 0 && (
                        <>
                          <h3 style={{ fontSize: '0.95rem', marginBottom: '0.35rem' }}>Components</h3>
                          <table className="quest-components">
                            <thead>
                              <tr>
                                <th>Have?</th>
                                <th>Item</th>
                                <th>Who / Where</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(questDetail.components || []).map((c, i) => (
                                <tr key={`${c.item}-${i}`}>
                                  <td>{c.have ? 'Yes' : 'No'}</td>
                                  <td>
                                    {c.item}
                                    {c.have_locations?.length ? (
                                      <div className="muted" style={{ fontSize: '0.72rem' }}>
                                        {c.have_locations.join(' · ')}
                                      </div>
                                    ) : null}
                                  </td>
                                  <td>{[c.who, c.where].filter(Boolean).join(' · ')}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </>
                      )}
                      <h3 style={{ fontSize: '0.95rem', marginBottom: '0.35rem' }}>Steps</h3>
                      {(questDetail.steps || []).length ? (
                        <ol className="quest-steps">
                          {(questDetail.steps || []).map((step, i) => (
                            <li key={i}>{step}</li>
                          ))}
                        </ol>
                      ) : (
                        <p className="muted" style={{ fontSize: '0.8rem' }}>
                          {questDetail.note || questDetail.error || 'Steps not available locally.'}
                        </p>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
          )}

          {tab === 'mobs' && (
            <div className="panel item-search">
              <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Mobs</h2>
              <p className="muted" style={{ marginTop: 0 }}>
                Single-click a mob for a preview. Double-click (or use the side arrow) to maximize the detail panel.
                Names and kinds come from eqlwiki (raid / mini boss / named / standard).
              </p>
              <div className={`quest-hub-layout${mobListCollapsed ? ' list-collapsed' : ''}`}>
                <div className="quest-hub-list-col">
                  <div className="item-search-bar" style={{ flexWrap: 'wrap' }}>
                    <input
                      type="text"
                      placeholder="Search mobs…"
                      value={mobQ}
                      onChange={(e) => setMobQ(e.target.value)}
                    />
                    <select
                      value={mobKind}
                      onChange={(e) => setMobKind(e.target.value)}
                      style={{ maxWidth: 180 }}
                      title="Filter by mob kind"
                    >
                      <option value="all">All combat mobs</option>
                      <option value="raid">Raid</option>
                      <option value="mini_boss">Mini Boss</option>
                      <option value="named">Named</option>
                      <option value="standard">Standard</option>
                    </select>
                  </div>
                  {(mobResults?.kinds || []).length ? (
                    <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
                      {(mobResults.kinds || []).map((k) => (
                        <button
                          key={k.id}
                          type="button"
                          className={mobKind === k.id ? 'primary' : ''}
                          style={{ padding: '0.25rem 0.55rem', fontSize: '0.78rem' }}
                          onClick={() => setMobKind(mobKind === k.id ? 'all' : k.id)}
                        >
                          {k.label}{k.count != null ? ` (${k.count})` : ''}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {mobResults && (
                    <p className="muted" style={{ marginTop: '0.65rem', marginBottom: '0.35rem' }}>
                      {mobLoading ? 'Searching…' : `${mobResults.total} mob${mobResults.total === 1 ? '' : 's'}`}
                      {mobResults.catalog_size != null ? ` · index ${mobResults.catalog_size}` : ''}
                    </p>
                  )}
                  {mobResults?.warning ? (
                    <p className="muted" style={{ fontSize: '0.78rem', color: 'var(--warn, #c9a227)' }}>
                      {mobResults.warning}
                    </p>
                  ) : null}
                  {mobResults?.note ? (
                    <p className="muted" style={{ fontSize: '0.78rem' }}>{mobResults.note}</p>
                  ) : null}
                  {!mobLoading && mobResults && mobResults.total === 0 ? (
                    <p className="muted" style={{ fontSize: '0.85rem' }}>
                      No mobs matched. If the index is 0, the mob database file is missing from this install —
                      rebuild/update the app so <code>eqlwiki_mob_names.json</code> is included.
                    </p>
                  ) : null}
                  <ul className="item-search-list quest-hub-list">
                    {(mobResults?.mobs || []).map((m) => (
                      <li key={m.name}>
                        <button
                          type="button"
                          className="item-search-result"
                          title="Click to preview · Double-click to maximize"
                          onClick={() => setSelectedMobName(m.name)}
                          onDoubleClick={() => {
                            setSelectedMobName(m.name)
                            setMobListCollapsed(true)
                          }}
                          style={selectedMobName === m.name ? { outline: '1px solid var(--accent)' } : undefined}
                        >
                          <div>
                            <div className="item-search-name">{m.name}</div>
                            <div className="muted" style={{ fontSize: '0.78rem' }}>
                              {(m.kind_labels || []).filter(Boolean).join(' · ') || m.primary_kind || '—'}
                            </div>
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
                <button
                  type="button"
                  className="quest-hub-rail"
                  title={mobListCollapsed ? 'Show mob list' : 'Maximize detail (hide list)'}
                  aria-label={mobListCollapsed ? 'Expand mob list' : 'Collapse mob list'}
                  onClick={() => setMobListCollapsed((v) => !v)}
                >
                  <span className="quest-hub-rail-arrow" aria-hidden="true">
                    {mobListCollapsed ? '›' : '‹'}
                  </span>
                </button>
                <div className="item-detail-panel quest-hub-detail">
                  {!selectedMobName && (
                    <p className="muted">Select a mob to view zone, level, and known drops.</p>
                  )}
                  {mobDetailLoading && <p className="muted">Loading mob…</p>}
                  {mobDetail && !mobDetailLoading && (
                    <>
                      <div className="item-name">
                        <strong>{mobDetail.name || selectedMobName}</strong>
                        {mobDetail.url ? (
                          <>
                            {' · '}
                            <a href={mobDetail.url} target="_blank" rel="noreferrer">eqlwiki</a>
                          </>
                        ) : null}
                      </div>
                      <div className="meta" style={{ marginTop: '0.35rem' }}>
                        {(mobDetail.kind_labels || []).join(' · ') || '—'}
                        {mobDetail.level ? ` · Level ${mobDetail.level}` : ''}
                        {mobDetail.zone ? ` · ${mobDetail.zone}` : ''}
                      </div>
                      {mobDetail.location ? (
                        <p className="muted" style={{ fontSize: '0.82rem' }}>Location: {mobDetail.location}</p>
                      ) : null}
                      {mobDetail.description ? (
                        <p style={{ marginTop: '0.65rem', fontSize: '0.85rem' }}>{mobDetail.description}</p>
                      ) : null}
                      {Object.keys(mobDetail.fields || {}).length > 0 && (
                        <>
                          <h3 style={{ fontSize: '0.95rem', marginBottom: '0.35rem' }}>Wiki fields</h3>
                          <ul className="mob-list">
                            {Object.entries(mobDetail.fields || {}).map(([k, v]) => (
                              <li key={k}>
                                <strong>{k.replace(/_/g, ' ')}</strong>: {String(v)}
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                      <h3 style={{ fontSize: '0.95rem', marginBottom: '0.35rem' }}>Known drops</h3>
                      {(mobDetail.drop_items || []).length ? (
                        <ul className="quest-rewards">
                          {(mobDetail.drops || []).slice(0, 60).map((d, i) => (
                            <li key={`${d.item}-${i}`}>
                              <button
                                type="button"
                                className="zone-link"
                                onClick={async () => {
                                  const itemName = d.item
                                  setTab('search')
                                  setSearchQ(itemName)
                                  setSearchLoading(true)
                                  try {
                                    const res = await searchItems({ q: itemName, limit: 80 })
                                    setSearchResults(res)
                                    const hit = (res.items || []).find((it) => String(it.name || '').toLowerCase() === String(itemName).toLowerCase())
                                      || (res.items || [])[0]
                                    if (hit?.name) await openItemDetail(hit.name)
                                  } catch (err) {
                                    setError(String(err.message || err))
                                  } finally {
                                    setSearchLoading(false)
                                  }
                                }}
                              >
                                {d.item}
                              </button>
                              {d.zone ? <span className="muted"> · {d.zone}</span> : null}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted" style={{ fontSize: '0.8rem' }}>
                          No decoded catalog drops linked to this name yet.
                        </p>
                      )}
                      {mobDetail.note ? (
                        <p className="muted" style={{ fontSize: '0.75rem', marginTop: '0.75rem' }}>{mobDetail.note}</p>
                      ) : null}
                    </>
                  )}
                </div>
              </div>
            </div>
          )}

          {tab === 'search' && (
            <div className="panel item-search">
              <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Item Search</h2>
              <p className="muted" style={{ marginTop: 0 }}>
                Full EQ Legends catalog (~11k+ names from eqlwiki Category:Items, plus tools stats when known).
                Open an item for description, tooltip, and quests (Quest Hub links when the quest is indexed).
                Stats and descriptions come from decoded tools data or the item’s eqlwiki page — never invented.
              </p>
              <div className="item-search-bar">
                <input
                  type="text"
                  placeholder="Search any item…"
                  value={searchQ}
                  onChange={(e) => setSearchQ(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') runSearch() }}
                />
                <select value={searchSlot} onChange={(e) => setSearchSlot(e.target.value)}>
                  <option value="">All slots</option>
                  {(meta?.slots || []).map((s) => (
                    <option key={s} value={s}>{slotLabel(s)}</option>
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
                  {searchResults.tools_items != null ? ` · tools ${searchResults.tools_items}` : ''}
                  {searchResults.eqlwiki_names != null ? ` · eqlwiki ${searchResults.eqlwiki_names}` : ''}
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
                            {it.catalog_source === 'eqlwiki' && !it.has_stats ? (
                              <span className="badge" style={{ marginLeft: 6 }}>eqlwiki</span>
                            ) : null}
                          </div>
                          <div className="muted" style={{ fontSize: '0.78rem' }}>
                            {it.classes_str || (it.classes || []).join(', ') || (it.catalog_source === 'eqlwiki' ? 'Non-tools / open for wiki details' : '—')}
                            {it.zone ? ` · ${it.zone}` : ''}
                          </div>
                          <div className="stats-line">
                            {fmtStats(it.stats_plus10 || it.stats_plus0, SHOW_UP) || (it.has_stats ? '—' : 'Open for wiki stats / description')}
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
                      {(itemDetail.slots || []).join(', ') || itemDetail.slot || (itemDetail.catalog_source === 'eqlwiki' ? 'Non-equipable / see description' : '—')}
                      {itemDetail.zone ? ` · ${itemDetail.zone}` : ''}
                      {itemDetail.catalog_source ? ` · ${itemDetail.catalog_source}` : ''}
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
                    {itemDetail.description ? (
                      <p style={{ marginTop: '0.65rem', fontSize: '0.85rem', whiteSpace: 'pre-wrap' }}>
                        {itemDetail.description}
                      </p>
                    ) : null}
                    {itemDetail.tooltipLines?.length > 0 && (
                      <pre className="help-md" style={{ marginTop: '0.65rem', fontSize: '0.75rem' }}>
                        {(itemDetail.tooltipLines || []).join('\n')}
                      </pre>
                    )}
                    {!itemDetail.tooltipLines?.length && !itemDetail.description && itemDetail.catalog_source === 'eqlwiki' && (
                      <p className="muted" style={{ marginTop: '0.65rem', fontSize: '0.8rem' }}>
                        No parsed wiki tooltip yet — open the eqlwiki link above for the full page.
                      </p>
                    )}
                    {(itemDetail.quests || []).length > 0 ? (
                      <div style={{ marginTop: '0.85rem' }}>
                        <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '0.35rem' }}>
                          Quests this item is for
                        </div>
                        <ul className="mob-list" style={{ margin: 0, paddingLeft: '1.1rem' }}>
                          {(itemDetail.quests || []).map((q) => {
                            const qn = q?.name || q
                            const label = typeof qn === 'string' ? qn : String(qn || '')
                            if (!label) return null
                            const inHub = Boolean(q?.in_hub)
                            return (
                              <li key={label} style={{ marginBottom: '0.25rem', fontSize: '0.85rem' }}>
                                {inHub ? (
                                  <button
                                    type="button"
                                    className="zone-link"
                                    onClick={() => openQuestHub(label)}
                                    title="Open in Quest Hub"
                                  >
                                    {label}
                                  </button>
                                ) : (
                                  <span>{label}</span>
                                )}
                                {q?.mentioned_as && q.mentioned_as !== label ? (
                                  <span className="muted"> · as {q.mentioned_as}</span>
                                ) : null}
                                {!inHub ? (
                                  <span className="muted"> · not in Quest Hub</span>
                                ) : null}
                              </li>
                            )
                          })}
                        </ul>
                      </div>
                    ) : (
                      <p className="muted" style={{ marginTop: '0.85rem', fontSize: '0.8rem' }}>
                        No linked quests in decoded rewards or eqlwiki Related quests yet.
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'sim' && (
            <div className="sim-grid">
              <div className="panel sim-equip-panel">
                <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Equipment</h2>
                <p className="muted" style={{ marginTop: 0, marginBottom: '0.65rem' }}>
                  Deltas update live as you change Worn / BiS. Apply / Recalculate also refreshes Upgrade Priority.
                </p>
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
                  Live Totals use race + class allotments + EQLT HP/Mana/END formulas. Turn on <strong>Cast Buffs</strong> for the best trio lines castable at your Character Level (not L50-only max spells).
                </p>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem', alignItems: 'center' }}>
                  <button type="button" onClick={clearEquipment}>Clear equipment</button>
                  <button
                    type="button"
                    onClick={resetToImportedWorn}
                    disabled={!importMeta?.equipment || !Object.keys(importMeta.equipment).length}
                    title="Restore worn slots from the last Inventory.txt import"
                  >
                    Reset to imported worn
                  </button>
                  <button type="button" onClick={loadFromBis} disabled={!bis?.slots?.length}>
                    Load from BiS
                  </button>
                  {isDesktopApp && (
                    <>
                      <button
                        type="button"
                        onClick={pickEqInstallFolder}
                        title="Point once at your EverQuest Legends install folder"
                      >
                        {eqInstallFolder ? 'Change EQ folder' : 'Set EQ folder'}
                      </button>
                      <button
                        type="button"
                        className="primary"
                        onClick={() => updateInventoryFromEqFolder({ switchTab: 'sim' })}
                        title="Find the newest *-Inventory.txt in your EQ install folder and import it"
                      >
                        Update from EQ folder
                      </button>
                    </>
                  )}
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
                </div>
                {isDesktopApp && (
                  <p className="muted" style={{ marginTop: '-0.35rem', marginBottom: '0.75rem', fontSize: '0.8rem' }}>
                    {eqInstallFolder
                      ? <>EQ folder: <code>{eqInstallFolder}</code>
                        {eqInventoryInfo?.name ? <> · last dump <code>{eqInventoryInfo.name}</code></> : null}
                        </>
                      : 'Set EQ folder once, then Update pulls the newest *-Inventory.txt after /outputfile inventory.'}
                  </p>
                )}

                {importMeta && (
                  <div className="import-unmatched">
                    <p style={{ marginTop: 0, marginBottom: '0.35rem' }}>
                      Inventory import: <strong>{wornSlotCount}</strong> worn slots filled
                      {importMeta.skipped_count ? ` · ${importMeta.skipped_count} bag/nested lines kept for Search My Bags` : ''}
                    </p>
                    <p className="muted" style={{ marginTop: 0, fontSize: '0.8rem' }}>
                      Bag/bank contents are searchable under <strong>Search My Bags</strong>.
                      Names are matched against eqlegendstools BiS data and eqlwiki item pages;
                      wiki-only matches do not invent stats.
                    </p>
                    {(importMeta.unmatched_count > 0 || unmatchedNames.length > 0) && (
                      <details>
                        <summary className="muted">Debug: {importMeta.unmatched_count ?? unmatchedNames.length} names not in item catalog</summary>
                        <ul className="mob-list">
                          {unmatchedNames.map((n, i) => <li key={`${n}-${i}`}>{n}</li>)}
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
                        <label>{slotLabel(slot)}</label>
                        <div className="equip-slot-cell">
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
                          <SlotUpgradeSelect
                            value={wornUpgrades[slot] ?? upgrade}
                            title={`${slotLabel(slot)} Worn +0…+10`}
                            onChange={(n) => {
                              setWornUpgrades((prev) => ({ ...prev, [slot]: n }))
                            }}
                          />
                        </div>
                        <div className="equip-slot-cell">
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
                          <SlotUpgradeSelect
                            value={bisUpgrades[slot] ?? upgrade}
                            title={`${slotLabel(slot)} BiS +0…+10`}
                            onChange={(n) => {
                              setBisUpgrades((prev) => ({ ...prev, [slot]: n }))
                            }}
                          />
                        </div>
                        <div className="equip-deltas">
                          {deltas.length === 0 ? (
                            <span className="muted">
                              {selectedBis && (equipment[slot] || '') &&
                              String(equipment[slot]).toLowerCase() === String(selectedBis).toLowerCase()
                                ? 'match'
                                : '—'}
                            </span>
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
                  <button className="primary" onClick={runSim} disabled={loading}>
                    {loading ? 'Updating…' : 'Apply / Recalculate'}
                  </button>
                </div>
              </div>

              <div className="panel sim-totals-panel">
                <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Live Totals</h2>
                {sim ? (
                  <>
                    <div style={{ marginBottom: '0.75rem', display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                      <span className="badge">Haste applied: +{sim.haste?.applied_pct || 0}%</span>
                      {(sim.haste?.worn_pct || 0) > 0 && (
                        <span className="badge">Item haste +{sim.haste.worn_pct}%</span>
                      )}
                      {sim.haste?.applied_slot && (
                        <span className="badge">{sim.haste.applied_slot}: {sim.haste.candidates?.find(c => c.slot === sim.haste.applied_slot)?.name}</span>
                      )}
                      {(sim.haste?.candidates?.length || 0) > 1 && (
                        <span className="badge warn">Extra item haste ignored</span>
                      )}
                      <span className="badge">Pools: race+class+STA/INT/WIS (EQLT)</span>
                      {sim.assume_max_aas && <span className="badge">Max AAs</span>}
                      {sim.character_level != null && (
                        <span className="badge">Level {sim.character_level}</span>
                      )}
                      {sim.haste?.buff_pct ? (
                        <span className="badge">Spell haste +{sim.haste.buff_pct}%</span>
                      ) : null}
                      {sim.haste?.capped ? (
                        <span className="badge warn">
                          Cap {sim.haste.cap_pct}% (was {sim.haste.raw_pct}%)
                        </span>
                      ) : sim.haste?.cap_pct ? (
                        <span className="badge">Cap {sim.haste.cap_pct}%</span>
                      ) : null}
                      {sim.cast_buffs?.mode === 'quick' ? (
                        <span className="badge">Quick Buff</span>
                      ) : null}
                    </div>
                    <div className="totals">
                      {['HP','MANA','END','AC','STR','STA','AGI','DEX','WIS','INT','CHA','SVF','SVC','SVM','SVP','SVD','SVV','ATK'].map((k) => (
                        <div className="tot" key={k}>
                          <div className="k">
                            {k === 'MANA' ? 'Mana' : k === 'END' ? 'Endurance' : k === 'HP' ? 'HP' : k}
                          </div>
                          <div className="v">{sim.totals?.[k] ?? 0}</div>
                        </div>
                      ))}
                      <div className="tot">
                        <div className="k">Haste</div>
                        <div className="v">{sim.haste?.applied_pct || 0}%</div>
                      </div>
                    </div>
                    {sim.cast_buffs?.mode && sim.cast_buffs.mode !== 'off' ? (
                      <CastBuffsIconStrip
                        castBuffs={sim.cast_buffs}
                        onShowTip={showHoverTip}
                        onMoveTip={moveHoverTip}
                        onHideTip={hideHoverTip}
                      />
                    ) : null}
                    {sim.weapons?.length > 0 && (
                      <div style={{ marginTop: '1rem' }}>
                        <h3 style={{ fontSize: '0.95rem' }}>Weapon ratios (per-slot +N)</h3>
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
                          <ItemIcon name={s.suggested} />
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
                            <div style={{ marginTop: '0.45rem' }}>
                              <button
                                type="button"
                                className="primary"
                                onClick={() => openQuestHub(s.suggested_quest_name || obtain.quest_name)}
                              >
                                Open in Quest Hub
                              </button>
                            </div>
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

          <footer className="muted" style={{ marginTop: '1.5rem', fontSize: '0.78rem', lineHeight: 1.45 }}>
            Stats from decoded catalog / eqlwiki only — never invented.
            Use the <strong>?</strong> help and <strong>cog</strong> settings in the header anytime.
          </footer>
        </div>
      </div>

      {settingsOpen && (
        <div className="modal-backdrop" onClick={() => setSettingsOpen(false)} role="presentation">
          <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Settings">
            <h2>Settings</h2>
            <p className="muted" style={{ marginTop: 0 }}>
              Options save on this device. Themes apply immediately.
            </p>
            <div className="settings-grid">
              <div className="settings-row">
                <div>
                  <label>Color theme</label>
                  <span className="muted">Pick a look that stays readable without clutter.</span>
                </div>
                <div className="theme-picks">
                  {THEME_OPTIONS.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      className={`theme-pick${uiSettings.theme === t.id ? ' on' : ''}`}
                      onClick={() => patchUiSettings({ theme: t.id })}
                    >
                      <strong>{t.label}</strong>
                      <span>{t.blurb}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="settings-row">
                <div>
                  <label htmlFor="set-funny-tips">Funny loading tips</label>
                  <span className="muted">EQ-style quips under the load bar.</span>
                </div>
                <label className="check" style={{ marginTop: 0 }}>
                  <input
                    id="set-funny-tips"
                    type="checkbox"
                    checked={uiSettings.funnyLoadingTips !== false}
                    onChange={(e) => patchUiSettings({ funnyLoadingTips: e.target.checked })}
                  />
                  Enabled
                </label>
              </div>
              <div className="settings-row">
                <div>
                  <label htmlFor="set-compact-badges">Compact status badges</label>
                  <span className="muted">Tighter badge row under BiS / Simulator controls.</span>
                </div>
                <label className="check" style={{ marginTop: 0 }}>
                  <input
                    id="set-compact-badges"
                    type="checkbox"
                    checked={uiSettings.compactBadges !== false}
                    onChange={(e) => patchUiSettings({ compactBadges: e.target.checked })}
                  />
                  Enabled
                </label>
              </div>
              <div className="settings-row">
                <div>
                  <label htmlFor="set-reduce-motion">Reduce motion</label>
                  <span className="muted">Steady progress bar instead of a sliding animation.</span>
                </div>
                <label className="check" style={{ marginTop: 0 }}>
                  <input
                    id="set-reduce-motion"
                    type="checkbox"
                    checked={!!uiSettings.reduceMotion}
                    onChange={(e) => patchUiSettings({ reduceMotion: e.target.checked })}
                  />
                  Enabled
                </label>
              </div>
            </div>
            <div className="modal-actions">
              <button type="button" onClick={() => setSettingsOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {appHelpOpen && (
        <div className="modal-backdrop" onClick={() => setAppHelpOpen(false)} role="presentation">
          <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Help">
            <h2>{APP_HELP.title}</h2>
            <p className="muted" style={{ marginTop: 0 }}>{APP_HELP.intro}</p>
            <div className="help-sections">
              {APP_HELP.sections.map((sec) => (
                <section key={sec.id} className="help-section">
                  <h3>{sec.title}</h3>
                  <ul>
                    {sec.body.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
            <div className="modal-actions">
              <button type="button" className="primary" onClick={() => setAppHelpOpen(false)}>Got it</button>
            </div>
          </div>
        </div>
      )}

      <ZoneModal detail={zoneDetail} onClose={() => setZoneDetail(null)} />
      <HelpModal markdown={helpMd} onClose={() => setHelpMd(null)} />
      {hoverTip ? (
        <div
          className="hover-tip"
          style={{ left: hoverTip.x, top: hoverTip.y }}
          role="tooltip"
        >
          {hoverTip.kind === 'buff' ? (
            <img
              className="item-icon buff-icon"
              src={hoverTip.image || spellIconUrl(hoverTip.icon)}
              alt=""
              width={40}
              height={40}
              onError={(e) => { e.currentTarget.style.display = 'none' }}
            />
          ) : (
            <ItemIcon name={hoverTip.name} />
          )}
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
