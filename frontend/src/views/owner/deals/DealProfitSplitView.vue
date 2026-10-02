<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/axios'
import { formatAmountForDisplay, parseAmountInput } from '@/utils/amountInput'
import { useToast } from '@/composables/useToast'
import { useFormValidation, minPct, maxPct } from '@/composables/useFormValidation'
import ProfitSplitSummary from '@/components/shared/ProfitSplitSummary.vue'

// "Deals" Stake and Profit Split (2026-09-23) — mirrors mobile's
// ProfitSplitScreen.tsx/ProfitSplitDetailScreen.tsx, wired to the real
// backend. Two real differences from the mobile mockup, both because this
// talks to the actual ProfitSplitArrangement model instead of a local log:
//
// - Stake/Payout are opt-in toggles here too, but the backend model has no
//   "off" state for either — house_stake_pct/cap_amount are always present
//   fields, and payout_split_method always defaults to STAKE_RATIO (which
//   the backend REJECTS when house_stake_pct is 0 — see
//   _validate_profit_split_arrangement). So "Stake off" sends
//   house_stake_pct/cap_amount as 0, and "Payout off" sends
//   payout_split_method: CUSTOM_RATIO, custom_ratio_pct: 0 — a real,
//   harmless no-op configuration, never omitted fields.
// - Ending an arrangement here has no reason field: mobile's local-only
//   "End confirm+reason" entry doesn't correspond to any real column —
//   deactivate_profit_split_arrangement(arrangement, operator) only ever
//   sets is_active/deactivated_at. A reason typed here would have nowhere
//   to go, so this is confirm-only.
const route = useRoute()
const router = useRouter()
const toast = useToast()

const player = ref(null)
const status = ref(null) // GET /deals/profit-split/{id}/ response, or null
const loading = ref(true)
const showForm = ref(false)
const deactivating = ref(false)
const confirmEnd = ref(false)

