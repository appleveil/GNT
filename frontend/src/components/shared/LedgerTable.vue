<script setup>
import { TRANSACTION_TYPES, TRANSACTION_STATUS_BADGE } from '@/constants/transactionTypes'

// Shared tabular ledger row renderer (2026-09-17) — replaces 7 near-identical
// hand-rolled `.feed-row`/`.ledger-row`/`.activity-row` implementations
// (GameDayLedgerView, GameDayDetailView, OutstandingView [folded into
// DashboardView 2026-09-23], RosterDetailView x2, ActiveGameDayView,
// PlayerDetailView) with one presentational
// component: no API calls, no store access — the parent still fetches its
// own data and handles voiding exactly as before, just renders through this
// instead of its own markup. See PLAN.md's "Ledgers: list rows → tabular
// Ledger Grid" entry for the chosen direction and per-view column mapping.
//
// Row height comes from --control-row-min (44px Cashier / 40px everyone
// else, via tokens.css's [data-density] — see App.vue) — so Cashier's
// tables stay touch-sized and back-office tables stay desktop-dense
// with no separate density prop needed here.
const props = defineProps({
  rows: { type: Array, required: true },
  // A row may carry its own `type_label`, overriding TRANSACTION_TYPES'
  // shared label for just that row — added 2026-09-25 for
  // MainAccountLedgerView, which shows PAYMENT_TRANSFER as "Deposit" on
  // that one table only (real bank money coming in) without renaming
  // "Transfer" everywhere else this type renders. The parent sets it per
  // row when building its own `rows` array; most callers never set it.
  //
  // Each row needs a `player_name` field already resolved by the parent
  // (name-lookup is a per-view concern today, e.g. via its own players list)
  // — this component never fetches or looks up a name itself.
  showPlayer: { type: Boolean, default: false },
  // row => path string, or null/undefined to render plain text (Cashier's
  // ActiveGameDayView has no /roster/:id route to link to).
  playerTo: { type: Function, default: null },
  // The Status column only ever means anything for Payout approval states
  // (PENDING_APPROVAL/APPROVED/REJECTED/TRANSFER_FAILED) — every other type
  // is always POSTED, rendering no badge. Defaults on (back-office ledgers
  // that regularly surface payouts want it); the Cashier's own Game-Day
  // activity feed turns it off (2026-09-22) — a mostly-blank column with no
  // real use on that screen.
  showStatus: { type: Boolean, default: true },
  // The "Type" column header reads oddly once every row already belongs to
  // one player (e.g. ActiveGameDayView's per-player ledger experiment,
  // 2026-09-22) — "Action" fits better there. Values in the column are
  // unchanged either way (TRANSACTION_TYPES[row.type].label).
  typeLabel: { type: String, default: 'Type' },
  dateFormat: { type: String, default: 'time' }, // 'time' | 'datetime'
  voidable: { type: Boolean, default: false },
  canVoidFn: { type: Function, default: () => false },
})
defineEmits(['void'])

function formatTime(iso) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}
function formatDateTime(iso) {
  const d = new Date(iso)
  return `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} · ${formatTime(iso)}`
}
const N = n => `₦${Number(n).toLocaleString()}`

// Amount coloring (2026-09-22, per the ledger design review) — chips going
// out reads as a debit (red), money coming back in reads as a credit
// (green), so the Amount column reinforces the +/- sign rather than just
// repeating it in neutral ink. See transactionTypes.js's `amountTone`.
function amountToneClass(type) {
  const tone = TRANSACTION_TYPES[type]?.amountTone
  return tone ? `amount--${tone}` : ''
}

// Auto-approval attribution (2026-09-25) — a payout that cleared the
// auto-approval threshold (status APPROVED, approved_by null — see
// services._execute_payout_transfer) now shows WHO INITIATED it
// (recorded_by_name, resolved server-side by TransactionSerializer)
// instead of a generic "Auto-approved" badge, on every ledger that renders
// through this component.
function isAutoApprovedPayout(row) {
  return row.type === 'PAYOUT' && row.status === 'APPROVED' && !row.approved_by
}
function statusBadgeText(row) {
  return isAutoApprovedPayout(row) ? `Auto-${row.recorded_by_name || 'Cashier'}` : row.status.replace('_', ' ')
}
</script>

