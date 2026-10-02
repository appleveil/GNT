<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/axios'
import { formatAmountForDisplay, parseAmountInput } from '@/utils/amountInput'
import { useToast } from '@/composables/useToast'
import { useFormValidation, required } from '@/composables/useFormValidation'

// "Deals" Transfer (2026-09-23) — mirrors mobile's TransferScreen.tsx, wired
// to the real backend: POST /deals/transfer/ {source_player, destination_player,
// amount, reason}, which creates the linked DEAL_TRANSFER_OUT/IN pair
// (gaming.services.record_deal_transfer) — always game_day=null
// (Outstanding), same as the backend endpoint itself; there's no game-day
// choice to offer here, unlike Fixed.
const route = useRoute()
const router = useRouter()
const toast = useToast()

const player = ref(null)
const otherPlayers = ref([])
const loading = ref(true)
const search = ref('')
const targetId = ref(null)
const amount = ref('')
const reason = ref('')
const submitting = ref(false)

async function load() {
  loading.value = true
  try {
    const [playerRes, playersRes] = await Promise.all([
      api.get(`/players/${route.params.playerId}/`),
      api.get('/players/'),
    ])
    player.value = playerRes.data
    otherPlayers.value = playersRes.data.filter(p => String(p.id) !== String(route.params.playerId))
  } catch {
    toast.error('Could not load players.')
  } finally {
    loading.value = false
  }
}
onMounted(load)

const available = computed(() => (player.value ? Math.max(Number(player.value.balance), 0) : 0))
const target = computed(() => otherPlayers.value.find(p => p.id === targetId.value) || null)

const filteredTargets = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return otherPlayers.value
  return otherPlayers.value.filter(p => p.display_name.toLowerCase().includes(q))
})

const displayAmount = computed(() => formatAmountForDisplay(amount.value))
const amountNumber = computed(() => Number(amount.value) || 0)

const { touched, errors, isValid, formError, touch, applyServerErrors } = useFormValidation({
  amount: {
    value: amount,
    rules: [
      v => (Number(v) > 0 ? null : 'Enter an amount greater than zero.'),
      v => (Number(v) > available.value ? "Can't exceed the available balance." : null),
    ],
  },
  reason: { value: reason, rules: [required('A reason is required.')] },
})
const canSubmit = computed(() => !!target.value && isValid.value)

// Once real progress has been made, switching the recipient by mistake
// would silently misattribute what was typed — confirm first, same rule as
// the mobile app's own onPickTarget.
const confirmSwitch = ref(null) // the candidate player id awaiting confirmation, or null
function onPickTarget(candidate) {
  if (targetId.value && candidate.id !== targetId.value && (amount.value.trim() || reason.value.trim())) {
    confirmSwitch.value = candidate.id
    return
  }
  targetId.value = candidate.id
}
function onConfirmSwitch() {
  targetId.value = confirmSwitch.value
  confirmSwitch.value = null
  amount.value = ''
  reason.value = ''
}

