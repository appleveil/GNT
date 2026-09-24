<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/api/axios'
import { useGameDayStore } from '@/stores/gameDay'
import BankAccountFields from '@/components/shared/BankAccountFields.vue'
import { useToast } from '@/composables/useToast'

// Bottom sheet — replaces the old routed /players/new page (2026-09-14) so
// the cashier never leaves the Game Day screen to seat someone.
//
// `seatNumber` — set when opened by tapping a specific empty seat pill on
// ActiveGameDayView.vue (seats them directly, either tab available); null
// when opened via the general "+ New Player" button (registers a brand-new
// club-wide Player with no seat yet — they show up under "Unassigned"
// until moved into one).
//
// `newOnly` (added 2026-09-22) — true only for the "+ New Player" button:
// that entry point is for registering someone brand-new, full stop, no
// tab choice. Picking an EXISTING player always goes through a seat tap
// now — there's no "add an existing player with no seat" path any more,
// closing what used to be a second, less obvious way to do the same thing
// two different ways.
const props = defineProps({
  seatNumber: { type: Number, default: null },
  newOnly: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'added'])

const gameDay = useGameDayStore()
const toast = useToast()

// 'existing' is the default for a seat tap (the common case — most empty
// seats get filled by someone already on the roster); newOnly forces 'new'
// and the tab switcher itself is hidden (see template), so this never
// changes away from 'new' in that mode.
const mode = ref(props.newOnly ? 'new' : 'existing')
const submitting = ref(false)
const error = ref('')

// New player — the "Account code" text field is gone (2026-09-25): a new
// player's code is now auto-assigned from the AccountCode pool
// (services._assign_next_account_code), not typed in by hand. This form
// checks the pool's available count up front so it can disable itself
// with a clear notice instead of failing only after submit — see
// codeAvailable/loadCodeAvailability below. The real, authoritative gate
// is still server-side either way.
const displayName = ref('')
const bank = ref({ bank_name: '', bank_code: '', account_number: '', account_name: '' })
const codeAvailable = ref(true) // optimistic until the check below resolves
const codeAvailabilityLoading = ref(true)

async function loadCodeAvailability() {
  codeAvailabilityLoading.value = true
  try {
    const { data } = await api.get('/account-codes/available-count/')
    codeAvailable.value = data.count > 0
  } catch {
    codeAvailable.value = true // fail open — the server-side check still guards the actual submit
  } finally {
    codeAvailabilityLoading.value = false
  }
}

// Existing player (seat-tap only — see newOnly above) — select against the
// roster MINUS anyone with a GameDayPlayer row for tonight at all, active
// OR departed. A departed player never appears here: bringing them back is
// ActiveGameDayView's own Rejoin at Seat action now (2026-09-22, picks a
// seat first, then re-activates them in one step) — not this modal, which
// only ever creates a fresh GameDayPlayer row, never revives an existing
// one. Per-game now (Texas Hold'em 9, Omaha 8, ...) — gaming.selectors.
// max_active_players resolves it server-side; GameDaySerializer exposes the
// resolved number directly as max_players so this never needs its own copy
// of the game/table lookup. Falls back to 9 only for the brief window before
// gameDay.current has loaded.
const maxActivePlayers = computed(() => gameDay.current?.max_players ?? 9)

const roster = ref([])
const rosterLoading = ref(false)
const search = ref('')
const selectedId = ref(null)
const activeCount = ref(0)
// A seat-less add (props.seatNumber null, from the general "+ New Player"
// button) never takes an active seat, so the table-full cap — which is
// about seat capacity — doesn't apply to it. Only a seat-scoped add can be
// blocked by a full table.
const isFull = computed(() => props.seatNumber != null && activeCount.value >= maxActivePlayers.value)
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
    const seatedIds = new Set(seatedRes.data.map(p => p.id)) // active + departed — all excluded
    activeCount.value = seatedRes.data.filter(p => !p.left_at).length
    roster.value = allRes.data.filter(p => !seatedIds.has(p.id))
    // Drop the current selection if they got seated elsewhere (another
    // cashier device, or a retry after a failure below).
    if (selectedId.value && seatedIds.has(selectedId.value)) selectedId.value = null
  } catch {
    toast.error('Could not load the player roster.')
  } finally {
    rosterLoading.value = false
  }
}

// newOnly never shows the existing-player tab, so there's nothing for the
// roster fetch to serve — skip it entirely rather than loading data that'll
// never render. Account-code availability is checked eagerly either way
// (cheap single GET) so the "New player" tab never flashes enabled before
// disabling itself once the user switches to it.
onMounted(() => {
  if (!props.newOnly) loadRoster()
  loadCodeAvailability()
})

