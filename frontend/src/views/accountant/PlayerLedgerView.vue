<script setup>
import { ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/axios'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import { useToast } from '@/composables/useToast'

// "View ledger" action, reached from the Players page's ⋮ menu — a full
// page (2026-09-25; started as PlayerLedgerModal.vue, converted per direct
// request) rather than a pop-up. Mirrors RosterDetailView's own "Any
// game-day's activity" picker+ledger, with one difference: the game-day
// picker here is scoped to GET /game-days/?player=<id> (only game-days
// this player was actually seated in — see GameDayViewSet.get_queryset),
// not every game-day club-wide.
const route = useRoute()
const router = useRouter()
const toast = useToast()

const player = ref(null)
const playerLoading = ref(true)

const gameDays = ref([])
const gameDaysLoading = ref(true)
const selectedGameDayId = ref('')
const ledger = ref([])
const ledgerLoading = ref(false)

async function loadPlayer() {
  playerLoading.value = true
  try {
    const { data } = await api.get(`/players/${route.params.id}/`)
    player.value = data
  } catch {
    toast.error('Could not load this player.')
  } finally {
    playerLoading.value = false
  }
}

async function loadGameDays() {
  gameDaysLoading.value = true
  try {
    const { data } = await api.get('/game-days/', { params: { player: route.params.id } })
    gameDays.value = data
    if (data.length) selectedGameDayId.value = data[0].id
  } catch {
    toast.error('Could not load this player’s game-days.')
  } finally {
    gameDaysLoading.value = false
  }
}

onMounted(() => {
  loadPlayer()
  loadGameDays()
})

watch(selectedGameDayId, async id => {
  if (!id) { ledger.value = []; return }
  ledgerLoading.value = true
  try {
    const { data } = await api.get(`/game-days/${id}/players/${route.params.id}/ledger/`)
    ledger.value = data.slice().reverse()
  } catch {
    toast.error('Could not load that game-day for this player.')
  } finally {
    ledgerLoading.value = false
  }
}, { immediate: true })

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
</script>

<template>
  <div class="page">
    <button class="back-btn" type="button" @click="router.push(`/roster/${route.params.id}`)">&larr; {{ player?.display_name || 'Player' }}</button>

    <div class="page-header">
      <h1>Ledger</h1>
      <p v-if="player">{{ player.display_name }} &middot; {{ player.account_code }}</p>
    </div>

    <p v-if="gameDaysLoading" class="muted">Loading…</p>
    <p v-else-if="!gameDays.length" class="muted">{{ player?.display_name || 'This player' }} hasn't played in any game-day yet.</p>

    <template v-else>
      <select v-model="selectedGameDayId" class="gd-select">
        <option v-for="gd in gameDays" :key="gd.id" :value="gd.id">
          Game-Day #{{ gd.number }} &middot; {{ formatDate(gd.started_at) }} &middot; {{ gd.status }}
        </option>
      </select>

      <div class="card ledger-card">
        <p v-if="ledgerLoading" class="muted">Loading…</p>
        <p v-else-if="!ledger.length" class="muted">Nothing recorded for {{ player?.display_name }} that game-day.</p>
        <LedgerTable v-else :rows="ledger" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 800px; }
.back-btn { border: none; background: none; font-size: 13.5px; font-weight: 600; color: var(--text-secondary); cursor: pointer; padding: 4px 0; margin-bottom: 16px; }
.back-btn:hover { color: var(--text-primary); }
.muted { color: var(--text-secondary); font-size: 13px; }

.page-header { margin-bottom: 20px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }

.gd-select {
  width: 100%;
  height: var(--control-row-min);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 12px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-primary);
  background: var(--surface);
  margin-bottom: 16px;
}
.gd-select:focus { outline: none; border-color: var(--accent); }

.ledger-card { padding: 18px 20px; }
</style>