async function onSubmit() {
  if (!canSubmit.value) return
  submitting.value = true
  try {
    await api.post('/deals/transfer/', {
      source_player: player.value.id,
      destination_player: target.value.id,
      amount: amountNumber.value.toFixed(0),
      reason: reason.value.trim(),
    })
    toast.success(`₦${amountNumber.value.toLocaleString()} moved from ${player.value.display_name} to ${target.value.display_name}.`)
    router.push(`/deals/${route.params.playerId}`)
  } catch (err) {
    applyServerErrors(err)
  } finally {
    submitting.value = false
  }
}

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="page">
    <button class="back-btn" type="button" @click="router.push(`/deals/${route.params.playerId}`)">&larr; {{ player?.display_name || 'Back' }}</button>

    <p v-if="loading" class="muted">Loading…</p>

    <template v-else-if="player">
      <div class="page-header">
        <h1>Transfer</h1>
        <p>From {{ player.display_name }} &middot; {{ player.account_code }}</p>
      </div>

      <div v-if="available <= 0" class="banner banner--danger">
        {{ player.display_name }} has no available balance — a Transfer requires a positive balance to give away.
      </div>

      <template v-else>
        <div class="card balance-card">
          <span class="balance-label">Available to transfer</span>
          <span class="balance-amount money--pos">{{ N(available) }}</span>
        </div>

        <input v-model="search" type="text" placeholder="Search players to transfer to…" class="search-input" />

        <div class="section-label">Transfer to <span class="req">*</span></div>
        <div class="target-list">
          <p v-if="!filteredTargets.length" class="muted">No players match.</p>
          <button
            v-for="p in filteredTargets" :key="p.id" type="button" class="target-row"
            :class="{ 'target-row--selected': targetId === p.id }" @click="onPickTarget(p)"
          >
            <span class="target-name">{{ p.display_name }}</span>
            <span class="money" :class="p.balance > 0 ? 'money--pos' : p.balance < 0 ? 'money--neg' : ''">{{ N(p.balance) }}</span>
          </button>
        </div>

        <label class="field">
          <span class="field-label">Amount <span class="req">*</span></span>
          <input
            :value="displayAmount" type="text" inputmode="numeric" placeholder="0" class="ff"
            :class="{ 'input--invalid': touched.amount && errors.amount }"
            @input="e => { amount = parseAmountInput(e.target.value); e.target.value = displayAmount }"
            @blur="touch('amount')"
          />
          <p v-if="touched.amount && errors.amount" class="field-error">{{ errors.amount }}</p>
        </label>

        <label class="field">
          <span class="field-label">Reason <span class="req">*</span></span>
          <textarea
            v-model="reason" class="ff ff--area" placeholder="Why is this being transferred?" rows="3"
            :class="{ 'input--invalid': touched.reason && errors.reason }" @blur="touch('reason')"
          />
          <p v-if="touched.reason && errors.reason" class="field-error">{{ errors.reason }}</p>
        </label>

        <p v-if="formError" class="form-error">{{ formError }}</p>

        <button class="btn btn--primary submit-btn" type="button" :disabled="!canSubmit || submitting" @click="onSubmit">
          {{ submitting ? 'Transferring…' : 'Transfer' }}
        </button>
      </template>
    </template>

    <div v-if="confirmSwitch" class="overlay" @click.self="confirmSwitch = null">
      <div class="dialog card">
        <div class="eyebrow">Change recipient?</div>
        <p class="dialog-text">This will clear the amount and reason you've entered for {{ target?.display_name }}.</p>
        <div class="dialog-actions">
          <button class="btn btn--secondary" type="button" @click="confirmSwitch = null">Cancel</button>
          <button class="btn btn--danger" type="button" @click="onConfirmSwitch">Change</button>
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

.balance-card { display: flex; align-items: center; justify-content: space-between; padding: 16px 18px; margin-bottom: 16px; }
.balance-label { font-size: 12px; font-weight: 600; color: var(--text-tertiary); }
.balance-amount { font-family: var(--font-mono); font-weight: 700; font-size: 19px; }
.money--pos { color: var(--success-text); }
.money--neg { color: var(--danger-text); }

.search-input {
  width: 100%;
  height: var(--control-row-min);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 14px;
  font-family: var(--font-sans);
  font-size: 13.5px;
  color: var(--text-primary);
  background: var(--surface);
  margin-bottom: 16px;
}
.search-input:focus { outline: none; border-color: var(--accent); }

.section-label { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 8px; }
.req { color: var(--danger-text); }

.target-list { max-height: 260px; overflow-y: auto; margin-bottom: 20px; }
.target-row {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  padding: 12px 14px;
  margin-bottom: 8px;
  font-family: var(--font-sans);
  cursor: pointer;
}
.target-row--selected { border-color: var(--accent); background: var(--accent-bg); }
.target-name { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }

.field { display: block; margin-bottom: 16px; }
.field-label { display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
.ff {
  width: 100%;
  height: var(--control-row-min);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 14px;
  font-family: var(--font-sans);
  font-size: 15px;
  color: var(--text-primary);
  background: var(--surface);
}
.ff:focus { outline: none; border-color: var(--accent); }
.ff--area { height: auto; padding: 12px 14px; resize: vertical; font-size: 13.5px; }

.banner { border-radius: var(--radius-sm); padding: 12px 14px; font-size: 12.5px; }
.banner--danger { background: var(--danger-bg); color: var(--danger-text); }

.submit-btn { width: 100%; }

.overlay {
  position: fixed;
  inset: 0;
  background: rgba(20, 25, 32, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.dialog { width: 400px; max-width: 92vw; box-shadow: var(--shadow-md); padding: 24px; }
.eyebrow { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.dialog-text { font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin: 8px 0 0; }
.dialog-actions { display: flex; gap: 14px; margin-top: 20px; }
.dialog-actions .btn { flex: 1; }
</style>
