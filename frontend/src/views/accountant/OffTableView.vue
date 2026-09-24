<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import api from '@/api/axios'
import VoidEntryModal from '@/components/shared/VoidEntryModal.vue'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import { canVoidTransaction } from '@/utils/canVoid'
import { useToast } from '@/composables/useToast'

// "Off-table" (renamed from "Outstanding" 2026-09-26) — activity recorded
// outside any game-day: deals, write-offs, direct payments. Lived inline
// on DashboardView.vue from 2026-09-23 until this move gave it a real page
// of its own under the renamed "Ledgers" section (was "Game Days"), a
// sibling to /ledgers/game-days via LedgersLayout.vue. Content/logic
// carried over as-is; only the player-name link destination changed, to
// /roster/:id/ledger — RosterDetailView.vue (the old /roster/:id) was
// removed the same day.
const auth = useAuthStore()
const toast = useToast()

const players = ref([])
const rows = ref([])
const loading = ref(true)
const voidTarget = ref(null)

async function load() {
  loading.value = true
  try {
    const [playersRes, ledgerRes] = await Promise.all([
      api.get('/players/'),
      api.get('/outstanding/'),
    ])
    players.value = playersRes.data
    rows.value = ledgerRes.data
  } catch {
    toast.error('Could not load the off-table ledger.')
  } finally {
    loading.value = false
  }
}

onMounted(load)

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
// running_balance on their chronologically LAST row (rows is ascending by
// created_at, as the API returns it), sorted biggest-absolute-balance
// first so the players who owe the most (or are owed the most) surface top.
const byPlayer = computed(() => {
  const latest = new Map() // player id -> last row seen, in ascending order
  for (const row of rows.value) {
    if (row.player) latest.set(row.player, row)
  }
  return Array.from(latest.values())
    .map(row => ({ playerId: row.player, name: playerName(row.player), balance: Number(row.running_balance) }))
    .sort((a, b) => Math.abs(b.balance) - Math.abs(a.balance))
})

const feed = computed(() => rows.value.slice().reverse().map(row => ({ ...row, player_name: playerName(row.player) })))
const playerTo = row => (row.player ? `/roster/${row.player}/ledger` : null)

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="off-table">
    <p class="intro">Activity recorded outside any game-day — deals, write-offs, direct payments — with each player's own running balance.</p>

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!rows.length" class="muted">No between-game-day activity recorded.</p>

    <div v-else class="grid-two">
      <div class="card feed-card">
        <div class="section-title">Full activity</div>
        <div class="feed">
          <LedgerTable :rows="feed" show-player :player-to="playerTo" date-format="datetime" voidable :can-void-fn="canVoid" @void="voidTarget = $event" />
        </div>
      </div>

      <div class="card summary-card">
        <div class="section-title">By player</div>
        <RouterLink v-for="p in byPlayer" :key="p.playerId" :to="`/roster/${p.playerId}/ledger`" class="summary-row">
          <span class="summary-name">{{ p.name }}</span>
          <span class="money" :class="p.balance > 0 ? 'money--pos' : p.balance < 0 ? 'money--neg' : ''">{{ N(p.balance) }}</span>
        </RouterLink>
      </div>
    </div>

    <VoidEntryModal
      v-if="voidTarget" :transaction="voidTarget" :player-name="playerName(voidTarget.player)"
      :recorded-by-name="auth.user?.fullName" @close="voidTarget = null" @voided="onVoided"
    />
  </div>
</template>

<style scoped>
.muted { color: var(--text-secondary); font-size: 13px; }
.intro { font-size: 13px; color: var(--text-secondary); margin: 0 0 16px; max-width: 620px; }

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

@media (max-width: 860px) {
  .grid-two { grid-template-columns: 1fr; }
}
</style>
