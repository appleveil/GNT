<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/axios'
import { useAuthStore } from '@/stores/auth'
import { useGameDayStore } from '@/stores/gameDay'
import { useClubSettingsStore } from '@/stores/clubSettings'
import { useToast } from '@/composables/useToast'
import VoidEntryModal from '@/components/shared/VoidEntryModal.vue'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import { canVoidTransaction } from '@/utils/canVoid'

// Accountant/Owner back-office dashboard (Phase B, 2026-09-14). Phase C
// (2026-09-14) adds two Owner-only pieces: main_account_balance (already
// present in the /dashboard/ response, only for OWNER — gaming/views.py's
// DashboardView) and a direct Open-Game-Day trigger. Opening this way posts
// straight to /api/game-days/open/ with no PIN — the Owner-login bypass
// confirmed in gaming/services.py's _resolve_owner_or_floor_manager, distinct
// from the Cashier-device picker-then-PIN flow in ActiveGameDayView.vue
// (whose nextGameDayNumber() this mirrors).
//
// The Outstanding ledger (feed + by-player summary) moved in here wholesale
// from its own /outstanding page on 2026-09-23 — that page is gone, this is
// now its only home, for both roles that already share this page.
//
// Also 2026-09-23: the 3rd stat card is role-conditional now.
// total_rake_this_month (Owner only) replaced "Unreturned chips" there;
// Accountant still gets outstanding_chips as before — the two fields are
// mutually exclusive per role in the API response, so the template below
// just checks which one showed up.
//
// 2026-09-24: the open/operate-game-day card is now Owner-configurable —
// off by default (see ClubSettings.owner_dashboard_game_day_enabled) —
// rather than always showing for every Owner. Settings screen has the
// toggle; this view just reads it.
const router = useRouter()
const auth = useAuthStore()
const gameDay = useGameDayStore()
const clubSettings = useClubSettingsStore()
const toast = useToast()

const totals = ref(null)
const loading = ref(true)
const opening = ref(false)

const players = ref([])
const outstandingRows = ref([])
const outstandingLoading = ref(true)
const voidTarget = ref(null)

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/dashboard/')
    totals.value = data
  } catch {
    toast.error('Could not load dashboard totals.')
  } finally {
    loading.value = false
  }
  // Own try/catch, own toast — a failure here never blocks the totals above
  // from showing, same convention as the gameDay.fetchCurrent() call below.
  outstandingLoading.value = true
  try {
    const [playersRes, ledgerRes] = await Promise.all([
      api.get('/players/'),
      api.get('/outstanding/'),
    ])
    players.value = playersRes.data
    outstandingRows.value = ledgerRes.data
  } catch {
    toast.error('Could not load the outstanding ledger.')
  } finally {
    outstandingLoading.value = false
  }
  // Separate from the totals fetch above (own try/catch, own toast) so a
  // failure here never blocks the totals from showing — see gameDay.js's
  // fetchCurrent for why it needs no catch of its own here.
  if (auth.isOwner) {
    try {
      await gameDay.fetchCurrent()
    } catch {
      /* fetchCurrent already toasted */
    }
    if (!clubSettings.current) {
      try {
        await clubSettings.fetchCurrent()
      } catch {
        /* fetchCurrent already toasted */
      }
    }
  }
}

onMounted(load)

async function onOpenGameDay() {
  opening.value = true
  try {
    const { data: gameDays } = await api.get('/game-days/')
    const number = (gameDays[0]?.number || 0) + 1
    const { data } = await api.post('/game-days/open/', { number })
    gameDay.current = data
    toast.success(`Game-Day #${number} opened.`)
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Could not open a game-day.')
  } finally {
    opening.value = false
  }
}

function playerName(playerId) {
  return players.value.find(p => p.id === playerId)?.display_name || ''
}

function canVoid(row) {
  return canVoidTransaction(row, auth.user)
}
function onVoided() {
  voidTarget.value = null
  toast.success('Entry voided.')
  load()
}

// One summary row per player — their current outstanding balance is the
// running_balance on their chronologically LAST row (outstandingRows is
// ascending by created_at, as the API returns it), sorted biggest-absolute-
// balance first so the players who owe the most (or are owed the most)
// surface top.
const byPlayer = computed(() => {
  const latest = new Map() // player id -> last row seen, in ascending order
  for (const row of outstandingRows.value) {
    if (row.player) latest.set(row.player, row)
  }
  return Array.from(latest.values())
    .map(row => ({ playerId: row.player, name: playerName(row.player), balance: Number(row.running_balance) }))
    .sort((a, b) => Math.abs(b.balance) - Math.abs(a.balance))
})

