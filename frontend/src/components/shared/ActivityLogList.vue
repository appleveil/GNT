<script setup>
import { ref, onMounted, watch } from 'vue'
import api from '@/api/axios'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'

// Shared Activity log table (added 2026-10-02) — GET /activity-log/,
// role-scoped entirely server-side (gaming.selectors.visible_activity):
// Owner sees everything, Accountant/Floor Manager see every Cashier's
// entries plus their own, Cashier sees only their own. This component just
// renders whatever the endpoint hands back — no role logic of its own,
// except for the actor filter (see staffOptions below). Mounted from
// AdminView.vue (Owner/Accountant section) and ActivityLogView.vue (the
// Floor Manager sidebar tab and the Cashier's avatar-menu route).
const auth = useAuthStore()
const toast = useToast()

const rows = ref([])
const loading = ref(false)
const count = ref(0)
const offset = ref(0)
const LIMIT = 50

const actionFilter = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const actorFilter = ref('')

// The actor dropdown is Owner-only — every other role either only ever
// sees their own entries (Cashier — nothing meaningful to filter by) or
// would need GET /staff-users/, which is Owner-only (StaffUserViewSet's
// own permission split). Failing to load this is non-fatal — the filter
// just has no options.
const staffOptions = ref([])
async function loadStaffOptions() {
  if (!auth.isOwner) return
  try {
    const { data } = await api.get('/staff-users/')
    staffOptions.value = data
  } catch {
    staffOptions.value = []
  }
}
function staffLabel(s) {
  return `${s.first_name} ${s.last_name}`.trim() || s.username
}

// Mirrors gaming.models.ActivityLog.Action — kept here rather than fetched,
// since the choice set almost never changes and this avoids a round trip
// just to populate a filter.
const ACTIONS = [
  ['CHIPS_OUT', 'Issued chips'], ['CHIPS_IN', 'Returned chips'], ['PAYMENT', 'Recorded a payment'],
  ['RAKE', 'Recorded rake'], ['TIP', 'Recorded a tip'], ['WRITE_OFF', 'Wrote off a balance'],
  ['DEAL_TRANSFER', "Transferred a player's balance"], ['VOID', 'Voided an entry'],
  ['SEAT_PLAYER', 'Seated a player'], ['LEAVE_TABLE', 'Marked a player as left the table'],
  ['MOVE_SEAT', 'Moved a seat'], ['OPEN_GAME_DAY', 'Opened a game-day'], ['CLOSE_GAME_DAY', 'Closed a game-day'],
  ['PAYOUT_REQUESTED', 'Requested a payout'], ['PAYOUT_APPROVED', 'Approved a payout'],
  ['PAYOUT_REJECTED', 'Rejected a payout'], ['DEAL_CREATED', 'Set up a deal'], ['DEAL_ENDED', 'Ended a deal'],
  ['CREDIT_LIMIT_CHANGED', "Changed a player's credit limit"], ['SETTINGS_CHANGED', 'Changed club settings'],
  ['TABLE_CHANGED', 'Changed a table'], ['STAFF_CREATED', 'Created a staff account'],
  ['PASSWORD_RESET', 'Reset a password'], ['PIN_RESET', 'Reset a PIN'],
  ['ACCOUNT_CODES_ADDED', 'Added account codes'], ['PLAYER_CREATED', 'Registered a player'],
  ['LOGIN', 'Logged in'],
]

async function load(resetOffset) {
  if (resetOffset) offset.value = 0
  loading.value = true
  try {
    const params = { limit: LIMIT, offset: offset.value }
    if (actionFilter.value) params.action = actionFilter.value
    if (dateFrom.value) params.date_from = dateFrom.value
    if (dateTo.value) params.date_to = dateTo.value
    if (actorFilter.value) params.actor = actorFilter.value
    const { data } = await api.get('/activity-log/', { params })
    rows.value = resetOffset ? data.results : [...rows.value, ...data.results]
    count.value = data.count
  } catch {
    toast.error('Could not load the activity log.')
  } finally {
    loading.value = false
  }
}

function loadMore() {
  offset.value += LIMIT
  load(false)
}

watch([actionFilter, dateFrom, dateTo, actorFilter], () => load(true))
onMounted(() => {
  loadStaffOptions()
  load(true)
})

function formatTime(iso) {
  const d = new Date(iso)
  return `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} · ${d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`
}
</script>

<template>
  <div class="activity-log">
    <div class="filters">
      <input v-model="dateFrom" type="date" class="filter-input" title="From date" />
      <input v-model="dateTo" type="date" class="filter-input" title="To date" />
      <select v-model="actionFilter" class="filter-input">
        <option value="">All actions</option>
        <option v-for="[value, label] in ACTIONS" :key="value" :value="value">{{ label }}</option>
      </select>
      <select v-if="auth.isOwner && staffOptions.length" v-model="actorFilter" class="filter-input">
        <option value="">Everyone</option>
        <option v-for="s in staffOptions" :key="s.id" :value="s.id">{{ staffLabel(s) }}</option>
      </select>
    </div>

    <p v-if="loading && !rows.length" class="muted">Loading…</p>
    <p v-else-if="!rows.length" class="muted">No activity yet.</p>

    <template v-else>
      <div class="table">
        <div class="t-head">
          <span>Time</span><span>Staff</span><span>Action</span><span>Details</span>
        </div>
        <div v-for="row in rows" :key="row.id" class="t-row">
          <span class="mono">{{ formatTime(row.created_at) }}</span>
          <span>{{ row.actor_name }}</span>
          <span>{{ row.action_display }}</span>
          <span class="summary">{{ row.summary }}</span>
        </div>
      </div>

      <button
        v-if="rows.length < count" class="btn btn--secondary load-more" type="button" :disabled="loading"
        @click="loadMore"
      >{{ loading ? 'Loading…' : `Load more (${count - rows.length} more)` }}</button>
    </template>
  </div>
</template>

<style scoped>
.filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.filter-input {
  height: var(--control-row-min);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 12px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-primary);
  background: var(--surface);
}
.filter-input:focus { outline: none; border-color: var(--accent); }
.muted { color: var(--text-secondary); font-size: 13px; }

.table { border: 1px solid var(--border); border-radius: var(--radius-md); overflow: visible; background: var(--surface); }
.t-head, .t-row {
  display: grid;
  grid-template-columns: 150px 160px 180px 1fr;
  align-items: center;
  padding: 0 20px;
  gap: 8px;
}
.t-head { height: var(--control-row-min); background: var(--bg); border-bottom: 1px solid var(--border); border-radius: var(--radius-md) var(--radius-md) 0 0; }
.t-head span { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.t-row { min-height: var(--control-row-max); border-bottom: 1px solid var(--border); font-size: 13px; color: var(--text-primary); padding-top: 8px; padding-bottom: 8px; }
.t-row:last-child { border-bottom: none; border-radius: 0 0 var(--radius-md) var(--radius-md); }
.mono { font-family: var(--font-mono); color: var(--text-secondary); font-size: 12px; }
.summary { color: var(--text-secondary); }

.load-more { margin-top: 14px; }

@media (max-width: 860px) {
  .t-head { display: none; }
  .t-row { grid-template-columns: 1fr; height: auto; padding: 12px 16px; gap: 2px; }
}
</style>
