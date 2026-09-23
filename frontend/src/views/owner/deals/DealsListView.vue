<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/axios'
import { useToast } from '@/composables/useToast'

// "Deals" — web version (2026-09-23). Same player-picker -> deal-type-
// picker -> form flow as the mobile app's DealsHomeScreen.tsx, but every
// write here calls the real backend directly (see router/index.js's own
// comment on why the mobile app couldn't do that yet and this can).
//
// GET /players/ already returns each player's live `balance` (PlayerSerializer),
// same as RosterListView.vue. The "active" badge comes from the new
// GET /deals/profit-split/active/ (2026-09-23) — one bulk call instead of an
// N+1 per-player status check.
const router = useRouter()
const toast = useToast()

const players = ref([])
const activeArrangements = ref([]) // [{ id, player, ... }] — every currently-active arrangement, club-wide
const loading = ref(true)
const search = ref('')

async function load() {
  loading.value = true
  try {
    const [playersRes, arrangementsRes] = await Promise.all([
      api.get('/players/'),
      api.get('/deals/profit-split/active/'),
    ])
    players.value = playersRes.data
    activeArrangements.value = arrangementsRes.data
  } catch {
    toast.error('Could not load players.')
  } finally {
    loading.value = false
  }
}

onMounted(load)

const activePlayerIds = computed(() => new Set(activeArrangements.value.map(a => a.player)))

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return players.value
  return players.value.filter(
    p => p.account_code.toLowerCase().includes(q) || p.display_name.toLowerCase().includes(q),
  )
})

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1>Deals</h1>
        <p>Fixed write-offs, player-to-player Transfers, and Stake/Profit Split arrangements — Owner only.</p>
      </div>
      <RouterLink to="/deals/history" class="link-btn">History &rarr;</RouterLink>
    </div>

    <input v-model="search" type="text" placeholder="Search by name or account code…" class="search-input" />

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!filtered.length" class="muted">No players match.</p>

    <div v-else class="table">
      <div class="t-head">
        <span>Code</span><span>Name</span><span>Balance</span><span></span>
      </div>
      <div
        v-for="p in filtered" :key="p.id" class="t-row"
        @click="router.push(`/deals/${p.id}`)"
      >
        <span class="mono">{{ p.account_code }}</span>
        <span>
          {{ p.display_name }}
          <span v-if="activePlayerIds.has(p.id)" class="active-tag">Stake/Profit split active</span>
        </span>
        <span class="money" :class="p.balance > 0 ? 'money--pos' : p.balance < 0 ? 'money--neg' : ''">{{ N(p.balance) }}</span>
        <span class="view-link">View &rarr;</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; max-width: 520px; }
.link-btn { font-size: 13px; font-weight: 700; color: var(--accent-text); text-decoration: none; white-space: nowrap; padding-top: 2px; }
.link-btn:hover { text-decoration: underline; }
.muted { color: var(--text-secondary); font-size: 13px; }

.search-input {
  width: 100%;
  max-width: 360px;
  height: var(--control-row-min);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 14px;
  font-family: var(--font-sans);
  font-size: 13.5px;
  color: var(--text-primary);
  background: var(--surface);
  margin-bottom: 16px;
}
.search-input:focus { outline: none; border-color: var(--accent); }

.table { border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; background: var(--surface); }
.t-head, .t-row {
  display: grid;
  grid-template-columns: 110px 1.6fr 1fr 70px;
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
.active-tag { display: inline-block; margin-left: 8px; font-size: 11px; font-weight: 600; color: var(--accent-text); }
.money--pos { color: var(--success-text); }
.money--neg { color: var(--danger-text); }

@media (max-width: 860px) {
  .t-head { display: none; }
  .t-row { grid-template-columns: 1fr; height: auto; padding: 14px 20px; gap: 4px; }
}
</style>
