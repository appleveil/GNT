<script setup>
import { TRANSACTION_TYPES, TRANSACTION_STATUS_BADGE } from '@/constants/transactionTypes'

// Shared tabular ledger row renderer (2026-09-17) — replaces 7 near-identical
// hand-rolled `.feed-row`/`.ledger-row`/`.activity-row` implementations
// (GameDayLedgerView, GameDayDetailView, OutstandingView, RosterDetailView
// x2, ActiveGameDayView, PlayerDetailView) with one presentational
// component: no API calls, no store access — the parent still fetches its
// own data and handles voiding exactly as before, just renders through this
// instead of its own markup. See PLAN.md's "Ledgers: list rows → tabular
// Ledger Grid" entry for the chosen direction and per-view column mapping.
//
// Row height comes from --control-row-min (44px Cashier / 40px Accountant,
// already themed via :root vs .theme-accountant) — so Cashier's tables stay
// touch-sized and Accountant's stay desktop-dense with no separate density
// prop needed here.
const props = defineProps({
  rows: { type: Array, required: true },
  // Each row needs a `player_name` field already resolved by the parent
  // (name-lookup is a per-view concern today, e.g. via its own players list)
  // — this component never fetches or looks up a name itself.
  showPlayer: { type: Boolean, default: false },
  // row => path string, or null/undefined to render plain text (Cashier's
  // GameDayLedgerView has no /roster/:id route to link to).
  playerTo: { type: Function, default: null },
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
</script>

<template>
  <div class="ledger-table-wrap">
    <table class="ledger-table">
      <thead>
        <tr>
          <th class="col-lane" aria-hidden="true" />
          <th>{{ dateFormat === 'datetime' ? 'Date' : 'Time' }}</th>
          <th>Type</th>
          <th v-if="showPlayer">Player</th>
          <th class="num">Amount</th>
          <th class="num">Balance</th>
          <th>Status</th>
          <th v-if="voidable" class="col-action" aria-hidden="true" />
        </tr>
      </thead>
      <tbody>
        <tr v-if="!rows.length">
          <td class="empty" :colspan="3 + (showPlayer ? 1 : 0) + 2 + 1 + (voidable ? 1 : 0)">Nothing recorded yet.</td>
        </tr>
        <tr v-for="row in rows" :key="row.id" :class="{ 'row--voided': row.is_voided }">
          <td class="col-lane"><span :class="`lane-${TRANSACTION_TYPES[row.type]?.lane || 'other'}`" /></td>
          <td class="mono">{{ dateFormat === 'datetime' ? formatDateTime(row.created_at) : formatTime(row.created_at) }}</td>
          <td>{{ TRANSACTION_TYPES[row.type]?.label || row.type }}</td>
          <td v-if="showPlayer">
            <RouterLink v-if="playerTo?.(row)" :to="playerTo(row)" class="player-link" @click.stop>{{ row.player_name }}</RouterLink>
            <span v-else>{{ row.player_name }}</span>
          </td>
          <td class="num mono">{{ row.signed_amount > 0 ? '+' : '' }}{{ N(row.signed_amount) }}</td>
          <td class="num mono">
            <span v-if="row.is_voided" class="voided-label">VOIDED</span>
            <span v-else>{{ N(row.running_balance) }}</span>
          </td>
          <td>
            <span v-if="TRANSACTION_STATUS_BADGE[row.status]" class="badge" :class="`badge--${TRANSACTION_STATUS_BADGE[row.status]}`">{{ row.status.replace('_', ' ') }}</span>
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
.ledger-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }

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
.ledger-table th.col-lane, .ledger-table td.col-lane { padding: 0; width: 4px; }
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

.col-lane span { display: block; height: 100%; min-height: 20px; }
.col-lane .lane-chips { background: var(--lane-chips-icon); }
.col-lane .lane-payments { background: var(--lane-payments-icon); }
.col-lane .lane-other { background: var(--lane-other-icon); }

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
