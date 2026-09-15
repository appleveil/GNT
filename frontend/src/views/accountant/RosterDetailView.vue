<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/axios'
import { useAuthStore } from '@/stores/auth'
import { TRANSACTION_TYPES, TRANSACTION_STATUS_BADGE } from '@/constants/transactionTypes'
import { formatAmountForDisplay, parseAmountInput } from '@/utils/amountInput'
import { useToast } from '@/composables/useToast'

// Read-only player detail for Accountant/Owner (Phase B, 2026-09-14) — the
// "any game-day's ledger" requirement is met with a plain game-day picker
// rather than a dedicated backend endpoint: GET
// /game-days/{id}/players/{player_pk}/ledger/ is a plain queryset filter
// server-side (gaming/selectors.py's player_game_day_ledger), so it just
// returns an empty list for a game-day this player wasn't part of — no 404,
// confirmed by reading that selector directly. The picker can therefore
// offer every game-day, not just ones this player attended.
//
// Phase C (2026-09-14) adds two Owner-only pieces: chips-limit becomes
// inline-editable (PATCH /api/players/{id}/ {chips_limit} — already
// Owner-gated server-side in PlayerSerializer.validate_chips_limit, no
// backend change needed) and a Deal/Write-off mini-form (POST
// /api/transactions/). Revised 2026-09-15: the form gained a game-day
// picker (reusing the `gameDays` list already fetched for "any game-day's
// activity" below) — a Deal recorded WITH a game-day selected lands in that
// game-day's ledger (Cashier's and Accountant's) instead of Outstanding,
// since RecordTransactionSerializer already accepts an optional game_day and
// player_game_day_ledger/game_day_ledger already include PAYMENT_DEAL rows
// once one is set (only RAKE/TIP are excluded) — no backend change needed,
// this view was just always omitting it. Leaving it blank (the default)
// keeps today's behavior: an Outstanding (between-game-day) entry.
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const toast = useToast()

const player = ref(null)
const loading = ref(true)

const editingLimit = ref(false)
const limitInput = ref('') // plain numeric string, no commas — see utils/amountInput.js
const displayLimitInput = computed(() => formatAmountForDisplay(limitInput.value))
const savingLimit = ref(false)

const dealType = ref('PAYMENT_DEAL')
const dealAmount = ref('') // plain numeric string, no commas
const displayDealAmount = computed(() => formatAmountForDisplay(dealAmount.value))
const dealReason = ref('')
const dealGameDayId = ref('') // '' = Outstanding (no game-day) — the default
const dealSubmitting = ref(false)
const dealError = ref('')

const outstanding = ref([])
const outstandingLoading = ref(false)

const gameDays = ref([])
const selectedGameDayId = ref('')
const gdLedger = ref([])
const gdLedgerLoading = ref(false)

async function load() {
  loading.value = true
  try {
    const [playerRes, gameDaysRes] = await Promise.all([
      api.get(`/players/${route.params.id}/`),
      api.get('/game-days/'),
    ])
    player.value = playerRes.data
    gameDays.value = gameDaysRes.data
    loadOutstanding() // don't block the rest of the page on this
  } catch {
    toast.error('Could not load this player.')
  } finally {
    loading.value = false
  }
}

async function loadOutstanding() {
  outstandingLoading.value = true
  try {
    const { data } = await api.get('/outstanding/', { params: { player: route.params.id } })
    outstanding.value = data.slice().reverse()
  } finally {
    outstandingLoading.value = false
  }
}

function onStartEditLimit() {
  limitInput.value = player.value.chips_limit ?? ''
  editingLimit.value = true
}

async function onSaveLimit() {
  savingLimit.value = true
  try {
    const { data } = await api.patch(`/players/${player.value.id}/`, {
      chips_limit: limitInput.value === '' ? null : limitInput.value,
    })
    player.value = data
    editingLimit.value = false
    toast.success('Chips limit updated.')
  } catch (err) {
    toast.error(err.response?.data?.chips_limit?.[0] || 'Could not update the chips limit.')
  } finally {
    savingLimit.value = false
  }
}

