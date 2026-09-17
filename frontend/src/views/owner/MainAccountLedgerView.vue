<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/api/axios'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import { useToast } from '@/composables/useToast'

// Main Account ledger (2026-09-17) — GET /api/main-account/ledger/,
// IsOwner-gated server-side. Rows are the only ones that actually touch the
// club's real bank account: a player's deposit sweeping in (channel =
// TRANSFER_DVA) or a payout going out (type = PAYOUT) — gaming.selectors's
// MAIN_ACCOUNT_FILTER already excludes every chip transaction, so this is
// deliberately NOT a replacement for the Game-Day ledger (which still shows
// payouts as part of that night's own story, matching its game_balance
// total) — this is a second, focused view of real money movement across
// every game-day and Outstanding combined.
//
// "Successful only" by default (status === POSTED — Paystack's
// transfer.success webhook, the only place POSTED is ever set — not
// APPROVED, which is just Paystack synchronously *accepting* the transfer;
// completion is confirmed later and can still turn into TRANSFER_FAILED). A
// toggle reveals every status, each with its usual badge, matching every
// other ledger in the app.
const toast = useToast()

const players = ref([])
const rows = ref([])
const mainAccountBalance = ref(null)
const loading = ref(true)
const showAllStatuses = ref(false)

async function load() {
  loading.value = true
  try {
    const [playersRes, ledgerRes, dashboardRes] = await Promise.all([
      api.get('/players/'),
      api.get('/main-account/ledger/'),
      api.get('/dashboard/'),
    ])
    players.value = playersRes.data
    rows.value = ledgerRes.data
    mainAccountBalance.value = dashboardRes.data.main_account_balance
  } catch {
    toast.error('Could not load the Main Account ledger.')
  } finally {
    loading.value = false
  }
}

onMounted(load)

function playerName(playerId) {
  return players.value.find(p => p.id === playerId)?.display_name || ''
}
const playerTo = row => (row.player ? `/roster/${row.player}` : null)

const feed = computed(() => {
  const visible = showAllStatuses.value ? rows.value : rows.value.filter(r => r.status === 'POSTED')
  return visible.slice().reverse().map(row => ({ ...row, player_name: playerName(row.player) }))
})

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Main Account</h1>
      <p>Money that actually touches the club's bank account — player deposits sweeping in, payouts going out. No chip activity.</p>
    </div>

    <p v-if="loading" class="muted">Loading…</p>

    <template v-else>
      <div class="card balance-card">
        <div class="stat-label">Main Account balance</div>
        <div class="stat-value">{{ N(mainAccountBalance) }}</div>
      </div>

      <div class="card feed-card">
        <div class="feed-head">
          <div class="section-title">Activity</div>
          <label class="filter-toggle">
            <input v-model="showAllStatuses" type="checkbox" />
            Show all statuses
          </label>
        </div>
        <p v-if="!feed.length" class="muted">
          {{ showAllStatuses ? 'Nothing recorded yet.' : 'No successful transfers yet — try "Show all statuses".' }}
        </p>
        <LedgerTable v-else :rows="feed" show-player :player-to="playerTo" date-format="datetime" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; max-width: 620px; }
.muted { color: var(--text-secondary); font-size: 13px; }

.balance-card { padding: 16px 18px; margin-bottom: 16px; display: flex; flex-direction: column; gap: 6px; }
.stat-label { font-size: 11px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.stat-value { font-family: var(--font-mono); font-weight: 600; font-size: 22px; font-variant-numeric: tabular-nums; color: var(--text-primary); }

.feed-card { padding: 18px 20px; }
.feed-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; gap: 12px; flex-wrap: wrap; }
.section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); }
.filter-toggle { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--text-secondary); cursor: pointer; }
</style>
