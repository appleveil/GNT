<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/axios'
import { useAuthStore } from '@/stores/auth'
import { useGameDayStore } from '@/stores/gameDay'
import { useToast } from '@/composables/useToast'

// Accountant/Owner back-office dashboard (Phase B, 2026-09-14). Phase C
// (2026-09-14) adds two Owner-only pieces: main_account_balance (already
// present in the /dashboard/ response, only for OWNER — gaming/views.py's
// DashboardView) and a direct Open-Game-Day trigger. Opening this way posts
// straight to /api/game-days/open/ with no PIN — the Owner-login bypass
// confirmed in gaming/services.py's _resolve_owner_or_floor_manager, distinct
// from the Cashier-device picker-then-PIN flow in ActiveGameDayView.vue
// (whose nextGameDayNumber() this mirrors).
const router = useRouter()
const auth = useAuthStore()
const gameDay = useGameDayStore()
const toast = useToast()

const totals = ref(null)
const loading = ref(true)
const opening = ref(false)

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
          <div class="stat-label">Outstanding from players</div>
          <div class="stat-value money--neg">{{ N(totals.total_outstanding_from_players) }}</div>
          <div class="stat-sub">owed to the club</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Outstanding to players</div>
          <div class="stat-value money--pos">{{ N(totals.total_outstanding_to_players) }}</div>
          <div class="stat-sub">owed by the club</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Debtors</div>
          <div class="stat-value">{{ totals.debtor_count }}</div>
          <div class="stat-sub">players in the red</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Outstanding chips</div>
          <div class="stat-value">{{ N(totals.outstanding_chips) }}</div>
          <div class="stat-sub">unreturned, across closed game-days</div>
        </div>
        <div v-if="totals.main_account_balance !== undefined" class="card stat-card">
          <div class="stat-label">Main account balance</div>
          <div class="stat-value">{{ N(totals.main_account_balance) }}</div>
          <div class="stat-sub">the club's real bank balance</div>
        </div>
      </div>

      <div v-if="auth.isOwner" class="card game-day-card">
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

      <div class="quick-links">
        <button class="card link-card" type="button" @click="router.push('/outstanding')">
          <div class="link-title">View outstanding ledger &rarr;</div>
          <div class="link-sub">Every player's cross-game-day running balance.</div>
        </button>
        <button class="card link-card" type="button" @click="router.push('/game-days')">
          <div class="link-title">Browse game-day history &rarr;</div>
          <div class="link-sub">Every game-day, open and closed, with full ledgers.</div>
        </button>
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

.quick-links { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }
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

@media (max-width: 720px) {
  .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .quick-links { grid-template-columns: 1fr; }
  .game-day-card { flex-direction: column; align-items: stretch; text-align: center; }
}
</style>
