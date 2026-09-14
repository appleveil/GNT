<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useGameDayStore } from '@/stores/gameDay'
import { useAuthorizerConfirm } from '@/composables/useAuthorizerConfirm'
import TransactionEntryModal from '@/components/shared/TransactionEntryModal.vue'
import { TRANSACTION_TYPES, TRANSACTION_STATUS_BADGE } from '@/constants/transactionTypes'
import api from '@/api/axios'

const auth = useAuthStore()
const gameDay = useGameDayStore()
const router = useRouter()
const { confirm } = useAuthorizerConfirm()

const opening = ref(false)
const openError = ref('')

const closePreview = ref(null) // null = confirm dialog closed
const closing = ref(false)
const closeError = ref('')

async function nextGameDayNumber() {
  const { data } = await api.get('/game-days/')
  return (data[0]?.number || 0) + 1
}

async function onOpenGameDay() {
  openError.value = ''
  opening.value = true
  let number
  try {
    number = await nextGameDayNumber()
  } catch {
    openError.value = 'Could not determine the next game-day number.'
    opening.value = false
    return
  }
  opening.value = false

  confirm({
    title: `Open Game-Day #${number}`,
    subtitle: 'Will start now',
    onSubmit: async payload => {
      const { data } = await api.post('/game-days/open/', { number, ...payload })
      gameDay.current = data
    },
  })
}

async function onOpenCloseConfirm() {
  closeError.value = ''
  try {
    const { data } = await api.get(`/game-days/${gameDay.current.id}/close-preview/`)
    closePreview.value = data
  } catch {
    closeError.value = 'Could not load game-day totals.'
  }
}

async function onConfirmClose() {
  closing.value = true
  closeError.value = ''
  try {
    await api.post(`/game-days/${gameDay.current.id}/close/`, {})
    closePreview.value = null
    gameDay.current = null
  } catch (err) {
    closeError.value = err.response?.data?.detail || 'Could not close the game-day.'
  } finally {
    closing.value = false
  }
}

// ── Players (seated tonight) + the entry-recording working screen ─────────

const players = ref([])
const playersLoading = ref(false)
const ledger = ref([])
const ledgerLoading = ref(false)

async function loadPlayers() {
  if (!gameDay.current) {
    players.value = []
    return
  }
  playersLoading.value = true
  try {
    const { data } = await api.get(`/game-days/${gameDay.current.id}/players/`)
    players.value = data
  } finally {
    playersLoading.value = false
  }
}

async function loadLedger() {
  if (!gameDay.current) {
    ledger.value = []
    return
  }
  ledgerLoading.value = true
  try {
    const { data } = await api.get(`/game-days/${gameDay.current.id}/ledger/`)
    ledger.value = data.slice().reverse() // most recent first
  } finally {
    ledgerLoading.value = false
  }
}

function refreshAll() {
  return Promise.all([loadPlayers(), loadLedger()])
}

// Player picker — type-to-filter combobox, same pattern as BankAccountFields.
const playerQuery = ref('')
const pickerOpen = ref(false)
const selectedPlayerId = ref(null)
const recentPlayerIds = ref([]) // most-recently-picked first, for the quick-switch pills

// Refetch whenever the open game-day changes (open, close, or the very first
// time AppShell's own fetchCurrent() resolves after this view has mounted).
// Must come after the refs above — immediate:true runs this synchronously,
// before any later `const` in this scope has initialized.
watch(() => gameDay.current?.id, id => {
  selectedPlayerId.value = null
  recentPlayerIds.value = []
  if (id) refreshAll()
  else {
    players.value = []
    ledger.value = []
  }
}, { immediate: true })

const filteredPlayers = computed(() => {
  const q = playerQuery.value.trim().toLowerCase()
  if (!q) return players.value
  return players.value.filter(
    p => p.display_name.toLowerCase().includes(q) || p.account_code.toLowerCase().includes(q),
  )
})
const selectedPlayer = computed(() => players.value.find(p => p.id === selectedPlayerId.value) || null)
const recentPlayers = computed(() =>
  recentPlayerIds.value.map(id => players.value.find(p => p.id === id)).filter(Boolean),
)

