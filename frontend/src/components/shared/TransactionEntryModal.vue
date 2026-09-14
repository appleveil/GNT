<script setup>
import { ref, computed } from 'vue'
import api from '@/api/axios'
import { useAuthorizerConfirm } from '@/composables/useAuthorizerConfirm'
import { TRANSACTION_TYPES } from '@/constants/transactionTypes'

// A bottom sheet for recording one Transaction — used from ActiveGameDayView
// for both per-player entries (Issue Chips, Chips In, Cash/POS/Transfer
// payments) and general/day-level ones (Rake, Tip — player is null, see
// CONCEPT.md's "Rake is not a per-player entry").
const props = defineProps({
  type: { type: String, required: true },
  player: { type: Object, default: null }, // seated-player row, or null for Rake/Tip
  gameDayId: { type: Number, required: true },
})
const emit = defineEmits(['close', 'saved'])

const { confirm: confirmFm } = useAuthorizerConfirm()

const config = computed(() => TRANSACTION_TYPES[props.type])

const CURRENCIES = ['NGN', 'USD', 'GBP', 'EUR', 'OTHER']

const amount = ref('')
const notes = ref('')
const provider = ref('')
const currency = ref('NGN')
const conversionRate = ref('')
const rateHint = ref('')
const submitting = ref(false)
const error = ref('')

async function onCurrencyChange() {
  rateHint.value = ''
  conversionRate.value = ''
  if (currency.value === 'NGN') return
  try {
    const { data } = await api.get('/conversion-rates/')
    // Most recent row for this currency, preferring one scoped to tonight's
    // game-day over the standing/default (game_day: null) — see
    // ConversionRate.game_day's docstring. List is already -created_at order.
    const match = data.find(r => r.currency === currency.value && r.game_day === props.gameDayId)
      || data.find(r => r.currency === currency.value && r.game_day === null)
    if (match) {
      conversionRate.value = match.rate_to_naira
      rateHint.value = `Current rate: ₦${Number(match.rate_to_naira).toLocaleString()} — override if this changed`
    }
  } catch {
    // No rate on file — cashier enters one manually, nothing to prefill.
  }
}

// amount is always the Naira-equivalent on the wire (Transaction.amount's own
// convention); for non-NGN cash the cashier enters the foreign-currency figure
// and we compute the equivalent from the rate.
const nairaAmount = computed(() => {
  const entered = Number(amount.value) || 0
  if (currency.value === 'NGN') return entered
  return entered * (Number(conversionRate.value) || 0)
})

// Client-side mirror of record_transaction's chips_limit guard (backend still
// enforces it — this is just so the cashier sees the block before submitting).
const chipsRemaining = computed(() => {
  if (props.type !== 'CHIPS_OUT' || !props.player || props.player.chips_limit == null) return null
  return Number(props.player.chips_limit) - Number(props.player.chips_used_today || 0)
})
const exceedsChipsLimit = computed(
  () => chipsRemaining.value !== null && Number(amount.value || 0) > chipsRemaining.value,
)

const canSubmit = computed(() => {
  if (!amount.value || Number(amount.value) <= 0) return false
  if (exceedsChipsLimit.value) return false
  if (config.value.needsCurrency && currency.value !== 'NGN' && !conversionRate.value) return false
  return true
})

function buildNotes() {
  if (config.value.needsProvider && provider.value) {
    return notes.value ? `${provider.value} — ${notes.value}` : provider.value
  }
  return notes.value
}

async function doSave(extra = {}) {
  const payload = {
    game_day: props.gameDayId,
    player: props.player ? props.player.id : null,
    type: props.type,
    amount: nairaAmount.value.toFixed(2),
    notes: buildNotes(),
    ...extra,
  }
  if (config.value.needsCurrency && currency.value !== 'NGN') {
    payload.currency = currency.value
    payload.conversion_rate = conversionRate.value
  }
  await api.post('/transactions/', payload)
}

async function onSubmit() {
  error.value = ''

  if (!config.value.physicalCount) {
    submitting.value = true
    try {
      await doSave()
      emit('saved')
    } catch (err) {
      error.value = Object.values(err.response?.data || {})[0]?.[0]
        || err.response?.data?.detail
        || 'Could not save this entry.'
    } finally {
      submitting.value = false
    }
    return
  }

  // Physical count — hand off to the Floor-Manager-only PIN sheet (see
  // useAuthorizerConfirm's 'fm-only' mode). This modal stays mounted
  // underneath it: if the PIN step is cancelled, the cashier lands right
  // back here with the amount/notes they'd already entered still intact.
  confirmFm({
    title: config.value.actionLabel,
    subtitle: props.player ? `for ${props.player.display_name} · ${props.player.account_code}` : "Tonight's box count",
    mode: 'fm-only',
    onSubmit: async fmPayload => {
      await doSave(fmPayload)
      emit('saved')
    },
  })
}

const N = n => `₦${Number(n || 0).toLocaleString()}`
</script>

