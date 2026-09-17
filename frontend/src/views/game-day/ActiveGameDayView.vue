<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useGameDayStore } from '@/stores/gameDay'
import { useAuthorizerConfirm } from '@/composables/useAuthorizerConfirm'
import TransactionEntryModal from '@/components/shared/TransactionEntryModal.vue'
import VoidEntryModal from '@/components/shared/VoidEntryModal.vue'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import AddPlayerModal from '@/components/shared/AddPlayerModal.vue'
import { canVoidTransaction } from '@/utils/canVoid'
import { useToast } from '@/composables/useToast'
import api from '@/api/axios'

const auth = useAuthStore()
const gameDay = useGameDayStore()
const router = useRouter()
const { confirm } = useAuthorizerConfirm()
const toast = useToast()

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
    // `activity` (not `ledger`) — running_balance here is scoped per-player,
    // not the club-wide cumulative total `ledger` returns. See
    // gaming.selectors.game_day_activity_feed's docstring.
    const { data } = await api.get(`/game-days/${gameDay.current.id}/activity/`)
    ledger.value = data.slice().reverse() // most recent first
  } finally {
    ledgerLoading.value = false
  }
}

function refreshAll() {
  return Promise.all([loadPlayers(), loadLedger()])
}

// Player picker — pills only (2026-09-14): every seated player is shown at
// once, no search. A real game-day never has more than ~10 people at the
// table, so browsing beats typing. Tapping a pill just selects it directly.
const selectedPlayerId = ref(null)

// Refetch whenever the open game-day changes (open, close, or the very first
// time AppShell's own fetchCurrent() resolves after this view has mounted).
watch(() => gameDay.current?.id, id => {
  selectedPlayerId.value = null
  if (id) refreshAll()
  else {
    players.value = []
    ledger.value = []
  }
}, { immediate: true })

const selectedPlayer = computed(() => players.value.find(p => p.id === selectedPlayerId.value) || null)

// "Active" vs "total" seated — total is every GameDayPlayer row for tonight
// (players.value, unchanged); active is those still at the table (left_at
// null). Only active counts toward MAX_ACTIVE_PLAYERS (see AddPlayerModal).
const activeCount = computed(() => players.value.filter(p => !p.left_at).length)
const departedCount = computed(() => players.value.length - activeCount.value)

function selectPlayer(p) {
  selectedPlayerId.value = p.id
}

// Add-player modal
const addPlayerOpen = ref(false)
function onPlayerAdded() {
  refreshAll()
}

// Entry sheet
const entryModal = ref(null) // { type, player } | null
// Set when the entry sheet was opened from the "Leave Table → Yes, return
// chips" choice below — its CHIPS_IN save is what then marks them left,
// chained here rather than in TransactionEntryModal itself.
const pendingLeave = ref(null)

function openEntry(type, player = selectedPlayer.value) {
  entryModal.value = { type, player }
}

function onEntryClosed() {
  entryModal.value = null
  pendingLeave.value = null
}

async function onEntrySaved() {
  const wasLeaving = pendingLeave.value
  entryModal.value = null
  pendingLeave.value = null
  if (wasLeaving) {
    try {
      await api.post(`/game-days/${gameDay.current.id}/players/${wasLeaving.id}/leave/`)
      toast.success(`${wasLeaving.display_name} returned their chips and left the table.`)
    } catch {
      toast.error(`Chips recorded, but couldn't mark ${wasLeaving.display_name} as left — try Leave Table again.`)
    }
    if (selectedPlayerId.value === wasLeaving.id) selectedPlayerId.value = null
  }
  refreshAll()
}

// Leave Table — see PLAN.md's "leave the table" entry. "Return to Table"
// was removed 2026-09-15: a departed player comes back ONLY by being issued
// chips (CHIPS_OUT), never through a bare re-add — so the 8th action-grid
// button only ever renders for a still-active player now (see template).
const leaveTarget = ref(null) // the player being asked "returning chips first?", or null

