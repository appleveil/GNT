<script setup>
import { ref, computed, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useGameDayStore } from '@/stores/gameDay'
import { useClubSettingsStore } from '@/stores/clubSettings'
import TransactionEntryModal from '@/components/shared/TransactionEntryModal.vue'
import VoidEntryModal from '@/components/shared/VoidEntryModal.vue'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import AddPlayerModal from '@/components/shared/AddPlayerModal.vue'
import StartGameDayModal from '@/components/shared/StartGameDayModal.vue'
import PlayerBankAccountModal from '@/components/shared/PlayerBankAccountModal.vue'
import { canVoidTransaction } from '@/utils/canVoid'
import { currentPlayerBalance } from '@/utils/nettedPayout'
import { useToast } from '@/composables/useToast'
import api from '@/api/axios'

const auth = useAuthStore()
const gameDay = useGameDayStore()
const clubSettings = useClubSettingsStore()
const toast = useToast()

const opening = ref(false)
const openError = ref('')

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

const players = ref([])
const playersLoading = ref(false)
const ledger = ref([])
const ledgerLoading = ref(false)
// rake/tips are excluded from `ledger`/`activity`, so they need their own fetch.
const chipsTotals = ref(null)

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
    // running_balance here is per-player, unlike `ledger`'s club-wide cumulative total
    const { data } = await api.get(`/game-days/${gameDay.current.id}/activity/`)
    ledger.value = data.slice().reverse() // most recent first
  } finally {
    ledgerLoading.value = false
  }
}

async function loadChipsTotals() {
  if (!gameDay.current) {
    chipsTotals.value = null
    return
  }
  try {
    const { data } = await api.get(`/game-days/${gameDay.current.id}/chips-totals/`)
    chipsTotals.value = data
  } catch {
    // silent — caption just shows '--'
  }
}

function refreshAll() {
  return Promise.all([loadPlayers(), loadLedger(), loadChipsTotals()])
}

const selectedPlayerId = ref(null)
const seatColumnTab = ref('seats')

watch(() => gameDay.current?.id, id => {
  selectedPlayerId.value = null
  seatColumnTab.value = 'seats'
  if (id) refreshAll()
  else {
    players.value = []
    ledger.value = []
    chipsTotals.value = null
  }
}, { immediate: true })

const selectedPlayer = computed(() => players.value.find(p => p.id === selectedPlayerId.value) || null)

const activeCount = computed(() => players.value.filter(p => !p.left_at).length)
const departedCount = computed(() => players.value.length - activeCount.value)

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

// Tapping an empty seat offers New/Existing; "+ New Player" forces
// New-player-only — there's no "seat an existing player" path outside a seat tap.
const addPlayerOpen = ref(false)
const seatTarget = ref(null)
const newPlayerFlow = ref(false)
function onEmptySeatClick(seatNumber) {
  seatTarget.value = seatNumber
  newPlayerFlow.value = false
  addPlayerOpen.value = true
}
function onAddPlayerButtonClick() {
  seatTarget.value = null
  newPlayerFlow.value = true
  addPlayerOpen.value = true
}
function onAddPlayerClosed() {
  addPlayerOpen.value = false
  seatTarget.value = null
  newPlayerFlow.value = false
}
// Auto-focus a newly seated player (2026-09-27, explicit follow-up) —
// AddPlayerModal now emits the seated player's own id (both the existing-
// player and new-player submit paths). refreshAll() first so `players`
// actually contains them before selectedPlayer's own computed looks them
// up; setting selectedPlayerId before that resolves would just render
// blank for one tick, not break anything, but this reads cleaner.
async function onPlayerAdded(playerId) {
  await refreshAll()
  if (playerId) selectedPlayerId.value = playerId
}

const moveSeatTarget = ref(null) // player being moved, or null
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

// A departed player is re-seated explicitly, into an empty seat only —
// their old seat_number may since have been taken by someone else.
const rejoinTarget = ref(null) // departed player being rejoined, or null
function onRejoinClick() {
  rejoinTarget.value = selectedPlayer.value
}
const rejoinSeatOptions = computed(() => {
  if (!rejoinTarget.value) return []
  return seatSlots.value.filter(s => !s.player).map(s => ({ seatNumber: s.seatNumber }))
})
async function onPickRejoinSeat(seatNumber) {
  const player = rejoinTarget.value
  rejoinTarget.value = null
  try {
    await api.post(`/game-days/${gameDay.current.id}/players/${player.id}/rejoin/`, { seat_number: seatNumber })
    toast.success(`${player.display_name} rejoined at Seat ${seatNumber}.`)
    refreshAll()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Could not rejoin this player.')
  }
}

