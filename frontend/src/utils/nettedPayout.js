/**
 * A payout that had to net against a player's prior outstanding balance
 * (gaming.services.initiate_payout sets requested_amount when this
 * happens — see LedgerTable.vue's expandedRows comment for the underlying
 * math) settles the player's account to exactly ₦0 the instant it lands,
 * and stays there unless it's later rejected (voided), in which case the
 * true balance reverts to that payout's own `amount` (what it had
 * cleared). This is a fact about the payout row itself, independent of
 * which ledger it's rendered on — but three call sites derived it
 * independently and drifted out of sync on 2026-09-27 (LedgerTable's
 * balance column, ActiveGameDayView's hero/stat tiles, and
 * GameDaysListView's per-player stats all showed a stale today-only
 * figure after an Owner approved a netted payout). Every "what is this
 * player's current balance" computation goes through these two functions
 * instead of re-deriving it.
 *
 * Known limitation, accepted rather than built for: this is a
 * point-in-time snapshot tied to that one payout row — further activity
 * for the same player after it isn't reflected.
 */

export function findNettedPayout(rows) {
  let latest = null
  for (const row of rows) {
    if (row.type !== 'PAYOUT' || !row.requested_amount) continue
    if (!latest || new Date(row.created_at) > new Date(latest.created_at)) latest = row
  }
  return latest
}

export function nettedPayoutBalance(row) {
  return row.is_voided ? Number(row.amount) : 0
}

// Convenience for the common case: given a player's ledger rows and what
// their balance would otherwise be, apply the netted-payout override if one
// applies.
export function currentPlayerBalance(rows, fallback) {
  const netted = findNettedPayout(rows)
  return netted ? nettedPayoutBalance(netted) : fallback
}
