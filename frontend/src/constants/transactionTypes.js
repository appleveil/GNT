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
  // "Deals" Transfer's linked pair (added 2026-09-20, given a real label
  // here 2026-09-23 once the web Deals History feed started showing them —
  // previously only ever rendered via their raw enum name, nothing read
  // them through this constant before then).
  DEAL_TRANSFER_OUT: { label: 'Deal Transfer (out)', actionLabel: 'Deal Transfer', lane: 'other', physicalCount: false, amountTone: 'debit' },
  DEAL_TRANSFER_IN: { label: 'Deal Transfer (in)', actionLabel: 'Deal Transfer', lane: 'other', physicalCount: false, amountTone: 'credit' },
  // "Deals" Profit Split's house-covered portion of a buy-in — never a
  // player-initiated entry, always auto-created by record_transaction's
  // CHIPS_OUT branch, paired via linked_transaction with the CHIPS_OUT it
  // offsets. Labeled "SPA" (Stake/Profit-split Agreement) 2026-09-28, per
  // explicit instruction — this is what the Cashier sees on their own
  // ledger now that it's a real credit (see gaming.selectors.CREDIT_TYPES),
  // not the earlier balance-neutral "Profit Split Stake" label from a time
  // this was hidden/informational only. amountTone: credit, not neutral,
  // now that it's a real balance-affecting entry like any other credit.
  PROFIT_SPLIT_STAKE: { label: 'SPA', actionLabel: 'SPA', lane: 'other', physicalCount: false, amountTone: 'credit' },
  // "One line per action" (added 2026-09-25, explicit instruction): a
  // buy-in's CHIPS_OUT line stays "chips issued" only — when part of it is
  // covered by a player's own carried-forward credit (the house owes them
  // from a previous game-day), that's a separate line, auto-created by
  // record_transaction's CHIPS_OUT branch and paired via linked_transaction
  // with PLAYER_BALANCE_OUT. PLAYER_BALANCE_OUT itself is dateless
  // (game_day=None) and never appears on any game-day-scoped ledger, so it
  // has no realistic path onto a Cashier screen — labeled here anyway for
  // the Owner/Accountant Outstanding ledger.
  PLAYER_BALANCE_IN: { label: 'Player balance', actionLabel: 'Player balance', lane: 'other', physicalCount: false, amountTone: 'credit' },
  PLAYER_BALANCE_OUT: {
    label: 'Player balance (carried forward)', actionLabel: 'Player balance', lane: 'other', physicalCount: false,
    amountTone: 'debit',
  },
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
