<script setup>
import { computed } from 'vue'
import { useGameDayStore } from '@/stores/gameDay'
import { useCloseGameDay } from '@/composables/useCloseGameDay'
import { describeChipsVariance } from '@/utils/chipsVariance'

// Moved out of ActiveGameDayView.vue (2026-09-21) so the trigger can live in
// AppShell's topbar instead — see useCloseGameDay.js's header comment.
// Mounted once in App.vue, alongside AuthorizerConfirmModal/AppToast.
const gameDay = useGameDayStore()
const { preview, closing, error, confirm, cancel } = useCloseGameDay()

const tonightsVariance = computed(() => preview.value ? describeChipsVariance(preview.value.chips_variance) : null)
const outstandingAfterClose = computed(() => preview.value ? describeChipsVariance(preview.value.outstanding_chips_after_close) : null)

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div v-if="preview" class="overlay">
    <div class="dialog card">
      <div class="eyebrow">Close Game-Day #{{ gameDay.current?.number }}?</div>
      <p class="muted">This locks entries — only the Owner can amend after closing.</p>

      <div class="stats">
        <div class="stat-row"><span>Players seated</span><span class="money">{{ preview.num_players_seated }}</span></div>
        <div class="stat-row"><span>Chips out</span><span class="money">{{ N(preview.chips_out_total) }}</span></div>
        <div class="stat-row"><span>Chips returned</span><span class="money">{{ N(preview.chips_in_total) }}</span></div>
        <div class="stat-row"><span>Payments received</span><span class="money">{{ N(preview.total_payments) }}</span></div>
        <div class="stat-row"><span>Rake / Tips</span><span class="money">{{ N(preview.rake_total) }} / {{ N(preview.tips_total) }}</span></div>
        <div class="stat-row">
          <span>{{ tonightsVariance.label }} tonight <small>(out − in − rake − tips)</small></span>
          <span class="money" :class="tonightsVariance.className">{{ N(tonightsVariance.amount) }}</span>
        </div>
        <div class="stat-row">
          <span>{{ outstandingAfterClose.label }} <small>(club-wide, after this close)</small></span>
          <span class="money" :class="outstandingAfterClose.className">{{ N(outstandingAfterClose.amount) }}</span>
        </div>
        <div class="stat-row stat-row--total"><span>Game balance</span><span class="money">{{ N(preview.game_balance) }}</span></div>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>

      <div class="actions">
        <button class="btn btn--secondary" type="button" @click="cancel">Cancel</button>
        <button class="btn btn--primary" type="button" :disabled="closing" @click="confirm">
          {{ closing ? 'Closing…' : 'Close Game-Day' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(20, 25, 32, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.dialog { width: 480px; max-width: 92vw; box-shadow: var(--shadow-md); padding: 24px; }
.muted { color: var(--text-secondary); font-size: 13px; line-height: 1.6; margin: 8px 0 0; }
.stats { margin-top: 12px; }
.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13.5px;
  color: var(--text-secondary);
}
.stat-row small { font-size: 10.5px; color: var(--text-tertiary); }
.stat-row--total { border-bottom: none; font-weight: 700; color: var(--text-primary); }
.money { font-family: var(--font-mono); font-weight: 700; color: var(--text-primary); }
.money.variance--deficit { color: var(--warning-text); }
.money.variance--excess { color: var(--accent-text); }
.money.variance--balanced { color: var(--text-tertiary); }
.form-error {
  font-size: 13px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  margin-top: 12px;
}
.actions { display: flex; gap: 14px; margin-top: 16px; }
.actions .btn { flex: 1; }
</style>
