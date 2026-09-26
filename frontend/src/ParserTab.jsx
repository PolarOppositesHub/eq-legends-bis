import { useEffect, useMemo, useRef, useState } from 'react'
import {
  getParserConfig,
  getParserFight,
  getParserFights,
  getParserLoot,
  getParserLogs,
  getParserRoster,
  getParserTimeline,
  openParserStream,
  postParserCandidate,
  postParserClearHistory,
  postParserConfig,
  postParserGroup,
  postParserLive,
  postParserLoad,
  postParserPet,
} from './parserApi.js'
import {
  AbilityList,
  DeathsPanel,
  FightTimeline,
  HealingPanel,
  LootPanel,
  MultiAttackTable,
  ProcsTable,
  ResistsPanel,
  SpellPage,
  TankingPanel,
} from './parserDepth.jsx'
import {
  FIGHT_PAGE_SIZE,
  LOOT_PAGE_SIZE,
  MERGE_LIMIT,
  PARSER_DETAIL_TABS,
  capIds,
  copyText,
  downloadText,
  filterFights,
  formatParseCsv,
  formatParseHtml,
  formatParseText,
  formatParseTsv,
  lootInWindow,
  markStorageKey,
  mergeFightDetails,
  pageSlice,
  scopeNames,
  sliceFromMark,
  stitchTimelines,
  upsertFights,
  zoneSession,
} from './parserDepth.js'
import {
  UPGRADE_STALLED_NOTE,
  isRebuildBusy,
  LEVEL_LOADOUT_NOTE,
  PARSER_EMPTY,
  PET_LEADER_HINT,
  RAID_SCOPE_NOTE,
  SOURCE_SCOPES,
  formatDamage,
  formatDuration,
  formatFightTime,
  formatRate,
  formatTargets,
  formatZone,
  loadoutText,
  loadoutsFor,
  logOptionLabel,
  petEvidenceLabel,
  sourceKindLabel,
  sourcesForScope,
  visibleDamage,
  visibleRate,
} from './parserView.js'

function HistoryControls({
  retentionDays,
  character,
  onRetentionDays,
  onClearHistory,
  historyBusy,
  upgrading,
}) {
  const [draft, setDraft] = useState(String(retentionDays ?? 0))
  useEffect(() => {
    setDraft(String(retentionDays ?? 0))
  }, [retentionDays])
  const save = () => {
    const parsed = Number(draft)
    if (!Number.isFinite(parsed) || parsed < 0) return
    if (typeof onRetentionDays === 'function') onRetentionDays(Math.floor(parsed))
  }
  return (
    <div className="parser-history" data-testid="parser-history">
      <label htmlFor="parser-retention">
        Keep fights (days)
        <input
          id="parser-retention"
          data-testid="parser-retention"
          type="number"
          min="0"
          step="1"
          value={draft}
          disabled={historyBusy || upgrading}
          onChange={(e) => setDraft(e.target.value)}
        />
      </label>
      <span className="muted">0 keeps every saved fight. Clearing fights keeps pet assignments, dismissals, and the group allowlist.</span>
      <button
        type="button"
        data-testid="parser-retention-save"
        disabled={historyBusy || upgrading}
        onClick={save}
      >
        Save
      </button>
      <button
        type="button"
        data-testid="parser-clear-history"
        disabled={!character || historyBusy || upgrading}
        onClick={onClearHistory}
      >
        Clear this character
      </button>
    </div>
  )
}

function progressFromUpgrade(data) {
  const size = Number(data?.size) || 0
  const offset = Number(data?.offset) || 0
  const lines = Number(data?.lines) || 0
  let pct = null
  if (size > 0) pct = Math.max(0, Math.min(100, Math.round((offset / size) * 100)))
  return {
    active: !data?.done,
    done: !!data?.done,
    pct: data?.done ? 100 : pct,
    lines,
  }
}

export const emptyRoster = { group: [], allowlist: [], candidates: [], loadouts: [], pets: [] }

const FIGHT_FETCH = 2000

async function fetchFightHistory(character) {
  const all = []
  let offset = 0
  while (offset < 20000) {
    const body = await getParserFights(character, { limit: FIGHT_FETCH, offset })
    const rows = Array.isArray(body?.fights) ? body.fights : []
    all.push(...rows)
    if (rows.length < FIGHT_FETCH) return { fights: all, truncated: false }
    offset += rows.length
  }
  return { fights: all, truncated: true }
}

async function loadMergedDetails(ids, mergePets) {
  const parts = []
  for (let i = 0; i < ids.length; i += 4) {
    const chunk = ids.slice(i, i + 4)
    const loaded = await Promise.all(chunk.map((id) => getParserFight(id, mergePets)))
    parts.push(...loaded)
  }
  return mergeFightDetails(parts)
}

async function loadCurve(current, ability) {
  if (!current?.id) return null
  const ids = Array.isArray(current.merged_ids) && current.merged_ids.length > 1
    ? current.merged_ids.slice(0, 8)
    : [current.id]
  const parts = []
  for (let i = 0; i < ids.length; i += 4) {
    const chunk = await Promise.all(ids.slice(i, i + 4).map((id) => getParserTimeline(id, ability)))
    parts.push(...chunk)
  }
  if (parts.length === 1) return parts[0]
  const curve = stitchTimelines(parts)
  curve.available = parts.some((part) => part?.available)
  const missing = parts.find((part) => part && part.available === false && part.reason)
  if (missing) curve.reason = missing.reason
  return curve
}

function ownerOptions(character, members, allowNames) {
  const names = []
  const seen = new Set()
  const push = (name) => {
    const text = typeof name === 'string' ? name.trim() : ''
    if (!text) return
    const key = text.toLowerCase()
    if (seen.has(key)) return
    seen.add(key)
    names.push(text)
  }
  push(character)
  for (const row of members) push(row?.name || row)
  for (const name of allowNames) push(name)
  return names
}

