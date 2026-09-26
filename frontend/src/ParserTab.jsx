import { useEffect, useMemo, useRef, useState } from 'react'
import {
  getParserConfig,
  getParserFight,
  getParserFights,
  getParserLogs,
  openParserStream,
  postParserClearHistory,
  postParserConfig,
  postParserLive,
  postParserLoad,
} from './parserApi.js'
import {
  LEVEL_LOADOUT_NOTE,
  PARSER_EMPTY,
  displaySources,
  formatDamage,
  formatDuration,
  formatFightTime,
  formatRate,
  formatTargets,
  formatZone,
  logOptionLabel,
  sourceKindLabel,
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
      <span className="muted">0 keeps every saved fight.</span>
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
  onLoadLog,
  onRefresh,
  onSetEqFolder,
  canSetFolder,
  onOpenCredits,
  notice,
  upgrading,
  character,
  retentionDays,
  onRetentionDays,
  onClearHistory,
  historyBusy,
}) {
  const list = Array.isArray(logs) ? logs : []
  const fightRows = Array.isArray(fights) ? fights : []
  const sources = displaySources(detail)
  const empty = logsStatus === 'ready' && list.length === 0
  const selected = list.find((log) => log.path === selectedPath) || null
  const pct = progress && progress.pct != null ? progress.pct : null

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
        <div className="parser-split">
          <div>
            <h3 className="parser-subhead">Fights</h3>
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
                      <th>Time</th>
                      <th>Zone</th>
                      <th>Targets</th>
                      <th>Duration</th>
                      <th>Total damage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fightRows.map((fight) => (
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
                          {formatFightTime(fight.start_ts)}
                          {fight.open ? <span className="parser-chip">open</span> : null}
                        </td>
                        <td>{formatZone(fight)}</td>
                        <td>
                          {formatTargets(fight.targets)}
                          {fight.player_died ? <span className="parser-chip">died</span> : null}
                        </td>
                        <td>{formatDuration(fight.duration_seconds)}</td>
                        <td>{formatDamage(fight.damage)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {fightRows.length >= 200 ? (
              <p className="note">Showing the latest 200 fights.</p>
            ) : null}
          </div>

          <div>
            <div className="parser-detail-head">
              <h3 className="parser-subhead">DPS</h3>
              <label className="check parser-merge" data-testid="parser-merge-pets">
                <input
                  type="checkbox"
                  checked={!!mergePets}
                  onChange={(e) => onMergePetsChange(!!e.target.checked)}
                />
                Merge pets
              </label>
            </div>
            <p className="note">
              {mergePets
                ? 'Merge pets adds each pet’s damage to its owner. The pet stays listed under that owner.'
                : 'Pets stay on their own rows.'}
              {' '}DPS uses that source’s active time. SDPS uses the whole fight.
            </p>
            {!selectedFightId ? (
              <p className="muted">Select a fight to see you, your pet, and your group.</p>
            ) : null}
            {selectedFightId && detailStatus === 'loading' ? <p className="muted">Loading fight…</p> : null}
            {selectedFightId && detailStatus === 'missing' ? (
              <p className="muted">That fight is not in the saved history.</p>
            ) : null}
            {detail && sources.length ? (
              <>
                <p className="parser-totals" data-testid="parser-totals">
                  Total damage {formatDamage(detail.totals?.damage)}
                  {' · '}
                  {formatRate(detail.totals?.dps)} DPS
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
                      </tr>
                    </thead>
                    <tbody>
                      {sources.map((row) => (
                        <tr
                          key={`${row.nested ? 'pet' : 'src'}:${row.source}`}
                          className={row.nested ? 'parser-pet-row' : undefined}
                          data-source={row.source}
                          data-nested={row.nested ? '1' : '0'}
                        >
                          <td>{row.nested ? `↳ ${row.source}` : row.source}</td>
                          <td>{sourceKindLabel(row.kind)}</td>
                          <td>{formatDamage(row.damage)}</td>
                          <td>{formatRate(row.dps)}</td>
                          <td>{formatRate(row.sdps)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}
            {detail && !sources.length && detailStatus === 'ready' ? (
              <p className="muted">No damage from you, your pet, or your group in this fight.</p>
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
}) {
  const [folder, setFolder] = useState('')
  const [logs, setLogs] = useState([])
  const [logsStatus, setLogsStatus] = useState('loading')
  const [logsError, setLogsError] = useState('')
  const [live, setLive] = useState(false)
  const [liveBusy, setLiveBusy] = useState(false)
  const [loadingLog, setLoadingLog] = useState(false)
  const [upgrading, setUpgrading] = useState(false)
  const [progress, setProgress] = useState(null)
  const [fights, setFights] = useState([])
  const [detail, setDetail] = useState(null)
  const [detailStatus, setDetailStatus] = useState('idle')
  const [notice, setNotice] = useState('')
  const [refreshNonce, setRefreshNonce] = useState(0)
  const [retentionDays, setRetentionDays] = useState(0)
  const [historyBusy, setHistoryBusy] = useState(false)
  const sizeRef = useRef(0)
  const fightIdRef = useRef(fightId)
  const characterRef = useRef('')
  const loadingRef = useRef(false)
  const upgradingRef = useRef(false)
  const mergeRef = useRef(mergePets)
  fightIdRef.current = fightId
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
          if (!cfg?.upgrading) {
            upgradingRef.current = false
            setUpgrading(false)
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
      return undefined
    }
    let cancelled = false
    getParserFights(selected.character)
      .then((body) => {
        if (!cancelled) setFights(Array.isArray(body?.fights) ? body.fights : [])
      })
      .catch((err) => {
        if (!cancelled) setNotice(String(err?.message || err))
      })
    return () => { cancelled = true }
  }, [selected?.character, selected?.path, refreshNonce])

  useEffect(() => {
    if (!fightId) {
      setDetail(null)
      setDetailStatus('idle')
      return undefined
    }
    let cancelled = false
    setDetailStatus('loading')
    getParserFight(fightId, mergePets)
      .then((body) => {
        if (cancelled) return
        setDetail(body)
        setDetailStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
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
      clearTimeout(refreshTimer)
      refreshTimer = setTimeout(() => {
        const character = characterRef.current
        if (!character) return
        getParserFights(character)
          .then((body) => setFights(Array.isArray(body?.fights) ? body.fights : []))
          .catch(() => {})
        const currentFight = fightIdRef.current
        if (currentFight) {
          getParserFight(currentFight, mergeRef.current)
            .then((body) => {
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
        if (data?.error) setNotice(String(data.error))
        if (data?.done) {
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
      const body = await getParserFights(selected.character)
      const nextFights = Array.isArray(body?.fights) ? body.fights : []
      setFights(nextFights)
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
        const body = await getParserFights(selected.character)
        setFights(Array.isArray(body?.fights) ? body.fights : [])
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
      const ok = window.confirm(`Clear saved fights for ${label}? Other characters stay.`)
      if (!ok) return
    }
    setHistoryBusy(true)
    setNotice('')
    try {
      await postParserClearHistory(label)
      onFightId(null)
      setDetail(null)
      setDetailStatus('idle')
      const body = await getParserFights(label)
      setFights(Array.isArray(body?.fights) ? body.fights : [])
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
      progress={progress}
      fights={fights}
      selectedFightId={fightId}
      onSelectFight={(id) => {
        setNotice('')
        onFightId(id)
      }}
      detail={detail}
      detailStatus={detailStatus}
      mergePets={mergePets}
      onMergePetsChange={onMergePets}
      onLoadLog={onLoadLog}
      onRefresh={() => setRefreshNonce((n) => n + 1)}
      onSetEqFolder={onSetFolder}
      canSetFolder={!!canSetFolder}
      onOpenCredits={onOpenCredits}
      notice={notice}
      character={selected?.character || ''}
      retentionDays={retentionDays}
      onRetentionDays={onRetentionDays}
      onClearHistory={onClearHistory}
      historyBusy={historyBusy}
    />
  )
}