function selectPlayer(p) {
  selectedPlayerId.value = p.id
  playerQuery.value = ''
  pickerOpen.value = false
  recentPlayerIds.value = [p.id, ...recentPlayerIds.value.filter(id => id !== p.id)].slice(0, 4)
}

// Entry sheet
const entryModal = ref(null) // { type, player } | null

function openEntry(type, player = selectedPlayer.value) {
  entryModal.value = { type, player }
}

function onEntrySaved() {
  entryModal.value = null
  refreshAll()
}

function playerName(playerId) {
  if (!playerId) return ''
  return players.value.find(p => p.id === playerId)?.display_name || ''
}

function formatTime(iso) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div>
    <!-- No game-day open -->
    <div v-if="!gameDay.isOpen" class="card empty-state">
      <div class="eyebrow">No Game-Day Open</div>
      <p class="muted">Open a game-day to start seating players and recording activity.</p>
      <p v-if="openError" class="form-error">{{ openError }}</p>
      <button class="btn btn--primary" type="button" :disabled="opening" @click="onOpenGameDay">
        {{ opening ? 'Loading…' : 'Open Game-Day' }}
      </button>
    </div>

    <!-- Game-day open: the real working screen -->
    <template v-else>
      <div class="card section general-section">
        <div class="lbl">General &mdash; not tied to a player</div>
        <div class="general-actions">
          <button class="general-btn" type="button" @click="openEntry('RAKE', null)">
            <span class="general-btn-title">Rake</span>
            <span class="general-btn-sub">from box, end of day</span>
          </button>
          <button class="general-btn" type="button" @click="openEntry('TIP', null)">
            <span class="general-btn-title">Tip</span>
            <span class="general-btn-sub">from tips, end of day</span>
          </button>
        </div>
      </div>

      <div class="picker-row">
        <div class="combobox">
          <input
            v-model="playerQuery" type="text" placeholder="Search or select a player…" autocomplete="off"
            @focus="pickerOpen = true" @blur="pickerOpen = false"
            @keydown.esc="pickerOpen = false"
          />
          <ul v-if="pickerOpen" class="combobox-list">
            <li
              v-for="p in filteredPlayers" :key="p.id" class="combobox-option"
              @mousedown.prevent="selectPlayer(p)"
            >
              {{ p.display_name }} &middot; {{ p.account_code }}
            </li>
            <li v-if="!filteredPlayers.length" class="combobox-empty">
              {{ playersLoading ? 'Loading…' : 'No matching players seated tonight' }}
            </li>
          </ul>
        </div>
        <button class="new-btn" type="button" @click="router.push('/players/new')">+ New</button>
      </div>

      <div v-if="recentPlayers.length" class="pills">
        <button
          v-for="p in recentPlayers" :key="p.id" type="button" class="pill"
          :class="{ 'pill--active': p.id === selectedPlayerId }" @click="selectPlayer(p)"
        >
          {{ p.display_name }} &middot; {{ p.account_code }}
        </button>
      </div>

      <div v-if="selectedPlayer" class="card section player-panel">
        <div class="panel-head">
          <div class="lbl">
            Record for {{ selectedPlayer.display_name }} ({{ selectedPlayer.account_code }}) &middot; balance
            <span class="money" :class="{ 'money--positive': selectedPlayer.balance > 0 }">{{ N(selectedPlayer.balance) }}</span>
          </div>
          <div v-if="selectedPlayer.chips_limit != null" class="chips-limit-badge">
            Chips limit: {{ N(selectedPlayer.chips_used_today) }} of {{ N(selectedPlayer.chips_limit) }} used
          </div>
        </div>

        <div class="action-grid">
          <button class="action-btn action-btn--accent" type="button" @click="openEntry('CHIPS_OUT')">Issue Chips</button>
          <button class="action-btn" type="button" @click="openEntry('CHIPS_IN')">Chips In</button>
          <button class="action-btn" type="button" @click="openEntry('PAYMENT_CASH')">Cash Payment</button>
          <button class="action-btn" type="button" @click="openEntry('PAYMENT_POS')">POS Payment</button>
          <button class="action-btn" type="button" @click="openEntry('PAYMENT_TRANSFER')">Transfer<br>(manual)</button>
          <button class="action-btn" type="button" @click="router.push(`/players/${selectedPlayer.id}`)">Payout</button>
        </div>
      </div>
      <div v-else class="card section player-panel player-panel--empty">
        <p class="muted">Pick a player above to issue chips, take a payment, or view their balance.</p>
      </div>

      <div class="ledger-head">
        <div class="lbl">Today's activity</div>
        <button class="link-btn" type="button" @click="onOpenCloseConfirm">Close Game-Day &rarr;</button>
      </div>
      <div class="ledger-feed">
        <p v-if="ledgerLoading" class="muted">Loading…</p>
        <p v-else-if="!ledger.length" class="muted">No activity yet tonight.</p>
        <div
          v-for="row in ledger" :key="row.id" class="ledger-row"
          :class="{ 'ledger-row--voided': row.is_voided }"
        >
          <div class="ledger-dot" :class="`lane-${TRANSACTION_TYPES[row.type]?.lane || 'other'}`" />
          <div class="ledger-info">
            <div class="ledger-title">
              <template v-if="playerName(row.player)">{{ playerName(row.player) }} &middot; </template>{{ TRANSACTION_TYPES[row.type]?.label || row.type }}
              <span
                v-if="TRANSACTION_STATUS_BADGE[row.status]" class="badge"
                :class="`badge--${TRANSACTION_STATUS_BADGE[row.status]}`"
              >{{ row.status.replace('_', ' ') }}</span>
            </div>
            <div class="ledger-meta">{{ formatTime(row.created_at) }}</div>
          </div>
          <div class="ledger-amounts">
            <div class="money">{{ row.signed_amount > 0 ? '+' : '' }}{{ N(row.signed_amount) }}</div>
            <div class="ledger-balance">bal {{ N(row.running_balance) }}</div>
          </div>
        </div>
      </div>
    </template>

    <!-- Close confirmation -->
    <div v-if="closePreview" class="overlay">
      <div class="dialog card">
        <div class="eyebrow">Close Game-Day #{{ gameDay.current.number }}?</div>
        <p class="muted">This locks entries — only the Owner can amend after closing.</p>

        <div class="stats">
          <div class="stat-row"><span>Players seated</span><span class="money">{{ closePreview.num_players_seated }}</span></div>
          <div class="stat-row"><span>Chips out</span><span class="money">{{ N(closePreview.chips_out_total) }}</span></div>
          <div class="stat-row"><span>Chips returned</span><span class="money">{{ N(closePreview.chips_in_total) }}</span></div>
          <div class="stat-row"><span>Payments received</span><span class="money">{{ N(closePreview.total_payments) }}</span></div>
          <div class="stat-row"><span>Rake / Tips</span><span class="money">{{ N(closePreview.rake_total) }} / {{ N(closePreview.tips_total) }}</span></div>
          <div class="stat-row">
            <span>Unreturned chips tonight <small>(out − in − rake − tips)</small></span>
            <span class="money warn">{{ N(closePreview.chips_variance) }}</span>
          </div>
          <div class="stat-row">
            <span>Outstanding chips <small>(club-wide, after this close)</small></span>
            <span class="money warn">{{ N(closePreview.outstanding_chips_after_close) }}</span>
          </div>
          <div class="stat-row stat-row--total"><span>Game balance</span><span class="money">{{ N(closePreview.game_balance) }}</span></div>
        </div>

        <p v-if="closeError" class="form-error">{{ closeError }}</p>

        <div class="actions">
          <button class="btn btn--secondary" type="button" @click="closePreview = null">Cancel</button>
          <button class="btn btn--primary" type="button" :disabled="closing" @click="onConfirmClose">
            {{ closing ? 'Closing…' : 'Close Game-Day' }}
          </button>
        </div>
      </div>
    </div>

    <TransactionEntryModal
      v-if="entryModal" :type="entryModal.type" :player="entryModal.player" :game-day-id="gameDay.current.id"
      @close="entryModal = null" @saved="onEntrySaved"
    />
  </div>
