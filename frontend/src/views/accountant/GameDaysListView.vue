<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import api from '@/api/axios'
import { useAuthStore } from '@/stores/auth'
import VoidEntryModal from '@/components/shared/VoidEntryModal.vue'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import { canVoidTransaction } from '@/utils/canVoid'
import { describeChipsVariance } from '@/utils/chipsVariance'
import { useToast } from '@/composables/useToast'

// Game-day history (Phase B, 2026-09-14) — GET /api/game-days/ is
// IsAuthenticated-only (gaming/views.py's GameDayViewSet), newest first per
// its own queryset ordering. Closed rows show their frozen GameDaySummary
// inline; OPEN rows don't fetch close-preview here (that'd be N+1 API calls
// for a list) — full live stats are one click away below.
//
// Hi-fi pass, 2026-09-14 -> 2026-09-23: GameDayDetailView.vue (formerly its
// own /game-days/:id route) is folded in here wholesale — clicking "View" on
// a row now opens that game-day's detail INLINE, below the (paginated, 7/
// page) list on this same page, per the lo-fi nav review sketch. No other
// screen linked to the old route (confirmed by search before removing it),
// so nothing else needed to change. Also new: a seated player's pill can be
// tapped to narrow the detail's stat row + ledger to just that player's own
// activity for the night (GET /game-days/{id}/players/{player_id}/ledger/,
// which already existed for RosterDetailView's own per-game-day section —
// the mini stat totals below are computed client-side from those rows,
// there's no new backend endpoint for this).
const auth = useAuthStore()
const toast = useToast()

const gameDays = ref([])
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/game-days/')
    gameDays.value = data
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

// A compact per-row read of the same signed chips_variance shown in full on
// the detail panel below — lets an Accountant/Owner spot a problem night
// while just scanning the list, without opening each one.
function chipsBadge(gd) {
  if (!gd.summary) return null
  const v = Number(gd.summary.chips_variance)
  const { amount, className } = describeChipsVariance(v)
  const label = v > 0 ? 'Deficit' : v < 0 ? 'Excess' : 'Balanced'
  return { label, amount, className }
}

const N = n => `₦${Number(n).toLocaleString()}`

// ── Pagination (7 per page — per the lo-fi sketch) ───────────────────────
const PAGE_SIZE = 7
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
const ledger = ref([])
const stats = ref(null)
const voidTarget = ref(null)

const displayStats = computed(() => {
  if (gameDay.value?.status === 'CLOSED' && gameDay.value.summary) return gameDay.value.summary
  return stats.value
})
const chipsVariance = computed(() => (displayStats.value ? describeChipsVariance(displayStats.value.chips_variance) : null))
const chipsVarianceShortLabel = computed(() => {
  const v = Number(displayStats.value?.chips_variance)
  return v > 0 ? 'Deficit' : v < 0 ? 'Excess' : 'Balanced'
})

async function loadDetail(id) {
  detailLoading.value = true
  try {
    const [gdRes, playersRes, ledgerRes] = await Promise.all([
      api.get(`/game-days/${id}/`),
      api.get(`/game-days/${id}/players/`),
      api.get(`/game-days/${id}/ledger/`),
    ])
    gameDay.value = gdRes.data
    players.value = playersRes.data
    ledger.value = ledgerRes.data.slice().reverse()
    stats.value = gameDay.value.status === 'OPEN' ? (await api.get(`/game-days/${id}/close-preview/`)).data : null
  } catch {
    toast.error('Could not load this game-day.')
  } finally {
    detailLoading.value = false
  }
}

