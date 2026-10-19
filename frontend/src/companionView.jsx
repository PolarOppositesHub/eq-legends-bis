import React, { useEffect, useState } from 'react'
import {
  getCompanionBuffs,
  getCompanionMaps,
  getCompanionPerf,
  getCompanionRespawns,
  postCompanionDuration,
  postCompanionExaltationNote,
  postCompanionExaltations,
  postCompanionExport,
  postCompanionImport,
  postCompanionManual,
  postCompanionResists,
  postCompanionRespawn,
} from './parserApi.js'
import {
  COMPANION_BUFF_NOTE,
  COMPANION_EXALTATION_NOTE,
  COMPANION_MAP_NOTE,
  COMPANION_RESIST_NOTE,
  COMPANION_RESPAWN_NOTE,
  COMPANION_SHARE_NOTE,
  buffOverlayText,
  exaltationCandidates,
  remainingLabel,
  wornResistRows,
} from './companionView.js'

function useLoad(loader, deps) {
  const [body, setBody] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let cancelled = false
    const run = () => {
      Promise.resolve()
        .then(loader)
        .then((next) => {
          if (!cancelled) {
            setBody(next)
            setError('')
          }
        })
        .catch((err) => {
          if (!cancelled) setError(String(err?.message || err))
        })
    }
    run()
    const timer = setInterval(run, 5000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  return { body, error, setBody }
}

export function CompanionPanel({
  character = '',
  loadout = '',
  classes = [],
  level = null,
  race = '',
  equipment = null,
  wornUpgrades = null,
  items = [],
  ui = null,
  onUi,
}) {
  const who = (character || '').trim()
  const buffs = useLoad(
    () => (who && loadout ? getCompanionBuffs(who, loadout) : null),
    [who, loadout],
  )
  const respawns = useLoad(() => (who ? getCompanionRespawns(who) : null), [who])
  const [spell, setSpell] = useState('')
  const [seconds, setSeconds] = useState('')
  const [target, setTarget] = useState('You')
  const [mob, setMob] = useState('')
  const [zone, setZone] = useState('')
  const [respawnSeconds, setRespawnSeconds] = useState('')
  const [profileText, setProfileText] = useState('')
  const [notice, setNotice] = useState('')
  const [perf, setPerf] = useState(null)
  const [exalt, setExalt] = useState(null)
  const [resists, setResists] = useState(null)

  useEffect(() => {
    if (!who || !loadout) {
      setExalt(null)
      return undefined
    }
    let cancelled = false
    postCompanionExaltations({
      character: who,
      loadout,
      items: exaltationCandidates(items),
    }).then((body) => {
      if (!cancelled) setExalt(body)
    }).catch((err) => {
      if (!cancelled) setNotice(String(err?.message || err))
    })
    return () => { cancelled = true }
  }, [who, loadout, items])

  useEffect(() => {
    if (!loadout) return undefined
    let cancelled = false
    postCompanionResists({
      character: who,
      loadout,
      classes,
      level,
      race,
      worn: wornResistRows(equipment, wornUpgrades),
      assume_max_aas: false,
    }).then((body) => {
      if (!cancelled) setResists(body)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [who, loadout, classes, level, race, equipment, wornUpgrades])

  const fail = (err) => setNotice(String(err?.message || err))

  const saveDuration = async () => {
    try {
      const body = await postCompanionDuration({
        character: who,
        loadout,
        spell,
        seconds: seconds.trim() ? Number(seconds) : null,
      })
      buffs.setBody(body)
      setNotice('')
    } catch (err) {
      fail(err)
    }
  }

  const startManual = async () => {
    try {
      const body = await postCompanionManual({
        character: who,
        loadout,
        spell,
        target,
        seconds: seconds.trim() ? Number(seconds) : null,
        action: 'start',
      })
      buffs.setBody(body)
    } catch (err) {
      fail(err)
    }
  }

  const saveRespawn = async () => {
    try {
      const body = await postCompanionRespawn({
        character: who,
        zone,
        mob,
        seconds: respawnSeconds.trim() ? Number(respawnSeconds) : null,
      })
      respawns.setBody(body)
    } catch (err) {
      fail(err)
    }
  }

  const saveTarget = async (key, value) => {
    try {
      await postCompanionExaltationNote({ character: who, loadout, key, target: value })
      const body = await postCompanionExaltations({
        character: who,
        loadout,
        items: exaltationCandidates(items),
      })
      setExalt(body)
    } catch (err) {
      fail(err)
    }
  }

  const exportProfile = async () => {
    try {
      const body = await postCompanionExport({ character: who, ui: ui || {} })
      setProfileText(JSON.stringify(body, null, 2))
      setNotice('')
    } catch (err) {
      fail(err)
    }
  }

  const importProfile = async () => {
    try {
      const profile = JSON.parse(profileText)
      const body = await postCompanionImport({ character: who, profile })
      if (body.ui && onUi) onUi(body.ui)
      setNotice('Profile imported for this character. Loadout entries stay on the loadout they were saved with.')
      const next = await getCompanionBuffs(who, loadout)
      buffs.setBody(next)
    } catch (err) {
      fail(err)
    }
  }

  const loadPerf = async () => {
    try {
      setPerf(await getCompanionPerf())
    } catch (err) {
      fail(err)
    }
  }

  const downloadFeedback = async () => {
    try {
      const response = await fetch('/api/parser/companion/feedback')
      if (!response.ok) throw new Error('Feedback bundle failed')
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'eq-legends-bis-feedback.zip'
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      fail(err)
    }
  }

  return (
    <div className="dashboard-grid" data-testid="companion-panel">
      <p className="muted">Loadout {loadout || 'unknown'}. Entries that depend on class or level stay on this loadout.</p>
      {notice ? <p className="warn">{notice}</p> : null}
      <section className="dashboard-card">
        <h3>Buff and debuff timers</h3>
        <p className="muted">{buffs.body?.note || COMPANION_BUFF_NOTE}</p>
        {!who ? <p>Choose a character log in the Parser.</p> : null}
        <ul className="dashboard-list" data-testid="buff-timers">
          {(buffs.body?.active || []).map((row) => (
            <li key={`${row.name}-${row.target}`}>
              {row.name} on {row.target || 'unknown'} · {remainingLabel(row.remaining_text)}
              {row.duration_source ? ` (${row.duration_source})` : ''}
            </li>
          ))}
        </ul>
        {(buffs.body?.recent || []).length ? (
          <ul className="dashboard-list">
            {buffs.body.recent.slice(-5).map((row, index) => (
              <li key={`${row.name}-${index}`}>
                {row.name} wore off · {row.observed_seconds == null ? 'duration unknown' : `${row.observed_seconds}s in your log`}
              </li>
            ))}
          </ul>
        ) : null}
        <label>
          Spell
          <input value={spell} onChange={(event) => setSpell(event.target.value)} />
        </label>
        <label>
          Target
          <input value={target} onChange={(event) => setTarget(event.target.value)} />
        </label>
        <label>
          Seconds for this loadout
          <input value={seconds} onChange={(event) => setSeconds(event.target.value)} inputMode="numeric" />
        </label>
        <button type="button" onClick={saveDuration}>Save duration</button>
        <button type="button" onClick={startManual}>Start timer</button>
      </section>
      <section className="dashboard-card">
        <h3>Respawn timers</h3>
        <p className="muted">{respawns.body?.note || COMPANION_RESPAWN_NOTE}</p>
        <ul className="dashboard-list" data-testid="respawn-timers">
          {(respawns.body?.rows || []).map((row) => (
            <li key={`${row.zone_text}-${row.mob}`}>
              {row.mob} in {row.zone_text} · last kill {row.last_kill || 'unknown'} · respawn {remainingLabel(row.remaining_text)}
            </li>
          ))}
        </ul>
        <label>
          Mob
          <input value={mob} onChange={(event) => setMob(event.target.value)} />
        </label>
        <label>
          Zone
          <input value={zone} onChange={(event) => setZone(event.target.value)} />
        </label>
        <label>
          Respawn seconds
          <input value={respawnSeconds} onChange={(event) => setRespawnSeconds(event.target.value)} inputMode="numeric" />
        </label>
        <button type="button" onClick={saveRespawn}>Save respawn</button>
      </section>
      <section className="dashboard-card" data-testid="exaltation-planner">
        <h3>Exaltation planner</h3>
        <p className="muted">{exalt?.note || COMPANION_EXALTATION_NOTE}</p>
        <ul className="dashboard-list">
          {(exalt?.rows || []).map((row) => (
            <li key={row.key}>
              {row.socket_label} · {row.name} · stats {row.stats_text || 'in catalog'}
              <label>
                Target for this loadout
                <input
                  defaultValue={row.target || ''}
                  onBlur={(event) => saveTarget(row.key, event.target.value)}
                />
              </label>
              {row.target ? <span> target stats {row.target_stats_text || 'in catalog'}</span> : null}
            </li>
          ))}
        </ul>
        {(exalt?.rows || []).length === 0 ? <p>No exaltation sockets in the current inventory import.</p> : null}
      </section>
      <section className="dashboard-card" data-testid="resist-profile">
        <h3>Resist profile</h3>
        <p className="muted">{resists?.note || COMPANION_RESIST_NOTE}</p>
        <p>Cap {resists?.cap_text || 'unknown'}. Total {resists?.totals_text || 'from the char-sheet pool for this loadout'}.</p>
        <ul className="dashboard-list">
          {Object.entries(resists?.totals || {}).map(([key, value]) => (
            <li key={key}>{key} {value == null ? 'unknown' : value}</li>
          ))}
        </ul>
        {(resists?.unknown_items || []).map((name) => (
          <p key={name}>{name}: stats unknown</p>
        ))}
        {resists?.warrior_note ? <p>{resists.warrior_note}</p> : null}
        <p>{resists?.svv_note}</p>
      </section>
      <section className="dashboard-card" data-testid="profile-share">
        <h3>Share profile</h3>
        <p className="muted">{COMPANION_SHARE_NOTE}</p>
        <button type="button" onClick={exportProfile}>Export</button>
        <button type="button" onClick={importProfile}>Import</button>
        <textarea
          value={profileText}
          onChange={(event) => setProfileText(event.target.value)}
          rows={6}
          spellCheck="false"
        />
      </section>
      <section className="dashboard-card" data-testid="perf-feedback">
        <h3>Perf and feedback</h3>
        <button type="button" onClick={loadPerf}>Read perf</button>
        <button type="button" onClick={downloadFeedback}>Download feedback bundle</button>
        {perf ? (
          <p data-testid="perf-readout">
            Version {perf.version}. Memory {perf.rss_text || 'unknown'}.
          </p>
        ) : null}
        <p className="muted" data-testid="buff-overlay-sample">{buffOverlayText(buffs.body)}</p>
      </section>
      {buffs.error ? <p className="warn">{buffs.error}</p> : null}
    </div>
  )
}

export function MapsPanel({ character = '' }) {
  const who = (character || '').trim()
  const maps = useLoad(() => (who ? getCompanionMaps(who) : Promise.resolve(null)), [who])
  return (
    <div className="dashboard-grid" data-testid="maps-panel">
      <section className="dashboard-card">
        <h3>Maps</h3>
        <p className="muted">{maps.body?.note || COMPANION_MAP_NOTE}</p>
        {!who ? <p>Choose a character log in the Parser.</p> : null}
        <ul className="dashboard-list">
          {(maps.body?.zones || []).map((zone) => (
            <li key={zone.zone}>
              <strong>{zone.zone}</strong>
              {' · map '}
              {zone.map_url ? <a href={zone.map_url}>{zone.map_text}</a> : zone.map_text || 'unknown'}
              {' · level requirement '}
              {zone.level_requirement_text || 'unknown'}
              {zone.note ? <div>{zone.note}</div> : null}
              <ul>
                {(zone.mobs || []).slice(0, 12).map((mob) => (
                  <li key={mob.name}>
                    {mob.name} · level {mob.level_text || 'unknown'} · location {mob.location_text || 'unknown'}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
        {who && (maps.body?.zones || []).length === 0 ? <p>No zones in the saved fights yet.</p> : null}
      </section>
    </div>
  )
}