async function onSubmitDeal() {
  dealError.value = ''
  dealSubmitting.value = true
  try {
    await api.post('/transactions/', {
      player: player.value.id,
      type: dealType.value,
      amount: dealAmount.value,
      notes: dealReason.value,
      ...(dealGameDayId.value ? { game_day: dealGameDayId.value } : {}),
    })
    const recordedGameDayId = dealGameDayId.value
    dealAmount.value = ''
    dealReason.value = ''
    dealGameDayId.value = ''
    toast.success(
      `${dealType.value === 'PAYMENT_DEAL' ? 'Deal' : 'Write-off'} recorded`
      + (recordedGameDayId ? ` against Game-Day #${gameDays.value.find(g => g.id === Number(recordedGameDayId))?.number}.` : ' — Outstanding.'),
    )
    loadOutstanding() // harmless no-op if this one was attached to a game-day instead
    // If they're currently looking at the same game-day this landed in, refresh
    // that view too so the new row appears without a manual re-pick.
    if (recordedGameDayId && String(selectedGameDayId.value) === String(recordedGameDayId)) {
      const { data } = await api.get(`/game-days/${recordedGameDayId}/players/${route.params.id}/ledger/`)
      gdLedger.value = data.slice().reverse()
    }
  } catch (err) {
    dealError.value = Object.values(err.response?.data || {})[0]?.[0] || err.response?.data?.detail || 'Could not record this.'
  } finally {
    dealSubmitting.value = false
  }
}

watch(selectedGameDayId, async id => {
  if (!id) { gdLedger.value = []; return }
  gdLedgerLoading.value = true
  try {
    const { data } = await api.get(`/game-days/${id}/players/${route.params.id}/ledger/`)
    gdLedger.value = data.slice().reverse()
  } catch {
    toast.error('Could not load that game-day for this player.')
  } finally {
    gdLedgerLoading.value = false
  }
})

onMounted(load)