async function onViewGameDay(gd) {
  if (detailId.value === gd.id) {
    closeDetail()
    return
  }
  detailId.value = gd.id
  selectedPlayerId.value = null
  playerLedger.value = []
  await loadDetail(gd.id)
  await nextTick()
  document.getElementById('game-day-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function closeDetail() {
  detailId.value = null
  gameDay.value = null
  selectedPlayerId.value = null
  playerLedger.value = []
}

function playerName(playerId) {
  if (!playerId) return ''
  return players.value.find(p => p.id === playerId)?.display_name || ''
}
const ledgerRows = computed(() => ledger.value.map(row => ({ ...row, player_name: playerName(row.player) })))
const playerTo = row => (row.player ? { path: `/roster/${row.player}`, query: { gameDay: detailId.value } } : null)

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
// same 4 types the club-wide "Payments" stat card above already sums,
// scoped down to just this one player's own rows.
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
  return { chipsOut, payments, chipsReturned, balance: last ? Number(last.running_balance) : 0 }
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
    <div class="page-header">
      <h1>Game Days</h1>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!gameDays.length" class="muted">No game-days recorded yet.</p>

    <template v-else>
      <div class="table">
        <div class="t-head">
          <span>#</span><span>Date</span><span>Status</span><span>Rake</span><span>Chips</span><span>Game balance</span><span>Players</span><span></span>
        </div>
        <div
          v-for="gd in pagedGameDays" :key="gd.id" class="t-row"
          :class="{ 't-row--selected': detailId === gd.id }"
          @click="onViewGameDay(gd)"
        >
          <span class="mono">{{ gd.number }}</span>
          <span>{{ formatDate(gd.started_at) }}</span>
          <span>
            <span class="badge" :class="gd.status === 'OPEN' ? 'badge--open' : 'badge--closed'">{{ gd.status }}</span>
          </span>
          <span class="money">{{ gd.summary ? N(gd.summary.rake_total) : '—' }}</span>
          <span class="money chips-cell" :class="chipsBadge(gd)?.className">
            {{ chipsBadge(gd) ? `${chipsBadge(gd).label} ${N(chipsBadge(gd).amount)}` : '—' }}
          </span>
          <span class="money">{{ gd.summary ? N(gd.summary.game_balance) : '—' }}</span>
          <span>{{ gd.summary ? gd.summary.num_players : '—' }}</span>
          <span class="view-link">{{ detailId === gd.id ? 'Hide ↑' : 'View ↓' }}</span>
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
            <button class="close-btn" type="button" @click="closeDetail">&times; Close</button>
          </div>
          <p class="date-line">{{ formatFullDate(gameDay.started_at) }} &middot; started {{ formatTime(gameDay.started_at) }}</p>

          <div v-if="displayStats" class="stat-grid">
            <div class="card stat-card">
              <div class="stat-label">Chips out</div>
              <div class="stat-value">{{ N(displayStats.chips_out_total) }}</div>
            </div>
            <div class="card stat-card">
              <div class="stat-label">Payments</div>
              <div class="stat-value">{{ N(displayStats.total_payments) }}</div>
            </div>
            <div class="card stat-card">
              <div class="stat-label">Rake</div>
              <div v-if="gameDay.status === 'OPEN'" class="stat-pending">pending &mdash; at close</div>
              <div v-else class="stat-value">{{ N(displayStats.rake_total) }}</div>
            </div>
            <div class="card stat-card">
              <div class="stat-label">Balance <span v-if="gameDay.status === 'OPEN'">(live)</span></div>
              <div class="stat-value">{{ N(displayStats.game_balance) }}</div>
            </div>
            <div class="card stat-card">
              <div class="stat-label">Chips</div>
              <div v-if="gameDay.status === 'OPEN'" class="stat-pending">pending &mdash; at close</div>
              <div v-else class="stat-value" :class="chipsVariance.className" :title="chipsVariance.label">
                {{ chipsVarianceShortLabel }} {{ N(chipsVariance.amount) }}
              </div>
            </div>
          </div>

          <div class="sub-head">Players seated <span class="lbl--muted">tap a player to see just their activity</span></div>
          <p v-if="!players.length" class="muted">No players seated.</p>
          <div v-else class="pill-row">
            <button
              v-for="p in players" :key="p.id" type="button" class="pill"
              :class="{ 'pill--selected': selectedPlayerId === p.id }" @click="onSelectPlayer(p)"
            >
              {{ p.display_name }} <span class="pill-code">{{ p.account_code }}</span>
              <span v-if="p.left_at" class="badge badge--voided">left</span>
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
                <RouterLink :to="{ path: `/roster/${selectedPlayerId}`, query: { gameDay: detailId } }" class="link-btn">View full profile &rarr;</RouterLink>
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

          <div v-else class="card ledger-card">
            <div class="section-title">Full ledger <span class="lbl--muted">running balance &middot; club-wide</span></div>
            <div class="ledger-feed">
              <LedgerTable :rows="ledgerRows" show-player :player-to="playerTo" voidable :can-void-fn="canVoid" @void="voidTarget = $event" />
            </div>
          </div>
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
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }
.muted { color: var(--text-secondary); font-size: 13px; }

.table { border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; background: var(--surface); }
.t-head, .t-row {
  display: grid;
  grid-template-columns: 60px 130px 100px 1fr 1fr 1fr 90px 70px;
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
.view-link { font-size: 12.5px; font-weight: 600; color: var(--accent-text); text-align: right; }
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
.close-btn { border: none; background: none; font-size: 13px; font-weight: 600; color: var(--text-secondary); cursor: pointer; padding: 4px 0; }
.close-btn:hover { color: var(--text-primary); }
.date-line { font-size: 12.5px; color: var(--text-tertiary); margin: 0 0 20px; }

.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin-bottom: 24px; }
.stat-card { padding: 16px 18px; display: flex; flex-direction: column; gap: 6px; }
.stat-label { font-size: 11px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.stat-value { font-family: var(--font-mono); font-weight: 600; font-size: 19px; font-variant-numeric: tabular-nums; color: var(--text-primary); }
.stat-value.variance--deficit { color: var(--warning-text); }
.stat-value.variance--excess { color: var(--accent-text); }
.stat-value.variance--balanced { color: var(--text-tertiary); }
.stat-pending { font-size: 12px; font-weight: 600; color: var(--text-tertiary); }

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

.player-panel, .ledger-card { padding: 18px 20px; }
.player-panel-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.pname { font-size: 14.5px; font-weight: 700; color: var(--text-primary); }
.pcode { font-family: var(--font-mono); font-size: 11.5px; color: var(--text-tertiary); margin-left: 8px; }
.link-btn { font-size: 12.5px; font-weight: 700; color: var(--accent-text); text-decoration: none; white-space: nowrap; }
.link-btn:hover { text-decoration: underline; }

.mini-stat-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }
.mini-box { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px 14px; }
.mini-box--balance { border-color: var(--accent); background: var(--accent-bg); }
.mini-label { font-size: 10px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 6px; }
.mini-value { font-family: var(--font-mono); font-weight: 700; font-size: 15px; font-variant-numeric: tabular-nums; color: var(--text-primary); }
.mini-box--balance .mini-value { color: var(--accent-text); }

.section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; }
.ledger-feed { border-top: 1px solid var(--border); }

@media (max-width: 860px) {
  .t-head { display: none; }
  .t-row { grid-template-columns: 1fr; height: auto; padding: 14px 20px; gap: 4px; }
  .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .mini-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
