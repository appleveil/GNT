/**
 * src/constants/transactionTypes.js
 *
 * Single source of truth for how each Transaction.Type renders and behaves
 * in the Cashier UI — label (ledger rows), actionLabel (entry-grid buttons
 * and the entry sheet's title), which --lane-* token family it draws its
 * icon/dot color from (tokens.css), which extra rules apply, and
 * `amountTone` — colors the ledger's own Amount figure red ('debit', chips
 * going out) or green ('credit', money coming back in), per the ledger
 * design review. Only CHIPS_OUT and the PAYMENT_* types carry a tone;
 * everything else (CHIPS_IN, PAYOUT, WRITE_OFF, RAKE, TIP) stays neutral —
 * not asked for, and their sign is less clear-cut as a pure debit/credit.
 *
 * Mirrors backend/gaming/models.py's Transaction.Type and gaming/services.py's
 * PHYSICAL_COUNT_TYPES/DEFAULT_CHANNEL_BY_TYPE — keep in sync if either
 * changes. RAKE/TIP are `general: true` (player is always null — see
 * CONCEPT.md's "Rake is not a per-player entry"); they're also excluded
 * server-side from game_day_ledger, so they never appear in the feed built
 * from GET /game-days/{id}/ledger/, only from their own entry action.
 */
export const TRANSACTION_TYPES = {
  CHIPS_OUT: { label: 'Chips Out', actionLabel: 'Issue Chips', lane: 'chips', physicalCount: true, amountTone: 'debit' },
  CHIPS_IN: { label: 'Return Chips', actionLabel: 'Return Chips', lane: 'chips', physicalCount: true },
  PAYMENT_CASH: {
    label: 'Cash Payment', actionLabel: 'Cash Payment', lane: 'payments', physicalCount: true, needsCurrency: true,
    amountTone: 'credit',
  },
  PAYMENT_TRANSFER: {
    label: 'Transfer', actionLabel: 'Transfer (manual)', lane: 'payments', physicalCount: false, amountTone: 'credit',
  },
  PAYMENT_POS: {
    label: 'POS Payment', actionLabel: 'POS Payment', lane: 'payments', physicalCount: false, needsProvider: true,
    amountTone: 'credit',
  },
  PAYMENT_DEAL: { label: 'Deal', actionLabel: 'Deal', lane: 'other', physicalCount: false, amountTone: 'credit' },
  PAYOUT: { label: 'Payout', actionLabel: 'Payout', lane: 'other', physicalCount: false },
  WRITE_OFF: { label: 'Write-off', actionLabel: 'Write-off', lane: 'other', physicalCount: false },
  RAKE: { label: 'Rake', actionLabel: 'Rake', lane: 'other', physicalCount: true, general: true },
  TIP: { label: 'Tip', actionLabel: 'Tip', lane: 'other', physicalCount: true, general: true },
}

// Status colors reuse the same badge--* classes as GameDay/Payout status
// elsewhere (see common.css) — this maps a Transaction.status value
// to that suffix.
export const TRANSACTION_STATUS_BADGE = {
  POSTED: null, // the default/expected state — no badge needed
  PENDING_APPROVAL: 'pending',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  TRANSFER_FAILED: 'rejected',
}
