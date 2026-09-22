<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useGameDayStore } from '@/stores/gameDay'
import TransactionEntryModal from '@/components/shared/TransactionEntryModal.vue'
import VoidEntryModal from '@/components/shared/VoidEntryModal.vue'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import AddPlayerModal from '@/components/shared/AddPlayerModal.vue'
import StartGameDayModal from '@/components/shared/StartGameDayModal.vue'
import { canVoidTransaction } from '@/utils/canVoid'
import { useToast } from '@/composables/useToast'
import api from '@/api/axios'

const auth = useAuthStore()
const gameDay = useGameDayStore()
const router = useRouter()
const toast = useToast()

const opening = ref(false)
const openError = ref('')

// "Start game-day" flow (2026-09-21) — Select game → Select table → confirm
// buy-in, THEN the Owner/FM PIN (still handled inside StartGameDayModal via
// the shared useAuthorizerConfirm). Replaces the old flow, which skipped
// straight from this button to the PIN modal with no game/table selection
// at all — the backend (open_game_day's game_id/table_id/buy_in_amount)
// already supported this; only the frontend step was missing. See
// PLAN.md's "Game/Table selection at start" entry.
const startFlowOpen = ref(false)
const startFlowNumber = ref(null)

async function nextGameDayNumber() {
  const { data } = await api.get('/game-days/')
  return (data[0]?.number || 0) + 1
}

async function onOpenGameDay() {
  openError.value = ''
  opening.value = true
  try {
    startFlowNumber.value = await nextGameDayNumber()
    startFlowOpen.value = true
  } catch {
    openError.value = 'Could not determine the next game-day number.'
  } finally {
    opening.value = false
  }
}

function onStartFlowClosed() {
  startFlowOpen.value = false
}

