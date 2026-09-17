<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/axios'
import { useGameDayStore } from '@/stores/gameDay'
import { useAuthStore } from '@/stores/auth'
import BankAccountFields from '@/components/shared/BankAccountFields.vue'
import VoidEntryModal from '@/components/shared/VoidEntryModal.vue'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import { TRANSACTION_STATUS_BADGE } from '@/constants/transactionTypes'
import { canVoidTransaction } from '@/utils/canVoid'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const router = useRouter()
const gameDay = useGameDayStore()
const auth = useAuthStore()
const toast = useToast()

const player = ref(null)
const loading = ref(true)
const error = ref('')

const addingBank = ref(false)
// Named distinctly from the `bank` loop var used below (v-for over
// player.bank_accounts) and onSetDefault's param, to avoid shadowing confusion.
const newBank = ref({ bank_name: '', bank_code: '', account_number: '', account_name: '' })
const bankError = ref('')
const bankSubmitting = ref(false)

// Tonight's activity — this player's own transactions for the CURRENT
// game-day only, not lifetime (see gaming.selectors.player_game_day_ledger).
// Also feeds "Payouts this game-day" below — both read the same fetch, just
// filtered differently. Most-recent-first, same convention as the Active
// Game-Day feed.
const ledger = ref([])
const ledgerLoading = ref(false)
const activity = computed(() => ledger.value.slice().reverse())
const payouts = computed(() => ledger.value.filter(r => r.type === 'PAYOUT').slice().reverse())

const payoutSubmitting = ref(false)
const payoutError = ref('')

const voidTarget = ref(null)
function canVoid(row) {
  return canVoidTransaction(row, auth.user, gameDay.current?.status)
}
function onVoided() {
  voidTarget.value = null
  toast.success('Entry voided.')
  refreshPlayer()
}

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
    await refreshPlayer()
    loadLedger() // don't block the rest of the page on this
  } catch (err) {
    error.value = err.response?.status === 404
      ? "This player isn't seated for tonight's game-day."
      : 'Could not load player.'
  } finally {
    loading.value = false
  }
}

// Refetches player + ledger WITHOUT toggling `loading` — used after a write
// (add bank, set default, payout, void) so the card updates in place instead
// of flashing back to the full loading state.
async function refreshPlayer() {
  const { data } = await api.get(`/game-days/${gameDay.current.id}/players/${route.params.id}/`)
  player.value = data
}

async function loadLedger() {
  ledgerLoading.value = true
  try {
    const { data } = await api.get(`/game-days/${gameDay.current.id}/players/${route.params.id}/ledger/`)
    ledger.value = data
  } finally {
    ledgerLoading.value = false
  }
}

onMounted(load)

async function onAddBank() {
  bankError.value = ''
  bankSubmitting.value = true
  try {
    await api.post(`/players/${player.value.id}/bank-accounts/`, {
      bank_name: newBank.value.bank_name,
      bank_code: newBank.value.bank_code,
      account_number: newBank.value.account_number,
      // Prefer the Paystack-resolved name; fall back to the player's own name
      // if resolution didn't complete (e.g. Paystack unreachable).
      account_name: newBank.value.account_name || player.value.display_name,
      is_default: player.value.bank_accounts.length === 0,
    })
    addingBank.value = false
    newBank.value = { bank_name: '', bank_code: '', account_number: '', account_name: '' }
    await refreshPlayer()
  } catch (err) {
    bankError.value = Object.values(err.response?.data || {})[0]?.[0] || 'Could not add bank account.'
  } finally {
    bankSubmitting.value = false
  }
}

async function onSetDefault(bank) {
  try {
    await api.patch(`/players/${player.value.id}/bank-accounts/${bank.id}/`, { is_default: true })
    await refreshPlayer()
  } catch {
    toast.error('Could not set this as the default bank account.')
  }
}