const payoutSubmitting = ref(false)

// ClubSettings.cashier_can_initiate_payout (Owner-only, default True, added
// 2026-09-27) — off disables this for a Cashier specifically (an Owner
// using this same screen is unaffected, matching how the setting is
// enforced server-side too — see gaming.services.initiate_payout). `===
// false` (not just falsy), same convention as every other clubSettings
// check in this app — only an explicit false short-circuits; a still-
// loading/failed fetch defaults to allowed, not blocked.
const cashierPayoutBlocked = computed(
  () => auth.user?.role === 'CASHIER' && clubSettings.current?.cashier_can_initiate_payout === false,
)

// A payout only makes sense once the club owes the player (balance > 0) and
// they've left the table — left_at doubles as "has returned/never held chips."
const payoutDisabled = computed(() => {
  const p = selectedPlayer.value
  return !p || !(p.balance > 0) || !p.left_at || payoutSubmitting.value || cashierPayoutBlocked.value
})

const bankModalOpen = ref(false)

async function onPayoutClick() {
  const p = selectedPlayer.value
  if (!p) return
  if (!(p.bank_accounts || []).some(b => b.is_default)) {
    bankModalOpen.value = true
    return
  }
  payoutSubmitting.value = true
  try {
    const { data } = await api.post('/transactions/payout/', { player: p.id, amount: p.balance })
    // data.amount is what actually resulted — may be less than p.balance if
    // it got netted against an older, prior-game-day balance (2026-09-27:
    // now shown to the Cashier too — see displayedBalance below and
    // LedgerTable's "Payout BBF" row). data.status already reflects
    // auto-approval (2026-09-23) too, not just netting — this replaces a
    // message that was always unconditionally "pending Owner approval"
    // regardless of what actually happened.
    const verb = data.status === 'APPROVED' ? 'sent — no approval needed' : 'initiated — pending Owner approval'
    toast.success(`Payout of ${N(data.amount)} ${verb} for ${p.display_name}.`)
    refreshAll()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Could not initiate the payout.')
  } finally {
    payoutSubmitting.value = false
  }
}
function onBankModalClosed() {
  bankModalOpen.value = false
}
function onBankAccountAdded() {
  bankModalOpen.value = false
  refreshAll().then(onPayoutClick)
}

const entryModal = ref(null) // { type, player } | null
// Set when Leave Table's "return chips" choice opens the CHIPS_IN entry —
// onEntrySaved uses this to also mark the player left afterward.
const pendingLeave = ref(null)

function openEntry(type, player = selectedPlayer.value) {
  entryModal.value = { type, player }
}

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

const leaveTarget = ref(null) // player being asked "returning chips first?", or null

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

// activity's running_balance is already partitioned per-player, so filtering
// client-side gives each row the correct balance for its own player.
const playerLedgerRows = computed(() => {
  if (!selectedPlayerId.value) return []
  return ledgerRows.value.filter(row => row.player === selectedPlayerId.value)
})

// The hero balance figure — today's own game-day balance
// (selectedPlayer.balance), unless a netted payout overrides it. See
// utils/nettedPayout.js for why — that's the single shared source for
// this fact, also used by LedgerTable's balance column and
// GameDaysListView's per-player stats after all three drifted out of
// sync on 2026-09-27.
const displayedBalance = computed(() =>
  currentPlayerBalance(playerLedgerRows.value, selectedPlayer.value?.balance ?? 0),
)

// Same game-day-wide scope record_transaction's CHIPS_IN ceiling checks —
// from the dedicated chipsTotals fetch, not `ledger` (which excludes RAKE/TIP).
const gameDayChipsOutTotal = computed(() => Number(chipsTotals.value?.chips_out_total || 0))
const gameDayChipsInTotal = computed(() => Number(chipsTotals.value?.chips_in_total || 0))
// Rake/tips never come back as a CHIPS_IN — shown only once nonzero.
const gameDayRakeTipsTotal = computed(
  () => Number(chipsTotals.value?.rake_total || 0) + Number(chipsTotals.value?.tips_total || 0),
)
const gameDayReturnableCeiling = computed(() => gameDayChipsOutTotal.value - gameDayRakeTipsTotal.value)