function onGameDayStarted(data) {
  startFlowOpen.value = false
  gameDay.current = data
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

// Numbered seats (2026-09-17) — per-game now (Texas Hold'em 9, Omaha 8, ...),
// via gaming.selectors.max_active_players, exposed directly on the game-day
// as max_players (2026-09-21) so this never needs its own game/table lookup.
// Every seat 1..MAX renders as its own pill, occupied or empty, so the
// Cashier can tell at a glance who's where and which seats are free; a
// still-active player with no seat_number yet (e.g. seated via the bulk
// "+ Add Player" flow) shows separately as "unassigned" until moved into one.
const maxSeats = computed(() => gameDay.current?.max_players ?? 9)
const seatSlots = computed(() => {
  const bySeat = new Map()
  for (const p of players.value) {
    if (!p.left_at && p.seat_number) bySeat.set(p.seat_number, p)
  }
  return Array.from({ length: maxSeats.value }, (_, i) => {
    const seatNumber = i + 1
    return { seatNumber, player: bySeat.get(seatNumber) || null }
  })
})
const unassignedPlayers = computed(() => players.value.filter(p => !p.left_at && !p.seat_number))
const departedPlayers = computed(() => players.value.filter(p => p.left_at))

function selectPlayer(p) {
  selectedPlayerId.value = p.id
}

// Add-player modal — always opened by tapping a specific empty seat pill
// (see the seat grid below). The standalone "+ Add Player" button (added
// 2026-09-14, generic/unassigned/multi-select) was removed 2026-09-21 as
// redundant — every empty seat is already its own visible "add here" tap
// target, so a second, seat-less entry point just duplicated the same
// modal for no real gain. AddPlayerModal.vue is now always seat-scoped.
const addPlayerOpen = ref(false)
const seatTarget = ref(null)
function onEmptySeatClick(seatNumber) {
  seatTarget.value = seatNumber
  addPlayerOpen.value = true
}
function onAddPlayerClosed() {
  addPlayerOpen.value = false
  seatTarget.value = null
}
function onPlayerAdded() {
  refreshAll()
}

// Move/swap seat
const moveSeatTarget = ref(null) // the player being moved, or null
function onMoveSeatClick() {
  moveSeatTarget.value = selectedPlayer.value
}
const moveSeatOptions = computed(() => {
  if (!moveSeatTarget.value) return []
  return seatSlots.value.map(s => ({
    seatNumber: s.seatNumber,
    isCurrent: s.player?.id === moveSeatTarget.value.id,
    label: s.player
      ? (s.player.id === moveSeatTarget.value.id ? 'Current seat' : `Swap with ${s.player.display_name}`)
      : 'Empty',
  }))
})
async function onPickMoveSeat(seatNumber) {
  const player = moveSeatTarget.value
  moveSeatTarget.value = null
  try {
    await api.post(`/game-days/${gameDay.current.id}/players/${player.id}/move-seat/`, { seat_number: seatNumber })
    toast.success(`${player.display_name} moved to Seat ${seatNumber}.`)
    refreshAll()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Could not move this player.')
  }
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

// "Payment" — was three separate action-grid buttons (Cash / POS /
// Transfer), each doing the exact same thing (record a payment) with only
// the channel differing. Consolidated into one button + a small picker
// (2026-09-21, see the Cashier layout wireframe review) — cuts the grid
// from 9 buttons to 7 with no capability lost.
const paymentPickerOpen = ref(false)
function pickPaymentType(type) {
  paymentPickerOpen.value = false
  openEntry(type)
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

// A short stat-tile row above tonight's activity — derived entirely from
// the already-loaded activity feed (no extra API call). Added 2026-09-21:
// the page had no summary/"hero number" moment anywhere on it at all,
// unlike every other ledger view in the app.
const PAYMENT_TYPES = new Set(['PAYMENT_CASH', 'PAYMENT_TRANSFER', 'PAYMENT_POS', 'PAYMENT_DEAL'])
const chipsOutTonight = computed(() =>
  ledger.value.filter(r => r.type === 'CHIPS_OUT' && !r.is_voided).reduce((sum, r) => sum + Number(r.amount), 0)
)
const paymentsTonight = computed(() =>
  ledger.value.filter(r => PAYMENT_TYPES.has(r.type) && !r.is_voided).reduce((sum, r) => sum + Number(r.amount), 0)
)
// Sum of every row's signed_amount, not running_balance — running_balance
// on this feed is per-player-partitioned (see loadLedger's comment above),
// not the club-wide total. PROFIT_SPLIT_STAKE rows carry signed_amount=0
// (balance-neutral by design), so they fall out of this sum on their own —
// no type filtering needed here.
const tableBalanceTonight = computed(() =>
  ledger.value.filter(r => !r.is_voided).reduce((sum, r) => sum + Number(r.signed_amount), 0)
)

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
      <!-- Compacted to one slim row (2026-09-21, see the Cashier layout
           wireframe review) — was a tall stacked card (label above two
           full-width detailed buttons); this is a low-frequency, not-
           player-specific action, so it shouldn't compete for height with
           the actual working area below. The "General — not tied to a
           player" eyebrow was dropped entirely and this slot now carries
           the seat-count summary instead (previously its own separate
           .picker-row above the seat grid) — one row doing both jobs
           rather than two adjacent one-line sections. -->
      <div class="card section general-section">
        <div class="lbl">
          {{ activeCount }} active &middot; {{ maxSeats - activeCount }} seats free <!-- — tap an empty seat to add a player -->
          <template v-if="departedCount">&middot; ({{ departedCount }} players have left)</template>
        </div>

        <div class="general-actions">
          <button class="general-btn" type="button" @click="openEntry('RAKE', null)">
            <span class="general-btn-title">Rake</span>
            <span class="general-btn-sub">end of day</span>
          </button>
          <button class="general-btn" type="button" @click="openEntry('TIP', null)">
            <span class="general-btn-title">Tip</span>
            <span class="general-btn-sub">end of day</span>
          </button>
        </div>
      </div>

      <!-- Seat grid + selected player sit side by side (2026-09-21, see the
           Cashier layout wireframe review) — previously both were full-
           width, stacked vertically, so picking a player pushed the whole
           action panel below the fold on a full table. A fixed-width seat
           column keeps every seat and the working panel on screen together. -->
      <div class="working-area">
        <div class="seat-column">
          <p v-if="playersLoading && !players.length" class="muted">Loading…</p>
          <template v-else>
            <div class="pills">
              <button
                v-for="s in seatSlots" :key="s.seatNumber" type="button" class="pill"
                :class="s.player ? { 'pill--active': s.player.id === selectedPlayerId } : 'pill--empty'"
                @click="s.player ? selectPlayer(s.player) : onEmptySeatClick(s.seatNumber)"
              >
                <span class="pill-seat">{{ s.seatNumber }}</span>
                <span class="pill-label">{{ s.player ? `${s.player.display_name} · ${s.player.account_code}` : 'Empty' }}</span>
              </button>
            </div>

            <div v-if="unassignedPlayers.length" class="pills pills--secondary">
              <div class="pills-label">Unassigned</div>
              <button
                v-for="p in unassignedPlayers" :key="p.id" type="button" class="pill"
                :class="{ 'pill--active': p.id === selectedPlayerId }"
                @click="selectPlayer(p)"
              >
                <span class="pill-label">{{ p.display_name }} &middot; {{ p.account_code }}</span>
              </button>
            </div>

            <div v-if="departedPlayers.length" class="pills pills--secondary">
              <div class="pills-label">Left tonight ({{ departedCount }})</div>
              <button
                v-for="p in departedPlayers" :key="p.id" type="button" class="pill pill--departed"
                :class="{ 'pill--active': p.id === selectedPlayerId }"
                @click="selectPlayer(p)"
              >
                <span class="pill-label">{{ p.display_name }} &middot; {{ p.account_code }}</span>
                <span class="pill-tag">left</span>
              </button>
            </div>
          </template>
        </div>

        <div v-if="selectedPlayer" class="card section player-panel">
          <div class="panel-head">
            <div class="lbl">{{ selectedPlayer.display_name }} &middot; {{ selectedPlayer.account_code }}</div>
            <div v-if="selectedPlayer.left_at" class="left-badge">Left the table</div>
            <div v-else-if="selectedPlayer.chips_limit != null" class="chips-limit-badge">
              Chips limit: {{ N(selectedPlayer.chips_used_today) }} of {{ N(selectedPlayer.chips_limit) }} used
            </div>
          </div>

          <!-- The one hero-number moment on this panel — was a small inline
               figure buried in the "Record for..." line, easy to miss for
               the single fact a Cashier checks most often when a player's
               selected. Added 2026-09-21, see the Cashier layout wireframe
               review. -->
          <div class="hero-balance">
            <div class="hero-value money" :class="{ 'money--positive': selectedPlayer.balance > 0 }">{{ N(selectedPlayer.balance) }}</div>
            <div class="hero-caption">{{ selectedPlayer.display_name }}'s balance</div>
          </div>

          <div class="action-grid">
            <button class="action-btn action-btn--accent" type="button" @click="openEntry('CHIPS_OUT')">Issue Chips</button>
            <button class="action-btn" type="button" @click="openEntry('CHIPS_IN')">Return Chips</button>
            <button class="action-btn" type="button" @click="paymentPickerOpen = true">Payment &#9662;</button>
            <button class="action-btn" type="button" @click="router.push(`/players/${selectedPlayer.id}`)">Payout</button>
            <button class="action-btn" type="button" @click="router.push(`/players/${selectedPlayer.id}`)">View Player</button>
            <button v-if="!selectedPlayer.left_at" class="action-btn" type="button" @click="onMoveSeatClick">Move Seat</button>
            <button
              v-if="!selectedPlayer.left_at" class="action-btn action-btn--warn" type="button"
              @click="onLeaveClick"
            >Leave Table</button>
          </div>
          <p v-if="selectedPlayer.left_at" class="left-hint">
            {{ selectedPlayer.display_name }} left the table — Issue Chips to bring them back.
          </p>
        </div>
        <!-- Regression fix (2026-09-21): this empty state was dropped
             during an earlier edit this session — with no player selected
             the right column rendered nothing at all, instead of a prompt. -->
        <div v-else class="card section player-panel player-panel--empty">
          <p class="muted">Pick a player to issue chips, take a payment, or view their balance.</p>
        </div>
      </div>
      <!-- Only tonight's numbers + activity feed sit in the boxed white
           "screen-frame" — everything above (seating, the player panel)
           stays on the page's own pale background, per the review
           artifact's own screen: the white card is for "tonight's
           record," not the whole working surface. -->
      <div class="screen-frame">
        <div class="stats-row">
          <div class="stat">
            <div class="stat-label">Active players</div>
            <div class="stat-value">{{ activeCount }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">Chips out</div>
            <div class="stat-value">{{ N(chipsOutTonight) }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">Payments</div>
            <div class="stat-value">{{ N(paymentsTonight) }}</div>
          </div>
          <div class="stat stat--accent">
            <div class="stat-label">Table balance</div>
            <div class="stat-value">{{ N(tableBalanceTonight) }}</div>
          </div>
        </div>

        <div class="ledger-feed">
          <p v-if="ledgerLoading" class="muted">Loading…</p>
          <p v-else-if="!ledger.length" class="muted">No activity yet tonight.</p>
          <LedgerTable v-else :rows="ledgerRows" show-player voidable :can-void-fn="canVoid" @void="voidTarget = $event" />
        </div>
      </div>
    </template>

    <TransactionEntryModal
      v-if="entryModal" :type="entryModal.type" :player="entryModal.player" :game-day-id="gameDay.current.id"
      @close="onEntryClosed" @saved="onEntrySaved"
    />

    <!-- Payment type picker — see pickPaymentType's comment above. -->
    <div v-if="paymentPickerOpen" class="overlay">
      <div class="dialog card leave-dialog">
        <div class="eyebrow">{{ selectedPlayer?.display_name }} &mdash; Payment</div>
        <p class="muted">How is this payment coming in?</p>
        <div class="leave-actions">
          <button class="btn btn--secondary" type="button" @click="pickPaymentType('PAYMENT_CASH')">Cash</button>
          <button class="btn btn--secondary" type="button" @click="pickPaymentType('PAYMENT_POS')">POS</button>
          <button class="btn btn--secondary" type="button" @click="pickPaymentType('PAYMENT_TRANSFER')">Transfer (manual)</button>
        </div>
        <button class="link-btn leave-cancel" type="button" @click="paymentPickerOpen = false">Cancel</button>
      </div>
    </div>

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

    <!-- Move/swap seat -->
    <div v-if="moveSeatTarget" class="overlay">
      <div class="dialog card">
        <div class="eyebrow">Move {{ moveSeatTarget.display_name }}</div>
        <p class="muted">Pick a seat — an occupied one swaps places, an empty one just moves them.</p>
        <div class="seat-options">
          <button
            v-for="opt in moveSeatOptions" :key="opt.seatNumber" type="button" class="seat-option"
            :disabled="opt.isCurrent"
            @click="onPickMoveSeat(opt.seatNumber)"
          >
            <span class="pill-seat">{{ opt.seatNumber }}</span> {{ opt.label }}
          </button>
        </div>
        <button class="link-btn leave-cancel" type="button" @click="moveSeatTarget = null">Cancel</button>
      </div>
    </div>

    <AddPlayerModal v-if="addPlayerOpen" :seat-number="seatTarget" @close="onAddPlayerClosed" @added="onPlayerAdded" />

    <StartGameDayModal
      v-if="startFlowOpen" :number="startFlowNumber"
      @close="onStartFlowClosed" @started="onGameDayStarted"
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

/* Was styled with the WARNING color (saturated amber card) — Rake/Tip
   entry isn't a caution state, so that borrowed a semantic color for
   decoration rather than meaning. A plain, quieter treatment reads as
   "its own section," not "pay attention" — restyled 2026-09-21. */
/* One slim row (label left, compact buttons right) — was a tall stacked
   card, out of proportion for a low-frequency, not-player-specific action.
   Restyled 2026-09-21, see the Cashier layout wireframe review. */
.general-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 16px;
  background: var(--bg);
}
/* This .lbl now carries the seat-count summary, not a section eyebrow —
   the shared .lbl class below is uppercase/bold/letter-spaced (right for
   "GENERAL — NOT TIED TO A PLAYER", wrong for a plain sentence like
   "7 active · 2 seats free"). Overridden back to the plain style the old
   standalone .picker-row used. */
.general-section .lbl {
  font-size: 11px;
  font-weight: 400;
  letter-spacing: normal;
  text-transform: none;
  color: var(--text-tertiary);
}
.general-actions { display: flex; gap: 8px; }
.general-btn {
  display: flex;
  flex-direction: column;
  gap: 1px;
  border: 1px solid var(--border-strong);
  background: var(--surface);
  border-radius: var(--radius-sm);
  padding: 6px 14px;
  cursor: pointer;
  text-align: left;
  min-width: 88px;
}
.general-btn-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.general-btn-sub { font-size: 10px; color: var(--text-tertiary); }

/* Seat grid (left) + selected player (right) side by side — was both
   full-width, stacked, so a busy table pushed the action panel below the
   fold. Fixed-width left column keeps every seat visible alongside it.
   Added 2026-09-21, see the Cashier layout wireframe review. Stacks back
   to one column below --control-row breakpoint (narrow/portrait tablet). */
.working-area { display: grid; grid-template-columns: minmax(240px, 360px) 1fr; gap: 16px; align-items: start; margin-bottom: 14px; }
@media (max-width: 720px) {
  .working-area { grid-template-columns: 1fr; }
}

.empty-players {
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 16px;
  text-align: center;
  margin-bottom: 14px;
}

/* A real 2-column grid (not flex-wrap) now that the seat list lives in its
   own fixed-width column — keeps every seat aligned into a clean block
   instead of ragged rows of variable-width pills. */
.pills { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 14px; }
/* Fixed height + a truncating label (not free-flowing text) — a long
   player name used to wrap the pill onto 2 lines, making that seat (and
   every other pill sharing its grid row) taller than the rest of the
   grid. One uniform row height regardless of name length now. Fixed
   2026-09-21. */
.pill {
  display: flex;
  align-items: center;
  height: var(--control-row-min);
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 18px;
  padding: 0 14px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
}
.pill--active { border-color: var(--accent); background: var(--accent); color: #fff; }
.pill--departed { background: var(--status-voided-bg); color: var(--status-voided-text); border-color: transparent; }
.pill--empty { border-style: dashed; color: var(--text-tertiary); background: var(--bg); }
.pill-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; flex: 1; text-align: left; }
.pill-tag { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; margin-left: 4px; opacity: 0.8; flex-shrink: 0; }
.pill-seat {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.08);
  font-size: 10.5px;
  font-weight: 700;
  margin-right: 6px;
  flex-shrink: 0;
}
.pill--active .pill-seat { background: rgba(255, 255, 255, 0.25); }
.pills--secondary { margin-top: -4px; }
.pills-label { grid-column: 1 / -1; font-size: 10.5px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: -2px; }

.seat-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 14px 0 4px; }
.seat-option {
  border: 1px solid var(--border-strong);
  background: var(--surface);
  border-radius: var(--radius-sm);
  padding: 10px 8px;
  font-family: var(--font-sans);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
  text-align: center;
}
.seat-option:disabled { opacity: 0.4; cursor: not-allowed; }

.player-panel--empty { text-align: center; }
.player-panel--empty .muted { margin: 4px 0; }
/* nowrap + truncating name (not flex-wrap) — the chips-limit badge only
   shows for some players, and letting the row wrap onto a second line
   when it's present made the whole panel visibly taller for those
   players than for one without a badge. One fixed-height row always,
   regardless of which badge (if any) is showing. Fixed 2026-09-21. */
.panel-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 4px; flex-wrap: nowrap; }
.panel-head .lbl {
  text-transform: none;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: normal;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

/* The one hero-number moment on this panel — was a small inline figure
   buried in a "Record for..." sentence. Added 2026-09-21, see the Cashier
   layout wireframe review. Money stays --font-mono per the design system
   (Fraunces is for headings, not figures) at real hero size instead. */
.hero-balance { text-align: center; margin: 10px 0 18px; }
.hero-value { font-size: 36px; font-weight: 700; line-height: 1; color: var(--text-primary); }
.hero-value.money--positive { color: var(--success); }
.hero-caption { font-size: 11.5px; color: var(--text-tertiary); margin-top: 6px; }

.chips-limit-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--warning-text);
  border: 1px solid var(--warning);
  background: var(--warning-bg);
  border-radius: 12px;
  padding: 3px 10px;
  white-space: nowrap;
  flex-shrink: 0;
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
  flex-shrink: 0;
}

