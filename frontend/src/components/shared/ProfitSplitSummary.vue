<script setup>
// Extracted from views/owner/deals/DealProfitSplitView.vue (2026-10-02) so
// the Ledgers -> Deals page's "click Deal ID -> summary pop-up" (no
// navigation — see LedgersDealsView.vue) can show the exact same card
// without duplicating its markup. `status` is the shape both
// GET /deals/profit-split/{player_id}/ and the new
// GET /deals/profit-split/arrangement/{id}/ return: { arrangement,
// covered_this_period, cumulative_covered, available_stake_this_period,
// is_exhausted, exhausted_reason }. The badge reads the arrangement's own
// `is_active` rather than being hardcoded "ACTIVE" — DealProfitSplitView
// only ever shows a player's current (always active) arrangement, but the
// Deals ledger's pop-up can reference a since-ended one too.
//
// `showEndButton` stays off by default — ending an arrangement is a
// specific action on DealProfitSplitView's own page, not something a
// read-only historical pop-up should offer. That page passes it on and
// handles the confirm+API call itself (keeps this component purely
// presentational, same split LedgerTable.vue/RowActionsMenu.vue already use).
defineProps({
  status: { type: Object, required: true },
  showEndButton: { type: Boolean, default: false },
})
defineEmits(['end'])

const PAYOUT_BASIS_LABEL = { BEFORE_BUYIN: 'Before buy-in', AFTER_BUYIN: 'After buy-in' }
const PAYOUT_METHOD_LABEL = { STAKE_RATIO: 'Ratio: according to stake', CUSTOM_RATIO: 'Ratio: house percentage', FIXED: 'Fixed amount' }

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="card status-card">
    <div class="status-head">
      <span class="badge" :class="status.arrangement.is_active ? 'badge--approved' : 'badge--closed'">
        {{ status.arrangement.is_active ? 'ACTIVE' : 'ENDED' }}
      </span>
      <span class="status-since">since {{ formatDate(status.arrangement.created_at) }}</span>
    </div>

    <div class="status-grid">
      <div class="status-box">
        <div class="status-label">Covered this period</div>
        <div class="status-value">{{ N(status.covered_this_period) }}</div>
      </div>
      <div class="status-box">
        <div class="status-label">Cumulative covered</div>
        <div class="status-value">{{ N(status.cumulative_covered) }}</div>
      </div>
      <div class="status-box">
        <div class="status-label">Available this period</div>
        <div class="status-value">{{ N(status.available_stake_this_period) }}</div>
      </div>
    </div>

    <p v-if="status.is_exhausted" class="exhausted-note">Exhausted — {{ status.exhausted_reason }}</p>

    <div class="config-lines">
      <div class="config-line">
        <span class="config-key">Stake</span>
        <span>
          {{ status.arrangement.house_stake_pct }}% of buy-in, capped at {{ N(status.arrangement.cap_amount) }}
          {{ status.arrangement.reset_cadence === 'ONE_OFF' ? 'total' : 'per game' }}
        </span>
      </div>
      <div class="config-line">
        <span class="config-key">Payout</span>
        <span>
          {{ PAYOUT_BASIS_LABEL[status.arrangement.payout_basis] }}, {{ PAYOUT_METHOD_LABEL[status.arrangement.payout_split_method] }}
          <template v-if="status.arrangement.payout_split_method === 'CUSTOM_RATIO'"> ({{ status.arrangement.custom_ratio_pct }}%)</template>
          <template v-if="status.arrangement.payout_split_method === 'FIXED'"> ({{ N(status.arrangement.fixed_amount) }})</template>
        </span>
      </div>
    </div>

    <button v-if="showEndButton" class="btn btn--danger end-btn" type="button" @click="$emit('end')">End arrangement</button>
  </div>
</template>

<style scoped>
.status-card { padding: 18px 20px; }
.status-head { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.status-since { font-size: 11.5px; color: var(--text-tertiary); }
.status-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
.status-box { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px 12px; }
.status-label { font-size: 9.5px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 4px; }
.status-value { font-family: var(--font-mono); font-weight: 700; font-size: 15px; color: var(--text-primary); }
.exhausted-note { font-size: 12px; color: var(--warning-text); background: var(--warning-bg); border-radius: var(--radius-sm); padding: 8px 10px; margin: 0 0 12px; }

.config-lines { border-top: 1px solid var(--border); padding-top: 12px; margin-bottom: 14px; }
.config-line { display: flex; gap: 8px; font-size: 12.5px; color: var(--text-secondary); padding: 3px 0; line-height: 1.5; }
.config-key { font-weight: 700; color: var(--text-tertiary); flex-shrink: 0; width: 52px; }

.end-btn { width: 100%; }
</style>
