<script setup>
import { ref, watch, onMounted } from 'vue'
import api from '@/api/axios'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import { useToast } from '@/composables/useToast'

// "View ledger" action (2026-09-24), reached from the Players page's ⋮
// menu — a large modal instead of a page nav. Mirrors RosterDetailView's
// "Any game-day's activity" picker+ledger, with one difference: the
// game-day picker here is scoped to GET /game-days/?player=<id> (only
// game-days this player was actually seated in — see
// GameDayViewSet.get_queryset), not every game-day club-wide.
const props = defineProps({
  player: { type: Object, required: true }, // { id, display_name }
})
const emit = defineEmits(['close'])
const toast = useToast()

const gameDays = ref([])
const gameDaysLoading = ref(true)
const selectedGameDayId = ref('')
const ledger = ref([])
const ledgerLoading = ref(false)

async function loadGameDays() {
  gameDaysLoading.value = true
  try {
    const { data } = await api.get('/game-days/', { params: { player: props.player.id } })
    gameDays.value = data
    if (data.length) selectedGameDayId.value = data[0].id
  } catch {
    toast.error('Could not load this player’s game-days.')
  } finally {
    gameDaysLoading.value = false
  }
}
onMounted(loadGameDays)

watch(selectedGameDayId, async id => {
  if (!id) { ledger.value = []; return }
  ledgerLoading.value = true
  try {
    const { data } = await api.get(`/game-days/${id}/players/${props.player.id}/ledger/`)
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
  <div class="overlay" @click.self="emit('close')">
    <div class="dialog card">
      <div class="head">
        <div class="eyebrow">{{ player.display_name }} &mdash; ledger</div>
        <button class="close-btn" type="button" @click="emit('close')">&times;</button>
      </div>

      <p v-if="gameDaysLoading" class="muted">Loading…</p>
      <p v-else-if="!gameDays.length" class="muted">{{ player.display_name }} hasn't played in any game-day yet.</p>

      <template v-else>
        <select v-model="selectedGameDayId" class="gd-select">
          <option v-for="gd in gameDays" :key="gd.id" :value="gd.id">
            Game-Day #{{ gd.number }} &middot; {{ formatDate(gd.started_at) }} &middot; {{ gd.status }}
          </option>
        </select>

        <div class="ledger-wrap">
          <p v-if="ledgerLoading" class="muted">Loading…</p>
          <p v-else-if="!ledger.length" class="muted">Nothing recorded for {{ player.display_name }} that game-day.</p>
          <LedgerTable v-else :rows="ledger" />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(20, 25, 32, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 24px;
}
.dialog { width: 760px; max-width: 100%; max-height: 88vh; overflow-y: auto; box-shadow: var(--shadow-md); padding: 24px; }
.head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 16px; }
.eyebrow { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.close-btn { border: none; background: none; font-size: 22px; line-height: 1; color: var(--text-tertiary); cursor: pointer; flex-shrink: 0; }
.muted { color: var(--text-secondary); font-size: 13px; }

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

.ledger-wrap { border-top: 1px solid var(--border); }
</style>
