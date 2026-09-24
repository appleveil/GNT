<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/api/axios'
import { useAuthStore } from '@/stores/auth'
import VoidEntryModal from '@/components/shared/VoidEntryModal.vue'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import { canVoidTransaction } from '@/utils/canVoid'
import { describeChipsVariance } from '@/utils/chipsVariance'
import { currentPlayerBalance } from '@/utils/nettedPayout'
import { useToast } from '@/composables/useToast'

// Game-day history (Phase B, 2026-09-14) — GET /api/game-days/ is
// IsAuthenticated-only (gaming/views.py's GameDayViewSet), newest first per
// its own queryset ordering. Closed rows show their frozen GameDaySummary
// inline (now right on the list row — see the table below); OPEN rows have
// no summary yet, cells fall back to '—'.
//
// Lives at /ledgers/game-days as of 2026-09-26 (was the flat /game-days) —
// LedgersLayout.vue is its parent route now and owns the page-level header
// + sub-nav (Game Days / Off-table), so this component's own former
// page-header/<h1> was removed as duplicate chrome.
//
// Hi-fi pass, 2026-09-14 -> 2026-09-23: GameDayDetailView.vue (formerly its
// own /game-days/:id route) is folded in here wholesale — clicking a row
// opens that game-day's detail INLINE, below the (paginated) list on this
// same page, per the lo-fi nav review sketch. No other screen linked to the
// old route (confirmed by search before removing it), so nothing else
// needed to change. A seated player's pill narrows the detail to just that
// player's own activity for the night (GET
// /game-days/{id}/players/{player_id}/ledger/, which already existed for
// RosterDetailView's own per-game-day section — the mini stat totals below
// are computed client-side from those rows, no new backend endpoint).
//
// Per-user edit, 2026-09-23: the club-wide "Full ledger" panel (shown when
// no player was selected) is gone — this page only ever shows a per-player
// ledger now, never the everyone-at-once one. The Owner still has the
// club-wide feed elsewhere (the Cashier's own ledger, and Main Account for
// money movements) — it just isn't duplicated here anymore. The topmost
// (most recent) game-day's detail now opens automatically on page load,
// instead of requiring a first click.
const route = useRoute()
const auth = useAuthStore()
const toast = useToast()

const gameDays = ref([])
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/game-days/')
    gameDays.value = data
    // ?gameDay=<id> (added 2026-09-26, from the Dashboard's live-tables
    // summary "View →" link) opens THAT game-day instead of the topmost
    // one, and flips to whichever page it falls on — same PAGE_SIZE below.
    const targetId = route.query.gameDay ? Number(route.query.gameDay) : null
    const targetIndex = targetId != null ? data.findIndex(gd => gd.id === targetId) : -1
    if (targetIndex >= 0) {
      page.value = Math.floor(targetIndex / PAGE_SIZE) + 1
      await openGameDay(data[targetIndex])
    } else if (data.length) {
      await openGameDay(data[0])
    }
  } catch {
    toast.error('Could not load game-day history.')
  } finally {
    loading.value = false
  }
}

onMounted(load)

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
function formatFullDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
}
function formatTime(iso) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

// A compact per-row read of a closed game-day's own chips_variance — lets
// an Accountant/Owner spot a problem night while just scanning the list.
function chipsBadge(gd) {
  if (!gd.summary) return null
  const v = Number(gd.summary.chips_variance)
  const { amount, className } = describeChipsVariance(v)
  const label = v > 0 ? 'Deficit' : v < 0 ? 'Excess' : 'Balanced'
  return { label, amount, className }
}

const N = n => `₦${Number(n).toLocaleString()}`

// ── Pagination ─────────────────────────────────────────────────────────
const PAGE_SIZE = 5
const page = ref(1)
const totalPages = computed(() => Math.max(1, Math.ceil(gameDays.value.length / PAGE_SIZE)))
const pagedGameDays = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE
  return gameDays.value.slice(start, start + PAGE_SIZE)
})
const rangeLabel = computed(() => {
  if (!gameDays.value.length) return ''
  const start = (page.value - 1) * PAGE_SIZE + 1
  const end = Math.min(page.value * PAGE_SIZE, gameDays.value.length)
  return `Showing ${start}–${end} of ${gameDays.value.length} game-days`
})
function goToPage(n) {
  page.value = Math.min(Math.max(1, n), totalPages.value)
}

