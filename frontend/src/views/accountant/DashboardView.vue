<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/axios'
import { useToast } from '@/composables/useToast'

// Accountant/Owner back-office dashboard (Phase B, 2026-09-14) — GET
// /api/dashboard/ already gates OWNER/ACCOUNTANT server-side and adds
// main_account_balance only for OWNER (gaming/views.py's DashboardView);
// that field is left for Phase C's Owner surface, not shown here.
const router = useRouter()
const toast = useToast()

const totals = ref(null)
const loading = ref(true)

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
}

onMounted(load)

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

.stat-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.stat-card { padding: 20px; display: flex; flex-direction: column; gap: 8px; }
.stat-label { font-size: 11px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.stat-value { font-family: var(--font-mono); font-weight: 600; font-size: 24px; font-variant-numeric: tabular-nums; color: var(--text-primary); }
.stat-value.money--pos { color: var(--success-text); }
.stat-value.money--neg { color: var(--danger-text); }
.stat-sub { font-size: 12px; color: var(--text-secondary); }

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
}
</style>