<template>
  <div class="overlay">
    <div class="sheet">
      <div class="grip" />

      <div class="head">
        <div class="sheet-title">{{ config.actionLabel }}</div>
        <button class="close-btn" type="button" @click="emit('close')">&times;</button>
      </div>
      <div class="sheet-subtitle">
        {{ player ? `for ${player.display_name} · ${player.account_code}` : 'General — not tied to a player' }}
      </div>

      <div class="lbl">
        Amount
        <span v-if="chipsRemaining !== null" class="lbl-hint" :class="{ 'lbl-hint--danger': exceedsChipsLimit }">
          ({{ N(chipsRemaining) }} left of chips limit tonight)
        </span>
      </div>
      <div class="amount-box" :class="{ 'amount-box--danger': exceedsChipsLimit }">
        <span class="amount-prefix">{{ config.needsCurrency && currency !== 'NGN' ? currency : '₦' }}</span>
        <input v-model="amount" type="text" inputmode="decimal" placeholder="0" class="amount-input" autofocus />
      </div>
      <p v-if="exceedsChipsLimit" class="warn-text">
        This exceeds {{ player.display_name }}'s chips limit for tonight ({{ N(player.chips_limit) }} total,
        {{ N(player.chips_used_today) }} already used). Lower the amount, or ask the Owner to raise the limit.
      </p>

      <template v-if="config.needsCurrency">
        <div class="lbl">Currency</div>
        <select v-model="currency" class="select" @change="onCurrencyChange">
          <option v-for="c in CURRENCIES" :key="c" :value="c">{{ c }}</option>
        </select>
        <template v-if="currency !== 'NGN'">
          <div class="lbl">Rate to Naira</div>
          <input v-model="conversionRate" type="text" inputmode="decimal" placeholder="e.g. 1600" />
          <p v-if="rateHint" class="rate-hint">{{ rateHint }}</p>
          <p class="rate-hint">&asymp; {{ N(nairaAmount) }}</p>
        </template>
      </template>

      <template v-if="config.needsProvider">
        <div class="lbl">Card reader / provider <span class="opt">(optional)</span></div>
        <input v-model="provider" type="text" placeholder="e.g. Terminal 1 · Moniepoint" />
      </template>

      <div class="lbl">Notes <span class="opt">(optional)</span></div>
      <input v-model="notes" type="text" />

      <div v-if="config.physicalCount" class="notice">
        Physical count — a Floor Manager confirms this on the next step
      </div>
      <div v-else class="notice notice--ok">
        No Floor Manager PIN needed — card/transfer rails aren't a physical count
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>

      <div class="spacer" />
      <div class="actions">
        <button class="btn btn--secondary" type="button" @click="emit('close')">Cancel</button>
        <button class="btn btn--primary" type="button" :disabled="!canSubmit || submitting" @click="onSubmit">
          {{ submitting ? 'Saving…' : config.physicalCount ? 'Continue → FM PIN' : 'Save' }}
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
  align-items: flex-end;
  justify-content: center;
  z-index: 90; /* below AuthorizerConfirmModal's 100 — its PIN sheet layers on top of this one */
}
.sheet {
  width: 100%;
  max-width: 480px;
  background: var(--surface);
  border-radius: 20px 20px 0 0;
  box-shadow: 0 -6px 28px rgba(20, 25, 32, 0.25);
  padding: 16px 28px 28px;
  display: flex;
  flex-direction: column;
  max-height: 90vh;
  overflow-y: auto;
}
.grip { width: 44px; height: 5px; border-radius: 3px; background: var(--border); align-self: center; margin-bottom: 18px; }
.head { display: flex; align-items: center; justify-content: space-between; }
.sheet-title { font-size: 18px; font-weight: 700; color: var(--text-primary); }
.close-btn { border: none; background: none; font-size: 22px; line-height: 1; color: var(--text-tertiary); cursor: pointer; }
.sheet-subtitle { font-size: 13px; color: var(--text-secondary); margin: 4px 0 20px; }

.lbl {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}
.lbl-hint { text-transform: none; font-weight: 400; color: var(--text-tertiary); }
.lbl-hint--danger { color: var(--danger); }
.opt { text-transform: none; font-weight: 400; color: var(--border-strong); }

.amount-box {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  padding: 14px;
  margin-bottom: 6px;
  background: var(--accent-bg);
}
.amount-box--danger { border-color: var(--danger); background: var(--danger-bg); }
.amount-prefix { font-family: var(--font-mono); font-size: 28px; font-weight: 600; color: var(--text-secondary); }
.amount-input {
  border: none;
  background: transparent;
  outline: none;
  font-family: var(--font-mono);
  font-size: 32px;
  font-weight: 600;
  color: var(--text-primary);
  text-align: center;
  width: 100%;
}
.amount-box--danger .amount-input { color: var(--danger); }
.warn-text { font-size: 12px; color: var(--danger-text); line-height: 1.5; margin-bottom: 16px; }

.select, input[type="text"] {
  width: 100%;
  height: 44px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 12px;
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text-primary);
  background: var(--surface);
  margin-bottom: 14px;
}
.rate-hint { font-size: 11.5px; color: var(--text-tertiary); margin: -8px 0 14px; }

.notice {
  display: flex;
  gap: 10px;
  align-items: center;
  border: 1px solid var(--warning);
  background: var(--warning-bg);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  margin-bottom: 8px;
  font-size: 12.5px;
  color: var(--warning-text);
  line-height: 1.4;
}
.notice--ok { border-color: var(--success); background: var(--success-bg); color: var(--success-text); }

.form-error {
  font-size: 13px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  margin-top: 8px;
}

.spacer { flex-grow: 1; min-height: 12px; }
.actions { display: flex; gap: 14px; margin-top: 16px; }
.actions .btn { flex: 1; }
</style>