</template>

<style scoped>
.card { padding: 24px; }
.muted { color: var(--text-secondary); font-size: 13px; line-height: 1.6; margin: 8px 0 16px; }
.empty-state { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.form-error {
  font-size: 13px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  margin-bottom: 8px;
}

.section { margin-bottom: 14px; }
.lbl {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.general-section { padding: 12px 14px; background: var(--warning-bg); border-color: var(--warning); }
.general-section .lbl { color: var(--warning-text); margin-bottom: 8px; }
.general-actions { display: flex; gap: 8px; }
.general-btn {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--border-strong);
  background: var(--surface);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  cursor: pointer;
  text-align: left;
}
.general-btn-title { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }
.general-btn-sub { font-size: 11px; color: var(--text-tertiary); }

.picker-row { display: flex; gap: 10px; margin-bottom: 12px; }
.combobox { position: relative; flex-grow: 1; }
.combobox input {
  width: 100%;
  height: 48px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 14px;
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text-primary);
  background: var(--surface);
}
.combobox-list {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: 20;
  max-height: 240px;
  overflow-y: auto;
  list-style: none;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-md);
}
.combobox-option { padding: 10px 14px; font-size: 13.5px; color: var(--text-primary); cursor: pointer; border-bottom: 1px solid var(--border); }
.combobox-option:last-child { border-bottom: none; }
.combobox-option:hover { background: var(--accent-bg); color: var(--accent-text); }
.combobox-empty { padding: 10px 14px; font-size: 13px; color: var(--text-tertiary); }
.new-btn {
  height: 48px;
  padding: 0 16px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  background: var(--surface);
  font-size: 13px;
  font-weight: 700;
  color: var(--accent);
  cursor: pointer;
  white-space: nowrap;
}

