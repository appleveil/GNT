<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/axios'
import { useToast } from '@/composables/useToast'

// Player roster (Phase B, 2026-09-14) — GET /api/players/, IsAuthenticated.
// PlayerSerializer's `balance` is the unmasked lifetime figure (Cashier's own
// player list had a negative-balance masking rule that doesn't apply to
// Accountant/Owner — see accounts/serializers.py's get_balance).
const router = useRouter()
const toast = useToast()

const players = ref([])
const loading = ref(true)
const search = ref('')

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/players/')
    players.value = data
  } catch {
    toast.error('Could not load the player roster.')
  } finally {
    loading.value = false
  }
}

onMounted(load)

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
      <h1>Players</h1>
      <p>Full club roster — lifetime balance across every game-day and outstanding entry.</p>
    </div>

    <input v-model="search" type="text" placeholder="Search by name or account code…" class="search-input" />

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!filtered.length" class="muted">No players match.</p>

    <div v-else class="table">
      <div class="t-head">
        <span>Code</span><span>Name</span><span>Balance</span><span>Chips limit</span><span>Chips used today</span><span></span>
      </div>
      <div
        v-for="p in filtered" :key="p.id" class="t-row"
        @click="router.push(`/roster/${p.id}`)"
      >
        <span class="mono">{{ p.account_code }}</span>
        <span>{{ p.display_name }}<span v-if="!p.is_active" class="badge badge--closed inactive-badge">inactive</span></span>
        <span class="money" :class="p.balance > 0 ? 'money--pos' : p.balance < 0 ? 'money--neg' : ''">{{ N(p.balance) }}</span>
        <span class="money">{{ N(p.chips_limit) }}</span>
        <span class="money">{{ N(p.chips_used_today) }}</span>
        <span class="view-link">View &rarr;</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.page-header { margin-bottom: 20px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }
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
  grid-template-columns: 110px 1.4fr 1fr 1fr 1fr 70px;
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
.money--pos { color: var(--success-text); }
.money--neg { color: var(--danger-text); }
.inactive-badge { margin-left: 8px; }

@media (max-width: 860px) {
  .t-head { display: none; }
  .t-row { grid-template-columns: 1fr; height: auto; padding: 14px 20px; gap: 4px; }
}
</style>