async function onPayOut() {
  payoutError.value = ''
  payoutSubmitting.value = true
  try {
    await api.post('/transactions/payout/', {
      player: player.value.id, amount: player.value.balance,
    })
    await refreshPlayer()
    await loadLedger() // the new PENDING_APPROVAL row shows up in the list below, not a separate banner
  } catch (err) {
    payoutError.value = err.response?.data?.detail || 'Could not initiate the payout.'
  } finally {
    payoutSubmitting.value = false
  }
}

function formatTime(iso) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div>
    <div class="header-row">
      <button class="back-btn" type="button" @click="router.push('/game-day')">&larr;</button>
      <div v-if="player" class="header-title">{{ player.display_name }} &middot; {{ player.account_code }}</div>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="error" class="muted">{{ error }}</p>

    <div v-else class="card detail">
      <div v-if="player.left_at" class="left-note">Left the table at {{ formatTime(player.left_at) }}</div>

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
          <BankAccountFields v-model="newBank" />
          <p v-if="bankError" class="form-error">{{ bankError }}</p>
          <button
            class="btn btn--secondary" type="submit"
            :disabled="bankSubmitting || newBank.account_number.length !== 10 || !newBank.bank_code"
          >
            {{ bankSubmitting ? 'Adding…' : 'Save bank account' }}
          </button>
        </form>
      </div>

      <div class="section">
        <div class="section-title">Tonight's activity</div>
        <p v-if="ledgerLoading && !activity.length" class="muted">Loading…</p>
        <p v-else-if="!activity.length" class="muted">Nothing recorded for {{ player.display_name }} tonight yet.</p>
        <LedgerTable v-else :rows="activity" voidable :can-void-fn="canVoid" @void="voidTarget = $event" />
      </div>

      <div class="section">
        <div class="section-title">Payout</div>
        <button
          class="btn btn--primary payout-btn" type="button"
          :disabled="!(player.balance > 0) || payoutSubmitting"
          @click="onPayOut"
        >
          {{ payoutSubmitting ? 'Requesting…' : 'Pay Out Balance' }}
        </button>
        <p v-if="!(player.balance > 0)" class="payout-note">
          Not available — {{ player.display_name }} owes the club, the club doesn't owe them
        </p>
        <p v-if="payoutError" class="form-error">{{ payoutError }}</p>

        <div class="payouts-list">
          <div class="payouts-title">Payouts this game-day</div>
          <p v-if="!payouts.length" class="muted">None requested yet tonight.</p>
          <div v-for="p in payouts" :key="p.id" class="payout-row">
            <div>
              <div class="money">{{ N(p.amount) }}</div>
              <div class="activity-meta">{{ formatTime(p.created_at) }}</div>
            </div>
            <span
              v-if="p.is_voided" class="badge badge--voided">VOIDED</span>
            <span v-else class="badge" :class="`badge--${TRANSACTION_STATUS_BADGE[p.status] || 'approved'}`">
              {{ p.status.replace('_', ' ') }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <VoidEntryModal
      v-if="voidTarget" :transaction="voidTarget" :player-name="player.display_name"
      :recorded-by-name="auth.user?.fullName" @close="voidTarget = null" @voided="onVoided"
    />
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
.left-note {
  text-align: center;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--status-voided-text);
  background: var(--status-voided-bg);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  margin-bottom: 16px;
}
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
.form-error {
  font-size: 13px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
}

.payout-btn { width: 100%; margin-bottom: 8px; }
.payout-note { text-align: center; font-size: 11.5px; color: var(--text-tertiary); }

.activity-meta { font-size: 10.5px; color: var(--text-tertiary); }

.payouts-list { margin-top: 18px; border-top: 1px solid var(--border); padding-top: 14px; }
.payouts-title { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 8px; }
.payout-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}
.payout-row:last-child { border-bottom: none; }
.payout-row .money { font-size: 13px; font-weight: 700; color: var(--text-primary); }
</style>
