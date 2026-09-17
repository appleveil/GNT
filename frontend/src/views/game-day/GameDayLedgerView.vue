<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/axios'
import { useAuthStore } from '@/stores/auth'
import VoidEntryModal from '@/components/shared/VoidEntryModal.vue'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import { canVoidTransaction } from '@/utils/canVoid'
import { useToast } from '@/composables/useToast'

// The club-wide Game-Day Ledger (per CONCEPT.md's "Game-day ledger" worked
// example) — running_balance here is a single cumulative total across every
// player's interleaved transactions, NOT any one player's own balance. That's
// a different endpoint/view from the Active Game-Day working screen's live
// "today's activity" feed (which is per-player-scoped, see
// gaming.selectors.game_day_activity_feed) — see HiFiGameDayLedger.dc.html's
// own "running balance · club-wide" label.
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const toast = useToast()

const gameDayId = route.params.id

const gameDay = ref(null) // GameDay detail: number, status, started_at, summary
const players = ref([]) // seated players — for player-name lookup only
const ledger = ref([])
const stats = ref(null) // close-preview data — only fetched while OPEN
const loading = ref(true)
const error = ref('')
const voidTarget = ref(null)

// While OPEN: live figures from the (non-mutating) close-preview endpoint,
// except Rake — deliberately shown as "pending" until the rake-box is
// actually counted at close, per HiFiGameDayLedger.dc.html's own note, even
// though a live rake_total technically exists the moment one's recorded.
// While CLOSED: the real frozen GameDaySummary.
const displayStats = computed(() => {
  if (gameDay.value?.status === 'CLOSED' && gameDay.value.summary) return gameDay.value.summary
  return stats.value
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [gdRes, playersRes, ledgerRes] = await Promise.all([
      api.get(`/game-days/${gameDayId}/`),
      api.get(`/game-days/${gameDayId}/players/`),
      api.get(`/game-days/${gameDayId}/ledger/`),
    ])
    gameDay.value = gdRes.data
    players.value = playersRes.data
    ledger.value = ledgerRes.data.slice().reverse() // most recent first
    if (gameDay.value.status === 'OPEN') {
      const { data } = await api.get(`/game-days/${gameDayId}/close-preview/`)
      stats.value = data
    }
  } catch {
    error.value = 'Could not load this game-day.'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function playerName(playerId) {
  if (!playerId) return ''
  return players.value.find(p => p.id === playerId)?.display_name || ''
}

// LedgerTable needs player_name pre-resolved on each row — no roster route
// exists on the Cashier's side, so no playerTo prop (name renders as plain text).
const ledgerRows = computed(() => ledger.value.map(row => ({ ...row, player_name: playerName(row.player) })))

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
  <div>
    <div class="header-row">
      <button class="back-btn" type="button" @click="router.push('/game-day')">&larr;</button>
      <div v-if="gameDay" class="header-title">Game-Day #{{ gameDay.number }}</div>
      <div class="spacer" />
      <span
        v-if="gameDay" class="badge" :class="gameDay.status === 'OPEN' ? 'badge--open' : 'badge--closed'"
      >{{ gameDay.status }}</span>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="error" class="muted">{{ error }}</p>

    <div v-else class="card ledger-card">
      <div class="date-line">{{ formatDate(gameDay.started_at) }} &middot; started {{ formatTime(gameDay.started_at) }}</div>

      <div v-if="displayStats" class="stats-row">
        <div class="stat">
          <div class="stat-label">Chips out</div>
          <div class="stat-value">{{ N(displayStats.chips_out_total) }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">Payments</div>
          <div class="stat-value">{{ N(displayStats.total_payments) }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">Rake</div>
          <div v-if="gameDay.status === 'OPEN'" class="stat-pending">pending &mdash; at close</div>
          <div v-else class="stat-value">{{ N(displayStats.rake_total) }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">Balance <span class="stat-label-note">{{ gameDay.status === 'OPEN' ? '(live)' : '' }}</span></div>
          <div class="stat-value">{{ N(displayStats.game_balance) }}</div>
        </div>
      </div>
      <p v-if="gameDay.status === 'OPEN'" class="stats-note">
        This game-day is still OPEN — rake isn't known until the rake-box is counted at close, and the balance shown is live/provisional.
      </p>

      <div class="ledger-head">
        <div class="lbl">Full ledger</div>
        <div class="lbl lbl--muted">running balance &middot; club-wide</div>
      </div>

      <div class="ledger-feed">
        <LedgerTable :rows="ledgerRows" show-player voidable :can-void-fn="canVoid" @void="voidTarget = $event" />
        <p class="scroll-note">&middot; scrolls for full day &middot;</p>
        <p class="scroll-note scroll-note--italic">Rake and Tips aren't rows in this ledger by design — see the totals above.</p>
      </div>
    </div>

    <VoidEntryModal
      v-if="voidTarget" :transaction="voidTarget" :player-name="playerName(voidTarget.player)"
      :recorded-by-name="auth.user?.fullName" @close="voidTarget = null" @voided="onVoided"
    />
  </div>
</template>

<style scoped>
.header-row { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }
.back-btn {
  border: none;
  background: none;
  font-size: 18px;
  cursor: pointer;
  color: var(--text-primary);
  padding: 4px;
}
.header-title { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.spacer { flex-grow: 1; }
.muted { color: var(--text-secondary); font-size: 13px; }

.ledger-card { padding: 20px 24px 8px; }
.date-line { font-size: 12px; color: var(--text-tertiary); margin-bottom: 12px; }

.stats-row { display: flex; gap: 8px; margin-bottom: 6px; }
.stat {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  text-align: center;
}
.stat-label { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 2px; }
.stat-label-note { text-transform: none; font-weight: 400; }
.stat-value { font-family: var(--font-mono); font-size: 13px; font-weight: 700; color: var(--text-primary); }
.stat-pending { font-size: 11.5px; font-weight: 600; color: var(--text-tertiary); }
.stats-note { font-size: 11px; color: var(--text-tertiary); margin: 4px 0 12px; }

.ledger-head { display: flex; align-items: baseline; justify-content: space-between; margin: 14px 0 4px; }
.lbl { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-primary); }
.lbl--muted { font-weight: 500; color: var(--text-tertiary); }

.ledger-feed { border-top: 1px solid var(--border); }

.scroll-note { text-align: center; font-size: 11px; color: var(--text-tertiary); padding: 10px 0 4px; }
.scroll-note--italic { font-style: italic; padding-top: 0; padding-bottom: 12px; }
</style>