const PAYMENT_TYPES = new Set(['PAYMENT_CASH', 'PAYMENT_TRANSFER', 'PAYMENT_POS', 'PAYMENT_DEAL'])
const chipsOutTonight = computed(() =>
  playerLedgerRows.value.filter(r => r.type === 'CHIPS_OUT' && !r.is_voided).reduce((sum, r) => sum + Number(r.amount), 0)
)
const paymentsTonight = computed(() =>
  playerLedgerRows.value.filter(r => PAYMENT_TYPES.has(r.type) && !r.is_voided).reduce((sum, r) => sum + Number(r.amount), 0)
)
const chipsInTonight = computed(() =>
  playerLedgerRows.value.filter(r => r.type === 'CHIPS_IN' && !r.is_voided).reduce((sum, r) => sum + Number(r.amount), 0)
)

const voidTarget = ref(null) // ledger row being voided, or null

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
    <div v-if="!gameDay.isOpen" class="card empty-state">
      <div class="eyebrow">No Game-Day Open</div>
      <p class="muted">Open a game-day to start seating players and recording activity.</p>
      <p v-if="openError" class="form-error">{{ openError }}</p>
      <button class="btn btn--primary" type="button" :disabled="opening" @click="onOpenGameDay">
        {{ opening ? 'Loading…' : 'Open Game-Day' }}
      </button>
    </div>

    <template v-else>
      <div class="section general-section">
        <div class="lbl">
          {{ activeCount }} active &middot; {{ maxSeats - activeCount }} seats free
          <template v-if="departedCount">&middot; ({{ departedCount }} players have left)</template>
        </div>

        <div class="general-actions">
          <button class="add-player-btn" type="button" @click="onAddPlayerButtonClick">
            <span class="add-player-icon">+</span> New Player
          </button>
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

      <div class="working-area">
        <div class="seat-column">
          <p v-if="playersLoading && !players.length" class="muted">Loading…</p>
          <template v-else>
            <div v-if="departedPlayers.length" class="seat-tabs">
              <button
                type="button" class="seat-tab" :class="{ 'seat-tab--active': seatColumnTab === 'seats' }"
                @click="seatColumnTab = 'seats'"
              >Seats</button>
              <button
                type="button" class="seat-tab" :class="{ 'seat-tab--active': seatColumnTab === 'left' }"
                @click="seatColumnTab = 'left'"
              >Left ({{ departedCount }})</button>
            </div>

            <template v-if="seatColumnTab === 'seats' || !departedPlayers.length">
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
            </template>

            <div v-else class="pills pills--secondary">
              <button
                v-for="p in departedPlayers" :key="p.id" type="button" class="pill pill--departed"
                :class="{ 'pill--active': p.id === selectedPlayerId }"
                @click="selectPlayer(p)"
              >
                <span class="pill-label">{{ p.display_name }} &middot; {{ p.account_code }}</span>
              </button>
            </div>
          </template>
        </div>

        <div class="card section player-panel">
          <div class="panel-head">
            <div class="panel-name">
              {{ selectedPlayer?.display_name || '--' }}
              <span v-if="selectedPlayer" class="panel-name-code">&middot; {{ selectedPlayer.account_code }}</span>
            </div>
            <!-- Not exclusive with the two below — a departed player can also have a stuck payout. -->
            <div class="panel-badges">
              <div v-if="selectedPlayer?.payout_failed" class="payout-failed-badge">Payout failed — ask the Owner</div>
              <div v-if="selectedPlayer?.left_at" class="left-badge">Left the table</div>
              <div v-else-if="selectedPlayer?.chips_limit != null" class="chips-limit-badge">
                Credit limit: {{ N(selectedPlayer.chips_used_today) }} of {{ N(selectedPlayer.chips_limit) }} used
              </div>
            </div>
          </div>

          <div class="hero-balance">
            <div class="hero-value money" :class="{ 'money--positive': displayedBalance > 0 }">
              {{ selectedPlayer ? N(displayedBalance) : '--' }}
            </div>
          </div>

          <div class="action-grid">
            <!-- Disabled, not hidden, once departed — Rejoin at Seat is the only way back in. -->
            <button
              class="action-btn action-btn--accent" type="button" :disabled="!selectedPlayer || !!selectedPlayer.left_at"
              @click="openEntry('CHIPS_OUT')"
            >Issue Chips</button>
            <button
              v-if="selectedPlayer?.left_at" class="action-btn action-btn--accent" type="button"
              @click="onRejoinClick"
            >Rejoin at Seat</button>
            <!-- Departed players only — a correction path for a cashier mistake made while they left. -->
            <button
              v-if="selectedPlayer?.left_at" class="action-btn" type="button"
              @click="openEntry('CHIPS_IN')"
            >Return Chips</button>
            <button class="action-btn" type="button" :disabled="!selectedPlayer" @click="paymentPickerOpen = true">Payment &#9662;</button>
            <button
              class="action-btn" type="button" :disabled="payoutDisabled"
              :title="cashierPayoutBlocked ? 'The Owner has turned off Cashier-initiated payouts' : null"
              @click="onPayoutClick"
            >{{ payoutSubmitting ? 'Paying out…' : 'Payout' }}</button>
            <button
              v-if="!selectedPlayer?.left_at" class="action-btn" type="button" :disabled="!selectedPlayer"
              @click="onMoveSeatClick"
            >Move Seat</button>
            <button
              v-if="!selectedPlayer?.left_at" class="action-btn action-btn--warn" type="button"
              :disabled="!selectedPlayer" @click="onLeaveClick"
            >Leave Table</button>
          </div>
          <p v-if="selectedPlayer?.left_at" class="left-hint">
            {{ selectedPlayer.display_name }} left the table — Issue Chips to bring them back.
          </p>
        </div>
      </div>

      <div class="screen-frame">
        <div class="chips-caption">
          Tonight: <span class="money">{{ N(gameDayChipsOutTotal) }}</span> chips out
          <template v-if="gameDayRakeTipsTotal > 0">
            (<span class="money">{{ N(gameDayReturnableCeiling) }}</span> returnable after rake/tips)
          </template>
          &middot; <span class="money">{{ N(gameDayChipsInTotal) }}</span> returned
        </div>

        <div class="stats-row">
          <div class="stat">
            <div class="stat-label">Chips out</div>
            <div class="stat-value">{{ selectedPlayer ? N(chipsOutTonight) : '--' }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">Payments</div>
            <div class="stat-value">{{ selectedPlayer ? N(paymentsTonight) : '--' }}</div>
          </div>
          <div class="stat">
            <div class="stat-label">Chips returned</div>
            <div class="stat-value">{{ selectedPlayer ? N(chipsInTonight) : '--' }}</div>
          </div>
          <div class="stat stat--accent">
            <div class="stat-label">Balance</div>
            <div class="stat-value">{{ selectedPlayer ? N(displayedBalance) : '--' }}</div>
          </div>
        </div>

        <div class="ledger-feed">
          <p v-if="!selectedPlayer" class="muted">Select a player above to see their ledger.</p>
          <p v-else-if="ledgerLoading" class="muted">Loading…</p>
          <p v-else-if="!playerLedgerRows.length" class="muted">No activity yet tonight for {{ selectedPlayer.display_name }}.</p>
          <LedgerTable
            v-else :rows="playerLedgerRows" type-label="Action" voidable :can-void-fn="canVoid"
            @void="voidTarget = $event"
          />
        </div>
      </div>
    </template>

    <TransactionEntryModal
      v-if="entryModal" :type="entryModal.type" :player="entryModal.player" :game-day-id="gameDay.current.id"
      @close="onEntryClosed" @saved="onEntrySaved"
    />

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
         non-Owner rule guarantees this) — needs a real lookup once an Owner-role
         frontend can void someone else's entry. -->
    <VoidEntryModal
      v-if="voidTarget" :transaction="voidTarget" :player-name="playerName(voidTarget.player)"
      :recorded-by-name="auth.user?.fullName" @close="voidTarget = null" @voided="onVoided"
    />

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

    <div v-if="rejoinTarget" class="overlay">
      <div class="dialog card">
        <div class="eyebrow">Rejoin {{ rejoinTarget.display_name }}</div>
        <p class="muted">Pick an empty seat to bring them back to the table.</p>
        <div class="seat-options">
          <button
            v-for="opt in rejoinSeatOptions" :key="opt.seatNumber" type="button" class="seat-option"
            @click="onPickRejoinSeat(opt.seatNumber)"
          >
            <span class="pill-seat">{{ opt.seatNumber }}</span> Empty
          </button>
        </div>
        <p v-if="!rejoinSeatOptions.length" class="muted">No empty seats right now.</p>
        <button class="link-btn leave-cancel" type="button" @click="rejoinTarget = null">Cancel</button>
      </div>
    </div>

    <AddPlayerModal
      v-if="addPlayerOpen" :seat-number="seatTarget" :new-only="newPlayerFlow"
      @close="onAddPlayerClosed" @added="onPlayerAdded"
    />

    <StartGameDayModal
      v-if="startFlowOpen" :number="startFlowNumber"
      @close="onStartFlowClosed" @started="onGameDayStarted"
    />

    <PlayerBankAccountModal
      v-if="bankModalOpen && selectedPlayer" :player="selectedPlayer"
      @close="onBankModalClosed" @added="onBankAccountAdded"
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
  font-size: 1400px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.general-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 16px;
  background: var(--bg);
}
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