function toggleSelect(id) {
  // One seat, one person — picking a different row replaces the selection.
  selectedId.value = selectedId.value === id ? null : id
}

async function onSubmitExisting() {
  if (!selectedId.value || submitting.value) return
  error.value = ''
  submitting.value = true
  try {
    const { data: seated } = await api.post(`/game-days/${gameDay.current.id}/players/`, {
      player_id: selectedId.value, seat_number: props.seatNumber,
    })
    emit('added', seated.id)
    emit('close')
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not seat this player.'
    await loadRoster() // in case someone else just took this seat/player
  } finally {
    submitting.value = false
  }
}

async function onSubmitNew() {
  if (submitting.value || !codeAvailable.value) return
  error.value = ''
  submitting.value = true
  try {
    const { data: seated } = await api.post(`/game-days/${gameDay.current.id}/players/`, {
      display_name: displayName.value,
      seat_number: props.seatNumber,
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
    emit('added', seated.id)
    emit('close')
  } catch (err) {
    if (err.response?.data?.registered_not_seated) {
      // A real partial success, not a failure — the Player record was
      // created, just not seated (table's full). Say so plainly rather than
      // showing this in the same red error state as a validation failure.
      toast.success(`${displayName.value} was registered but the table is full — seat them once a spot opens up.`)
      displayName.value = ''
      bank.value = { bank_name: '', bank_code: '', account_number: '', account_name: '' }
      loadCodeAvailability() // that registration just consumed a code — refresh the count
    } else {
      error.value = Object.values(err.response?.data || {})[0]?.[0]
        || err.response?.data?.detail
        || 'Could not add player.'
      if (err.response?.data?.detail?.includes('No available account codes')) codeAvailable.value = false
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
        <div class="sheet-title">
          {{ seatNumber ? `Seat ${seatNumber}` : 'New Player' }} &mdash; Game-Day #{{ gameDay.current?.number ?? '—' }}
        </div>
        <button class="close-btn" type="button" @click="emit('close')">&times;</button>
      </div>

      <!-- newOnly (the "+ New Player" button) skips the tab choice
           entirely — see its own comment above. -->
      <div v-if="!newOnly" class="tabs">
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
          Table is full ({{ activeCount }}/{{ maxActivePlayers }} active) — seat a player once someone leaves the table.
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
              :class="{ 'search-row--selected': selectedId === p.id, 'search-row--disabled': isFull }"
              @click="!isFull && toggleSelect(p.id)"
            >
              <span class="check" :class="{ 'check--on': selectedId === p.id }">
                <span v-if="selectedId === p.id">&#10003;</span>
              </span>
              {{ p.account_code }} — {{ p.display_name }}
            </div>
            <p v-if="!filtered.length" class="muted">No matches — everyone's already seated tonight, or none exist yet.</p>
          </template>
        </div>

        <p v-if="error" class="form-error">{{ error }}</p>

        <button
          class="btn btn--primary" type="button" :disabled="isFull || !selectedId || submitting"
          @click="onSubmitExisting"
        >
          {{ submitting ? 'Adding…' : (seatNumber ? `Seat in Seat ${seatNumber}` : 'Add Player') }}
        </button>
      </template>

      <form v-else class="form" @submit.prevent="onSubmitNew">
        <p v-if="!codeAvailabilityLoading && !codeAvailable" class="dva-note dva-note--danger">
          No account codes available — ask the Owner or Accountant to add more from the Admin page before
          registering a new player.
        </p>
        <label class="field">
          <span class="eyebrow">Name</span>
          <input v-model="displayName" type="text" required :disabled="!codeAvailable" />
        </label>
        <p class="section-note">Bank account (optional — for future winnings)</p>
        <BankAccountFields v-model="bank" />
        <p class="dva-note">
          Gaming Account / Dedicated Virtual Account isn't available yet — Paystack's
          Dedicated NUBAN approval is still pending. The player can still be added and issued chips.
        </p>

        <p v-if="error" class="form-error">{{ error }}</p>

        <button class="btn btn--primary" type="submit" :disabled="submitting || !codeAvailable">
          {{ submitting ? 'Adding…' : (seatNumber ? `Seat in Seat ${seatNumber}` : 'Add Player') }}
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
.dva-note--danger { color: var(--danger); background: var(--danger-bg); margin-bottom: 12px; }
.form-error {
  font-size: 13px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  margin-bottom: 12px;
}
</style>
