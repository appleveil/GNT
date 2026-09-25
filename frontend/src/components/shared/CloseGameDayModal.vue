<script setup>
import { computed } from 'vue'
import { useGameDayStore } from '@/stores/gameDay'
import { useCloseGameDay } from '@/composables/useCloseGameDay'
import { describeChipsVariance } from '@/utils/chipsVariance'

// Moved out of ActiveGameDayView.vue (2026-09-21) so the trigger can live in
// AppShell's topbar instead — see useCloseGameDay.js's header comment.
// Mounted once in App.vue, alongside AuthorizerConfirmModal/AppToast.
//
// Revised 2026-09-22 — the actions row branches into up to three steps
// (see useCloseGameDay.js's own header comment for the order):
//   1. close_blocked_reason (hard block, active players) — no actions,
//      just a dismiss.
//   2. chip_discrepancy (acknowledge-and-sign-off) — a reason textarea +
//      "Acknowledge & Continue".
//   3. rakeConfirmStep (rake is ₦0) — a yes/no prompt.
//   4. otherwise, the plain "Close Game-Day" button, which now hands off
//      to the shared Floor-Manager-PIN modal (or Owner-or-FM when a
//      discrepancy was just acknowledged) via useAuthorizerConfirm.
const gameDay = useGameDayStore()
const {
  preview, error, discrepancyReason, rakeConfirmStep,
  confirm, acknowledgeDiscrepancy, confirmNoRake, cancelRakeConfirm, cancel,
} = useCloseGameDay()

const tonightsVariance = computed(() => preview.value ? describeChipsVariance(preview.value.chips_variance) : null)
const outstandingAfterClose = computed(() => preview.value ? describeChipsVariance(preview.value.outstanding_chips_after_close) : null)
// Rake and tips are chips too — skimmed from play or handed to staff, but
// still chips that came back off the table, just not to a player's stack
// (see gaming.selectors.game_day_summary_data's own chips_variance comment).
// "Chips returned" here means the full reconciliation figure, not just
// CHIPS_IN — added 2026-09-28 after chips_in_total alone under-reported it.
const chipsReturnedTotal = computed(() =>
  preview.value
    ? Number(preview.value.chips_in_total) + Number(preview.value.rake_total) + Number(preview.value.tips_total)
    : 0,
)

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div v-if="preview" class="overlay">
    <div class="dialog card">
      <div class="eyebrow">Close Game-Day #{{ gameDay.current?.number }}?</div>

      <div class="stats">
        <div class="stat-row"><span>Total players</span><span class="money">{{ preview.num_players_seated }}</span></div>
        <div class="stat-row"><span>Chips out</span><span class="money">{{ N(preview.chips_out_total) }}</span></div>
        <div class="stat-row"><span>Chips returned</span><span class="money">{{ N(chipsReturnedTotal) }}</span></div>
        <div class="stat-row"><span>Payments received</span><span class="money">{{ N(preview.total_payments) }}</span></div>
        <div class="stat-row"><span>— of which Rake / Tips</span><span class="money">{{ N(preview.rake_total) }} / {{ N(preview.tips_total) }}</span></div>
        <div class="stat-row">
          <span>{{ tonightsVariance.label }} tonight <small>(chips out − chips returned)</small></span>
          <span class="money" :class="tonightsVariance.className">{{ N(tonightsVariance.amount) }}</span>
        </div>
        <div class="stat-row">
          <span>{{ outstandingAfterClose.label }} <small>(club-wide, after this close)</small></span>
          <span class="money" :class="outstandingAfterClose.className">{{ N(outstandingAfterClose.amount) }}</span>
        </div>
        <div class="stat-row stat-row--total"><span>Game balance</span><span class="money">{{ N(preview.game_balance) }}</span></div>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>

      <!-- Blocked outright — see gaming.services.close_blocked_reason.
           Nothing to confirm until this is resolved, so no actions row. -->
      <template v-if="preview.close_blocked_reason">
        <p class="form-error">{{ preview.close_blocked_reason }}</p>
        <div class="actions">
          <button class="btn btn--secondary" type="button" @click="cancel">Close</button>
        </div>
      </template>

      <!-- Chip discrepancy — doesn't block closing, but needs a reason
           before it can proceed (see gaming.services.game_day_chip_discrepancy). -->
      <template v-else-if="preview.chip_discrepancy">
        <p class="discrepancy-note">
          Chips don't reconcile — ₦{{ N(preview.chip_discrepancy.amount) }} {{ preview.chip_discrepancy.direction }}.
          A player may have walked off with chips, or this may be a miscount — either way, this
          needs a reason and an Owner or Floor Manager's sign-off to close anyway.
        </p>
        <textarea
          v-model="discrepancyReason" class="reason-field" rows="3"
          placeholder="What happened? (required)"
        />
        <div class="actions">
          <button class="btn btn--secondary" type="button" @click="cancel">Cancel</button>
          <button
            class="btn btn--primary" type="button" :disabled="!discrepancyReason.trim()"
            @click="acknowledgeDiscrepancy"
          >Acknowledge &amp; Continue</button>
        </div>
      </template>

      <!-- Rake is exactly ₦0 — likely a miscount (forgotten entry), not
           necessarily a real no-rake night. One extra confirmation before
           it's locked in. -->
      <template v-else-if="rakeConfirmStep">
        <p class="rake-check">Rake for tonight is ₦0 — are you sure none was taken?</p>
        <div class="actions">
          <button class="btn btn--secondary" type="button" @click="cancelRakeConfirm">Go back</button>
          <button class="btn btn--primary" type="button" @click="confirmNoRake">Yes, ₦0 is correct</button>
        </div>
      </template>

      <div v-else class="actions">
        <button class="btn btn--secondary" type="button" @click="cancel">Cancel</button>
        <button class="btn btn--primary" type="button" @click="confirm">Close Game-Day</button>
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
  /* Below AuthorizerConfirmModal's 100 — this stays open (preview.value)
     while the PIN step layers on top of it for the actual close/discrepancy
     sign-off, same as TransactionEntryModal's own overlay. */
  z-index: 90;
}
.dialog { width: 480px; max-width: 92vw; box-shadow: var(--shadow-md); padding: 24px; }
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
.discrepancy-note {
  font-size: 13px;
  line-height: 1.6;
  color: var(--warning-text);
  background: var(--warning-bg);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  margin-top: 12px;
}
.reason-field {
  width: 100%;
  margin-top: 10px;
  padding: 10px 12px;
  font-family: var(--font-sans);
  font-size: 13.5px;
  color: var(--text-primary);
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  resize: vertical;
}
.rake-check {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--warning-text);
  background: var(--warning-bg);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  margin-top: 12px;
}
.actions { display: flex; gap: 14px; margin-top: 16px; }
.actions .btn { flex: 1; }
</style>
