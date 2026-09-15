/**
 * src/utils/amountInput.js
 *
 * Live thousands-separator formatting for a plain-text amount input, without
 * changing what's actually stored. Every ref bound through this stays a
 * plain numeric string (e.g. "400000" or "400000.50") — exactly what
 * Number(...) and every existing computed/payload in the callers already
 * expect — while the <input> itself DISPLAYS the comma-grouped form. Kept
 * as two small pure functions rather than a directive/composable so each
 * caller wires its own :value/@input explicitly (a plain v-model can't do
 * this, since the displayed string and the stored value are shape-different).
 */

// raw: a plain numeric string, or '' — never contains commas.
export function formatAmountForDisplay(raw) {
  if (raw === '' || raw == null) return ''
  const [intPart, decPart] = String(raw).split('.')
  const withCommas = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return decPart !== undefined ? `${withCommas}.${decPart}` : withCommas
}

// typed: whatever the input's raw value is right now (commas and all, since
// that's what the user sees) — strips it back to a plain numeric string,
// allowing at most one decimal point.
export function parseAmountInput(typed) {
  let v = typed.replace(/[^\d.]/g, '')
  const firstDot = v.indexOf('.')
  if (firstDot !== -1) {
    v = v.slice(0, firstDot + 1) + v.slice(firstDot + 1).replace(/\./g, '')
  }
  return v
}
