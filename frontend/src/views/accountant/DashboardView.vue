<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api/axios'
import { useAuthStore } from '@/stores/auth'
import { useGameDayStore } from '@/stores/gameDay'
import { useClubSettingsStore } from '@/stores/clubSettings'
import { useToast } from '@/composables/useToast'
import { readApiError } from '@/utils/apiError'

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
// from its own /outstanding page on 2026-09-23, then OUT again on
// 2026-09-26 to its own real page — /ledgers/off-table, renamed "Off-table"
// — once "Game Days" became "Ledgers" with room for a sibling sub-page.
//
// Also 2026-09-23: the 3rd stat card is role-conditional now.
// total_rake_this_month (Owner only) replaced "Unreturned chips" there;
// Accountant still gets outstanding_chips as before — the two fields are
// mutually exclusive per role in the API response, so the template below
// just checks which one showed up.
//
// 2026-09-24: the open/operate-game-day card became Owner-configurable —
// off by default (see ClubSettings.owner_dashboard_game_day_enabled).
// 2026-09-26: that single card is now a "Live tables" summary — nothing in
// this schema ever stopped more than one game-day being OPEN at once (one
// per Table; see GameDay/Table's own docstrings), only this dashboard
// (and the Cashier's single-table screen) ever assumed there'd be just
// one. GET /game-days/?status=OPEN lists every one of them; "View →" on a
// row deep-links into /ledgers/game-days?gameDay=<id> (see
// GameDaysListView.vue's own handling of that param) rather than the
// Cashier's /game-day screen, which still only ever operates whichever one
// gameDay.current (singular) resolves to — a real gap for true concurrent
// OPERATION, not attempted here; this is read-only visibility only.
const auth = useAuthStore()
const gameDay = useGameDayStore()
const clubSettings = useClubSettingsStore()
const toast = useToast()

const totals = ref(null)
const loading = ref(true)
const opening = ref(false)

const openGameDays = ref([])
const tables = ref([])

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
    try {
      const [gdRes, tablesRes] = await Promise.all([
        api.get('/game-days/', { params: { status: 'OPEN' } }),
        api.get('/tables/'),
      ])
      openGameDays.value = gdRes.data
      tables.value = tablesRes.data
    } catch {
      toast.error('Could not load live tables.')
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
    openGameDays.value = [data, ...openGameDays.value]
    toast.success(`Game-Day #${number} opened.`)
  } catch (err) {
    toast.error(readApiError(err, 'Could not open a game-day.').message)
  } finally {
    opening.value = false
  }
}

function tableName(tableId) {
  return tables.value.find(t => t.id === tableId)?.name || null
}
function formatStarted(iso) {
  return new Date(iso).toLocaleString('en-US', { hour: 'numeric', minute: '2-digit', month: 'short', day: 'numeric' })
}

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
        <!-- Placeholder, added 2026-10-02 — Owner asked for a "Deals ROI"
             card; definition (what counts as the return, over what period)
             is still pending from them, so this shows "—" until there's a
             real number to compute. No backend field yet — see PLAN.md's
             dated entry. -->
        <div v-if="auth.isOwner" class="card stat-card">
          <div class="stat-label">Deals ROI</div>
          <div class="stat-value">—</div>
          <div class="stat-stub">This month</div>
        </div>
      </div>

      <div v-if="auth.isOwner && clubSettings.current?.owner_dashboard_game_day_enabled" class="card live-tables-card">
        <div class="live-tables-head">
          <div class="section-title">Live tables</div>
          <button class="btn btn--primary" type="button" :disabled="opening" @click="onOpenGameDay">
            {{ opening ? 'Opening…' : '+ Open Game-Day' }}
          </button>
        </div>

        <p v-if="!openGameDays.length" class="muted">No game-day is open right now.</p>
        <div v-else class="table-list">
          <RouterLink v-for="gd in openGameDays" :key="gd.id" :to="`/ledgers/game-days?gameDay=${gd.id}`" class="table-row">
            <div>
              <div class="table-row-title">{{ tableName(gd.table) || `Game-Day #${gd.number}` }}</div>
              <div class="table-row-sub">Game-Day #{{ gd.number }} &middot; started {{ formatStarted(gd.started_at) }}</div>
            </div>
            <span class="view-link">View &rarr;</span>
          </RouterLink>
        </div>
      </div>
    </template>
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

.live-tables-card { padding: 18px 20px; margin-top: 16px; }
.live-tables-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 4px; }
.section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); }

.table-list { margin-top: 8px; }
.table-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid var(--border);
  text-decoration: none;
}
.table-row:last-child { border-bottom: none; }
.table-row-title { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }
.table-row-sub { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
.view-link { font-size: 12.5px; font-weight: 600; color: var(--accent-text); flex-shrink: 0; }
.table-row:hover .table-row-title { color: var(--accent-text); }

@media (max-width: 720px) {
  .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .live-tables-head { flex-direction: column; align-items: stretch; }
}
</style>
