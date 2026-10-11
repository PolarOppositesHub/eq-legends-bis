/** Display helpers for overlay meters. Zone scope does not invent a DPS rate. */

export const ZONE_METER_NOTE = 'Totals are the sum of saved fights in this zone. DPS stays on the fight meter.'
export const FULLSCREEN_NOTE = 'Exclusive fullscreen draws over every window. This overlay does not send input to the game.'
export const AUTO_HIDE_NOTE = 'Auto-hide when EverQuest is not the focused window stays off. This version does not query the foreground window.'

export function meterRows(payload) {
  const scope = payload?.scope === 'zone' ? 'zone' : 'fight'
  const rows = Array.isArray(payload?.rows) ? payload.rows : []
  return rows.map((row) => {
    const line = {
      source: row?.source || '',
      damage: Number(row?.damage) || 0,
      heals: Number(row?.heals) || 0,
    }
    if (scope === 'fight') {
      line.dps = row?.dps == null ? null : row.dps
      line.sdps = row?.sdps == null ? null : row.sdps
    }
    return line
  })
}

export function overlayIdFromSearch(search) {
  const params = new URLSearchParams(search || '')
  const id = params.get('overlay')
  if (id === 'dps' || id === 'heal' || id === 'alert') return id
  return ''
}
