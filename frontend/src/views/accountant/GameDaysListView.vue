<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/axios'
import { useToast } from '@/composables/useToast'
import { describeChipsVariance } from '@/utils/chipsVariance'

// Game-day history (Phase B, 2026-09-14) — GET /api/game-days/ is
// IsAuthenticated-only (gaming/views.py's GameDayViewSet), newest first per
// its own queryset ordering. Closed rows show their frozen GameDaySummary
// inline; OPEN rows don't fetch close-preview here (that'd be N+1 API calls
// for a list) — full live stats are one click away on the detail page.
const router = useRouter()
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

// A compact per-row read of the same signed chips_variance shown in full
// on the detail page — lets an Accountant/Owner spot a problem night while
// just scanning history, without opening each one. Short label only (the
// full "Chips deficit"/"Chips excess returned" wording is used where there's
// more room, e.g. the close dialog and the detail page's stat card).
function chipsBadge(gd) {
  if (!gd.summary) return null
  const v = Number(gd.summary.chips_variance)
  const { amount, className } = describeChipsVariance(v)
  const label = v > 0 ? 'Deficit' : v < 0 ? 'Excess' : 'Balanced'
  return { label, amount, className }
}

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Game Days</h1>
      <p>Every game-day, open and closed — click through for the full ledger.</p>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!gameDays.length" class="muted">No game-days recorded yet.</p>

    <div v-else class="table">
      <div class="t-head">
        <span>#</span><span>Date</span><span>Status</span><span>Rake</span><span>Chips</span><span>Game balance</span><span>Players</span><span></span>
      </div>
      <div
        v-for="gd in gameDays" :key="gd.id" class="t-row"
        @click="router.push(`/game-days/${gd.id}`)"
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
        <span class="view-link">View &rarr;</span>
      </div>
    </div>
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
.mono { font-family: var(--font-mono); color: var(--text-secondary); }
.view-link { font-size: 12.5px; font-weight: 600; color: var(--accent-text); text-align: right; }
.chips-cell { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.chips-cell.variance--deficit { color: var(--warning-text); }
.chips-cell.variance--excess { color: var(--accent-text); }
.chips-cell.variance--balanced { color: var(--text-tertiary); }

@media (max-width: 860px) {
  .t-head { display: none; }
  .t-row { grid-template-columns: 1fr; height: auto; padding: 14px 20px; gap: 4px; }
}
</style>