function formatTime(iso) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}
function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="page">
    <div class="header-row">
      <button class="back-btn" type="button" @click="router.push('/roster')">&larr; Players</button>
    </div>

    <p v-if="loading" class="muted">Loading…</p>

    <template v-else-if="player">
      <div class="page-header">
        <h1>{{ player.display_name }}</h1>
        <span class="mono code">{{ player.account_code }}</span>
        <span v-if="!player.is_active" class="badge badge--closed">inactive</span>
      </div>

      <div class="stat-grid">
        <div class="card stat-card">
          <div class="stat-label">Lifetime balance</div>
          <div class="stat-value" :class="player.balance > 0 ? 'money--pos' : player.balance < 0 ? 'money--neg' : ''">{{ N(player.balance) }}</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Chips limit</div>
          <div v-if="!auth.isOwner || !editingLimit" class="limit-row">
            <div class="stat-value">{{ player.chips_limit != null ? N(player.chips_limit) : 'No cap' }}</div>
            <button v-if="auth.isOwner" class="link-btn" type="button" @click="onStartEditLimit">Edit</button>
          </div>
          <div v-else class="limit-edit">
            <input
              :value="displayLimitInput" type="text" inputmode="decimal" placeholder="No cap" class="limit-input"
              @input="e => (limitInput = parseAmountInput(e.target.value))"
            />
            <button class="link-btn" type="button" :disabled="savingLimit" @click="onSaveLimit">{{ savingLimit ? 'Saving…' : 'Save' }}</button>
            <button class="link-btn link-btn--muted" type="button" @click="editingLimit = false">Cancel</button>
          </div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Chips used today</div>
          <div class="stat-value">{{ N(player.chips_used_today) }}</div>
        </div>
      </div>

      <div class="grid-two">
        <div class="col">
          <div class="card section-card">
            <div class="section-title">Gaming account (deposit DVA)</div>
            <div v-if="player.gaming_account" class="dva-row">
              <div v-for="dva in player.gaming_account.dvas" :key="dva.id">{{ dva.bank_name }} &middot; {{ dva.account_number }}</div>
            </div>
            <div v-else class="dva-empty">No gaming account/DVA provisioned yet.</div>
          </div>

          <div class="card section-card">
            <div class="section-title">Receiving bank accounts</div>
            <div v-for="bank in player.bank_accounts" :key="bank.id" class="bank-row">
              <div>
                <div class="bank-name">{{ bank.bank_name }} &middot; {{ bank.account_number }}</div>
                <div class="bank-account-name">{{ bank.account_name }}</div>
              </div>
              <span v-if="bank.is_default" class="badge badge--open">default</span>
            </div>
            <p v-if="!player.bank_accounts.length" class="muted">No bank accounts on file.</p>
          </div>

          <div class="card section-card">
            <div class="section-title">Outstanding activity <span class="lbl--muted">between game-days</span></div>
            <p v-if="outstandingLoading && !outstanding.length" class="muted">Loading…</p>
            <p v-else-if="!outstanding.length" class="muted">Nothing recorded outside a game-day for {{ player.display_name }}.</p>
            <div v-for="row in outstanding" :key="row.id" class="feed-row" :class="{ 'feed-row--voided': row.is_voided }">
              <div class="feed-dot" :class="`lane-${TRANSACTION_TYPES[row.type]?.lane || 'other'}`" />
              <div class="feed-info">
                <div class="feed-title">
                  {{ TRANSACTION_TYPES[row.type]?.label || row.type }}
                  <span v-if="TRANSACTION_STATUS_BADGE[row.status]" class="badge" :class="`badge--${TRANSACTION_STATUS_BADGE[row.status]}`">{{ row.status.replace('_', ' ') }}</span>
                </div>
                <div class="feed-meta">{{ formatDate(row.created_at) }} &middot; {{ formatTime(row.created_at) }}</div>
              </div>
              <div class="feed-amounts">
                <div class="money">{{ row.signed_amount > 0 ? '+' : '' }}{{ N(row.signed_amount) }}</div>
                <div v-if="row.is_voided" class="feed-balance feed-balance--voided">VOIDED</div>
                <div v-else class="feed-balance">{{ N(row.running_balance) }}</div>
              </div>
            </div>
          </div>

          <div v-if="auth.isOwner" class="card section-card">
            <div class="section-title">Record Deal / Write-off</div>
            <form class="deal-form" @submit.prevent="onSubmitDeal">
              <div class="deal-type-row">
                <label class="deal-type">
                  <input v-model="dealType" type="radio" value="PAYMENT_DEAL" />
                  Deal
                </label>
                <label class="deal-type">
                  <input v-model="dealType" type="radio" value="WRITE_OFF" />
                  Write-off
                </label>
              </div>
              <input
                :value="displayDealAmount" type="text" inputmode="decimal" placeholder="Amount" required class="deal-input"
                @input="e => (dealAmount = parseAmountInput(e.target.value))"
              />
              <input v-model="dealReason" type="text" placeholder="Reason" required class="deal-input" />
              <select v-model="dealGameDayId" class="deal-input">
                <option value="">Outstanding (no game-day)</option>
                <option v-for="gd in gameDays" :key="gd.id" :value="gd.id">Game-Day #{{ gd.number }} &middot; {{ formatDate(gd.started_at) }}</option>
              </select>
              <p v-if="dealError" class="form-error">{{ dealError }}</p>
              <button class="btn btn--primary" type="submit" :disabled="dealSubmitting">
                {{ dealSubmitting ? 'Recording…' : `Record ${dealType === 'PAYMENT_DEAL' ? 'Deal' : 'Write-off'}` }}
              </button>
            </form>
          </div>
        </div>

        <div class="col">
          <div class="card section-card">
            <div class="section-title">Any game-day's activity</div>
            <select v-model="selectedGameDayId" class="gd-select">
              <option value="">Select a game-day…</option>
              <option v-for="gd in gameDays" :key="gd.id" :value="gd.id">
                Game-Day #{{ gd.number }} &middot; {{ formatDate(gd.started_at) }} &middot; {{ gd.status }}
              </option>
            </select>

            <p v-if="!selectedGameDayId" class="muted gd-hint">Pick a game-day to see {{ player.display_name }}'s activity for just that day.</p>
            <p v-else-if="gdLedgerLoading" class="muted">Loading…</p>
            <p v-else-if="!gdLedger.length" class="muted">{{ player.display_name }} wasn't part of that game-day.</p>
            <div v-else>
              <div v-for="row in gdLedger" :key="row.id" class="feed-row" :class="{ 'feed-row--voided': row.is_voided }">
                <div class="feed-dot" :class="`lane-${TRANSACTION_TYPES[row.type]?.lane || 'other'}`" />
                <div class="feed-info">
                  <div class="feed-title">
                    {{ TRANSACTION_TYPES[row.type]?.label || row.type }}
                    <span v-if="TRANSACTION_STATUS_BADGE[row.status]" class="badge" :class="`badge--${TRANSACTION_STATUS_BADGE[row.status]}`">{{ row.status.replace('_', ' ') }}</span>
                  </div>
                  <div class="feed-meta">{{ formatTime(row.created_at) }}</div>
                </div>
                <div class="feed-amounts">
                  <div class="money">{{ row.signed_amount > 0 ? '+' : '' }}{{ N(row.signed_amount) }}</div>
                  <div v-if="row.is_voided" class="feed-balance feed-balance--voided">VOIDED</div>
                  <div v-else class="feed-balance">bal {{ N(row.running_balance) }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.header-row { margin-bottom: 16px; }
.back-btn { border: none; background: none; font-size: 13.5px; font-weight: 600; color: var(--text-secondary); cursor: pointer; padding: 4px 0; }
.back-btn:hover { color: var(--text-primary); }
.muted { color: var(--text-secondary); font-size: 13px; }

.page-header { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0; }
.code { color: var(--text-tertiary); font-size: 13px; }

.stat-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-bottom: 16px; }
.stat-card { padding: 16px 18px; display: flex; flex-direction: column; gap: 6px; }
.stat-label { font-size: 11px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.stat-value { font-family: var(--font-mono); font-weight: 600; font-size: 20px; font-variant-numeric: tabular-nums; color: var(--text-primary); }
.money--pos { color: var(--success-text); }
.money--neg { color: var(--danger-text); }

.limit-row { display: flex; align-items: baseline; gap: 10px; }
.limit-edit { display: flex; align-items: center; gap: 8px; }
.limit-input {
  width: 100px;
  height: 32px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 8px;
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-primary);
  background: var(--surface);
}
.limit-input:focus { outline: none; border-color: var(--accent); }
.link-btn { border: none; background: none; font-size: 12px; font-weight: 700; color: var(--accent-text); cursor: pointer; padding: 0; }
.link-btn--muted { color: var(--text-tertiary); font-weight: 500; }
.link-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.deal-form { display: flex; flex-direction: column; gap: 10px; }
.deal-type-row { display: flex; gap: 16px; }
.deal-type { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-primary); cursor: pointer; }
.deal-input {
  height: var(--control-row-min);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 12px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-primary);
  background: var(--surface);
}
.deal-input:focus { outline: none; border-color: var(--accent); }
.form-error {
  font-size: 12.5px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
}

