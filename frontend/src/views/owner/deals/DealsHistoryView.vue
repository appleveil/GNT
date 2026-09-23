<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/axios'
import { useAuthStore } from '@/stores/auth'
import VoidEntryModal from '@/components/shared/VoidEntryModal.vue'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import { canVoidTransaction } from '@/utils/canVoid'
import { useToast } from '@/composables/useToast'

// "Deals" History (2026-09-23) — every real ledger effect a Deal has ever
// had: WRITE_OFF (Fixed), DEAL_TRANSFER_OUT/IN (Transfer), PROFIT_SPLIT_STAKE
// (a Profit Split arrangement's own house-covered buy-in portions). No
// dedicated "list deal transactions" endpoint exists (same accepted
// trade-off as PayoutsView.vue's own client-side filter over the full
// /transactions/ list) — fetches everything and filters to these 4 types.
//
// This is a money-movement feed only — it does NOT separately list a Profit
// Split arrangement's own create/end events (no money moves on either), the
// way the mobile app's local log does. See each player's own Stake and
// Profit Split screen for an arrangement's current config/status instead.
const DEAL_TYPES = ['WRITE_OFF', 'DEAL_TRANSFER_OUT', 'DEAL_TRANSFER_IN', 'PROFIT_SPLIT_STAKE']

const router = useRouter()
const auth = useAuthStore()
const toast = useToast()

const players = ref([])
const rows = ref([])
const loading = ref(true)
const voidTarget = ref(null)
const filterType = ref('ALL')

async function load() {
  loading.value = true
  try {
    const [playersRes, txRes] = await Promise.all([
      api.get('/players/'),
      api.get('/transactions/'),
    ])
    players.value = playersRes.data
    rows.value = txRes.data.filter(t => DEAL_TYPES.includes(t.type))
  } catch {
    toast.error('Could not load Deals history.')
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

const filtered = computed(() => {
  if (filterType.value === 'ALL') return rows.value
  if (filterType.value === 'TRANSFER') return rows.value.filter(r => r.type === 'DEAL_TRANSFER_OUT' || r.type === 'DEAL_TRANSFER_IN')
  return rows.value.filter(r => r.type === filterType.value)
})
const feed = computed(() =>
  filtered.value
    .slice()
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    .map(row => ({ ...row, player_name: playerName(row.player) })),
)
const playerTo = row => (row.player ? `/roster/${row.player}` : null)

const FILTERS = [
  { value: 'ALL', label: 'All' },
  { value: 'WRITE_OFF', label: 'Fixed' },
  { value: 'TRANSFER', label: 'Transfer' },
  { value: 'PROFIT_SPLIT_STAKE', label: 'Stake' },
]
</script>

<template>
  <div class="page">
    <button class="back-btn" type="button" @click="router.push('/deals')">&larr; Deals</button>

    <div class="page-header">
      <h1>Deals History</h1>
      <p>Every Fixed write-off, Transfer, and Profit Split stake ever recorded.</p>
    </div>

    <div class="filter-row">
      <button
        v-for="f in FILTERS" :key="f.value" type="button" class="filter-chip"
        :class="{ 'filter-chip--active': filterType === f.value }" @click="filterType = f.value"
      >{{ f.label }}</button>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!feed.length" class="muted">Nothing recorded yet.</p>

    <div v-else class="card feed-card">
      <LedgerTable :rows="feed" show-player :player-to="playerTo" date-format="datetime" voidable :can-void-fn="canVoid" @void="voidTarget = $event" />
    </div>

    <VoidEntryModal
      v-if="voidTarget" :transaction="voidTarget" :player-name="playerName(voidTarget.player)"
      :recorded-by-name="auth.user?.fullName" @close="voidTarget = null" @voided="onVoided"
    />
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.back-btn { border: none; background: none; font-size: 13.5px; font-weight: 600; color: var(--text-secondary); cursor: pointer; padding: 4px 0; margin-bottom: 16px; }
.back-btn:hover { color: var(--text-primary); }
.muted { color: var(--text-secondary); font-size: 13px; }

.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }

.filter-row { display: flex; gap: 8px; margin-bottom: 16px; }
.filter-chip {
  border: 1px solid var(--border-strong);
  border-radius: 20px;
  background: var(--surface);
  padding: 6px 14px;
  font-family: var(--font-sans);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
}
.filter-chip--active { border-color: var(--accent); background: var(--accent-bg); color: var(--accent-text); }

.feed-card { padding: 18px 20px; }
</style>
