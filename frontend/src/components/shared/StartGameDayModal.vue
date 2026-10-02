<script setup>
/**
 * src/components/shared/StartGameDayModal.vue
 *
 * "Start game-day" flow (2026-09-21) — Select game (Texas, Omaha) → Select
 * table (filtered by game) → confirm buy-in (pre-filled from the table's
 * default_buy_in, editable) → Owner/Floor-Manager PIN, same as every other
 * authorized action. Backend support (Game/Table models, read-only
 * /games/ + /tables/?game=<id> endpoints, open_game_day's game_id/table_id/
 * buy_in_amount) already existed — this was the missing frontend half; the
 * old "Open Game-Day" button skipped straight to the PIN modal with no game/
 * table selection at all. See PLAN.md's "Game/Table selection at start"
 * entry and gaming/services.open_game_day.
 *
 * "One table per game, for now" (per PLAN.md) means step 2 will usually
 * show exactly one table — it's still its own step, not skipped, since nothing
 * on the frontend should assume that stays true once Owner CRUD (parked) adds
 * more tables later.
 */
import { ref, onMounted } from 'vue'
import api from '@/api/axios'
import { useAuthorizerConfirm } from '@/composables/useAuthorizerConfirm'
import { usePlainConfirm } from '@/composables/usePlainConfirm'
import { useClubSettingsStore } from '@/stores/clubSettings'

const props = defineProps({ number: { type: Number, required: true } })
const emit = defineEmits(['close', 'started'])
const { confirm } = useAuthorizerConfirm()
const { plainConfirm } = usePlainConfirm()
const clubSettings = useClubSettingsStore()

const step = ref('game') // 'game' | 'table' | 'buyin'

const games = ref([])
const gamesLoading = ref(false)
const selectedGame = ref(null)

const tables = ref([])
const tablesLoading = ref(false)
const selectedTable = ref(null)

const buyIn = ref('')
const error = ref('')

async function loadGames() {
  gamesLoading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/games/')
    games.value = data
  } catch {
    error.value = 'Could not load games.'
  } finally {
    gamesLoading.value = false
  }
}
onMounted(loadGames)

async function pickGame(game) {
  selectedGame.value = game
  selectedTable.value = null
  step.value = 'table'
  tablesLoading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/tables/', { params: { game: game.id } })
    tables.value = data
  } catch {
    error.value = 'Could not load tables.'
  } finally {
    tablesLoading.value = false
  }
}

function pickTable(table) {
  selectedTable.value = table
  buyIn.value = table.default_buy_in
  step.value = 'buyin'
}

const N = n => `₦${Number(n).toLocaleString()}`

