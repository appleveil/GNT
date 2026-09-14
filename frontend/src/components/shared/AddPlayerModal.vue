<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/api/axios'
import { useGameDayStore } from '@/stores/gameDay'
import BankAccountFields from '@/components/shared/BankAccountFields.vue'
import { useToast } from '@/composables/useToast'

// Bottom sheet — replaces the old routed /players/new page (2026-09-14) so
// the cashier never leaves the Game Day screen to seat someone. Existing
// player selection is multi-select (a cashier often needs to seat several
// returning players in one go); a new player is still exactly one at a
// time. The two modes stay mutually exclusive, same as before.
const emit = defineEmits(['close', 'added'])

const gameDay = useGameDayStore()
const toast = useToast()

const mode = ref('existing') // 'existing' | 'new' — existing is the common case, so it's the default
const submitting = ref(false)
const error = ref('')

// New player
const accountCode = ref('')
const displayName = ref('')
const bank = ref({ bank_name: '', bank_code: '', account_number: '', account_name: '' })

// Existing player — multi-select against the roster MINUS whoever's
// ACTIVELY seated tonight (a departed player — left_at set — is meant to be
// re-addable via "Return to Table", same as this modal; only currently-
// active seats are excluded).
const MAX_ACTIVE_PLAYERS = 9 // mirrors gaming.services.MAX_ACTIVE_PLAYERS_PER_GAME_DAY

const roster = ref([])
const rosterLoading = ref(false)
const search = ref('')
const selectedIds = ref([])
const activeCount = ref(0)
const isFull = computed(() => activeCount.value >= MAX_ACTIVE_PLAYERS)
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return roster.value
  return roster.value.filter(
    p => p.account_code.toLowerCase().includes(q) || p.display_name.toLowerCase().includes(q),
  )
})

async function loadRoster() {
  if (!gameDay.current) return
  rosterLoading.value = true
  try {
    const [allRes, seatedRes] = await Promise.all([
      api.get('/players/'),
      api.get(`/game-days/${gameDay.current.id}/players/`),
    ])
    const activeIds = new Set(seatedRes.data.filter(p => !p.left_at).map(p => p.id))
    activeCount.value = activeIds.size
    roster.value = allRes.data.filter(p => !activeIds.has(p.id))
    // Drop anyone from the current selection who got seated elsewhere
    // (another cashier device, or a retry after a partial failure below).
    selectedIds.value = selectedIds.value.filter(id => !activeIds.has(id))
  } catch {
    toast.error('Could not load the player roster.')
  } finally {
    rosterLoading.value = false
  }
}

onMounted(loadRoster)

function toggleSelect(id) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter(x => x !== id)
    : [...selectedIds.value, id]
}

async function onSubmitExisting() {
  if (!selectedIds.value.length || submitting.value) return
  error.value = ''
  submitting.value = true
  const ids = selectedIds.value
  const results = await Promise.allSettled(
    ids.map(id => api.post(`/game-days/${gameDay.current.id}/players/`, { player_id: id })),
  )
  submitting.value = false

  const failures = ids
    .map((id, i) => ({ id, result: results[i] }))
    .filter(({ result }) => result.status === 'rejected')
  if (!failures.length) {
    emit('added')
    emit('close')
    return
  }

  emit('added') // the ones that DID succeed are seated — parent's list needs them
  // Surface the real reason per player (table full vs. anything else) rather
  // than a generic "still need to retry" for all of them.
  const lines = failures.map(({ id, result }) => {
    const name = roster.value.find(p => p.id === id)?.display_name || 'a player'
    const reason = result.reason?.response?.data?.detail || 'could not be seated'
    return `${name} — ${reason}`
  })
  error.value = `Added ${ids.length - failures.length} of ${ids.length}. ${lines.join(' ')}`
  await loadRoster() // drops the succeeded ones from the list; failed ones stay selected for a retry
}

async function onSubmitNew() {
  if (submitting.value) return
  error.value = ''
  submitting.value = true
  try {
    const { data: seated } = await api.post(`/game-days/${gameDay.current.id}/players/`, {
      account_code: accountCode.value,
      display_name: displayName.value,
    })
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
    emit('added')
    emit('close')
  } catch (err) {
    if (err.response?.data?.registered_not_seated) {
      // A real partial success, not a failure — the Player record was
      // created, just not seated (table's full). Say so plainly rather than
      // showing this in the same red error state as a validation failure.
      toast.success(`${displayName.value} was registered but the table is full — seat them once a spot opens up.`)
      accountCode.value = ''
      displayName.value = ''
      bank.value = { bank_name: '', bank_code: '', account_number: '', account_name: '' }
    } else {
      error.value = Object.values(err.response?.data || {})[0]?.[0]
        || err.response?.data?.detail
        || 'Could not add player.'
    }
  } finally {
    submitting.value = false
  }
}