.add-player-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--accent);
  background: var(--accent-bg);
  color: var(--accent-text);
  border-radius: var(--radius-sm);
  padding: 6px 16px;
  font-family: var(--font-sans);
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
}
.add-player-btn:hover { background: var(--accent); color: #fff; }
.add-player-icon { font-size: 15px; font-weight: 700; line-height: 1; }

.working-area { display: grid; grid-template-columns: minmax(240px, 360px) 1fr; gap: 16px; align-items: start; margin-bottom: 14px; }
@media (max-width: 720px) {
  .working-area { grid-template-columns: 1fr; }
}

.seat-tabs { display: flex; gap: 6px; margin-bottom: 10px; }
.seat-tab {
  flex: 1;
  height: 32px;
  border: 1px solid var(--border-strong);
  background: var(--surface);
  border-radius: var(--radius-sm);
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 700;
  color: var(--text-secondary);
  cursor: pointer;
}
.seat-tab--active { background: var(--accent-bg); color: var(--accent-text); border-color: var(--accent); }

.pills { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 14px; }
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
/* .pill--departed comes AFTER .pill--active below it in source order, so at
   equal specificity it was winning outright on a selected departed pill —
   selecting someone in "Left" looked identical to not selecting them, with
   several departed players easy to mix up. Found 2026-09-26. This
   two-class selector outranks the single-class rule above regardless of
   source order, so the accent highlight actually shows. */
.pill--departed.pill--active { background: var(--accent); color: #fff; border-color: var(--accent); }
.pill--empty { border-style: dashed; color: var(--text-tertiary); background: var(--bg); }
.pill-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; flex: 1; text-align: left; }
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

.panel-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 4px; flex-wrap: nowrap; }
.panel-name {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.panel-name-code { font-family: var(--font-sans); font-size: 13px; font-weight: 500; color: var(--text-tertiary); }

.hero-balance { text-align: center; margin: 10px 0 18px; }
.hero-value { font-size: 36px; font-weight: 700; line-height: 1; color: var(--text-primary); }
.hero-value.money--positive { color: var(--success); }

.panel-badges { display: flex; align-items: center; gap: 6px; flex-shrink: 0; flex-wrap: wrap; justify-content: flex-end; }
.payout-failed-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--danger-text);
  border: 1px solid var(--danger);
  background: var(--danger-bg);
  border-radius: 12px;
  padding: 3px 10px;
  white-space: nowrap;
  flex-shrink: 0;
}
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