.action-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.left-hint { font-size: 11.5px; color: var(--text-tertiary); text-align: center; margin-top: 8px; }
.action-btn {
  border: 1px solid var(--border-strong);
  background: var(--surface);
  border-radius: var(--radius-sm);
  padding: 14px 6px;
  /* Was a bare "64px" magic number, disconnected from the touch-target
     system entirely — now tracks the same control-height-primary
     every other primary control on this touch-first screen uses (and
     will move correctly if that ever changes). */
  min-height: var(--control-height-primary);
  font-family: var(--font-sans);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
  text-align: center;
  line-height: 1.3;
}
/* "Issue Chips" is the single most frequent action on this screen —
   was only a slightly-thicker colored border among eight otherwise
   identical buttons, not enough hierarchy for the most-used one. A
   filled accent-tint background now sets it apart at a glance without
   competing with the actual primary buttons (.btn--primary) elsewhere
   in the app. */
.action-btn--accent { border-color: var(--accent); background: var(--accent-bg); color: var(--accent-text); font-weight: 700; }
.action-btn--warn { border-color: var(--warning); color: var(--warning-text); }

/* The one "hero number" moment on this screen — added 2026-09-21, see
   the Ledger Directions review artifact this was compared against.
   Money stays in --font-mono (correct, per the design system — Fraunces
   is for headings, not figures) but at real size/weight instead of the
   13px convention used in the back-office ledger views. */
