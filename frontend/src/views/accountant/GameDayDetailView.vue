<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/axios'
import { useAuthStore } from '@/stores/auth'
import VoidEntryModal from '@/components/shared/VoidEntryModal.vue'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import { canVoidTransaction } from '@/utils/canVoid'
import { describeChipsVariance } from '@/utils/chipsVariance'
import { useToast } from '@/composables/useToast'

// Read-only game-day detail (Phase B, 2026-09-14) — close-preview while
// OPEN, frozen GameDaySummary while CLOSED, the club-wide /ledger/ feed
// (formerly shared with the Cashier's own GameDayLedgerView.vue, removed
// 2026-09-21 as redundant with the Cashier's main working screen — this
// back-office view is unaffected, it's the only place this data now
// surfaces at all), plus a seated-players list, since an Accountant is
// here to review, not to record or correct anything. Phase C (2026-09-14)
// adds one exception: a void
// trigger, shown only for OWNER (canVoidTransaction already returns true
// unconditionally for that role, including on a CLOSED game-day — this is
// the real, already-built mechanism behind PLAN.md's "post-close
// corrections/amendments," see PLAN.md's Phase C entry for why nothing more
// than void exists to build on).
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const toast = useToast()

const gameDayId = route.params.id

const gameDay = ref(null)
const players = ref([])
const ledger = ref([])
const stats = ref(null)
const loading = ref(true)
const voidTarget = ref(null)

const displayStats = computed(() => {
  if (gameDay.value?.status === 'CLOSED' && gameDay.value.summary) return gameDay.value.summary
  return stats.value
})
// Same "pending until close" treatment as Rake — depends on both rake_total
// and a chips_in_total that can still change while the night's open, so it's
// not meaningfully final until CLOSED either.
const chipsVariance = computed(() => (displayStats.value ? describeChipsVariance(displayStats.value.chips_variance) : null))
const chipsVarianceShortLabel = computed(() => {
  const v = Number(displayStats.value?.chips_variance)
  return v > 0 ? 'Deficit' : v < 0 ? 'Excess' : 'Balanced'
})

async function load() {
  loading.value = true
  try {
    const [gdRes, playersRes, ledgerRes] = await Promise.all([
      api.get(`/game-days/${gameDayId}/`),
      api.get(`/game-days/${gameDayId}/players/`),
      api.get(`/game-days/${gameDayId}/ledger/`),
    ])
    gameDay.value = gdRes.data
    players.value = playersRes.data
    ledger.value = ledgerRes.data.slice().reverse()
    if (gameDay.value.status === 'OPEN') {
      const { data } = await api.get(`/game-days/${gameDayId}/close-preview/`)
      stats.value = data
    }
  } catch {
    toast.error('Could not load this game-day.')
  } finally {
    loading.value = false
  }
}

onMounted(load)

function playerName(playerId) {
  if (!playerId) return ''
  return players.value.find(p => p.id === playerId)?.display_name || ''
}

const ledgerRows = computed(() => ledger.value.map(row => ({ ...row, player_name: playerName(row.player) })))
// Carries this game-day's id along so RosterDetailView.vue can land the
// Owner directly on this player's activity for THIS game-day, instead of a
// blank "select a game-day" picker — see PLAN.md's "Jumping from a
// Game-Day to a player" entry.
const playerTo = row => (row.player ? { path: `/roster/${row.player}`, query: { gameDay: gameDayId } } : null)

function formatTime(iso) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}
function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
}

function canVoid(row) {
  return canVoidTransaction(row, auth.user, gameDay.value?.status)
}
function onVoided() {
  voidTarget.value = null
  toast.success('Entry voided.')
  load()
}

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="page">
    <div class="header-row">
      <button class="back-btn" type="button" @click="router.push('/game-days')">&larr; Game Days</button>
      <div class="spacer" />
    </div>

    <p v-if="loading" class="muted">Loading…</p>

    <template v-else-if="gameDay">
      <div class="page-header">
        <h1>Game-Day #{{ gameDay.number }}</h1>
        <span class="badge" :class="gameDay.status === 'OPEN' ? 'badge--open' : 'badge--closed'">{{ gameDay.status }}</span>
      </div>
      <p class="date-line">{{ formatDate(gameDay.started_at) }} &middot; started {{ formatTime(gameDay.started_at) }}</p>

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

      <div class="grid-two">
        <div class="card ledger-card">
          <div class="section-title">Full ledger <span class="lbl--muted">running balance &middot; club-wide</span></div>
          <div class="ledger-feed">
            <LedgerTable :rows="ledgerRows" show-player :player-to="playerTo" voidable :can-void-fn="canVoid" @void="voidTarget = $event" />
          </div>
        </div>

        <div class="card players-card">
          <div class="section-title">Players seated</div>
          <p v-if="!players.length" class="muted">No players seated.</p>
          <RouterLink v-for="p in players" :key="p.id" :to="{ path: `/roster/${p.id}`, query: { gameDay: gameDayId } }" class="player-row">
            <div>
              <div class="player-name">{{ p.display_name }}</div>
              <div class="player-code">{{ p.account_code }}</div>
            </div>
            <span v-if="p.left_at" class="badge badge--voided">left</span>
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
.page { max-width: 1100px; }
.header-row { display: flex; align-items: center; margin-bottom: 16px; }
.back-btn { border: none; background: none; font-size: 13.5px; font-weight: 600; color: var(--text-secondary); cursor: pointer; padding: 4px 0; }
.back-btn:hover { color: var(--text-primary); }
.spacer { flex-grow: 1; }
.muted { color: var(--text-secondary); font-size: 13px; }

.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 2px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0; }
.date-line { font-size: 12.5px; color: var(--text-tertiary); margin: 0 0 20px; }

.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin-bottom: 20px; }
.stat-card { padding: 16px 18px; display: flex; flex-direction: column; gap: 6px; }
.stat-label { font-size: 11px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.stat-value { font-family: var(--font-mono); font-weight: 600; font-size: 19px; font-variant-numeric: tabular-nums; color: var(--text-primary); }
.stat-value.variance--deficit { color: var(--warning-text); }
.stat-value.variance--excess { color: var(--accent-text); }
.stat-value.variance--balanced { color: var(--text-tertiary); }
.stat-pending { font-size: 12px; font-weight: 600; color: var(--text-tertiary); }

.grid-two { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; align-items: start; }

.ledger-card, .players-card { padding: 18px 20px; }
.section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; }
.lbl--muted { font-weight: 500; text-transform: none; color: var(--text-tertiary); font-size: 11px; margin-left: 8px; }

.ledger-feed { border-top: 1px solid var(--border); }

.player-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  text-decoration: none;
  color: inherit;
}
.player-row:last-child { border-bottom: none; }
.player-row:hover .player-name { color: var(--accent-text); }
.player-name { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }
.player-code { font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); }

@media (max-width: 860px) {
  .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grid-two { grid-template-columns: 1fr; }
}
</style>