<template>
  <div class="ledger-table-wrap">
    <table class="ledger-table">
      <thead>
        <tr>
          <th class="col-lane" aria-hidden="true" />
          <th>{{ dateFormat === 'datetime' ? 'Date' : 'Time' }}</th>
          <th>{{ typeLabel }}</th>
          <th v-if="showPlayer">Player</th>
          <th class="num">Amount</th>
          <th class="num">Balance</th>
          <th v-if="showStatus">Status</th>
          <th v-if="voidable" class="col-action" aria-hidden="true" />
        </tr>
      </thead>
      <tbody>
        <tr v-if="!rows.length">
          <td class="empty" :colspan="3 + (showPlayer ? 1 : 0) + 2 + (showStatus ? 1 : 0) + (voidable ? 1 : 0)">Nothing recorded yet.</td>
        </tr>
        <tr v-for="row in rows" :key="row.id" :class="{ 'row--voided': row.is_voided }">
          <td class="col-lane"><span :class="`lane-${TRANSACTION_TYPES[row.type]?.lane || 'other'}`" /></td>
          <td class="mono">{{ dateFormat === 'datetime' ? formatDateTime(row.created_at) : formatTime(row.created_at) }}</td>
          <td>{{ row.type_label || TRANSACTION_TYPES[row.type]?.label || row.type }}</td>
          <td v-if="showPlayer">
            <RouterLink v-if="playerTo?.(row)" :to="playerTo(row)" class="player-link" @click.stop>{{ row.player_name }}</RouterLink>
            <span v-else>{{ row.player_name }}</span>
          </td>
          <td class="num mono" :class="amountToneClass(row.type)">{{ row.signed_amount > 0 ? '+' : '' }}{{ N(row.signed_amount) }}</td>
          <td class="num mono">
            <span v-if="row.is_voided" class="voided-label">VOIDED</span>
            <span v-else>{{ N(row.running_balance) }}</span>
          </td>
          <td v-if="showStatus">
            <span v-if="isAutoApprovedPayout(row)" class="badge badge--auto-approved">{{ statusBadgeText(row) }}</span>
            <span v-else-if="TRANSACTION_STATUS_BADGE[row.status]" class="badge" :class="`badge--${TRANSACTION_STATUS_BADGE[row.status]}`">{{ statusBadgeText(row) }}</span>
          </td>
          <td v-if="voidable" class="col-action">
            <button v-if="canVoidFn(row)" class="void-trigger" type="button" title="Void this entry" @click="$emit('void', row)">&#8942;</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.ledger-table-wrap { overflow-x: auto; }
/* font-family explicit, not just inherited from body — some engines don't
   reliably carry it onto table cells across every browser/zoom context,
   which is what made the ledger read as off-face from the rest of the
   app's Public Sans. Fixed 2026-09-22. */
.ledger-table { width: 100%; border-collapse: collapse; font-family: var(--font-sans); font-size: 12.5px; }

.ledger-table thead th {
  position: sticky;
  top: 0;
  background: var(--surface);
  text-align: left;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  padding: 0 10px 8px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.ledger-table th.num, .ledger-table td.num { text-align: right; }
.ledger-table th.col-lane, .ledger-table td.col-lane { padding: 6px 0 6px 4px; width: 38px; }
.ledger-table th.col-action, .ledger-table td.col-action { width: 32px; padding: 0; }

.ledger-table tbody td {
  height: var(--control-row-min);
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  color: var(--text-primary);
  vertical-align: middle;
}
.ledger-table tbody tr:last-child td { border-bottom: none; }
.ledger-table tbody tr.row--voided td { opacity: 0.55; text-decoration: line-through; }
.ledger-table tbody tr.row--voided td.col-lane { text-decoration: none; }

.ledger-table td.mono, .ledger-table td.num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.ledger-table td.empty { text-align: center; color: var(--text-secondary); padding: 20px 10px; font-family: var(--font-sans); }
.ledger-table td.amount--debit { color: var(--danger-text); }
.ledger-table td.amount--credit { color: var(--success-text); }

/* Was a bare 4px solid-color bar — upgraded 2026-09-21 to a proper
   tinted swatch (matching the Ledger Directions review artifact's
   ledger-row treatment) so the lane actually reads as a colored icon
   moment repeated down the table, not just a thin rule at the edge. */
.col-lane span {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: var(--radius-sm);
  font-size: 10px;
}
.col-lane span::before { content: '\25CF'; }
.col-lane .lane-chips    { background: var(--lane-chips-bg);    color: var(--lane-chips-icon); }
.col-lane .lane-payments { background: var(--lane-payments-bg); color: var(--lane-payments-icon); }
.col-lane .lane-other    { background: var(--lane-other-bg);    color: var(--lane-other-icon); }

.player-link { color: var(--text-primary); text-decoration: none; font-weight: 600; }
.player-link:hover { color: var(--accent-text); text-decoration: underline; }

.voided-label { font-weight: 700; letter-spacing: 0.04em; color: var(--status-voided-text); font-family: var(--font-sans); }

.void-trigger {
  border: none;
  background: none;
  color: var(--text-tertiary);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
}
.void-trigger:hover { background: var(--bg); color: var(--text-primary); }
</style>