async function load() {
  loading.value = true
  try {
    const [playerRes, statusRes] = await Promise.all([
      api.get(`/players/${route.params.playerId}/`),
      api.get(`/deals/profit-split/${route.params.playerId}/`),
    ])
    player.value = playerRes.data
    status.value = statusRes.data
    showForm.value = !status.value
  } catch {
    toast.error('Could not load this arrangement.')
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function onEndArrangement() {
  deactivating.value = true
  try {
    await api.post(`/deals/profit-split/${status.value.arrangement.id}/deactivate/`)
    toast.success('Arrangement ended.')
    confirmEnd.value = false
    await load()
  } catch {
    toast.error('Could not end this arrangement.')
  } finally {
    deactivating.value = false
  }
}

// ── Create form ────────────────────────────────────────────────────────
const stakeOn = ref(false)
const housePct = ref('')
const capAmount = ref('')
const displayCapAmount = computed(() => formatAmountForDisplay(capAmount.value))
const resetCadence = ref('ONE_OFF')
const endsAt = ref('')
const maxResets = ref('')
const maxCumulativeValue = ref('')
const displayMaxCumulativeValue = computed(() => formatAmountForDisplay(maxCumulativeValue.value))

const payoutOn = ref(false)
const payoutBasis = ref('AFTER_BUYIN')
const payoutSplitMethod = ref('STAKE_RATIO')
const customRatioPct = ref('')
const fixedAmount = ref('')
const displayFixedAmount = computed(() => formatAmountForDisplay(fixedAmount.value))
const fixedOffset = ref('')
const displayFixedOffset = computed(() => formatAmountForDisplay(fixedOffset.value))

// "Ratio: according to stake" is meaningless with no stake set — switch
// away from it automatically if Stake is turned off while it's selected
// (mirrors the mobile app's own rule).
watch(stakeOn, on => {
  if (!on && payoutSplitMethod.value === 'STAKE_RATIO') payoutSplitMethod.value = 'CUSTOM_RATIO'
})

const submitting = ref(false)

// House stake % and the custom payout % are the only two free-text numeric
// fields here that can be out of range — validated live (2026-10-02, see
// PLAN.md's dated entry on the site-wide validation pass). Each rule is a
// no-op while its section is off/inapplicable, so turning Stake or Payout
// off never blocks Save on a percentage that no longer matters.
const { touched, errors, isValid, formError, touch, applyServerErrors } = useFormValidation({
  housePct: { value: housePct, rules: [v => (stakeOn.value ? minPct()(v) || maxPct()(v) : null)] },
  customRatioPct: {
    value: customRatioPct,
    rules: [v => (payoutOn.value && payoutSplitMethod.value === 'CUSTOM_RATIO' ? minPct()(v) || maxPct()(v) : null)],
  },
})
const canSubmit = computed(() => (stakeOn.value || payoutOn.value) && isValid.value)

async function onSubmit() {
  if (!canSubmit.value) return
  submitting.value = true
  try {
    const payload = {
      player: player.value.id,
      house_stake_pct: stakeOn.value ? String(Number(housePct.value) || 0) : '0',
      cap_amount: stakeOn.value ? (Number(capAmount.value) || 0).toFixed(0) : '0',
      reset_cadence: stakeOn.value ? resetCadence.value : 'ONE_OFF',
    }
    if (stakeOn.value && resetCadence.value !== 'ONE_OFF') {
      if (endsAt.value) payload.ends_at = new Date(endsAt.value).toISOString()
      if (maxResets.value) payload.max_resets = Number(maxResets.value)
      if (maxCumulativeValue.value) payload.max_cumulative_value = (Number(maxCumulativeValue.value) || 0).toFixed(0)
    }
    if (payoutOn.value) {
      payload.payout_basis = payoutBasis.value
      payload.payout_split_method = payoutSplitMethod.value
      if (payoutSplitMethod.value === 'CUSTOM_RATIO') payload.custom_ratio_pct = String(Number(customRatioPct.value) || 0)
      if (payoutSplitMethod.value === 'FIXED') {
        payload.fixed_amount = (Number(fixedAmount.value) || 0).toFixed(0)
        if (fixedOffset.value) payload.fixed_offset = (Number(fixedOffset.value) || 0).toFixed(0)
      }
    } else {
      payload.payout_split_method = 'CUSTOM_RATIO'
      payload.custom_ratio_pct = '0'
    }
    await api.post('/deals/profit-split/', payload)
    toast.success(`Arrangement set up for ${player.value.display_name}.`)
    router.push(`/deals/${route.params.playerId}`)
  } catch (err) {
    applyServerErrors(err)
  } finally {
    submitting.value = false
  }
}

const RESET_CADENCE_LABEL = { ONE_OFF: 'One-off', PER_GAME: 'Per game' }

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="page">
    <button class="back-btn" type="button" @click="router.push(`/deals/${route.params.playerId}`)">&larr; {{ player?.display_name || 'Back' }}</button>

    <p v-if="loading" class="muted">Loading…</p>

    <template v-else-if="player">
      <div class="page-header">
        <h1>Stake and Profit Split</h1>
        <p>{{ player.display_name }} &middot; {{ player.account_code }}</p>
      </div>

      <ProfitSplitSummary v-if="status" :status="status" show-end-button class="status-card-wrap" @end="confirmEnd = true" />

      <button v-if="status && !showForm" class="link-btn" type="button" @click="showForm = true">Set up a new arrangement &rarr;</button>

      <form v-if="showForm" class="deal-form" novalidate @submit.prevent="onSubmit">
        <p v-if="status" class="replace-note">Setting up a new arrangement replaces the active one above.</p>

        <div class="section">
          <label class="toggle-row">
            <span class="toggle-label">Stake — house covers part of buy-in</span>
            <button type="button" class="switch" :class="{ 'switch--on': stakeOn }" role="switch" :aria-checked="stakeOn" @click="stakeOn = !stakeOn">
              <span class="switch-knob" />
            </button>
          </label>

          <template v-if="stakeOn">
            <label class="field">
              <span class="field-label">House stake %</span>
              <input
                v-model="housePct" type="number" step="0.5" placeholder="0" class="ff"
                :class="{ 'input--invalid': touched.housePct && errors.housePct }" @blur="touch('housePct')"
              />
              <p v-if="touched.housePct && errors.housePct" class="field-error">{{ errors.housePct }}</p>
            </label>
            <label class="field">
              <span class="field-label">Cap per game</span>
              <input
                :value="displayCapAmount" type="text" inputmode="numeric" placeholder="0" class="ff"
                @input="e => { capAmount = parseAmountInput(e.target.value); e.target.value = displayCapAmount }"
              />
            </label>
            <label class="field">
              <span class="field-label">Resets</span>
              <select v-model="resetCadence" class="ff">
                <option value="ONE_OFF">One-off (no reset)</option>
                <option value="PER_GAME">Per game</option>
              </select>
            </label>
            <!-- Order matches the end-condition check itself (whichever is
                 reached first ends the arrangement — see
                 selectors.profit_split_status): max total value, then end
                 date, then number of games. -->
            <template v-if="resetCadence !== 'ONE_OFF'">
              <label class="field">
                <span class="field-label">Max total value covered <span class="optional">(optional)</span></span>
                <input
                  :value="displayMaxCumulativeValue" type="text" inputmode="numeric" placeholder="Unlimited" class="ff"
                  @input="e => { maxCumulativeValue = parseAmountInput(e.target.value); e.target.value = displayMaxCumulativeValue }"
                />
              </label>
              <label class="field">
                <span class="field-label">Ends on <span class="optional">(optional)</span></span>
                <input v-model="endsAt" type="date" class="ff" />
              </label>
              <label class="field">
                <span class="field-label">Number of games <span class="optional">(optional)</span></span>
                <input v-model="maxResets" type="number" min="1" placeholder="Unlimited" class="ff" />
              </label>
            </template>
          </template>
        </div>

        <div class="section">
          <label class="toggle-row">
            <span class="toggle-label">Payout — house takes a cut when chips return</span>
            <button type="button" class="switch" :class="{ 'switch--on': payoutOn }" role="switch" :aria-checked="payoutOn" @click="payoutOn = !payoutOn">
              <span class="switch-knob" />
            </button>
          </label>

          <template v-if="payoutOn">
            <label class="field">
              <span class="field-label">Basis</span>
              <select v-model="payoutBasis" class="ff">
                <option value="BEFORE_BUYIN">Before buy-in</option>
                <option value="AFTER_BUYIN">After buy-in</option>
              </select>
            </label>
            <div class="radio-group">
              <label class="radio-row" :class="{ 'radio-row--disabled': !stakeOn || !(Number(housePct) > 0) }">
                <input
                  v-model="payoutSplitMethod" type="radio" value="STAKE_RATIO"
                  :disabled="!stakeOn || !(Number(housePct) > 0)"
                />
                Ratio: according to stake
              </label>
              <label class="radio-row">
                <input v-model="payoutSplitMethod" type="radio" value="CUSTOM_RATIO" />
                Ratio: house percentage
              </label>
              <label class="radio-row">
                <input v-model="payoutSplitMethod" type="radio" value="FIXED" />
                Fixed amount
              </label>
            </div>
            <label v-if="payoutSplitMethod === 'CUSTOM_RATIO'" class="field">
              <span class="field-label">House percentage</span>
              <input
                v-model="customRatioPct" type="number" step="0.5" placeholder="0" class="ff"
                :class="{ 'input--invalid': touched.customRatioPct && errors.customRatioPct }"
                @blur="touch('customRatioPct')"
              />
              <p v-if="touched.customRatioPct && errors.customRatioPct" class="field-error">{{ errors.customRatioPct }}</p>
            </label>
            <template v-if="payoutSplitMethod === 'FIXED'">
              <label class="field">
                <span class="field-label">Fixed amount</span>
                <input
                  :value="displayFixedAmount" type="text" inputmode="numeric" placeholder="0" class="ff"
                  @input="e => { fixedAmount = parseAmountInput(e.target.value); e.target.value = displayFixedAmount }"
                />
              </label>
              <label class="field">
                <span class="field-label">Off-set <span class="optional">(optional)</span></span>
                <input
                  :value="displayFixedOffset" type="text" inputmode="numeric" placeholder="0" class="ff"
                  @input="e => { fixedOffset = parseAmountInput(e.target.value); e.target.value = displayFixedOffset }"
                />
              </label>
            </template>
          </template>
        </div>

        <p v-if="formError" class="form-error">{{ formError }}</p>

        <button class="btn btn--primary submit-btn" type="submit" :disabled="!canSubmit || submitting">
          {{ submitting ? 'Saving…' : 'Save arrangement' }}
        </button>
      </form>
    </template>

    <div v-if="confirmEnd" class="overlay" @click.self="deactivating || (confirmEnd = false)">
      <div class="dialog card">
        <div class="eyebrow">End this arrangement?</div>
        <p class="dialog-text">The per-period cap stops applying to future buy-ins — this doesn't undo any stake already covered.</p>
        <div class="dialog-actions">
          <button class="btn btn--secondary" type="button" :disabled="deactivating" @click="confirmEnd = false">Cancel</button>
          <button class="btn btn--danger" type="button" :disabled="deactivating" @click="onEndArrangement">{{ deactivating ? 'Ending…' : 'End it' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 560px; }
.back-btn { border: none; background: none; font-size: 13.5px; font-weight: 600; color: var(--text-secondary); cursor: pointer; padding: 4px 0; margin-bottom: 16px; }
.back-btn:hover { color: var(--text-primary); }
.muted { color: var(--text-secondary); font-size: 13px; }

.page-header { margin-bottom: 20px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 2px; }
.page-header p { font-size: 12.5px; color: var(--text-tertiary); margin: 0; }

.status-card-wrap { margin-bottom: 16px; }

.link-btn { display: block; border: none; background: none; font-size: 13px; font-weight: 700; color: var(--accent-text); cursor: pointer; padding: 8px 0 20px; }
.link-btn:hover { text-decoration: underline; }

.replace-note { font-size: 12px; color: var(--text-tertiary); margin: 0 0 16px; }

.deal-form { display: flex; flex-direction: column; }
.section { border: 1px solid var(--border); border-radius: var(--radius-md); padding: 16px 18px; margin-bottom: 16px; }
.toggle-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; cursor: pointer; }
.toggle-label { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }

.switch { width: 40px; height: 24px; border-radius: 12px; border: none; background: var(--border-strong); position: relative; cursor: pointer; flex-shrink: 0; transition: background 0.15s; }
.switch--on { background: var(--accent); }
.switch-knob { position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 50%; background: #fff; transition: transform 0.15s; }
.switch--on .switch-knob { transform: translateX(16px); }

.field { display: block; margin-top: 14px; }
.field-label { display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
.optional { font-weight: 400; color: var(--text-tertiary); }
.ff {
  width: 100%;
  height: var(--control-row-min);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 14px;
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text-primary);
  background: var(--surface);
}
.ff:focus { outline: none; border-color: var(--accent); }

.radio-group { display: flex; flex-direction: column; gap: 10px; margin-top: 14px; }
.radio-row { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-primary); cursor: pointer; }
.radio-row--disabled { opacity: 0.45; cursor: default; }

.submit-btn { width: 100%; }

.overlay { position: fixed; inset: 0; background: rgba(20, 25, 32, 0.5); display: flex; align-items: center; justify-content: center; z-index: 100; }
.dialog { width: 420px; max-width: 92vw; box-shadow: var(--shadow-md); padding: 24px; }
.eyebrow { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.dialog-text { font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin: 8px 0 0; }
.dialog-actions { display: flex; gap: 14px; margin-top: 20px; }
.dialog-actions .btn { flex: 1; }
</style>
