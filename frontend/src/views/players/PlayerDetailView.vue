<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/axios'
import { useGameDayStore } from '@/stores/gameDay'

const route = useRoute()
const router = useRouter()
const gameDay = useGameDayStore()

const player = ref(null)
const loading = ref(true)
const error = ref('')

const addingBank = ref(false)
const bankName = ref('')
const bankCode = ref('')
const accountNumber = ref('')
const bankError = ref('')
const bankSubmitting = ref(false)

const payoutState = ref(null) // null | 'submitting' | { amount, status }
const payoutError = ref('')

const gameDayDate = computed(() => {
  if (!gameDay.current) return ''
  return new Date(gameDay.current.started_at).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  })
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    if (!gameDay.current) await gameDay.fetchCurrent()
    if (!gameDay.current) {
      error.value = 'No game-day is open.'
      return
    }
    const { data } = await api.get(`/game-days/${gameDay.current.id}/players/${route.params.id}/`)
    player.value = data
  } catch (err) {
    error.value = err.response?.status === 404
      ? "This player isn't seated for tonight's game-day."
      : 'Could not load player.'
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function onAddBank() {
  bankError.value = ''
  bankSubmitting.value = true
  try {
    await api.post(`/players/${player.value.id}/bank-accounts/`, {
      bank_name: bankName.value,
      bank_code: bankCode.value,
      account_number: accountNumber.value,
      account_name: player.value.display_name,
      is_default: player.value.bank_accounts.length === 0,
    })
    addingBank.value = false
    bankName.value = ''
    bankCode.value = ''
    accountNumber.value = ''
    await load()
  } catch (err) {
    bankError.value = Object.values(err.response?.data || {})[0]?.[0] || 'Could not add bank account.'
  } finally {
    bankSubmitting.value = false
  }
}

async function onSetDefault(bank) {
  await api.patch(`/players/${player.value.id}/bank-accounts/${bank.id}/`, { is_default: true })
  await load()
}

async function onPayOut() {
  payoutError.value = ''
  payoutState.value = 'submitting'
  try {
    const { data } = await api.post('/transactions/payout/', {
      player: player.value.id, amount: player.value.balance,
    })
    payoutState.value = { amount: data.amount, status: data.status }
  } catch (err) {
    payoutError.value = err.response?.data?.detail || 'Could not initiate the payout.'
    payoutState.value = null
  }
}

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div>
    <div class="header-row">
      <button class="back-btn" type="button" @click="router.push('/players')">&larr;</button>
      <div v-if="player" class="header-title">{{ player.display_name }} &middot; {{ player.account_code }}</div>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="error" class="muted">{{ error }}</p>

    <div v-else class="card detail">
      <div class="balance-block">
        <div class="eyebrow">
          Today's balance <span class="scope">(Game-Day #{{ gameDay.current.number }}, {{ gameDayDate }}, only)</span>
        </div>
        <div class="balance" :class="{ 'balance--positive': player.balance > 0 }">
          {{ player.balance > 0 ? '+' : '' }}{{ N(player.balance) }}
        </div>
      </div>

      <div class="notice">
        This is only what {{ player.display_name }} {{ player.balance < 0 ? 'owes' : 'is owed' }} from today's
        game-day. Older activity is never shown here — ask the Accountant or Owner for full history.
      </div>

      <div class="section">
        <div class="section-title">Gaming account (deposit DVA)</div>
        <div v-if="player.gaming_account" class="dva-row">
          <div v-for="dva in player.gaming_account.dvas" :key="dva.id">
            {{ dva.bank_name }} &middot; {{ dva.account_number }}
          </div>
        </div>
        <div v-else class="dva-empty">
          Not yet available — this player has no gaming account/DVA to receive transfers into.
          Paystack's Dedicated NUBAN approval is still pending.
        </div>
      </div>

      <div class="section">
        <div class="section-title-row">
          <div class="section-title">Receiving bank accounts</div>
          <button class="link-btn" type="button" @click="addingBank = !addingBank">
            {{ addingBank ? 'Cancel' : '+ Add' }}
          </button>
        </div>

        <div v-for="bank in player.bank_accounts" :key="bank.id" class="bank-row">
          <div class="bank-info">
            <div class="bank-name">{{ bank.bank_name }} &middot; {{ bank.account_number }}</div>
            <div class="bank-account-name">{{ bank.account_name }}</div>
          </div>
          <div v-if="bank.is_default" class="default-badge">DEFAULT</div>
          <button v-else class="link-btn small" type="button" @click="onSetDefault(bank)">Set default</button>
        </div>
        <p v-if="!player.bank_accounts.length" class="muted">No bank accounts on file.</p>

        <form v-if="addingBank" class="bank-form" @submit.prevent="onAddBank">
          <input v-model="bankName" type="text" placeholder="Bank name" required />
          <div class="field-row">
            <input v-model="bankCode" type="text" placeholder="Bank code" required />
            <input v-model="accountNumber" type="text" placeholder="Account number" required />
          </div>
          <p v-if="bankError" class="form-error">{{ bankError }}</p>
          <button class="btn btn--secondary" type="submit" :disabled="bankSubmitting">
            {{ bankSubmitting ? 'Adding…' : 'Save bank account' }}
          </button>
        </form>
      </div>

      <div v-if="payoutState && payoutState !== 'submitting'" class="payout-confirm">
        Payout of {{ N(payoutState.amount) }} requested — pending Owner approval.
      </div>
      <template v-else>
        <button
          class="btn btn--primary payout-btn" type="button"
          :disabled="!(player.balance > 0) || payoutState === 'submitting'"
          @click="onPayOut"
        >
          {{ payoutState === 'submitting' ? 'Requesting…' : 'Pay Out Balance' }}
        </button>
        <p v-if="!(player.balance > 0)" class="payout-note">
          Not available — {{ player.display_name }} owes the club, the club doesn't owe them
        </p>
        <p v-if="payoutError" class="form-error">{{ payoutError }}</p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.header-row { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }
.back-btn {
  border: none;
  background: none;
  font-size: 18px;
  cursor: pointer;
  color: var(--text-primary);
  padding: 4px;
}
.header-title { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.muted { color: var(--text-secondary); font-size: 13px; }

.detail { padding: 24px; max-width: 560px; }
.balance-block { text-align: center; margin-bottom: 10px; }
.scope { text-transform: none; color: var(--text-tertiary); }
.balance {
  font-family: var(--font-mono);
  font-size: 30px;
  font-weight: 600;
  color: var(--text-primary);
  margin-top: 4px;
}
.balance--positive { color: var(--success); }

.notice {
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  margin: 16px 0 22px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.section { margin-bottom: 22px; }
.section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 10px; }
.section-title-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.section-title-row .section-title { margin: 0; }
.link-btn {
  border: none;
  background: none;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--accent);
  cursor: pointer;
}
.link-btn.small { font-size: 11px; font-weight: 500; color: var(--text-tertiary); }

.dva-row, .dva-empty {
  border: 1px dashed var(--border-strong);
  background: var(--disabled-surface);
  border-radius: var(--radius-sm);
  padding: 14px;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.bank-row {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  margin-bottom: 8px;
  background: var(--surface);
}
.bank-info { flex-grow: 1; }
.bank-name { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }
.bank-account-name { font-size: 11.5px; color: var(--text-tertiary); }
.default-badge {
  border: 1px solid var(--accent);
  border-radius: 12px;
  padding: 4px 10px;
  font-size: 10.5px;
  font-weight: 700;
  color: var(--accent);
}

.bank-form { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }
.field-row { display: flex; gap: 10px; }
.field-row input { flex: 1; }
.form-error {
  font-size: 13px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
}

.payout-btn { width: 100%; margin-bottom: 8px; }
.payout-note { text-align: center; font-size: 11.5px; color: var(--text-tertiary); }
.payout-confirm {
  text-align: center;
  font-size: 13px;
  color: var(--success-text);
  background: var(--success-bg);
  border-radius: var(--radius-sm);
  padding: 14px;
}
</style>