function FragmentRow({
  row,
  open,
  abilities,
  binding,
  evidence,
  classesFor,
  character,
  ownerChoices,
  assignPet,
  assignOwner,
  setAssignPet,
  setAssignOwner,
  onSetPet,
  onUnassignPet,
  onToggle,
  onOpenSpell,
}) {
  const swings = (Number(row.hits) || 0)
  const critPct = swings ? ((Number(row.crits) || 0) / swings) * 100 : 0
  return (
    <>
      <tr
        className={row.nested ? 'parser-pet-row' : undefined}
        data-source={row.source}
        data-nested={row.nested ? '1' : '0'}
        title={evidence || undefined}
        onContextMenu={(e) => {
          e.preventDefault()
          setAssignPet(row.source)
          setAssignOwner(binding?.owner || character || '')
        }}
      >
        <td>
          {abilities.length ? (
            <button
              type="button"
              data-testid="parser-expand"
              data-source={row.source}
              aria-expanded={open}
              onClick={(e) => {
                e.stopPropagation()
                onToggle()
              }}
            >
              {open ? 'Hide' : 'Attacks'}
            </button>
          ) : null}
          {' '}
          {row.nested ? `↳ ${row.source}` : row.source}
          {classesFor ? <span className="parser-classes">{classesFor}</span> : null}
        </td>
        <td>{sourceKindLabel(row.kind)}{binding?.owner ? ` of ${binding.owner}` : ''}</td>
        <td>{formatDamage(row.damage)}</td>
        <td>{formatRate(row.dps)}</td>
        <td>{formatRate(row.sdps)}</td>
        <td>{formatDamage(row.hits)}</td>
        <td>{formatRate(critPct)}%</td>
        <td>{formatDamage(row.max_hit)}</td>
        <td className="parser-actions">
          <button
            type="button"
            data-testid="parser-set-pet"
            data-pet={row.source}
            onClick={() => {
              setAssignPet(row.source)
              setAssignOwner(binding?.owner || character || '')
            }}
          >
            Set as pet of…
          </button>
          <button
            type="button"
            data-testid="parser-unassign"
            data-pet={row.source}
            onClick={() => onUnassignPet && onUnassignPet(row.source)}
          >
            Unassign
          </button>
          {assignPet === row.source ? (
            <form
              className="parser-assign"
              data-testid="parser-assign"
              onSubmit={(e) => {
                e.preventDefault()
                if (assignOwner && onSetPet) onSetPet(row.source, assignOwner)
                setAssignPet('')
              }}
            >
              <label>
                Owner
                <select
                  value={assignOwner}
                  onChange={(e) => setAssignOwner(e.target.value)}
                  data-testid="parser-assign-owner"
                >
                  <option value="">Choose</option>
                  {ownerChoices.map((name) => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
              </label>
              <button type="submit">Save</button>
            </form>
          ) : null}
        </td>
      </tr>
      {open ? (
        <tr className="parser-ability-row" data-testid="parser-ability-row">
          <td colSpan={9}>
            <AbilityList abilities={abilities} onOpenSpell={onOpenSpell} />
          </td>
        </tr>
      ) : null}
    </>
  )
}

export function ParserPanel({
  folder,
  logs,
  logsStatus,
  logsError,
  selectedPath,
  onSelectLog,
  live,
  liveBusy,
  onToggleLive,
  loadingLog,
  progress,
  fights,
  selectedFightId,
  onSelectFight,
  detail,
  detailStatus,
  mergePets,
  onMergePetsChange,
  scope = 'group',
  onScopeChange,
  candidates = [],
  onConfirmPet,
  onDismissPet,
  onSetPet,
  onUnassignPet,
  groupMembers = [],
  allowlist = [],
  loadouts = [],
  petBindings = [],
  character = '',
  onAddAllow,
  onRemoveAllow,
  onLoadLog,
  onRefresh,
  onSetEqFolder,
  canSetFolder,
  onOpenCredits,
  notice,
  upgrading,
  upgradeStalled = false,
  retentionDays,
  onRetentionDays,
  onClearHistory,
  historyBusy,
  timeline = null,
  timelineStatus = 'idle',
  loot = null,
  lootStatus = 'idle',
  onDetailTab,
  onMergeFights,
  mergeBusy = false,
  mergeNote = '',
  onRequestSpell,
  spellTimeline = null,
  fightsTruncated = false,
  itemNameProps = null,
}) {
  const [assignPet, setAssignPet] = useState('')
  const [assignOwner, setAssignOwner] = useState('')
  const [allowName, setAllowName] = useState('')
  const list = Array.isArray(logs) ? logs : []
  const fightRows = Array.isArray(fights) ? fights : []
  const allowNames = Array.isArray(allowlist) ? allowlist : []
  const sources = sourcesForScope(detail, scope, allowNames)
  const prompts = Array.isArray(candidates) ? candidates : []
  const members = Array.isArray(groupMembers) ? groupMembers : []
  const classes = Array.isArray(loadouts) ? loadouts : []
  const ownerChoices = ownerOptions(character, members, allowNames)
  const empty = logsStatus === 'ready' && list.length === 0
  const selected = list.find((log) => log.path === selectedPath) || null
  const pct = progress && progress.pct != null ? progress.pct : null
  const [detailTab, setDetailTab] = useState('damage')
  const [fightQuery, setFightQuery] = useState('')
  const [fightPage, setFightPage] = useState(1)
  const [openSources, setOpenSources] = useState({})
  const [spell, setSpell] = useState(null)
  const [checked, setChecked] = useState({})
  const [copyPreview, setCopyPreview] = useState('')
  const [sliceOn, setSliceOn] = useState(false)
  const [sessionMark, setSessionMark] = useState(null)
  const [lootFightOnly, setLootFightOnly] = useState(true)
  const [lootPage, setLootPage] = useState(1)
  const detailKey = detail?.merged_ids ? detail.merged_ids.join(',') : detail?.id
  useEffect(() => {
    setOpenSources({})
    setSpell(null)
    setCopyPreview('')
  }, [detailKey])
  useEffect(() => {
    if (!character || typeof localStorage === 'undefined') return undefined
    try {
      const raw = localStorage.getItem(markStorageKey(character))
      setSessionMark(raw ? JSON.parse(raw) : null)
    } catch {
      setSessionMark(null)
    }
    return undefined
  }, [character])
  const markedRows = sliceOn && sessionMark?.ts ? sliceFromMark(fightRows, sessionMark.ts) : fightRows
  const filteredFights = filterFights(markedRows, fightQuery)
  const fightPageView = pageSlice(filteredFights, fightPage, FIGHT_PAGE_SIZE)
  const checkedIds = fightRows.filter((fight) => checked[fight.id]).map((fight) => fight.id)
  const scoped = scopeNames(sources)
  const rememberMark = (mark) => {
    setSessionMark(mark)
    try {
      if (character && typeof localStorage !== 'undefined') {
        if (mark) localStorage.setItem(markStorageKey(character), JSON.stringify(mark))
        else localStorage.removeItem(markStorageKey(character))
      }
    } catch {
      /* the mark still applies for this view */
    }
  }
  const selectTab = (id) => {
    setDetailTab(id)
    if (onDetailTab) onDetailTab(id)
  }
  const openSpell = (row) => {
    setSpell(row)
    if (onRequestSpell) onRequestSpell(row)
  }
  const writeCopy = async (kind) => {
    if (!detail) return
    const text = kind === 'tsv'
      ? formatParseTsv(detail, sources)
      : (kind === 'csv'
        ? formatParseCsv(detail, sources)
        : (kind === 'html' ? formatParseHtml(detail, sources) : formatParseText(detail, sources)))
    if (kind === 'csv') downloadText('parse.csv', text, 'text/csv;charset=utf-8')
    else if (kind === 'html') downloadText('parse.html', text, 'text/html;charset=utf-8')
    else {
      setCopyPreview(text)
      try {
        await copyText(text)
      } catch {
        /* the preview is the same text that would have been copied */
      }
    }
  }
  const lootRows = lootFightOnly && detail?.start_ts
    ? lootInWindow(loot?.loot, detail.start_ts, detail.end_ts)
    : (loot?.loot || [])
  const lootGives = lootFightOnly && detail?.start_ts
    ? lootInWindow(loot?.gives, detail.start_ts, detail.end_ts)
    : (loot?.gives || [])
  const lootMerges = lootFightOnly && detail?.start_ts
    ? lootInWindow(loot?.merges, detail.start_ts, detail.end_ts)
    : (loot?.merges || [])
  const lootView = pageSlice(lootRows, lootPage, LOOT_PAGE_SIZE)

  return (
    <div className="panel parser-panel" data-testid="parser-tab">
      <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Parser</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Reads <code>Logs\eqlog_name_server.txt</code> from the EQ install folder.
        Damage, DPS, and SDPS come from that file.
      </p>

      <div className="parser-toolbar">
        <div className="field" style={{ minWidth: 280, flex: '1 1 280px' }}>
          <label htmlFor="parser-log">Character log</label>
          <select
            id="parser-log"
            value={selected ? selected.path : ''}
            onChange={(e) => onSelectLog(e.target.value)}
            disabled={!list.length}
          >
            {!list.length ? <option value="">No logs found</option> : null}
            {list.map((log) => (
              <option key={log.path} value={log.path}>{logOptionLabel(log)}</option>
            ))}
          </select>
        </div>
        <button
          type="button"
          className={live ? 'parser-live on' : 'parser-live'}
          aria-pressed={!!live}
          disabled={!selected || liveBusy || loadingLog || upgrading}
          onClick={onToggleLive}
        >
          {live ? 'Live on' : 'Live'}
        </button>
        <button
          type="button"
          className="primary"
          disabled={!selected || loadingLog || upgrading}
          onClick={onLoadLog}
        >
          {loadingLog ? 'Loading log…' : 'Load old log'}
        </button>
        <button type="button" onClick={onRefresh} disabled={logsStatus === 'loading'}>
          Refresh
        </button>
        {canSetFolder ? (
          <button type="button" onClick={onSetEqFolder}>
            {folder ? 'Change EQ folder' : 'Set EQ folder'}
          </button>
        ) : null}
      </div>

      <HistoryControls
        retentionDays={retentionDays}
        character={character || ''}
        onRetentionDays={onRetentionDays}
        onClearHistory={onClearHistory}
        historyBusy={!!historyBusy}
        upgrading={!!upgrading}
      />

      {folder ? (
        <p className="note" data-testid="parser-folder">
          EQ install folder: <code>{folder}</code>
        </p>
      ) : (
        <p className="note">EQ install folder is not set.</p>
      )}

      {logsStatus === 'loading' ? <p className="muted">Looking for logs…</p> : null}
      {logsError ? <p className="warn-box" role="alert">{logsError}</p> : null}
      {notice ? <p className="warn-box" role="alert">{notice}</p> : null}

      {upgrading ? (
        <p className="note" data-testid="parser-upgrade" role="status">Updating parser data…</p>
      ) : null}
      {upgrading && upgradeStalled ? (
        <p className="warn-box" data-testid="parser-upgrade-stalled" role="alert">{UPGRADE_STALLED_NOTE}</p>
      ) : null}

      {progress && (progress.active || progress.done) ? (
        <div data-testid="parser-progress-wrap">
          <div className="load-bar-track">
            <div
              className={progress.active && pct == null ? 'load-bar-fill indeterminate' : 'load-bar-fill'}
              style={pct == null ? undefined : { width: `${pct}%` }}
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct == null ? undefined : pct}
              aria-label="Log load progress"
              data-testid="parser-progress"
            />
          </div>
          <p className="muted" data-testid="parser-progress-label">
            {progress.done && !progress.active
              ? `Loaded ${formatDamage(progress.lines)} lines.`
              : (progress.lines
                ? `${formatDamage(progress.lines)} lines${pct != null ? ` · ${pct}%` : ''}`
                : 'Reading log…')}
          </p>
        </div>
      ) : null}

      {empty ? (
        <div className="parser-empty" data-testid="parser-empty">
          <h3>{PARSER_EMPTY.title}</h3>
          <ul className="parser-notes">
            <li>{PARSER_EMPTY.logOn}</li>
            <li>{PARSER_EMPTY.folder}</li>
            <li>{PARSER_EMPTY.filters}</li>
          </ul>
          {canSetFolder ? (
            <button type="button" className="primary" onClick={onSetEqFolder}>Set EQ folder</button>
          ) : (
            <p className="muted">Set the EQ install folder in the desktop app, then press Refresh.</p>
          )}
        </div>
      ) : null}

      {!empty && logsStatus === 'ready' ? (
        <section className="parser-roster" data-testid="parser-group">
          <h3 className="parser-subhead">Group</h3>
          <p className="note">
            From the log: {members.length ? members.map((row) => row.name || row).join(', ') : 'none yet'}
          </p>
          <form
            className="parser-allow"
            onSubmit={(e) => {
              e.preventDefault()
              const name = allowName.trim()
              if (!name || !onAddAllow) return
              onAddAllow(name)
              setAllowName('')
            }}
          >
            <label htmlFor="parser-allow-input">Allowlist</label>
            <input
              id="parser-allow-input"
              data-testid="parser-allow-input"
              value={allowName}
              onChange={(e) => setAllowName(e.target.value)}
              placeholder="Character name"
            />
            <button type="submit">Add</button>
          </form>
          {allowNames.length ? (
            <ul className="parser-allow-list" data-testid="parser-allow-list">
              {allowNames.map((name) => (
                <li key={name}>
                  {name}
                  <button type="button" data-testid="parser-allow-remove" data-member={name} onClick={() => onRemoveAllow && onRemoveAllow(name)}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Allowlist is empty. Names here stay in the group across restarts.</p>
          )}
          <h3 className="parser-subhead">Classes from /who</h3>
          {classes.length ? (
            <ul className="parser-loadouts" data-testid="parser-loadouts">
              {classes.map((row) => (
                <li key={`${row.name}:${row.classes}`}>
                  {row.name} · {row.classes} · {row.level}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No /who lines yet. A line looks like [36 PAL/DRU/WIZ] Zasariz.</p>
          )}
          <p className="note">{PET_LEADER_HINT}</p>
        </section>
      ) : null}

      {!empty && logsStatus === 'ready' ? (
        <div className="parser-split">
          <div>
            <div className="parser-detail-head">
              <h3 className="parser-subhead">Saved fights</h3>
              <span className="muted" data-testid="parser-history-count">{fightRows.length} saved</span>
            </div>
            {fightRows.length ? (
              <div className="parser-toolbar">
                <input
                  type="search"
                  data-testid="parser-fight-search"
                  placeholder="Zone or target"
                  value={fightQuery}
                  aria-label="Filter saved fights"
                  onChange={(e) => {
                    setFightQuery(e.target.value)
                    setFightPage(1)
                  }}
                />
                <button
                  type="button"
                  data-testid="parser-merge-fights"
                  disabled={checkedIds.length < 2 || mergeBusy}
                  onClick={() => onMergeFights && onMergeFights(checkedIds)}
                >
                  Merge selected
                </button>
                <button
                  type="button"
                  data-testid="parser-zone-session"
                  disabled={!selectedFightId || mergeBusy}
                  onClick={() => {
                    const ids = zoneSession(fightRows, selectedFightId).map((fight) => fight.id)
                    if (onMergeFights) onMergeFights(capIds(ids))
                  }}
                >
                  Zone session
                </button>
                <button
                  type="button"
                  data-testid="parser-set-mark"
                  disabled={!selectedFightId}
                  onClick={() => {
                    const fight = fightRows.find((row) => row.id === selectedFightId)
                    if (!fight?.start_ts) return
                    rememberMark({ fightId: fight.id, ts: fight.start_ts })
                    setSliceOn(true)
                    setFightPage(1)
                  }}
                >
                  Set session mark
                </button>
                {sessionMark ? (
                  <button
                    type="button"
                    data-testid="parser-clear-mark"
                    onClick={() => {
                      rememberMark(null)
                      setSliceOn(false)
                    }}
                  >
                    Clear mark
                  </button>
                ) : null}
              </div>
            ) : null}
            {sessionMark ? (
              <p className="note" data-testid="parser-session-mark">
                Session mark at {formatFightTime(sessionMark.ts)}. Fights from the mark can be merged.
                {' '}
                <label className="check">
                  <input
                    type="checkbox"
                    checked={sliceOn}
                    onChange={(e) => {
                      setSliceOn(e.target.checked)
                      setFightPage(1)
                    }}
                  />
                  Show fights from the mark
                </label>
                {' '}
                <button
                  type="button"
                  data-testid="parser-merge-slice"
                  disabled={mergeBusy}
                  onClick={() => {
                    const ids = sliceFromMark(fightRows, sessionMark.ts).map((fight) => fight.id)
                    if (onMergeFights) onMergeFights(capIds(ids))
                  }}
                >
                  Merge from mark
                </button>
              </p>
            ) : null}
            {mergeNote ? <p className="note" data-testid="parser-merge-note">{mergeNote}</p> : null}
            {selected && !fightRows.length ? (
              <p className="muted" data-testid="parser-no-fights">
                No fights in this log yet. Load old log to replay the file, or turn Live on and fight something.
              </p>
            ) : null}
            {fightRows.length ? (
              <div className="parser-table-wrap">
                <table className="parser-table" data-testid="parser-fights">
                  <thead>
                    <tr>
                      <th>Pick</th>
                      <th>Time</th>
                      <th>Zone</th>
                      <th>Targets</th>
                      <th>Duration</th>
                      <th>Total damage</th>
                      <th>Your DPS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fightPageView.rows.map((fight) => (
                      <tr
                        key={fight.id}
                        data-fight-id={fight.id}
                        aria-selected={fight.id === selectedFightId}
                        tabIndex={0}
                        onClick={() => onSelectFight(fight.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            onSelectFight(fight.id)
                          }
                        }}
                      >
                        <td>
                          <input
                            type="checkbox"
                            data-testid="parser-fight-check"
                            checked={!!checked[fight.id]}
                            aria-label={`Select fight ${fight.id}`}
                            onClick={(e) => e.stopPropagation()}
                            onChange={() => setChecked((prev) => ({ ...prev, [fight.id]: !prev[fight.id] }))}
                          />
                        </td>
                        <td>
                          {formatFightTime(fight.start_ts)}
                          {fight.open ? <span className="parser-chip">open</span> : null}
                          {sessionMark?.fightId === fight.id ? <span className="parser-chip">mark</span> : null}
                        </td>
                        <td>{formatZone(fight)}</td>
                        <td>
                          {formatTargets(fight.targets)}
                          {fight.player_died ? <span className="parser-chip">died</span> : null}
                        </td>
                        <td>{formatDuration(fight.duration_seconds)}</td>
                        <td>{formatDamage(fight.damage)}</td>
                        <td>{formatRate(fight.your_dps)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {fightRows.length ? (
              <p className="note" data-testid="parser-fight-page">
                {fightPageView.start}–{fightPageView.end} of {fightPageView.total}
                {' '}
                <button type="button" disabled={fightPageView.page <= 1} onClick={() => setFightPage(fightPageView.page - 1)}>Previous</button>
                {' '}
                <button type="button" disabled={fightPageView.page >= fightPageView.pages} onClick={() => setFightPage(fightPageView.page + 1)}>Next</button>
              </p>
            ) : null}
            {fightsTruncated ? (
              <p className="note">Showing the newest saved fights. Older fights are still in the history store.</p>
            ) : null}
          </div>

          <div>
            <div className="parser-detail-head">
              <h3 className="parser-subhead">DPS</h3>
              <div className="parser-scope" data-testid="parser-scope" role="group" aria-label="Source scope">
                {SOURCE_SCOPES.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={scope === item.id ? 'on' : undefined}
                    aria-pressed={scope === item.id}
                    data-testid={`parser-scope-${item.id}`}
                    onClick={() => onScopeChange && onScopeChange(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <label className="check parser-merge" data-testid="parser-merge-pets">
                <input
                  type="checkbox"
                  checked={!!mergePets}
                  onChange={(e) => onMergePetsChange(!!e.target.checked)}
                />
                Merge pets
              </label>
            </div>
            {scope === 'raid' ? (
              <p className="note" data-testid="parser-raid-note">{RAID_SCOPE_NOTE}</p>
            ) : null}
            {prompts.length ? (
              <div className="parser-prompts" data-testid="parser-pet-prompts">
                {prompts.map((row) => (
                  <div key={row.pet} className="parser-prompt" data-testid="parser-pet-prompt" data-pet={row.pet}>
                    <p>{row.pet} — your pet?</p>
                    <button type="button" onClick={() => onConfirmPet && onConfirmPet(row.pet)}>Yes</button>
                    <button type="button" onClick={() => onDismissPet && onDismissPet(row.pet)}>Dismiss</button>
                  </div>
                ))}
                <p className="note">{PET_LEADER_HINT} An unconfirmed name is never merged into you.</p>
              </div>
            ) : null}
            <p className="note">
              {mergePets
                ? 'Merge pets adds each pet’s damage to its owner. The pet stays listed under that owner.'
                : 'Pets stay on their own rows.'}
              {' '}DPS uses that source’s active time. SDPS uses the whole fight.
            </p>
            {!selectedFightId && !detail ? (
              <p className="muted">Select a fight to see you, your pet, and your group.</p>
            ) : null}
            {selectedFightId && detailStatus === 'loading' ? <p className="muted">Loading fight…</p> : null}
            {selectedFightId && detailStatus === 'missing' ? (
              <p className="muted">That fight is not in the saved history.</p>
            ) : null}
            {detail ? (
              <div className="parser-actions" data-testid="parser-export">
                <button type="button" data-testid="parser-copy-text" onClick={() => writeCopy('text')}>Copy text</button>
                <button type="button" data-testid="parser-copy-tsv" onClick={() => writeCopy('tsv')}>Copy TSV</button>
                <button type="button" data-testid="parser-export-csv" onClick={() => writeCopy('csv')}>Export CSV</button>
                <button type="button" data-testid="parser-export-html" onClick={() => writeCopy('html')}>Export HTML</button>
                <span className="muted">Copy puts text on the clipboard. Paste it into EQ yourself.</span>
              </div>
            ) : null}
            {copyPreview ? (
              <pre className="parser-copy-out" data-testid="parser-copy-output">{copyPreview}</pre>
            ) : null}
            {detail && detail.merged_count > 1 ? (
              <p className="note" data-testid="parser-merged-banner">
                Merged {detail.merged_count} fights. Duration is the sum of each fight. Gaps between fights are left out.
              </p>
            ) : null}
            {detail ? (
              <div className="parser-tabs" data-testid="parser-detail-tabs" role="tablist">
                {PARSER_DETAIL_TABS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    role="tab"
                    className={detailTab === item.id ? 'on' : undefined}
                    aria-selected={detailTab === item.id}
                    data-testid={`parser-tab-${item.id}`}
                    onClick={() => selectTab(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            ) : null}
            {spell ? <SpellPage row={spell} timeline={spellTimeline} onClose={() => setSpell(null)} /> : null}
            {detail && detailTab === 'damage' && sources.length ? (
              <>
                <p className="parser-totals" data-testid="parser-totals">
                  Total damage {formatDamage(visibleDamage(sources))}
                  {' · '}
                  {formatRate(visibleRate(sources, detail.duration_seconds))} DPS
                  {' · '}
                  {formatDuration(detail.duration_seconds)}
                </p>
                <div className="parser-table-wrap">
                  <table className="parser-table" data-testid="parser-sources">
                    <thead>
                      <tr>
                        <th>Source</th>
                        <th>Who</th>
                        <th>Damage</th>
                        <th>DPS</th>
                        <th>SDPS</th>
                        <th>Hits</th>
                        <th>Crit %</th>
                        <th>Max</th>
                        <th>Pet</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sources.map((row) => {
                        const binding = (Array.isArray(petBindings) ? petBindings : []).find((pet) => pet.pet === row.source)
                        const evidence = petEvidenceLabel(binding?.evidence)
                        const classesFor = loadoutText(loadoutsFor(row.source, classes))
                        const open = !!openSources[row.source]
                        const abilities = Array.isArray(row.abilities) ? row.abilities : []
                        return (
                        <FragmentRow
                          key={`${row.nested ? 'pet' : 'src'}:${row.source}`}
                          row={row}
                          open={open}
                          abilities={abilities}
                          binding={binding}
                          evidence={evidence}
                          classesFor={classesFor}
                          character={character}
                          ownerChoices={ownerChoices}
                          assignPet={assignPet}
                          assignOwner={assignOwner}
                          setAssignPet={setAssignPet}
                          setAssignOwner={setAssignOwner}
                          onSetPet={onSetPet}
                          onUnassignPet={onUnassignPet}
                          onToggle={() => setOpenSources((prev) => ({ ...prev, [row.source]: !prev[row.source] }))}
                          onOpenSpell={openSpell}
                        />
                        )
                      })}
                    </tbody>
                  </table>
                </div>
                <MultiAttackTable multi={detail.multi_attack} names={scoped} />
                <ProcsTable procs={detail.procs} names={scoped} itemNameProps={itemNameProps} />
              </>
            ) : null}
            {detail && detailTab === 'damage' && !sources.length && detailStatus === 'ready' ? (
              <p className="muted">No damage from you, your pet, or your group in this fight.</p>
            ) : null}
            {detail && detailTab === 'healing' ? (
              <HealingPanel healing={detail.healing} names={scoped} onOpenSpell={openSpell} />
            ) : null}
            {detail && detailTab === 'tanking' ? (
              <TankingPanel tanking={detail.tanking} names={scoped} />
            ) : null}
            {detail && detailTab === 'deaths' ? (
              <DeathsPanel deaths={detail.deaths} names={scoped} />
            ) : null}
            {detail && detailTab === 'resists' ? (
              <ResistsPanel resists={detail.resists} names={scoped} />
            ) : null}
            {detail && detailTab === 'timeline' ? (
              <FightTimeline timeline={timeline} scope={scope} status={timelineStatus} />
            ) : null}
            {detail && detailTab === 'loot' ? (
              <LootPanel
                loot={{
                  rows: lootView.rows,
                  gives: lootGives.slice(0, LOOT_PAGE_SIZE),
                  merges: lootMerges.slice(0, LOOT_PAGE_SIZE),
                }}
                status={lootStatus}
                page={lootView.page}
                pages={lootView.pages}
                onPage={setLootPage}
                fightOnly={lootFightOnly}
                onFightOnly={(next) => {
                  setLootFightOnly(next)
                  setLootPage(1)
                }}
                itemNameProps={itemNameProps}
              />
            ) : null}
          </div>
        </div>
      ) : null}

      <p className="note" data-testid="parser-level-note">{LEVEL_LOADOUT_NOTE}</p>
      <p className="note">
        <button type="button" className="zone-link" onClick={onOpenCredits}>Credits</button>
        {' '}for eqlwiki (CC BY-SA) and eqlegendstools.com.
      </p>
    </div>
  )
}

export default function ParserTab({
  logPath,
  onLogPath,
  mergePets,
  onMergePets,
  fightId,
  onFightId,
  eqInstallFolder,
  onSetEqFolder,
  canSetFolder,
  onOpenCredits,
  itemNameProps,
}) {
  const [folder, setFolder] = useState('')
  const [logs, setLogs] = useState([])
  const [logsStatus, setLogsStatus] = useState('loading')
  const [logsError, setLogsError] = useState('')
  const [live, setLive] = useState(false)
  const [liveBusy, setLiveBusy] = useState(false)
  const [loadingLog, setLoadingLog] = useState(false)
  const [upgrading, setUpgrading] = useState(false)
  const [upgradeStalled, setUpgradeStalled] = useState(false)
  const [progress, setProgress] = useState(null)
  const [fights, setFights] = useState([])
  const [detail, setDetail] = useState(null)
  const [detailStatus, setDetailStatus] = useState('idle')
  const [notice, setNotice] = useState('')
  const [refreshNonce, setRefreshNonce] = useState(0)
  const [scope, setScope] = useState('group')
  const [roster, setRoster] = useState(emptyRoster)
  const [retentionDays, setRetentionDays] = useState(0)
  const [historyBusy, setHistoryBusy] = useState(false)
  const [fightsTruncated, setFightsTruncated] = useState(false)
  const [timeline, setTimeline] = useState(null)
  const [timelineStatus, setTimelineStatus] = useState('idle')
  const [spellTimeline, setSpellTimeline] = useState(null)
  const [loot, setLoot] = useState(null)
  const [lootStatus, setLootStatus] = useState('idle')
  const [mergeBusy, setMergeBusy] = useState(false)
  const [mergeNote, setMergeNote] = useState('')
  const mergeKeyRef = useRef('')
  const detailRef = useRef(null)
  const sizeRef = useRef(0)
  const fightIdRef = useRef(fightId)
  const characterRef = useRef('')
  const loadingRef = useRef(false)
  const upgradingRef = useRef(false)
  const mergeRef = useRef(mergePets)
  fightIdRef.current = fightId
  detailRef.current = detail
  loadingRef.current = loadingLog
  upgradingRef.current = upgrading
  mergeRef.current = mergePets

  const selected = useMemo(
    () => logs.find((log) => log.path === logPath) || null,
    [logs, logPath],
  )
  characterRef.current = selected?.character || ''

  useEffect(() => {
    let cancelled = false
    setLogsStatus('loading')
    setLogsError('')
    Promise.all([getParserLogs(), getParserConfig()])
      .then(([listed, cfg]) => {
        if (cancelled) return
        const nextLogs = Array.isArray(listed?.logs) ? listed.logs : []
        setFolder(listed?.folder || cfg?.eq_install_folder || '')
        setLogs(nextLogs)
        setLogsStatus('ready')
        setLive(!!cfg?.live)
        const days = Number(cfg?.fight_retention_days)
        setRetentionDays(Number.isFinite(days) && days > 0 ? Math.floor(days) : 0)
        const rebuild = !!cfg?.upgrading
        upgradingRef.current = rebuild
        setUpgrading(rebuild)
        if (rebuild && cfg.upgrade_progress) setProgress(progressFromUpgrade(cfg.upgrade_progress))
        setUpgradeStalled(rebuild && !!cfg?.upgrade_stalled)
        if (cfg?.live && cfg.live_path && nextLogs.some((log) => log.path === cfg.live_path)) {
          onLogPath(cfg.live_path)
        }
      })
      .catch((err) => {
        if (cancelled) return
        setLogs([])
        setLogsStatus('error')
        setLogsError(String(err?.message || err))
      })
    return () => { cancelled = true }
  }, [eqInstallFolder, refreshNonce, onLogPath])

  useEffect(() => {
    if (!upgrading) return undefined
    const timer = setInterval(() => {
      getParserConfig()
        .then((cfg) => {
          if (cfg?.upgrade_progress) setProgress(progressFromUpgrade(cfg.upgrade_progress))
          setUpgradeStalled(!!cfg?.upgrading && !!cfg?.upgrade_stalled)
          if (!cfg?.upgrading) {
            upgradingRef.current = false
            setUpgrading(false)
            if (cfg?.upgrade_error) setNotice(String(cfg.upgrade_error))
            setRefreshNonce((n) => n + 1)
          }
        })
        .catch(() => {})
    }, 1000)
    return () => clearInterval(timer)
  }, [upgrading])

  useEffect(() => {
    if (!logs.length) return
    if (logPath && logs.some((log) => log.path === logPath)) return
    onLogPath(logs[0].path)
  }, [logs, logPath, onLogPath])

  useEffect(() => {
    if (!selected?.character) {
      setFights([])
      setRoster(emptyRoster)
      return undefined
    }
    let cancelled = false
    fetchFightHistory(selected.character)
      .then((body) => {
        if (cancelled) return
        setFights(body.fights)
        setFightsTruncated(body.truncated)
      })
      .catch((err) => {
        if (!cancelled && !isRebuildBusy(err)) setNotice(String(err?.message || err))
      })
    getParserRoster(selected.character)
      .then((body) => {
        if (!cancelled) setRoster(body || emptyRoster)
      })
      .catch((err) => {
        if (!cancelled && !isRebuildBusy(err)) setNotice(String(err?.message || err))
      })
    return () => { cancelled = true }
  }, [selected?.character, selected?.path, refreshNonce])

  useEffect(() => {
    if (mergeKeyRef.current) {
      const ids = mergeKeyRef.current.split(',').filter(Boolean)
      let cancelled = false
      setDetailStatus('loading')
      loadMergedDetails(ids, mergePets)
        .then((merged) => {
          if (cancelled || !merged) return
          detailRef.current = merged
          setDetail(merged)
          setDetailStatus('ready')
          setTimeline(null)
          setTimelineStatus('idle')
        })
        .catch((err) => {
          if (!cancelled) setNotice(String(err?.message || err))
        })
      return () => { cancelled = true }
    }
    if (!fightId) {
      setDetail(null)
      setDetailStatus('idle')
      return undefined
    }
    let cancelled = false
    setDetailStatus('loading')
    getParserFight(fightId, mergePets)
      .then((body) => {
        if (cancelled || mergeKeyRef.current) return
        detailRef.current = body
        setDetail(body)
        setDetailStatus('ready')
        setTimeline(null)
        setTimelineStatus('idle')
      })
      .catch((err) => {
        if (cancelled) return
        if (isRebuildBusy(err)) return
        setDetail(null)
        const missing = err?.status === 404 || /not found/i.test(String(err?.message || ''))
        setDetailStatus(missing ? 'missing' : 'error')
        if (!missing) setNotice(String(err?.message || err))
      })
    return () => { cancelled = true }
  }, [fightId, mergePets])

  useEffect(() => {
    let refreshTimer = null
    const scheduleFights = () => {
      // Requests made during a rebuild would only get 503. The upgrade done
      // event refreshes everything once.
      if (upgradingRef.current) return
      clearTimeout(refreshTimer)
      refreshTimer = setTimeout(() => {
        const character = characterRef.current
        if (!character) return
        getParserFights(character, { limit: 200 })
          .then((body) => setFights((prev) => upsertFights(prev, body?.fights)))
          .catch(() => {})
        getParserRoster(character)
          .then((body) => setRoster(body || emptyRoster))
          .catch(() => {})
        const currentFight = fightIdRef.current
        if (currentFight && !mergeKeyRef.current) {
          getParserFight(currentFight, mergeRef.current)
            .then((body) => {
              if (mergeKeyRef.current) return
              detailRef.current = body
              setDetail(body)
              setDetailStatus('ready')
            })
            .catch(() => {})
        }
      }, 300)
    }
    const stream = openParserStream({
      upgrade: (data) => {
        const active = !!(data && data.active && !data.done)
        upgradingRef.current = active
        setUpgrading(active)
        if (typeof data?.stalled === 'boolean') setUpgradeStalled(active && data.stalled)
        if (!active) setUpgradeStalled(false)
        if (data?.error) setNotice(String(data.error))
        if (data?.done) {
          setRefreshNonce((n) => n + 1)
          setProgress((prev) => (
            prev ? { ...prev, active: false, done: true, pct: prev.pct == null ? 100 : prev.pct } : prev
          ))
          scheduleFights()
        }
      },
      progress: (data) => {
        const fromUpgrade = !!data?.upgrade
        if (fromUpgrade && !data?.done) {
          upgradingRef.current = true
          setUpgrading(true)
        }
        if (!loadingRef.current && !fromUpgrade && !data?.done) return
        const size = Number(data?.size) || sizeRef.current
        const offset = Number(data?.offset) || 0
        const lines = Number(data?.lines) || 0
        let nextPct = null
        if (size > 0 && offset >= 0) {
          nextPct = Math.max(0, Math.min(100, Math.round((offset / size) * 100)))
        }
        if (data?.done) nextPct = 100
        // A per-file "done" during a rebuild is not the end of the update.
        const stillUpdating = fromUpgrade && upgradingRef.current
        setProgress({
          active: stillUpdating || !data?.done,
          done: stillUpdating ? false : !!data?.done,
          pct: nextPct,
          lines,
        })
      },
      fight: () => scheduleFights(),
      live: (data) => {
        if (data && typeof data.on === 'boolean') setLive(data.on)
      },
      reset: () => scheduleFights(),
      roster: () => scheduleFights(),
    })
    return () => {
      clearTimeout(refreshTimer)
      stream.close()
    }
  }, [])

  const onSelectLog = (path) => {
    setNotice('')
    onLogPath(path)
    if (live) {
      const next = logs.find((log) => log.path === path)
      if (next) {
        postParserLive({ path: next.path, on: true, from_end: true }).catch((err) => {
          setLive(false)
          setNotice(String(err?.message || err))
        })
      }
    }
  }

  const onToggleLive = async () => {
    if (!selected) return
    setLiveBusy(true)
    setNotice('')
    try {
      if (live) {
        await postParserLive({ on: false })
        setLive(false)
      } else {
        await postParserLive({ path: selected.path, on: true, from_end: true })
        setLive(true)
      }
    } catch (err) {
      setNotice(String(err?.message || err))
    } finally {
      setLiveBusy(false)
    }
  }

  const onLoadLog = async () => {
    if (!selected) return
    setNotice('')
    setLoadingLog(true)
    sizeRef.current = Number(selected.size) || 0
    setProgress({ active: true, done: false, pct: sizeRef.current ? 0 : null, lines: 0 })
    try {
      if (live) {
        setLive(false)
      }
      const result = await postParserLoad(selected.path)
      setProgress({
        active: false,
        done: true,
        pct: 100,
        lines: Number(result?.lines) || 0,
      })
      const body = await fetchFightHistory(selected.character)
      const nextFights = body.fights
      setFights(nextFights)
      setFightsTruncated(body.truncated)
      const nextRoster = await getParserRoster(selected.character)
      setRoster(nextRoster || emptyRoster)
      if (nextFights[0]) onFightId(nextFights[0].id)
    } catch (err) {
      setProgress(null)
      setNotice(String(err?.message || err))
    } finally {
      setLoadingLog(false)
    }
  }

  const onRetentionDays = async (days) => {
    setHistoryBusy(true)
    setNotice('')
    try {
      const cfg = await postParserConfig({ fight_retention_days: days })
      const saved = Number(cfg?.fight_retention_days)
      setRetentionDays(Number.isFinite(saved) && saved > 0 ? Math.floor(saved) : 0)
      if (selected?.character) {
        const body = await fetchFightHistory(selected.character)
        setFights(body.fights)
        setFightsTruncated(body.truncated)
      }
    } catch (err) {
      setNotice(String(err?.message || err))
    } finally {
      setHistoryBusy(false)
    }
  }

  const onClearHistory = async () => {
    if (!selected?.character) return
    const label = selected.character
    if (typeof window !== 'undefined' && typeof window.confirm === 'function') {
      const ok = window.confirm(
        `Clear saved fights for ${label}? Pet assignments, dismissals, and the group allowlist stay. Other characters stay.`,
      )
      if (!ok) return
    }
    setHistoryBusy(true)
    setNotice('')
    try {
      await postParserClearHistory(label)
      onFightId(null)
      setDetail(null)
      setDetailStatus('idle')
      const body = await fetchFightHistory(label)
      setFights(body.fights)
      setFightsTruncated(body.truncated)
    } catch (err) {
      setNotice(String(err?.message || err))
    } finally {
      setHistoryBusy(false)
    }
  }

  const onSetFolder = async () => {
    if (!onSetEqFolder) return
    setNotice('')
    const path = await onSetEqFolder()
    if (!path) return
    try {
      await postParserConfig({ eq_install_folder: path })
    } catch (err) {
      setNotice(String(err?.message || err))
    }
    setRefreshNonce((n) => n + 1)
  }

  return (
    <ParserPanel
      folder={folder}
      logs={logs}
      logsStatus={logsStatus}
      logsError={logsError}
      selectedPath={logPath}
      onSelectLog={onSelectLog}
      live={live}
      liveBusy={liveBusy}
      onToggleLive={onToggleLive}
      loadingLog={loadingLog}
      upgrading={upgrading}
      upgradeStalled={upgradeStalled}
      progress={progress}
      fights={fights}
      selectedFightId={fightId}
      onSelectFight={(id) => {
        mergeKeyRef.current = ''
        setMergeNote('')
        setNotice('')
        onFightId(id)
      }}
      timeline={timeline}
      timelineStatus={timelineStatus}
      spellTimeline={spellTimeline}
      loot={loot}
      lootStatus={lootStatus}
      fightsTruncated={fightsTruncated}
      mergeBusy={mergeBusy}
      mergeNote={mergeNote}
      itemNameProps={itemNameProps}
      onDetailTab={(id) => {
        const current = detailRef.current
        if (!current) return
        if (id === 'timeline') {
          setTimelineStatus('loading')
          loadCurve(current)
            .then((curve) => {
              setTimeline(curve)
              setTimelineStatus(curve?.available === false ? 'missing' : 'ready')
            })
            .catch((err) => {
              setTimelineStatus('missing')
              setNotice(String(err?.message || err))
            })
        }
        if (id === 'loot' && selected?.character && lootStatus !== 'ready' && lootStatus !== 'loading') {
          setLootStatus('loading')
          getParserLoot(selected.character, { limit: 2000 })
            .then((body) => {
              setLoot(body)
              setLootStatus('ready')
            })
            .catch((err) => {
              setLootStatus('idle')
              setNotice(String(err?.message || err))
            })
        }
      }}
      onRequestSpell={(row) => {
        const current = detailRef.current
        const name = row?.ability || row?.spell
        if (!current || !name) return
        setSpellTimeline(null)
        loadCurve(current, name)
          .then((curve) => setSpellTimeline(curve))
          .catch(() => setSpellTimeline(null))
      }}
      onMergeFights={async (ids) => {
        const capped = capIds(ids)
        if (capped.length < 2) {
          setMergeNote(ids.length ? 'Select at least two fights to merge.' : 'That slice has fewer than two fights.')
          return
        }
        const dropped = ids.length - capped.length
        setMergeNote(dropped > 0
          ? `Merged the first ${MERGE_LIMIT} of ${ids.length} fights. Duration is the sum of each fight.`
          : `Merged ${capped.length} fights. Duration is the sum of each fight.`)
        setMergeBusy(true)
        mergeKeyRef.current = capped.join(',')
        try {
          const merged = await loadMergedDetails(capped, mergePets)
          detailRef.current = merged
          setDetail(merged)
          setDetailStatus('ready')
          setTimeline(null)
          setTimelineStatus('idle')
        } catch (err) {
          mergeKeyRef.current = ''
          setMergeNote(String(err?.message || err))
        } finally {
          setMergeBusy(false)
        }
      }}
      detail={detail}
      detailStatus={detailStatus}
      mergePets={mergePets}
      onMergePetsChange={onMergePets}
      scope={scope}
      onScopeChange={setScope}
      candidates={roster.candidates}
      groupMembers={roster.group}
      allowlist={roster.allowlist}
      loadouts={roster.loadouts}
      petBindings={roster.pets}
      character={selected?.character || ''}
      onConfirmPet={(pet) => {
        const name = selected?.character
        if (!name) return
        postParserCandidate({ character: name, pet, action: 'confirm', owner: name })
          .then(() => getParserRoster(name))
          .then((body) => {
            setRoster(body || emptyRoster)
            if (fightId) return getParserFight(fightId, mergePets)
            return null
          })
          .then((body) => {
            if (body && !mergeKeyRef.current) {
              detailRef.current = body
              setDetail(body)
              setDetailStatus('ready')
            }
          })
          .catch((err) => setNotice(String(err?.message || err)))
      }}
      onDismissPet={(pet) => {
        const name = selected?.character
        if (!name) return
        postParserCandidate({ character: name, pet, action: 'dismiss' })
          .then(() => getParserRoster(name))
          .then((body) => setRoster(body || emptyRoster))
          .catch((err) => setNotice(String(err?.message || err)))
      }}
      onSetPet={(pet, owner) => {
        const name = selected?.character
        if (!name) return
        postParserPet({ character: name, pet, owner })
          .then(() => getParserRoster(name))
          .then((body) => {
            setRoster(body || emptyRoster)
            if (fightId) return getParserFight(fightId, mergePets)
            return null
          })
          .then((body) => {
            if (body && !mergeKeyRef.current) {
              detailRef.current = body
              setDetail(body)
              setDetailStatus('ready')
            }
          })
          .catch((err) => setNotice(String(err?.message || err)))
      }}
      onUnassignPet={(pet) => {
        const name = selected?.character
        if (!name) return
        postParserPet({ character: name, pet, owner: null })
          .then(() => getParserRoster(name))
          .then((body) => {
            setRoster(body || emptyRoster)
            if (fightId) return getParserFight(fightId, mergePets)
            return null
          })
          .then((body) => {
            if (body && !mergeKeyRef.current) {
              detailRef.current = body
              setDetail(body)
              setDetailStatus('ready')
            }
          })
          .catch((err) => setNotice(String(err?.message || err)))
      }}
      onAddAllow={(member) => {
        const name = selected?.character
        if (!name) return
        postParserGroup({ character: name, member, action: 'add' })
          .then(() => getParserRoster(name))
          .then((body) => setRoster(body || emptyRoster))
          .catch((err) => setNotice(String(err?.message || err)))
      }}
      onRemoveAllow={(member) => {
        const name = selected?.character
        if (!name) return
        postParserGroup({ character: name, member, action: 'remove' })
          .then(() => getParserRoster(name))
          .then((body) => setRoster(body || emptyRoster))
          .catch((err) => setNotice(String(err?.message || err)))
      }}
      onLoadLog={onLoadLog}
      onRefresh={() => setRefreshNonce((n) => n + 1)}
      onSetEqFolder={onSetFolder}
      canSetFolder={!!canSetFolder}
      onOpenCredits={onOpenCredits}
      notice={notice}
      retentionDays={retentionDays}
      onRetentionDays={onRetentionDays}
      onClearHistory={onClearHistory}
      historyBusy={historyBusy}
    />
  )
}
