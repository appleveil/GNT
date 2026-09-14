<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/axios'
import { useGameDayStore } from '@/stores/gameDay'
import BankAccountFields from '@/components/shared/BankAccountFields.vue'
import { useToast } from '@/composables/useToast'

const router = useRouter()
const gameDay = useGameDayStore()
const toast = useToast()

const mode = ref('new') // 'new' | 'existing'
const submitting = ref(false)
const error = ref('')

// New player
const accountCode = ref('')
const displayName = ref('')
const bank = ref({ bank_name: '', bank_code: '', account_number: '', account_name: '' })

// Existing player search
const allPlayers = ref([])
const search = ref('')
const selectedPlayerId = ref(null)
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return allPlayers.value
  return allPlayers.value.filter(
    p => p.account_code.toLowerCase().includes(q) || p.display_name.toLowerCase().includes(q),
  )
})

onMounted(async () => {
  if (!gameDay.current) await gameDay.fetchCurrent()
  try {
    // The full club roster — deliberately NOT the game-day-scoped endpoint,
    // since the point here is finding someone not yet seated tonight.
    const { data } = await api.get('/players/')
    allPlayers.value = data
  } catch {
    toast.error('Could not load the player roster — the search below may be incomplete.')
  }
})

async function onSubmit() {
  if (!gameDay.current) return
  error.value = ''
  submitting.value = true
  try {
    let seated
    if (mode.value === 'new') {
      const { data } = await api.post(`/game-days/${gameDay.current.id}/players/`, {
        account_code: accountCode.value,
        display_name: displayName.value,
      })
      seated = data
      if (bank.value.account_number.length === 10 && bank.value.bank_code) {
        await api.post(`/players/${seated.id}/bank-accounts/`, {
          bank_name: bank.value.bank_name,
          bank_code: bank.value.bank_code,
          account_number: bank.value.account_number,
          // Prefer the Paystack-resolved name; fall back to the typed player
          // name if resolution didn't complete (e.g. Paystack unreachable).
          account_name: bank.value.account_name || displayName.value,
          is_default: true,
        })
      }
    } else {
      if (!selectedPlayerId.value) {
        error.value = 'Select a player.'
        return
      }
      const { data } = await api.post(`/game-days/${gameDay.current.id}/players/`, {
        player_id: selectedPlayerId.value,
      })
      seated = data
    }
    router.push('/players')
  } catch (err) {
    error.value = Object.values(err.response?.data || {})[0]?.[0]
      || err.response?.data?.detail
      || 'Could not add player.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="card form-card">
    <div class="eyebrow">Add Player — Game-Day #{{ gameDay.current?.number ?? '—' }}</div>

    <div v-if="!gameDay.current" class="empty-state">
      No game-day is open. Open one before adding players.
    </div>

    <template v-else>
      <div class="tabs">
        <button
          type="button" class="tab" :class="{ 'tab--active': mode === 'new' }"
          @click="mode = 'new'"
        >New player</button>
        <button
          type="button" class="tab" :class="{ 'tab--active': mode === 'existing' }"
          @click="mode = 'existing'"
        >Existing player</button>
      </div>

      <form class="form" @submit.prevent="onSubmit">
        <template v-if="mode === 'new'">
          <label class="field">
            <span class="eyebrow">Account code</span>
            <input v-model="accountCode" type="text" placeholder="e.g. WWI 15" required />
          </label>
          <label class="field">
            <span class="eyebrow">Name</span>
            <input v-model="displayName" type="text" required />
          </label>
          <p class="section-note">Bank account (optional — for future winnings)</p>
          <BankAccountFields v-model="bank" />
          <p class="dva-note">
            Gaming Account / Dedicated Virtual Account isn't available yet — Paystack's
            Dedicated NUBAN approval is still pending. The player can still be added and issued chips.
          </p>
        </template>

        <template v-else>
          <input v-model="search" type="text" placeholder="Search by name or account code…" />
          <ul class="search-list">
            <li
              v-for="p in filtered" :key="p.id" class="search-row"
              :class="{ 'search-row--selected': selectedPlayerId === p.id }"
              @click="selectedPlayerId = p.id"
            >
              {{ p.account_code }} — {{ p.display_name }}
            </li>
            <li v-if="!filtered.length" class="muted">No matches.</li>
          </ul>
        </template>

        <p v-if="error" class="form-error">{{ error }}</p>

        <button class="btn btn--primary" type="submit" :disabled="submitting">
          {{ submitting ? 'Adding…' : 'Add to tonight' }}
        </button>
      </form>
    </template>
  </div>
</template>

<style scoped>
.form-card { padding: 24px; max-width: 480px; }
.empty-state {
  color: var(--text-secondary);
  font-size: 13px;
  padding: 24px;
  text-align: center;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
  margin-top: 12px;
}
.tabs { display: flex; gap: 8px; margin: 16px 0; }
.tab {
  flex: 1;
  height: 44px;
  border: 1px solid var(--border-strong);
  background: var(--surface);
  border-radius: var(--radius-sm);
  font-family: var(--font-sans);
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
}
.tab--active { background: var(--accent-bg); color: var(--accent-text); border-color: var(--accent); }
.form { display: flex; flex-direction: column; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.section-note {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 8px;
  border-top: 1px solid var(--border);
  padding-top: 12px;
}
.dva-note {
  font-size: 12px;
  color: var(--warning-text);
  background: var(--warning-bg);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
}
.search-list { list-style: none; max-height: 260px; overflow-y: auto; }
.search-row {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  font-size: 14px;
}
.search-row:hover { background: var(--bg); }
.search-row--selected { background: var(--accent-bg); color: var(--accent-text); font-weight: 600; }
.muted { color: var(--text-secondary); font-size: 13px; padding: 12px; }
.form-error {
  font-size: 13px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
}
</style>
