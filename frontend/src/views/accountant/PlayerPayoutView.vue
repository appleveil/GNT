<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/axios'
import PlayerBankAccountModal from '@/components/shared/PlayerBankAccountModal.vue'
import { usePayoutRequestsStore } from '@/stores/payoutRequests'
import { formatAmountForDisplay, parseAmountInput } from '@/utils/amountInput'
import { useToast } from '@/composables/useToast'
import { useFormValidation } from '@/composables/useFormValidation'

// Owner-only "Payout" action, reached from the Players page's ⋮ menu — a
// full page (2026-09-25; started as DirectPayoutModal.vue, converted per
// direct request) rather than a pop-up. POST /transactions/direct-payout/
// (services.initiate_direct_payout), distinct from the Cashier's
// game-day-scoped payout (ActiveGameDayView.vue): no game-day involved,
// capped at the player's LIFETIME balance, and the Owner picks how much of
// it to send (not forced to pay out everything — "this isn't a bank"). The
// "add a bank account" step stays a stacked modal (PlayerBankAccountModal),
// same as ActiveGameDayView's own payout button.
//
// 2026-09-26: RosterDetailView.vue (the old "player profile" page) was
// removed — mostly genuinely redundant against the Players table's own ⋮
// menu, but its "Receiving bank accounts" list had no other home, so it
// moved in here (the one place on this page's whole flow where seeing —
// and being able to add/change — a bank account actually matters). Back
// links and the post-submit redirect now go to /roster (the list) instead
// of the removed /roster/:id.
const route = useRoute()
const router = useRouter()
const toast = useToast()
const payoutRequests = usePayoutRequestsStore()

const player = ref(null)
const loading = ref(true)

async function loadPlayer() {
  loading.value = true
  try {
    const { data } = await api.get(`/players/${route.params.id}/`)
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
const bankModalOpen = ref(false)

const { touched, errors, isValid, formError, touch, touchAll, applyServerErrors } = useFormValidation({
  amountInput: {
    value: amountInput,
    rules: [
      v => (Number(v) > 0 ? null : 'Enter an amount.'),
      v => (Number(v) > available.value ? `Can't exceed what's owed (${N(available.value)}).` : null),
    ],
  },
})
// Distinguishes "opened because a submit needed a bank account" (auto-retry
// the payout once one's added) from "opened via the plain 'Manage' link"
// (just viewing/adding — never auto-submits a payout the Owner didn't ask
// for). See onBankAdded below.
const bankModalFromSubmit = ref(false)

function onPayAll() {
  amountInput.value = String(available.value)
}

const N = n => `₦${Number(n).toLocaleString()}`

async function onSubmit() {
  touchAll()
  if (!isValid.value) return
  const amount = Number(amountInput.value || 0)
  if (!hasDefaultBank.value) {
    bankModalFromSubmit.value = true
    bankModalOpen.value = true
    return
  }
  submitting.value = true
  try {
    const { data } = await api.post('/transactions/direct-payout/', { player: player.value.id, amount: amountInput.value })
    toast.success(`Payout of ${N(amount)} ${data.status === 'APPROVED' ? 'sent to' : 'requested for'} ${player.value.display_name}.`)
    payoutRequests.fetchPendingCount() // a non-auto-approved payout adds to the sidebar's pending badge
    router.push('/roster')
  } catch (err) {
    applyServerErrors(err)
  } finally {
    submitting.value = false
  }
}

function onManageBankAccounts() {
  bankModalFromSubmit.value = false
  bankModalOpen.value = true
}

function onBankAdded() {
  bankModalOpen.value = false
  if (bankModalFromSubmit.value) loadPlayer().then(onSubmit)
  else loadPlayer()
}
</script>

<template>
  <div class="page">
    <button class="back-btn" type="button" @click="router.push('/roster')">&larr; Players</button>

    <div class="page-header">
      <h1>Payout</h1>
      <p v-if="player">{{ player.display_name }} &middot; {{ player.account_code }}</p>
    </div>

    <p v-if="loading" class="muted">Loading…</p>

    <template v-else-if="player">
      <div class="card">
        <div class="available-row">
          <span class="available-label">Owed to {{ player.display_name }}</span>
          <span class="available-amount">{{ N(available) }}</span>
        </div>

        <p v-if="!available" class="muted">Nothing currently owed to {{ player.display_name }}.</p>

        <form v-else class="form" novalidate @submit.prevent="onSubmit">
          <label class="field">
            <span class="field-label">Amount to send</span>
            <div class="amount-row">
              <input
                :value="displayAmountInput" type="text" inputmode="numeric" placeholder="0" class="ff"
                :class="{ 'input--invalid': touched.amountInput && errors.amountInput }"
                @input="e => (amountInput = parseAmountInput(e.target.value))" @blur="touch('amountInput')"
              />
              <button class="link-btn" type="button" @click="onPayAll">All ({{ N(available) }})</button>
            </div>
            <p v-if="touched.amountInput && errors.amountInput" class="field-error">{{ errors.amountInput }}</p>
          </label>
          <p v-if="formError" class="form-error">{{ formError }}</p>
          <div class="actions">
            <button class="btn btn--primary" type="submit" :disabled="submitting || !isValid">{{ submitting ? 'Sending…' : 'Send payout' }}</button>
          </div>
        </form>
      </div>

      <div class="card bank-card">
        <div class="bank-card-head">
          <div class="section-title">Receiving bank accounts</div>
          <button class="link-btn" type="button" @click="onManageBankAccounts">{{ player.bank_accounts.length ? 'Manage' : '+ Add' }}</button>
        </div>
        <div v-for="bank in player.bank_accounts" :key="bank.id" class="bank-row">
          <div>
            <div class="bank-name">{{ bank.bank_name }} &middot; {{ bank.account_number }}</div>
            <div class="bank-account-name">{{ bank.account_name }}</div>
          </div>
          <span v-if="bank.is_default" class="badge badge--open">default</span>
        </div>
        <p v-if="!player.bank_accounts.length" class="muted">No bank accounts on file.</p>
      </div>
    </template>

    <PlayerBankAccountModal
      v-if="bankModalOpen && player" :player="player"
      @close="bankModalOpen = false" @added="onBankAdded"
    />
  </div>
</template>

<style scoped>
.page { max-width: 520px; }
.back-btn { border: none; background: none; font-size: 13.5px; font-weight: 600; color: var(--text-secondary); cursor: pointer; padding: 4px 0; margin-bottom: 16px; }
.back-btn:hover { color: var(--text-primary); }
.muted { color: var(--text-secondary); font-size: 13px; }

.page-header { margin-bottom: 20px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }

.card { padding: 22px; }
.available-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px dashed var(--border-strong);
  background: var(--disabled-surface);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  margin-bottom: 18px;
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

.actions { display: flex; justify-content: flex-end; margin-top: 4px; }

.bank-card { padding: 18px 20px; margin-top: 16px; }
.bank-card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); }
.bank-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--border); }
.bank-row:last-child { border-bottom: none; }
.bank-name { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.bank-account-name { font-size: 11.5px; color: var(--text-tertiary); }
</style>
