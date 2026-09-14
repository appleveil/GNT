<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useGameDayStore } from '@/stores/gameDay'
import { useAuthorizerConfirm } from '@/composables/useAuthorizerConfirm'
import api from '@/api/axios'

const auth = useAuthStore()
const gameDay = useGameDayStore()
const { confirm } = useAuthorizerConfirm()

const opening = ref(false)
const openError = ref('')

const closePreview = ref(null) // null = confirm dialog closed
const closing = ref(false)
const closeError = ref('')

async function nextGameDayNumber() {
  const { data } = await api.get('/game-days/')
  return (data[0]?.number || 0) + 1
}

async function onOpenGameDay() {
  openError.value = ''
  opening.value = true
  let number
  try {
    number = await nextGameDayNumber()
  } catch {
    openError.value = 'Could not determine the next game-day number.'
    opening.value = false
    return
  }
  opening.value = false

  confirm({
    title: `Open Game-Day #${number}`,
    subtitle: 'Will start now',
    onSubmit: async payload => {
      const { data } = await api.post('/game-days/open/', { number, ...payload })
      gameDay.current = data
    },
  })
}

async function onOpenCloseConfirm() {
  closeError.value = ''
  try {
    const { data } = await api.get(`/game-days/${gameDay.current.id}/close-preview/`)
    closePreview.value = data
  } catch {
    closeError.value = 'Could not load game-day totals.'
  }
}

async function onConfirmClose() {
  closing.value = true
  closeError.value = ''
  try {
    await api.post(`/game-days/${gameDay.current.id}/close/`, {})
    closePreview.value = null
    gameDay.current = null
  } catch (err) {
    closeError.value = err.response?.data?.detail || 'Could not close the game-day.'
  } finally {
    closing.value = false
  }
}

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div>
    <!-- No game-day open -->
    <div v-if="!gameDay.isOpen" class="card empty-state">
      <div class="eyebrow">No Game-Day Open</div>
      <p class="muted">Open a game-day to start seating players and recording activity.</p>
      <p v-if="openError" class="form-error">{{ openError }}</p>
      <button class="btn btn--primary" type="button" :disabled="opening" @click="onOpenGameDay">
        {{ opening ? 'Loading…' : 'Open Game-Day' }}
      </button>
    </div>

    <!-- Game-day open -->
    <div v-else class="card active">
      <div class="eyebrow">Active — Game-Day #{{ gameDay.current.number }}</div>
      <p class="muted">
        Signed in as <strong>{{ auth.user?.fullName }}</strong> ({{ auth.user?.role }}).
        The full working screen — player picker, entry grid, live ledger — isn't built yet;
        this confirms open/close work end to end.
      </p>
      <button class="btn btn--secondary" type="button" @click="onOpenCloseConfirm">Close Game-Day</button>
    </div>

    <!-- Close confirmation -->
    <div v-if="closePreview" class="overlay">
      <div class="dialog card">
        <div class="eyebrow">Close Game-Day #{{ gameDay.current.number }}?</div>
        <p class="muted">This locks entries — only the Owner can amend after closing.</p>

        <div class="stats">
          <div class="stat-row"><span>Players seated</span><span class="money">{{ closePreview.num_players_seated }}</span></div>
          <div class="stat-row"><span>Chips out</span><span class="money">{{ N(closePreview.chips_out_total) }}</span></div>
          <div class="stat-row"><span>Chips returned</span><span class="money">{{ N(closePreview.chips_in_total) }}</span></div>
          <div class="stat-row"><span>Payments received</span><span class="money">{{ N(closePreview.total_payments) }}</span></div>
          <div class="stat-row"><span>Rake / Tips</span><span class="money">{{ N(closePreview.rake_total) }} / {{ N(closePreview.tips_total) }}</span></div>
          <div class="stat-row">
            <span>Unreturned chips tonight <small>(out − in − rake − tips)</small></span>
            <span class="money warn">{{ N(closePreview.chips_variance) }}</span>
          </div>
          <div class="stat-row">
            <span>Outstanding chips <small>(club-wide, after this close)</small></span>
            <span class="money warn">{{ N(closePreview.outstanding_chips_after_close) }}</span>
          </div>
          <div class="stat-row stat-row--total"><span>Game balance</span><span class="money">{{ N(closePreview.game_balance) }}</span></div>
        </div>

        <p v-if="closeError" class="form-error">{{ closeError }}</p>

        <div class="actions">
          <button class="btn btn--secondary" type="button" @click="closePreview = null">Cancel</button>
          <button class="btn btn--primary" type="button" :disabled="closing" @click="onConfirmClose">
            {{ closing ? 'Closing…' : 'Close Game-Day' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card { padding: 24px; }
.muted { color: var(--text-secondary); font-size: 13px; line-height: 1.6; margin: 8px 0 16px; }
.empty-state { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.active { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.form-error {
  font-size: 13px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  margin-bottom: 8px;
}

.overlay {
  position: fixed;
  inset: 0;
  background: rgba(20, 25, 32, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.dialog { width: 480px; max-width: 92vw; box-shadow: var(--shadow-md); }
.stats { margin-top: 12px; }
.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13.5px;
  color: var(--text-secondary);
}
.stat-row small { font-size: 10.5px; color: var(--text-tertiary); }
.stat-row--total { border-bottom: none; font-weight: 700; color: var(--text-primary); }
.money { font-family: var(--font-mono); font-weight: 700; color: var(--text-primary); }
.money.warn { color: var(--warning-text); }
.actions { display: flex; gap: 14px; margin-top: 16px; }
.actions .btn { flex: 1; }
</style>
