<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/api/axios'
import PlayerBankAccountModal from '@/components/shared/PlayerBankAccountModal.vue'
import { formatAmountForDisplay, parseAmountInput } from '@/utils/amountInput'
import { useToast } from '@/composables/useToast'

// Owner-only "Payout" action (2026-09-24), reached from the Players page's
// ⋮ menu — POST /transactions/direct-payout/ (services.initiate_direct_payout),
// distinct from the Cashier's game-day-scoped payout (ActiveGameDayView.vue):
// no game-day involved, capped at the player's LIFETIME balance, and the
// Owner picks how much of it to send (not forced to pay out everything —
// "this isn't a bank"). Fetches its own fresh player record on open rather
// than trusting the row passed in from the list, so balance/bank_accounts
// are current even if the list was loaded a while ago.
const props = defineProps({
  playerId: { type: [Number, String], required: true },
  playerName: { type: String, default: '' }, // shown immediately, before the fresh fetch resolves
})
const emit = defineEmits(['close', 'paid'])
const toast = useToast()

const player = ref(null)
const loading = ref(true)

async function loadPlayer() {
  loading.value = true
  try {
    const { data } = await api.get(`/players/${props.playerId}/`)
    player.value = data
  } catch {
    toast.error('Could not load this player.')
  } finally {
    loading.value = false
  }
}
onMounted(loadPlayer)

const available = computed(() => (player.value ? Math.max(Number(player.value.balance), 0) : 0))
const hasDefaultBank = computed(() => (player.value?.bank_accounts || []).some(b => b.is_default))

const amountInput = ref('') // plain numeric string, no commas
const displayAmountInput = computed(() => formatAmountForDisplay(amountInput.value))
const submitting = ref(false)
const error = ref('')
const bankModalOpen = ref(false)

function onPayAll() {
  amountInput.value = String(available.value)
}

const N = n => `₦${Number(n).toLocaleString()}`

async function onSubmit() {
  error.value = ''
  const amount = Number(amountInput.value || 0)
  if (!amount) { error.value = 'Enter an amount.'; return }
  if (amount > available.value) { error.value = `Can't exceed what's owed (${N(available.value)}).`; return }
  if (!hasDefaultBank.value) {
    bankModalOpen.value = true
    return
  }
  submitting.value = true
  try {
    const { data } = await api.post('/transactions/direct-payout/', { player: player.value.id, amount: amountInput.value })
    toast.success(`Payout of ${N(amount)} ${data.status === 'APPROVED' ? 'sent to' : 'requested for'} ${player.value.display_name}.`)
    emit('paid', data)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not initiate the payout.'
  } finally {
    submitting.value = false
  }
}

function onBankAdded() {
  bankModalOpen.value = false
  loadPlayer().then(onSubmit)
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="dialog card">
      <div class="head">
        <div class="eyebrow">{{ player?.display_name || playerName }} &mdash; payout</div>
        <button class="close-btn" type="button" @click="emit('close')">&times;</button>
      </div>

      <p v-if="loading" class="muted">Loading…</p>

      <template v-else-if="player">
        <div class="available-row">
          <span class="available-label">Owed to {{ player.display_name }}</span>
          <span class="available-amount">{{ N(available) }}</span>
        </div>

        <p v-if="!available" class="muted">Nothing currently owed to {{ player.display_name }}.</p>

        <form v-else class="form" @submit.prevent="onSubmit">
          <label class="field">
            <span class="field-label">Amount to send</span>
            <div class="amount-row">
              <input
                :value="displayAmountInput" type="text" inputmode="numeric" placeholder="0" class="ff"
                @input="e => (amountInput = parseAmountInput(e.target.value))"
              />
              <button class="link-btn" type="button" @click="onPayAll">All ({{ N(available) }})</button>
            </div>
          </label>
          <p v-if="error" class="form-error">{{ error }}</p>
          <div class="actions">
            <button class="btn btn--secondary" type="button" :disabled="submitting" @click="emit('close')">Cancel</button>
            <button class="btn btn--primary" type="submit" :disabled="submitting">{{ submitting ? 'Sending…' : 'Send payout' }}</button>
          </div>
        </form>
      </template>
    </div>

    <PlayerBankAccountModal
      v-if="bankModalOpen && player" :player="player"
      @close="bankModalOpen = false" @added="onBankAdded"
    />
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
.dialog { width: 440px; max-width: 92vw; box-shadow: var(--shadow-md); padding: 24px; }
.head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 16px; }
.eyebrow { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.close-btn { border: none; background: none; font-size: 22px; line-height: 1; color: var(--text-tertiary); cursor: pointer; flex-shrink: 0; }
.muted { color: var(--text-secondary); font-size: 13px; }

.available-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px dashed var(--border-strong);
  background: var(--disabled-surface);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  margin-bottom: 16px;
}
.available-label { font-size: 12.5px; color: var(--text-secondary); }
.available-amount { font-family: var(--font-mono); font-weight: 700; font-size: 16px; color: var(--success-text); }

.form { display: flex; flex-direction: column; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 12px; font-weight: 600; color: var(--text-secondary); }
.amount-row { display: flex; align-items: center; gap: 10px; }
.ff {
  flex: 1;
  height: var(--control-row-min);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 12px;
  font-family: var(--font-mono);
  font-size: 14px;
  color: var(--text-primary);
  background: var(--surface);
}
.ff:focus { outline: none; border-color: var(--accent); }
.link-btn { border: none; background: none; font-size: 12px; font-weight: 700; color: var(--accent-text); cursor: pointer; padding: 0; white-space: nowrap; }

.form-error {
  font-size: 12.5px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
}
.actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 4px; }
</style>
