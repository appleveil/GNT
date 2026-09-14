<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/axios'
import { useGameDayStore } from '@/stores/gameDay'

const router = useRouter()
const gameDay = useGameDayStore()

const players = ref([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    if (!gameDay.current) await gameDay.fetchCurrent()
    if (gameDay.current) {
      const { data } = await api.get(`/game-days/${gameDay.current.id}/players/`)
      players.value = data
    } else {
      players.value = []
    }
  } catch {
    error.value = 'Could not load players.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="card players">
    <div class="header-row">
      <div>
        <div class="eyebrow">Players</div>
        <p v-if="gameDay.current" class="scope-note">
          For game-day #{{ gameDay.current.number }} only
        </p>
      </div>
      <button class="btn btn--primary" type="button" @click="router.push('/players/new')">
        + Add Player
      </button>
    </div>

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="error" class="muted">{{ error }}</p>
    <div v-else-if="!gameDay.current" class="empty-state">
      No game-day is open. Open one to start adding players.
    </div>
    <p v-else-if="!players.length" class="muted">No players seated yet tonight.</p>
    <ul v-else class="list">
      <li v-for="p in players" :key="p.id" class="row" @click="router.push(`/players/${p.id}`)">
        <span>{{ p.account_code }} — {{ p.display_name }}</span>
        <span class="money">₦{{ Number(p.balance).toLocaleString() }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.players { padding: 24px; }
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}
.scope-note { font-size: 12.5px; color: var(--text-tertiary); margin-top: 2px; }
.muted { color: var(--text-secondary); font-size: 13px; margin-top: 8px; }
.empty-state {
  color: var(--text-secondary);
  font-size: 13px;
  padding: 24px;
  text-align: center;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
  margin-top: 12px;
}
.list { list-style: none; margin-top: 12px; display: flex; flex-direction: column; }
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: var(--control-row-min);
  padding: 8px 4px;
  border-bottom: 1px solid var(--border);
  font-size: 14px;
  cursor: pointer;
}
.row:hover { background: var(--bg); }
</style>
