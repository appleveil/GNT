/**
 * src/utils/amountInput.js
 *
 * Live thousands-separator formatting for a plain-text amount input, without
 * changing what's actually stored. Every ref bound through this stays a
 * plain numeric string (e.g. "400000") — exactly what Number(...) and every
 * existing computed/payload in the callers already expect — while the
 * <input> itself DISPLAYS the comma-grouped form. Kept as two small pure
 * functions rather than a directive/composable so each caller wires its own
 * :value/@input explicitly (a plain v-model can't do this, since the
 * displayed string and the stored value are shape-different).
 *
 * Whole Naira only (2026-09-23) — this club never deals in kobo, so a typed
 * "." is dropped outright rather than treated as a decimal point.
 */

// raw: a plain whole-number numeric string, or '' — never contains commas or a dot.
export function formatAmountForDisplay(raw) {
  if (raw === '' || raw == null) return ''
  return String(raw).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

// typed: whatever the input's raw value is right now (commas and all, since
// that's what the user sees) — strips it back to a plain whole-number string.
export function parseAmountInput(typed) {
  return typed.replace(/\D/g, '')
}
