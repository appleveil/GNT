/**
 * src/utils/canVoid.js
 *
 * Mirrors gaming.services.void_transaction's eligibility rule exactly: the
 * Owner can always void; a Cashier can void only their own entry, and only
 * while its game-day is still open. Used to HIDE the void action (not just
 * disable it) when ineligible — per HiFiVoidEntry.dc.html's own note: "Only
 * shown when eligible... otherwise this action is hidden from the ledger row."
 *
 * `row.recorded_by` comes back from the API as a plain integer; `user.id` is
 * a string (SimpleJWT stringifies the `user_id` JWT claim) — compare as
 * strings so this never silently false-negatives on a type mismatch.
 */
export function canVoidTransaction(row, user, gameDayStatus) {
  if (!row || row.is_voided) return false
  if (user?.role === 'OWNER') return true
  return String(row.recorded_by) === String(user?.id) && gameDayStatus === 'OPEN'
}