// ── Detail (opens inline below the list) ──────────────────────────────────
const detailId = ref(null)
const detailLoading = ref(false)
const gameDay = ref(null)
const players = ref([])
const voidTarget = ref(null)

async function loadDetail(id) {
  detailLoading.value = true
  try {
    const [gdRes, playersRes] = await Promise.all([
      api.get(`/game-days/${id}/`),
      api.get(`/game-days/${id}/players/`),
    ])
    gameDay.value = gdRes.data
    players.value = playersRes.data
  } catch {
    toast.error('Could not load this game-day.')
  } finally {
    detailLoading.value = false
  }
}

// Shared by the initial auto-open (load, below) and a row click — only the
// click scrolls (a freshly loaded page has nothing to scroll away from).
async function openGameDay(gd) {
  detailId.value = gd.id
  selectedPlayerId.value = null
  playerLedger.value = []
  await loadDetail(gd.id)
}

async function onViewGameDay(gd) {
  if (detailId.value === gd.id) return // already open — nothing to do
  await openGameDay(gd)
  await nextTick()
  document.getElementById('game-day-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function playerName(playerId) {
  if (!playerId) return ''
  return players.value.find(p => p.id === playerId)?.display_name || ''
}

function canVoid(row) {
  return canVoidTransaction(row, auth.user, gameDay.value?.status)
}
async function onVoided() {
  voidTarget.value = null
  toast.success('Entry voided.')
  if (!detailId.value) return
  await loadDetail(detailId.value)
  if (selectedPlayerId.value) await loadPlayerLedger(selectedPlayerId.value)
}

// ── Per-player pill selection ─────────────────────────────────────────────
// Matches gaming/selectors.py's PAYMENT_TYPES (game_day_summary_data) — the
// same 4 types the list's own "Payments" column already sums club-wide,
// scoped down here to just this one player's own rows.
const PAYMENT_TYPES = new Set(['PAYMENT_CASH', 'PAYMENT_TRANSFER', 'PAYMENT_POS', 'PAYMENT_DEAL'])

const selectedPlayerId = ref(null)
const playerLedger = ref([])
const playerLedgerLoading = ref(false)

const selectedPlayer = computed(() => players.value.find(p => p.id === selectedPlayerId.value) || null)
const selectedPlayerLedgerRows = computed(() => playerLedger.value.slice().reverse())
const selectedPlayerStats = computed(() => {
  let chipsOut = 0
  let payments = 0
  let chipsReturned = 0
  for (const r of playerLedger.value) {
    if (r.is_voided) continue
    const amt = Number(r.amount)
    if (r.type === 'CHIPS_OUT') chipsOut += amt
    else if (r.type === 'CHIPS_IN') chipsReturned += amt
    else if (PAYMENT_TYPES.has(r.type)) payments += amt
  }
  const last = playerLedger.value[playerLedger.value.length - 1]
  const rawBalance = last ? Number(last.running_balance) : 0
  // See utils/nettedPayout.js — a netted payout's game-day-scoped
  // running_balance understates what's actually still owed once cleared;
  // this was the third of three independently-drifting copies of the same
  // fact, found 2026-09-27 while fixing the live bug in the other two.
  return { chipsOut, payments, chipsReturned, balance: currentPlayerBalance(playerLedger.value, rawBalance) }
})

async function loadPlayerLedger(playerId) {
  playerLedgerLoading.value = true
  try {
    const { data } = await api.get(`/game-days/${detailId.value}/players/${playerId}/ledger/`)
    playerLedger.value = data
  } catch {
    toast.error("Could not load this player's activity.")
  } finally {
    playerLedgerLoading.value = false
  }
}

async function onSelectPlayer(p) {
  if (selectedPlayerId.value === p.id) {
    selectedPlayerId.value = null
    playerLedger.value = []
    return
  }
  selectedPlayerId.value = p.id
  await loadPlayerLedger(p.id)
}
</script>

<template>
  <div class="page">
    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!gameDays.length" class="muted">No game-days recorded yet.</p>

    <template v-else>
      <div class="table">
        <div class="t-head">
          <span>#</span><span>Date</span><span>Rake</span><span>Balance</span><span>Payments</span><span>Chips out</span><span>Chips</span><span>Players</span>
        </div>
        <div
          v-for="gd in pagedGameDays" :key="gd.id" class="t-row"
          :class="{ 't-row--selected': detailId === gd.id }"
          @click="onViewGameDay(gd)"
        >
          <span class="mono">{{ gd.number }}</span>
          <span>{{ formatDate(gd.started_at) }}</span>
          <span class="money">{{ gd.summary ? N(gd.summary.rake_total) : '—' }}</span>
          <span class="money">{{ gd.summary ? N(gd.summary.game_balance) : '—' }}</span>
          <span class="money">{{ gd.summary ? N(gd.summary.total_payments) : '—' }}</span>
          <span class="money">{{ gd.summary ? N(gd.summary.chips_out_total) : '—' }}</span>
          <span class="money chips-cell" :class="chipsBadge(gd)?.className">
            {{ chipsBadge(gd) ? `${chipsBadge(gd).label} ${N(chipsBadge(gd).amount)}` : '—' }}
          </span>
          <span>{{ gd.summary ? gd.summary.num_players : '—' }}</span>
        </div>

        <div v-if="totalPages > 1" class="pagination">
          <span class="range-label">{{ rangeLabel }}</span>
          <div class="page-btns">
            <button class="page-btn" type="button" :disabled="page === 1" @click="goToPage(page - 1)">&larr; Prev</button>
            <button
              v-for="n in totalPages" :key="n" class="page-btn" type="button"
              :class="{ 'page-btn--current': page === n }" @click="goToPage(n)"
            >{{ n }}</button>
            <button class="page-btn" type="button" :disabled="page === totalPages" @click="goToPage(page + 1)">Next &rarr;</button>
          </div>
        </div>
      </div>

      <div v-if="detailId" id="game-day-detail" class="detail">
        <p v-if="detailLoading" class="muted">Loading…</p>
        <template v-else-if="gameDay">
          <div class="detail-head">
            <h2>Game-Day #{{ gameDay.number }}</h2>
            <span class="badge" :class="gameDay.status === 'OPEN' ? 'badge--open' : 'badge--closed'">{{ gameDay.status }}</span>
            <div class="spacer" />
          </div>
          <p class="date-line">{{ formatFullDate(gameDay.started_at) }} &middot; started {{ formatTime(gameDay.started_at) }}</p>

          <p v-if="!players.length" class="muted">No players seated.</p>
          <div v-else class="pill-row">
            <button
              v-for="p in players" :key="p.id" type="button" class="pill"
              :class="{ 'pill--selected': selectedPlayerId === p.id }" @click="onSelectPlayer(p)"
            >
              {{ p.display_name }} <span class="pill-code">{{ p.account_code }}</span>
            </button>
          </div>

          <div v-if="selectedPlayerId" class="card player-panel">
            <p v-if="playerLedgerLoading" class="muted">Loading…</p>
            <template v-else>
              <div class="player-panel-head">
                <div>
                  <span class="pname">{{ selectedPlayer?.display_name }}</span>
                  <span class="pcode">{{ selectedPlayer?.account_code }}</span>
                </div>
              </div>

              <div class="mini-stat-grid">
                <div class="mini-box">
                  <div class="mini-label">Chips out</div>
                  <div class="mini-value">{{ N(selectedPlayerStats.chipsOut) }}</div>
                </div>
                <div class="mini-box">
                  <div class="mini-label">Payments</div>
                  <div class="mini-value">{{ N(selectedPlayerStats.payments) }}</div>
                </div>
                <div class="mini-box">
                  <div class="mini-label">Chips returned</div>
                  <div class="mini-value">{{ N(selectedPlayerStats.chipsReturned) }}</div>
                </div>
                <div class="mini-box mini-box--balance">
                  <div class="mini-label">Balance</div>
                  <div class="mini-value">{{ N(selectedPlayerStats.balance) }}</div>
                </div>
              </div>

              <LedgerTable
                :rows="selectedPlayerLedgerRows" type-label="Action" voidable :can-void-fn="canVoid"
                @void="voidTarget = $event"
              />
            </template>
          </div>

          <p v-else-if="players.length" class="muted">Tap a player above to see their activity for this game-day.</p>
        </template>
      </div>
    </template>

    <VoidEntryModal
      v-if="voidTarget" :transaction="voidTarget" :player-name="playerName(voidTarget.player)"
      :recorded-by-name="auth.user?.fullName" @close="voidTarget = null" @voided="onVoided"
    />
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.muted { color: var(--text-secondary); font-size: 13px; }

.table { border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; background: var(--surface); }
.t-head, .t-row {
  display: grid;
  grid-template-columns: 50px 110px 1fr 1fr 1fr 1fr 1fr 70px;
  align-items: center;
  padding: 0 20px;
  gap: 8px;
}
.t-head { height: var(--control-row-min); background: var(--bg); border-bottom: 1px solid var(--border); }
.t-head span { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.t-row { height: var(--control-row-max); border-bottom: 1px solid var(--border); font-size: 13.5px; color: var(--text-primary); cursor: pointer; }
.t-row:last-child { border-bottom: none; }
.t-row:hover { background: var(--bg); }
.t-row--selected { background: var(--accent-bg); }
.t-row--selected:hover { background: var(--accent-bg); }
.mono { font-family: var(--font-mono); color: var(--text-secondary); }
.chips-cell { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.chips-cell.variance--deficit { color: var(--warning-text); }
.chips-cell.variance--excess { color: var(--accent-text); }
.chips-cell.variance--balanced { color: var(--text-tertiary); }

.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
  background: var(--bg);
  font-size: 12px;
  color: var(--text-tertiary);
}
.page-btns { display: flex; gap: 6px; }
.page-btn {
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  padding: 5px 11px;
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
}
.page-btn:disabled { opacity: 0.45; cursor: default; }
.page-btn--current { border-color: var(--accent); color: var(--accent-text); font-weight: 700; }

/* ── Detail panel — opens inline below the list ──────────────────────── */
.detail { margin-top: 26px; }
.detail-head { display: flex; align-items: center; gap: 12px; margin-bottom: 2px; }
.detail-head h2 { font-size: 19px; font-weight: 700; color: var(--text-primary); margin: 0; }
.spacer { flex-grow: 1; }
.date-line { font-size: 12.5px; color: var(--text-tertiary); margin: 0 0 20px; }

.sub-head { font-size: 12px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; }
.lbl--muted { font-weight: 500; text-transform: none; color: var(--text-tertiary); font-size: 11.5px; margin-left: 4px; }

.pill-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 22px; }
.pill {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  padding: 7px 13px;
  font-family: var(--font-sans);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
}
.pill:hover { border-color: var(--accent); }
.pill--selected { border-color: var(--accent); background: var(--accent-bg); color: var(--accent-text); }
.pill-code { font-family: var(--font-mono); font-size: 11px; font-weight: 500; color: var(--text-tertiary); }
.pill--selected .pill-code { color: var(--accent-text); opacity: 0.75; }

.player-panel { padding: 18px 20px; }
.player-panel-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.pname { font-size: 14.5px; font-weight: 700; color: var(--text-primary); }
.pcode { font-family: var(--font-mono); font-size: 11.5px; color: var(--text-tertiary); margin-left: 8px; }

.mini-stat-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }
.mini-box { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px 14px; }
.mini-box--balance { border-color: var(--accent); background: var(--accent-bg); }
.mini-label { font-size: 10px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 6px; }
.mini-value { font-family: var(--font-mono); font-weight: 700; font-size: 15px; font-variant-numeric: tabular-nums; color: var(--text-primary); }
.mini-box--balance .mini-value { color: var(--accent-text); }

@media (max-width: 860px) {
  .t-head { display: none; }
  .t-row { grid-template-columns: 1fr; height: auto; padding: 14px 20px; gap: 4px; }
  .mini-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
