/** When the desktop shell asks the sidecar to sync. */
const SYNC_INTERVAL_MS = 2 * 60 * 1000
const SYNC_DEBOUNCE_MS = 10 * 1000

function planSync(reason) {
  if (reason === 'change' || reason === 'watch') return { run: true, delayMs: SYNC_DEBOUNCE_MS }
  if (reason === 'launch' || reason === 'now' || reason === 'quit') return { run: true, delayMs: 0 }
  if (reason === 'interval') return { run: true, delayMs: SYNC_INTERVAL_MS }
  return { run: false, delayMs: 0 }
}

module.exports = {
  SYNC_INTERVAL_MS,
  SYNC_DEBOUNCE_MS,
  planSync,
}