.stats-row { display: flex; gap: 10px; margin-bottom: 18px; flex-wrap: wrap; }
.stat { flex: 1 1 140px; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 14px 16px; }
.stat--accent { background: var(--accent-bg); border-color: transparent; }
.stat-label { font-size: 10.5px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 6px; }
.stat--accent .stat-label { color: var(--accent-text); opacity: 0.85; }
.stat-value { font-family: var(--font-mono); font-size: 22px; font-weight: 600; color: var(--text-primary); font-variant-numeric: tabular-nums; }
.stat--accent .stat-value { color: var(--accent-text); }

.link-btn { border: none; background: none; font-size: 11.5px; font-weight: 700; color: var(--accent); cursor: pointer; }
.ledger-feed { border-top: 1px solid var(--border); }

/* The one boxed-white moment on this screen — "tonight's record"
   (stats + activity feed), matching the review artifact's own
   .screen-frame treatment exactly: white card, thin border, generous
   padding, a soft lifted shadow. Everything above it (seating, the
   player panel) stays unboxed on the page's own background. */
.screen-frame {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 26px;
  box-shadow: var(--shadow-md);
}
.screen-frame .stats-row:last-child,
.screen-frame .ledger-feed:last-child { margin-bottom: 0; }

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

.leave-dialog .muted { margin: 6px 0 20px; }
.leave-actions { display: flex; flex-direction: column; gap: 10px; }
.leave-cancel { display: block; margin: 16px auto 0; }
</style>