.grid-two { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }
.col { display: flex; flex-direction: column; gap: 16px; }
.section-card { padding: 18px 20px; }
.section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; }
.lbl--muted { font-weight: 500; text-transform: none; color: var(--text-tertiary); font-size: 11px; margin-left: 6px; }

.dva-row, .dva-empty {
  border: 1px dashed var(--border-strong);
  background: var(--disabled-surface);
  border-radius: var(--radius-sm);
  padding: 12px;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.bank-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--border); }
.bank-row:last-child { border-bottom: none; }
.bank-name { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.bank-account-name { font-size: 11.5px; color: var(--text-tertiary); }

.gd-select {
  width: 100%;
  height: var(--control-row-min);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 12px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-primary);
  background: var(--surface);
  margin-bottom: 12px;
}
.gd-select:focus { outline: none; border-color: var(--accent); }
.gd-hint { padding: 8px 0; }

.feed-row { display: flex; align-items: center; gap: 10px; padding: 9px 0; border-bottom: 1px solid var(--border); font-size: 12.5px; }
.feed-row:last-child { border-bottom: none; }
.feed-row--voided { opacity: 0.55; text-decoration: line-through; }
.feed-dot { width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0; background: var(--lane-other-bg); }
.feed-dot.lane-chips { background: var(--lane-chips-bg); }
.feed-dot.lane-payments { background: var(--lane-payments-bg); }
.feed-info { flex-grow: 1; min-width: 0; }
.feed-title { font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.feed-meta { font-size: 10.5px; color: var(--text-tertiary); }
.feed-amounts { text-align: right; flex-shrink: 0; }
.feed-amounts .money { display: block; font-family: var(--font-mono); font-weight: 700; color: var(--text-primary); }
.feed-balance { font-family: var(--font-mono); font-size: 10.5px; color: var(--text-tertiary); }
.feed-balance--voided { font-weight: 700; letter-spacing: 0.04em; color: var(--status-voided-text); }

@media (max-width: 860px) {
  .stat-grid { grid-template-columns: 1fr; }
  .grid-two { grid-template-columns: 1fr; }
}
</style>