function onStartConfirm() {
  const opts = {
    title: `Open Game-Day #${props.number}`,
    subtitle: `${selectedGame.value.name} · ${selectedTable.value.name} · ${N(buyIn.value)} buy-in`,
    onSubmit: async payload => {
      const { data } = await api.post('/game-days/open/', {
        number: props.number,
        game_id: selectedGame.value.id,
        table_id: selectedTable.value.id,
        buy_in_amount: buyIn.value,
        ...payload,
      })
      emit('started', data)
    },
  }
  // ClubSettings.require_approval_open_game_day, Owner-editable (added
  // 2026-09-23) — off, and this is a plain confirm instead of the PIN
  // sheet. `=== false` (not just falsy) so a still-loading/failed fetch
  // (clubSettings.current is null) keeps the safer PIN default.
  if (clubSettings.current?.require_approval_open_game_day === false) plainConfirm(opts)
  else confirm(opts)
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="sheet">
      <div class="grip" />
      <div class="head">
        <div class="sheet-title">Start Game-Day #{{ number }}</div>
        <button class="close-btn" type="button" @click="emit('close')">&times;</button>
      </div>

      <!-- Step indicator -->
      <div class="steps">
        <div class="step-dot" :class="{ 'step-dot--active': step === 'game', 'step-dot--done': step !== 'game' }">1</div>
        <div class="step-line" />
        <div class="step-dot" :class="{ 'step-dot--active': step === 'table', 'step-dot--done': step === 'buyin' }">2</div>
        <div class="step-line" />
        <div class="step-dot" :class="{ 'step-dot--active': step === 'buyin' }">3</div>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>

      <!-- Step 1: game -->
      <template v-if="step === 'game'">
        <div class="lbl">Select game</div>
        <p v-if="gamesLoading" class="muted">Loading…</p>
        <div v-else class="option-list">
          <button
            v-for="g in games" :key="g.id" type="button" class="option-row"
            @click="pickGame(g)"
          >
            {{ g.name }}
            <span class="chevron">&rarr;</span>
          </button>
          <p v-if="!games.length" class="muted">No games configured yet.</p>
        </div>
      </template>

      <!-- Step 2: table -->
      <template v-else-if="step === 'table'">
        <button class="back-link" type="button" @click="step = 'game'">&larr; back to games</button>
        <div class="lbl">Select table &mdash; {{ selectedGame.name }}</div>
        <p v-if="tablesLoading" class="muted">Loading…</p>
        <div v-else class="option-list">
          <button
            v-for="t in tables" :key="t.id" type="button" class="option-row"
            @click="pickTable(t)"
          >
            <span>
              {{ t.name }}
              <span class="option-sub">default buy-in {{ N(t.default_buy_in) }}</span>
            </span>
            <span class="chevron">&rarr;</span>
          </button>
          <p v-if="!tables.length" class="muted">No tables configured for this game yet.</p>
        </div>
      </template>

      <!-- Step 3: buy-in -->
      <template v-else>
        <button class="back-link" type="button" @click="step = 'table'">&larr; back to tables</button>
        <div class="lbl">Buy-in &mdash; {{ selectedGame.name }} · {{ selectedTable.name }}</div>
        <p class="muted">
          Pre-filled from the table's default — every seated player's first buy-in tonight starts here
          unless recorded otherwise.
        </p>
        <label class="field">
          <span class="eyebrow">Buy-in amount</span>
          <input v-model.number="buyIn" type="number" min="0" step="1000" class="buyin-input" />
        </label>

        <div class="spacer" />
        <button class="btn btn--primary" type="button" :disabled="!buyIn" @click="onStartConfirm">
          Continue &mdash; {{ N(buyIn || 0) }}
        </button>
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
  align-items: flex-end;
  justify-content: center;
  z-index: 90;
}
.sheet {
  width: 100%;
  max-width: 480px;
  background: var(--surface);
  border-radius: 20px 20px 0 0;
  box-shadow: 0 -6px 28px rgba(20, 25, 32, 0.25);
  padding: 16px 24px 28px;
  display: flex;
  flex-direction: column;
  max-height: 90vh;
  overflow-y: auto;
}
.grip { width: 44px; height: 5px; border-radius: 3px; background: var(--border); align-self: center; margin-bottom: 18px; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.sheet-title { font-size: 17px; font-weight: 700; color: var(--text-primary); }
.close-btn { border: none; background: none; font-size: 22px; line-height: 1; color: var(--text-tertiary); cursor: pointer; flex-shrink: 0; }

.steps { display: flex; align-items: center; gap: 6px; margin: 16px 0 20px; }
.step-dot {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 1.5px solid var(--border-strong);
  background: var(--surface);
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}
.step-dot--active { border-color: var(--accent); background: var(--accent); color: #fff; }
.step-dot--done { border-color: var(--accent); background: var(--accent-bg); color: var(--accent-text); }
.step-line { flex: 1; height: 1px; background: var(--border-strong); }

.lbl {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  margin-bottom: 10px;
}
.muted { color: var(--text-secondary); font-size: 13px; padding: 4px 0; }

.option-list { display: flex; flex-direction: column; gap: 8px; }
.option-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: var(--radius-sm);
  padding: 14px 16px;
  font-family: var(--font-sans);
  font-size: 14.5px;
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
  min-height: var(--control-height-primary);
}
.option-row:hover { border-color: var(--accent); background: var(--accent-bg); }
.option-sub { display: block; font-size: 11.5px; font-weight: 500; color: var(--text-tertiary); margin-top: 2px; }
.chevron { color: var(--text-tertiary); flex-shrink: 0; }

.back-link {
  border: none;
  background: none;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  cursor: pointer;
  margin-bottom: 14px;
  align-self: flex-start;
  padding: 0;
}

.field { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.eyebrow {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
.buyin-input {
  height: var(--control-height-primary);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 16px;
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  background: var(--surface);
}
.buyin-input:focus { outline: none; border-color: var(--accent); }

.spacer { flex-grow: 1; min-height: 16px; }
.form-error {
  font-size: 13px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  margin-bottom: 12px;
}
</style>