function onLeaveClick() {
  leaveTarget.value = selectedPlayer.value
}

async function onLeaveWithoutChips() {
  const player = leaveTarget.value
  leaveTarget.value = null
  try {
    await api.post(`/game-days/${gameDay.current.id}/players/${player.id}/leave/`)
    toast.success(`${player.display_name} left the table.`)
    if (selectedPlayerId.value === player.id) selectedPlayerId.value = null
    refreshAll()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Could not mark this player as left.')
  }
}

function onLeaveWithChips() {
  const player = leaveTarget.value
  leaveTarget.value = null
  pendingLeave.value = player
  openEntry('CHIPS_IN', player)
}

function playerName(playerId) {
  if (!playerId) return ''
  return players.value.find(p => p.id === playerId)?.display_name || ''
}

const ledgerRows = computed(() => ledger.value.map(row => ({ ...row, player_name: playerName(row.player) })))

// Void
const voidTarget = ref(null) // the ledger row being voided, or null

function canVoid(row) {
  return canVoidTransaction(row, auth.user, gameDay.current?.status)
}

function onVoided() {
  voidTarget.value = null
  toast.success('Entry voided.')
  refreshAll()
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
        <div>
          <div class="lbl">Tonight's players</div>
          <div v-if="departedCount" class="picker-sub">{{ activeCount }} active &middot; {{ departedCount }} left tonight</div>
        </div>
        <button class="new-btn" type="button" @click="addPlayerOpen = true">+ Add Player</button>
      </div>

      <p v-if="playersLoading && !players.length" class="muted">Loading…</p>
      <p v-else-if="!players.length" class="muted empty-players">No players yet tonight — add one to get started.</p>
      <div v-else class="pills">
        <button
          v-for="p in players" :key="p.id" type="button" class="pill"
          :class="{ 'pill--active': p.id === selectedPlayerId, 'pill--departed': p.left_at }"
          @click="selectPlayer(p)"
        >
          {{ p.display_name }} &middot; {{ p.account_code }}
          <span v-if="p.left_at" class="pill-tag">left</span>
        </button>
      </div>

      <div v-if="selectedPlayer" class="card section player-panel">
        <div class="panel-head">
          <div class="lbl">
            Record for {{ selectedPlayer.display_name }} ({{ selectedPlayer.account_code }}) &middot; balance
            <span class="money" :class="{ 'money--positive': selectedPlayer.balance > 0 }">{{ N(selectedPlayer.balance) }}</span>
          </div>
          <div v-if="selectedPlayer.left_at" class="left-badge">Left the table</div>
          <div v-else-if="selectedPlayer.chips_limit != null" class="chips-limit-badge">
            Chips limit: {{ N(selectedPlayer.chips_used_today) }} of {{ N(selectedPlayer.chips_limit) }} used
          </div>
        </div>

        <div class="action-grid">
          <button class="action-btn action-btn--accent" type="button" @click="openEntry('CHIPS_OUT')">Issue Chips</button>
          <button class="action-btn" type="button" @click="openEntry('CHIPS_IN')">Return Chips</button>
          <button class="action-btn" type="button" @click="openEntry('PAYMENT_CASH')">Cash Payment</button>
          <button class="action-btn" type="button" @click="openEntry('PAYMENT_POS')">POS Payment</button>
          <button class="action-btn" type="button" @click="openEntry('PAYMENT_TRANSFER')">Transfer<br>(manual)</button>
          <button class="action-btn" type="button" @click="router.push(`/players/${selectedPlayer.id}`)">Payout</button>
          <button class="action-btn" type="button" @click="router.push(`/players/${selectedPlayer.id}`)">View Player</button>
          <button
            v-if="!selectedPlayer.left_at" class="action-btn action-btn--warn" type="button"
            @click="onLeaveClick"
          >Leave Table</button>
        </div>
        <p v-if="selectedPlayer.left_at" class="left-hint">
          {{ selectedPlayer.display_name }} left the table — Issue Chips to bring them back.
        </p>
      </div>
      <div v-else class="card section player-panel player-panel--empty">
        <p class="muted">Pick a player above to issue chips, take a payment, or view their balance.</p>
      </div>

      <div class="ledger-head">
        <div class="lbl">Today's activity</div>
        <div class="ledger-head-links">
          <button class="link-btn" type="button" @click="router.push(`/game-day/${gameDay.current.id}/ledger`)">Full Ledger &rarr;</button>
          <button class="link-btn" type="button" @click="onOpenCloseConfirm">Close Game-Day &rarr;</button>
        </div>
      </div>
      <div class="ledger-feed">
        <p v-if="ledgerLoading" class="muted">Loading…</p>
        <p v-else-if="!ledger.length" class="muted">No activity yet tonight.</p>
        <LedgerTable v-else :rows="ledgerRows" show-player voidable :can-void-fn="canVoid" @void="voidTarget = $event" />
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
      @close="onEntryClosed" @saved="onEntrySaved"
    />

    <!-- Leave Table: the confirmation IS the chips question, not a separate step. -->
    <div v-if="leaveTarget" class="overlay">
      <div class="dialog card leave-dialog">
        <div class="eyebrow">{{ leaveTarget.display_name }} is leaving the table</div>
        <p class="muted">Are they returning any chips first?</p>
        <div class="leave-actions">
          <button class="btn btn--secondary" type="button" @click="onLeaveWithChips">Yes &mdash; return chips</button>
          <button class="btn btn--secondary" type="button" @click="onLeaveWithoutChips">No &mdash; just leaving</button>
        </div>
        <button class="link-btn leave-cancel" type="button" @click="leaveTarget = null">Cancel</button>
      </div>
    </div>

    <!-- recorded-by-name assumes the voider is also the recorder (canVoid's own
         non-Owner rule guarantees this) — will need a real lookup once an
         Owner-role frontend can void someone else's entry. -->
    <VoidEntryModal
      v-if="voidTarget" :transaction="voidTarget" :player-name="playerName(voidTarget.player)"
      :recorded-by-name="auth.user?.fullName" @close="voidTarget = null" @voided="onVoided"
    />

    <AddPlayerModal v-if="addPlayerOpen" @close="addPlayerOpen = false" @added="onPlayerAdded" />
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

.picker-row { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 10px; }
.picker-sub { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
.new-btn {
  height: 40px;
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
.empty-players {
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 16px;
  text-align: center;
  margin-bottom: 14px;
}

/* flex-wrap (not overflow-x scroll) — up to ~10 seated players should all
   stay visible across a couple of rows, not require a side-scroll. */
.pills { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.pill {
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
.pill--departed { background: var(--status-voided-bg); color: var(--status-voided-text); border-color: transparent; }
.pill-tag { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; margin-left: 4px; opacity: 0.8; }

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
.left-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--status-voided-text);
  border: 1px solid var(--border-strong);
  background: var(--status-voided-bg);
  border-radius: 12px;
  padding: 3px 10px;
  white-space: nowrap;
}

.action-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.left-hint { font-size: 11.5px; color: var(--text-tertiary); text-align: center; margin-top: 8px; }
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
.action-btn--warn { border-color: var(--warning); color: var(--warning-text); }

.ledger-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 6px; margin-top: 4px; }
.ledger-head-links { display: flex; gap: 16px; }
.link-btn { border: none; background: none; font-size: 11.5px; font-weight: 700; color: var(--accent); cursor: pointer; }
.ledger-feed { border-top: 1px solid var(--border); }

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

.leave-dialog .muted { margin: 6px 0 20px; }
.leave-actions { display: flex; flex-direction: column; gap: 10px; }
.leave-cancel { display: block; margin: 16px auto 0; }
</style>