.pills { display: flex; gap: 8px; margin-bottom: 14px; overflow-x: auto; }
.pill {
  flex-shrink: 0;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 18px;
  padding: 8px 14px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
}
.pill--active { border-color: var(--accent); background: var(--accent); color: #fff; }

.player-panel--empty { text-align: center; }
.player-panel--empty .muted { margin: 4px 0; }
.panel-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.panel-head .lbl { text-transform: none; font-size: 13px; font-weight: 500; color: var(--text-secondary); letter-spacing: normal; }
.panel-head .money { font-weight: 700; color: var(--text-primary); }
.panel-head .money--positive { color: var(--success); }
.chips-limit-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--warning-text);
  border: 1px solid var(--warning);
  background: var(--warning-bg);
  border-radius: 12px;
  padding: 3px 10px;
  white-space: nowrap;
}

.action-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.action-btn {
  border: 1px solid var(--border-strong);
  background: var(--surface);
  border-radius: var(--radius-sm);
  padding: 14px 6px;
  min-height: 64px;
  font-family: var(--font-sans);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
  text-align: center;
  line-height: 1.3;
}
.action-btn--accent { border-color: var(--accent); border-width: 1.5px; color: var(--accent-text); }

.ledger-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 6px; margin-top: 4px; }
.link-btn { border: none; background: none; font-size: 11.5px; font-weight: 700; color: var(--accent); cursor: pointer; }
.ledger-feed { border-top: 1px solid var(--border); }
.ledger-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 4px;
  border-bottom: 1px solid var(--border);
}
.ledger-row--voided { opacity: 0.5; text-decoration: line-through; }
.ledger-dot { width: 30px; height: 30px; border-radius: 50%; flex-shrink: 0; background: var(--lane-other-bg); }
.ledger-dot.lane-chips { background: var(--lane-chips-bg); }
.ledger-dot.lane-payments { background: var(--lane-payments-bg); }
.ledger-info { flex-grow: 1; min-width: 0; }
.ledger-title { font-size: 13px; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.ledger-meta { font-size: 11px; color: var(--text-tertiary); }
.ledger-amounts { text-align: right; flex-shrink: 0; }
.ledger-amounts .money { display: block; font-size: 13px; font-weight: 700; color: var(--text-primary); }
.ledger-balance { font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); }

.overlay {
  position: fixed;
  inset: 0;
  background: rgba(20, 25, 32, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.dialog { width: 480px; max-width: 92vw; box-shadow: var(--shadow-md); }
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
.money.warn { color: var(--warning-text); }
.actions { display: flex; gap: 14px; margin-top: 16px; }
.actions .btn { flex: 1; }
</style>
