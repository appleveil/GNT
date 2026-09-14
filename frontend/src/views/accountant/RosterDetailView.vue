<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/axios'
import { TRANSACTION_TYPES, TRANSACTION_STATUS_BADGE } from '@/constants/transactionTypes'
import { useToast } from '@/composables/useToast'

// Read-only player detail for Accountant/Owner (Phase B, 2026-09-14) — the
// "any game-day's ledger" requirement is met with a plain game-day picker
// rather than a dedicated backend endpoint: GET
// /game-days/{id}/players/{player_pk}/ledger/ is a plain queryset filter
// server-side (gaming/selectors.py's player_game_day_ledger), so it just
// returns an empty list for a game-day this player wasn't part of — no 404,
// confirmed by reading that selector directly. The picker can therefore
// offer every game-day, not just ones this player attended.
const route = useRoute()
const router = useRouter()
const toast = useToast()

const player = ref(null)
const loading = ref(true)

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
          <div class="stat-value">{{ N(player.chips_limit) }}</div>
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