.action-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; }
.left-hint { font-size: 11.5px; color: var(--text-tertiary); text-align: center; margin-top: 8px; }
.action-btn {
  border: 1px solid var(--border-strong);
  background: var(--surface);
  border-radius: var(--radius-sm);
  padding: 14px 6px;
  min-height: var(--control-height-primary);
  font-family: var(--font-sans);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
  text-align: center;
  line-height: 1.3;
}
.action-btn--accent { border-color: var(--accent); background: var(--accent-bg); color: var(--accent-text); font-weight: 700; }
.action-btn--warn { border-color: var(--warning); color: var(--warning-text); }
.action-btn:disabled {
  cursor: not-allowed;
  background: var(--disabled-surface);
  border-color: var(--disabled-border);
  color: var(--text-tertiary);
}

.chips-caption { font-size: 12px; color: var(--text-tertiary); margin-bottom: 14px; }
.chips-caption .money { color: var(--text-secondary); }

.stats-row { display: flex; gap: 10px; margin-bottom: 18px; flex-wrap: wrap; }
.stat { flex: 1 1 140px; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 14px 16px; }
.stat--accent { background: var(--accent-bg); border-color: transparent; }
.stat-label { font-size: 10.5px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 6px; }
.stat--accent .stat-label { color: var(--accent-text); opacity: 0.85; }
.stat-value { font-family: var(--font-mono); font-size: 22px; font-weight: 600; color: var(--text-primary); font-variant-numeric: tabular-nums; }
.stat--accent .stat-value { color: var(--accent-text); }

.link-btn { border: none; background: none; font-size: 11.5px; font-weight: 700; color: var(--accent); cursor: pointer; }

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