function onModeChange(next) {
  mode.value = next
  error.value = ''
}
</script>

<template>
  <div class="overlay">
    <div class="sheet">
      <div class="grip" />
      <div class="head">
        <div class="sheet-title">Add Player &mdash; Game-Day #{{ gameDay.current?.number ?? '—' }}</div>
        <button class="close-btn" type="button" @click="emit('close')">&times;</button>
      </div>

      <div class="tabs">
        <button
          type="button" class="tab" :class="{ 'tab--active': mode === 'existing' }"
          @click="onModeChange('existing')"
        >Existing player</button>
        <button
          type="button" class="tab" :class="{ 'tab--active': mode === 'new' }"
          @click="onModeChange('new')"
        >New player</button>
      </div>

      <template v-if="mode === 'existing'">
        <p v-if="isFull" class="dva-note">
          Table is full ({{ activeCount }}/{{ MAX_ACTIVE_PLAYERS }} active) — seat a player once someone leaves the table.
        </p>
        <input
          v-model="search" type="text" placeholder="Search by name or account code…" class="search-input"
          :disabled="isFull"
        />
        <div class="search-list">
          <p v-if="rosterLoading" class="muted">Loading…</p>
          <template v-else>
            <div
              v-for="p in filtered" :key="p.id" class="search-row"
              :class="{ 'search-row--selected': selectedIds.includes(p.id), 'search-row--disabled': isFull }"
              @click="!isFull && toggleSelect(p.id)"
            >
              <span class="check" :class="{ 'check--on': selectedIds.includes(p.id) }">
                <span v-if="selectedIds.includes(p.id)">&#10003;</span>
              </span>
              {{ p.account_code }} — {{ p.display_name }}
            </div>
            <p v-if="!filtered.length" class="muted">No matches — everyone's already seated tonight, or none exist yet.</p>
          </template>
        </div>

        <p v-if="error" class="form-error">{{ error }}</p>

        <button
          class="btn btn--primary" type="button" :disabled="isFull || !selectedIds.length || submitting"
          @click="onSubmitExisting"
        >
          {{ submitting ? 'Adding…' : `Add ${selectedIds.length || ''} Selected`.trim() }}
        </button>
      </template>

      <form v-else class="form" @submit.prevent="onSubmitNew">
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

        <p v-if="error" class="form-error">{{ error }}</p>

        <button class="btn btn--primary" type="submit" :disabled="submitting">
          {{ submitting ? 'Adding…' : 'Add to tonight' }}
        </button>
      </form>
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
  padding: 16px 24px 24px;
  display: flex;
  flex-direction: column;
  max-height: 90vh;
  overflow-y: auto;
}
.grip { width: 44px; height: 5px; border-radius: 3px; background: var(--border); align-self: center; margin-bottom: 18px; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.sheet-title { font-size: 17px; font-weight: 700; color: var(--text-primary); }
.close-btn { border: none; background: none; font-size: 22px; line-height: 1; color: var(--text-tertiary); cursor: pointer; flex-shrink: 0; }

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

.search-input {
  width: 100%;
  height: 44px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 14px;
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text-primary);
  background: var(--surface);
  margin-bottom: 10px;
}
.search-list { list-style: none; max-height: 320px; overflow-y: auto; margin-bottom: 14px; }
.search-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  font-size: 14px;
}
.search-row:hover { background: var(--bg); }
.search-row--selected { background: var(--accent-bg); color: var(--accent-text); font-weight: 600; }
.search-row--disabled { opacity: 0.5; cursor: not-allowed; }
.check {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  border: 1.5px solid var(--border-strong);
  border-radius: 5px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #fff;
}
.check--on { background: var(--accent); border-color: var(--accent); }
.muted { color: var(--text-secondary); font-size: 13px; padding: 12px; }

.form { display: flex; flex-direction: column; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.eyebrow {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
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
.form-error {
  font-size: 13px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  margin-bottom: 12px;
}
</style>
