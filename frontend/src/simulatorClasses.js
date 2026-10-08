/** When the Simulator may recalculate.

A full set is 3 classes. Below level 10 a character only has 2 classes,
so 2 is a full set. An incomplete set must not start a request or the
loading overlay.
*/

export function classesRequiredForLevel(level) {
  const n = Number(level)
  if (Number.isFinite(n) && n < 10) return 2
  return 3
}

export function simulatorRecalcDecision(classes, level) {
  const have = Array.isArray(classes) ? classes.filter(Boolean).length : 0
  const need = classesRequiredForLevel(level)
  const more = Math.max(0, need - have)
  const recalc = more === 0
  const noun = more === 1 ? 'class' : 'classes'
  return {
    recalc,
    overlay: recalc,
    hint: recalc ? '' : `Pick ${more} more ${noun}`,
  }
}