const feed = computed(() => outstandingRows.value.slice().reverse().map(row => ({ ...row, player_name: playerName(row.player) })))
const playerTo = row => (row.player ? `/roster/${row.player}` : null)

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="dashboard">
    <div class="page-header">
      <h1>Dashboard</h1>
      <p>Club-wide totals, reconciled against the master transaction ledger.</p>
    </div>

    <p v-if="loading" class="muted">Loading…</p>

    <template v-else-if="totals">
      <div class="stat-grid">
        <div class="card stat-card">
          <div class="stat-label">Owed by players</div>
          <div class="stat-value money--pos">{{ N(totals.total_outstanding_from_players) }}</div>
          <div class="stat-stub">{{ totals.debtor_count }} players</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Owed to players</div>
          <div class="stat-value money--neg">{{ N(totals.total_outstanding_to_players) }}</div>
          <div class="stat-stub">{{ totals.creditor_count }} players</div>
        </div>
        <div v-if="totals.total_rake_this_month !== undefined" class="card stat-card">
          <div class="stat-label">Total rake this month</div>
          <div class="stat-value">{{ N(totals.total_rake_this_month) }}</div>
        </div>
        <div v-else class="card stat-card">
          <div class="stat-label">Unreturned chips</div>
          <div class="stat-value">{{ N(totals.outstanding_chips) }}</div>
        </div>
        <div v-if="totals.main_account_balance !== undefined" class="card stat-card">
          <div class="stat-label">Main account balance</div>
          <div class="stat-value">{{ N(totals.main_account_balance) }}</div>
        </div>
      </div>

      <div v-if="auth.isOwner && clubSettings.current?.owner_dashboard_game_day_enabled" class="card game-day-card">
        <template v-if="gameDay.isOpen">
          <div>
            <div class="gd-title">Game-Day #{{ gameDay.current.number }} is open</div>
            <div class="gd-sub">Started {{ new Date(gameDay.current.started_at).toLocaleString('en-US', { hour: 'numeric', minute: '2-digit', month: 'short', day: 'numeric' }) }}</div>
          </div>
          <button class="btn btn--secondary" type="button" @click="router.push('/game-day')">Operate it &rarr;</button>
        </template>
        <template v-else>
          <div>
            <div class="gd-title">No game-day is open right now</div>
            <div class="gd-sub">Opens immediately under your own login — no PIN needed.</div>
          </div>
          <button class="btn btn--primary" type="button" :disabled="opening" @click="onOpenGameDay">
            {{ opening ? 'Opening…' : 'Open Game-Day' }}
          </button>
        </template>
      </div>

      <div class="section-heading">
        <h2>Outstanding</h2>
        <p>Activity recorded outside any game-day — deals, write-offs, direct payments — with each player's own running balance.</p>
      </div>

      <p v-if="outstandingLoading" class="muted">Loading…</p>
      <p v-else-if="!outstandingRows.length" class="muted">No between-game-day activity recorded.</p>

      <div v-else class="grid-two">
        <div class="card feed-card">
          <div class="section-title">Full activity</div>
          <div class="feed">
            <LedgerTable :rows="feed" show-player :player-to="playerTo" date-format="datetime" voidable :can-void-fn="canVoid" @void="voidTarget = $event" />
          </div>
        </div>

        <div class="card summary-card">
          <div class="section-title">By player</div>
          <RouterLink v-for="p in byPlayer" :key="p.playerId" :to="`/roster/${p.playerId}`" class="summary-row">
            <span class="summary-name">{{ p.name }}</span>
            <span class="money" :class="p.balance > 0 ? 'money--pos' : p.balance < 0 ? 'money--neg' : ''">{{ N(p.balance) }}</span>
          </RouterLink>
        </div>
      </div>
    </template>

    <VoidEntryModal
      v-if="voidTarget" :transaction="voidTarget" :player-name="playerName(voidTarget.player)"
      :recorded-by-name="auth.user?.fullName" @close="voidTarget = null" @voided="onVoided"
    />
  </div>
</template>

<style scoped>
.dashboard { max-width: 1100px; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }
.muted { color: var(--text-secondary); font-size: 13px; }

.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
.stat-card { padding: 20px; display: flex; flex-direction: column; gap: 8px; }
.stat-label { font-size: 11px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.stat-value { font-family: var(--font-mono); font-weight: 600; font-size: 24px; font-variant-numeric: tabular-nums; color: var(--text-primary); }
.stat-value.money--pos { color: var(--success-text); }
.stat-value.money--neg { color: var(--danger-text); }
.stat-sub { font-size: 12px; color: var(--text-secondary); }

.game-day-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  margin-top: 16px;
}
.gd-title { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.gd-sub { font-size: 12.5px; color: var(--text-secondary); margin-top: 2px; }

.quick-links { display: grid; grid-template-columns: 1fr; gap: 16px; margin-top: 16px; }
.link-card {
  padding: 18px 20px;
  text-align: left;
  cursor: pointer;
  font-family: var(--font-sans);
  border: 1px solid var(--border);
}
.link-card:hover { border-color: var(--accent); }
.link-title { font-size: 14px; font-weight: 700; color: var(--accent-text); margin-bottom: 4px; }
.link-sub { font-size: 12.5px; color: var(--text-secondary); }

/* Outstanding section — carried over from the retired OutstandingView.vue
   (2026-09-23), styles included. */
.section-heading { margin: 28px 0 16px; }
.section-heading h2 { font-size: 17px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.section-heading p { font-size: 13px; color: var(--text-secondary); margin: 0; max-width: 620px; }

.grid-two { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; align-items: start; }
.feed-card, .summary-card { padding: 18px 20px; }
.section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; }

.feed { border-top: 1px solid var(--border); }

.summary-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  text-decoration: none;
}
.summary-row:last-child { border-bottom: none; }
.summary-name { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }
.summary-row:hover .summary-name { color: var(--accent-text); }
.money--pos { color: var(--success-text); }
.money--neg { color: var(--danger-text); }

@media (max-width: 720px) {
  .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .game-day-card { flex-direction: column; align-items: stretch; text-align: center; }
}
@media (max-width: 860px) {
  .grid-two { grid-template-columns: 1fr; }
}
</style>
