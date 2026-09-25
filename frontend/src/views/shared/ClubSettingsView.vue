<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/api/axios'
import { useAuthStore } from '@/stores/auth'
import { useClubSettingsStore } from '@/stores/clubSettings'
import { useToast } from '@/composables/useToast'

// Shared "Settings" page (added 2026-09-23) — visible to both Owner and
// Floor Manager (see router/index.js's FLOOR_MANAGER_ROLES), copying
// AdminView.vue's own per-section CRUD-lite pattern: each section is its
// own ref(s) + load/save functions + its own <div class="card
// section-card">. Tables is the shared half (both roles can edit);
// Approvals, Payout auto-approval, and FX Rates are Owner-only, hidden
// inline via v-if rather than a second route — same idea as
// MasseuseListView.vue reusing AdminView's Floor-Managers-section shape.
//
// FX Rates moved in from AdminView.vue on 2026-09-23 — same
// /conversion-rates/ data and set_rate action as before, just grouped here
// with the club's other Owner-tunable numbers instead of the staff-roster
// page. Still Owner-only (the section itself, and this page's own route
// stays open to Floor Manager for the Tables section above it) — nothing
// about who can set a rate changed server-side.
const auth = useAuthStore()
const clubSettings = useClubSettingsStore()
const toast = useToast()

// ── Tables ───────────────────────────────────────────────────────────────
const tables = ref([])
const games = ref([]) // only for resolving a table's game id -> name in the label below
const tablesLoading = ref(true)
const editingTableId = ref(null) // a Table's id currently showing the edit form, or null
const editForm = ref({})
const tableSaving = ref(false)
const tableError = ref('')

async function loadTables() {
  tablesLoading.value = true
  try {
    const [tablesRes, gamesRes] = await Promise.all([api.get('/tables/'), api.get('/games/')])
    tables.value = tablesRes.data
    games.value = gamesRes.data
  } catch {
    toast.error('Could not load tables.')
  } finally {
    tablesLoading.value = false
  }
}

function gameName(gameId) {
  return games.value.find(g => g.id === gameId)?.name || '—'
}

function onStartEditTable(table) {
  editingTableId.value = table.id
  tableError.value = ''
  editForm.value = {
    default_buy_in: table.default_buy_in,
    rake_percentage: table.rake_percentage ?? '',
    small_blind: table.small_blind ?? '',
    big_blind: table.big_blind ?? '',
    max_players: table.max_players ?? '',
    max_chips_issuable: table.max_chips_issuable ?? '',
  }
}

function onCancelEditTable() {
  editingTableId.value = null
  tableError.value = ''
}

async function onSaveTable(table) {
  tableSaving.value = true
  tableError.value = ''
  try {
    // '' -> null: an emptied field means "no override"/"no cap," not 0 —
    // matches every field's own nullable meaning (see Table's docstring).
    const payload = Object.fromEntries(
      Object.entries(editForm.value).map(([k, v]) => [k, v === '' ? null : v]),
    )
    const { data } = await api.patch(`/tables/${table.id}/`, payload)
    Object.assign(table, data)
    editingTableId.value = null
    toast.success(`${table.name} updated.`)
  } catch (err) {
    tableError.value = Object.values(err.response?.data || {})[0]?.[0] || 'Could not save this table.'
  } finally {
    tableSaving.value = false
  }
}

// ── Floor rules (Owner + Floor Manager) ─────────────────────────────────
// Added 2026-09-27 — the first fields on ClubSettings a Floor Manager can
// write at all (see gaming.views.ClubSettingsView.FLOOR_MANAGER_EDITABLE_FIELDS);
// lives alongside Tables above (outside the Owner-only template block
// below), not with the Owner-only Approvals section. observe_min_player_time
// gates RETURNING chips only — a player can always leave the table, see
// ClubSettings' own docstring. track_away_from_table's own away-tracking
// mechanism (an actual "player got up"/"player's back" action pair on the
// Cashier screen) is deliberately NOT built yet — this round only adds the
// two settings fields it'll need, ahead of that work.
const floorRuleTogglingField = ref('')
async function onToggleFloorRule(field) {
  floorRuleTogglingField.value = field
  try {
    const { data } = await api.patch('/club-settings/', { [field]: !clubSettings.current[field] })
    clubSettings.current = data
  } catch {
    toast.error('Could not update that setting.')
  } finally {
    floorRuleTogglingField.value = ''
  }
}

const minPlayerTimeInput = ref('')
const minPlayerTimeSaving = ref(false)
const minPlayerTimeError = ref('')
async function onSaveMinPlayerTime() {
  minPlayerTimeSaving.value = true
  minPlayerTimeError.value = ''
  try {
    const { data } = await api.patch('/club-settings/', { min_player_time_minutes: minPlayerTimeInput.value })
    clubSettings.current = data
    toast.success('Minimum player time updated.')
  } catch (err) {
    minPlayerTimeError.value = err.response?.data?.min_player_time_minutes?.[0] || 'Could not save this.'
  } finally {
    minPlayerTimeSaving.value = false
  }
}

const awayMaxInput = ref('')
const awayMaxSaving = ref(false)
const awayMaxError = ref('')
async function onSaveAwayMax() {
  awayMaxSaving.value = true
  awayMaxError.value = ''
  try {
    const { data } = await api.patch('/club-settings/', { away_max_minutes: awayMaxInput.value })
    clubSettings.current = data
    toast.success('Away time updated.')
  } catch (err) {
    awayMaxError.value = err.response?.data?.away_max_minutes?.[0] || 'Could not save this.'
  } finally {
    awayMaxSaving.value = false
  }
}

// ── Cashier permissions (Owner-only) ────────────────────────────────────
const cashierPayoutToggling = ref(false)
async function onToggleCashierCanInitiatePayout() {
  cashierPayoutToggling.value = true
  try {
    const { data } = await api.patch('/club-settings/', {
      cashier_can_initiate_payout: !clubSettings.current.cashier_can_initiate_payout,
    })
    clubSettings.current = data
  } catch {
    toast.error('Could not update that setting.')
  } finally {
    cashierPayoutToggling.value = false
  }
}

// ── Approvals (Owner-only) ──────────────────────────────────────────────
const APPROVAL_TOGGLES = [
  { field: 'require_approval_open_game_day', label: 'Open a game-day' },
  { field: 'require_approval_close_game_day', label: 'Close a game-day', note: 'A chip discrepancy always still requires sign-off, regardless of this.' },
  { field: 'require_approval_issue_chips', label: 'Issue chips' },
  { field: 'require_approval_return_chips', label: 'Return chips' },
  { field: 'require_approval_add_tip', label: 'Add a tip' },
  { field: 'require_approval_add_rake', label: 'Add rake' },
]
const togglingField = ref('') // which toggle's PATCH is in flight, or ''

async function onToggleApproval(field) {
  togglingField.value = field
  try {
    const { data } = await api.patch('/club-settings/', { [field]: !clubSettings.current[field] })
    clubSettings.current = data
  } catch {
    toast.error('Could not update that setting.')
  } finally {
    togglingField.value = ''
  }
}

// ── Dashboard (Owner-only) ──────────────────────────────────────────────
// A single visibility toggle, added 2026-09-24 — distinct in kind from the
// require_approval_* switches above (those gate sign-off; this gates
// whether the open/operate-game-day widget shows on Dashboard at all), so
// it gets its own switch + its own PATCH call rather than joining
// APPROVAL_TOGGLES/onToggleApproval.
const dashboardTogglingField = ref('')
async function onToggleDashboardGameDay() {
  dashboardTogglingField.value = 'owner_dashboard_game_day_enabled'
  try {
    const { data } = await api.patch('/club-settings/', {
      owner_dashboard_game_day_enabled: !clubSettings.current.owner_dashboard_game_day_enabled,
    })
    clubSettings.current = data
  } catch {
    toast.error('Could not update that setting.')
  } finally {
    dashboardTogglingField.value = ''
  }
}

// ── Payout auto-approval (Owner-only) ───────────────────────────────────
const thresholdInput = ref('')
const thresholdSaving = ref(false)
const thresholdError = ref('')

async function onSaveThreshold() {
  thresholdSaving.value = true
  thresholdError.value = ''
  try {
    const { data } = await api.patch('/club-settings/', { payout_auto_approve_threshold: thresholdInput.value })
    clubSettings.current = data
    toast.success('Payout auto-approval threshold updated.')
  } catch (err) {
    thresholdError.value = err.response?.data?.payout_auto_approve_threshold?.[0] || 'Could not save this threshold.'
  } finally {
    thresholdSaving.value = false
  }
}

// ── FX Rates (Owner-only) ───────────────────────────────────────────────
const rates = ref([])
const ratesLoading = ref(true)
const gameDaysForRates = ref([])
const newRate = ref({ currency: 'USD', rate_to_naira: '', game_day: '' })
const rateSubmitting = ref(false)
const rateError = ref('')

async function loadRates() {
  ratesLoading.value = true
  try {
    const [ratesRes, gameDaysRes] = await Promise.all([
      api.get('/conversion-rates/'),
      api.get('/game-days/'),
    ])
    rates.value = ratesRes.data
    gameDaysForRates.value = gameDaysRes.data
  } catch {
    toast.error('Could not load FX rates.')
  } finally {
    ratesLoading.value = false
  }
}

// Standing (game_day: null) rate per currency — the most recently created
// row, since a rate change is always a new row, never an edit (immutable
// once created, per SCHEMA.md). rates.value comes back newest-first already
// (ConversionRateViewSet has no explicit ordering override, but set_rate
// creates rows in order — sort defensively by created_at desc to be sure).
const standingByCurrency = computed(() => {
  const sorted = rates.value.slice().sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  const found = {}
  for (const r of sorted) {
    if (r.game_day == null && !(r.currency in found)) found[r.currency] = r
  }
  return found
})
const recentRates = computed(() => rates.value.slice().sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 10))

async function onSetRate() {
  rateError.value = ''
  rateSubmitting.value = true
  try {
    const payload = { currency: newRate.value.currency, rate_to_naira: newRate.value.rate_to_naira }
    if (newRate.value.game_day) payload.game_day = newRate.value.game_day
    await api.post('/conversion-rates/set_rate/', payload)
    newRate.value = { currency: newRate.value.currency, rate_to_naira: '', game_day: '' }
    await loadRates()
    toast.success('Rate set.')
  } catch (err) {
    rateError.value = Object.values(err.response?.data || {})[0]?.[0] || err.response?.data?.detail || 'Could not set this rate.'
  } finally {
    rateSubmitting.value = false
  }
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

onMounted(async () => {
  loadTables()
  if (!clubSettings.current) await clubSettings.fetchCurrent().catch(() => {})
  if (clubSettings.current) {
    thresholdInput.value = clubSettings.current.payout_auto_approve_threshold
    minPlayerTimeInput.value = clubSettings.current.min_player_time_minutes
    awayMaxInput.value = clubSettings.current.away_max_minutes
  }
  if (auth.user?.role === 'OWNER') loadRates()
})

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Settings</h1>
      <p>Per-table limits and defaults{{ auth.user?.role === 'OWNER' ? ', plus sign-off and payout rules' : '' }}.</p>
    </div>

    <div class="card section-card">
      <div class="section-title">Tables</div>
      <p class="section-note">
        Max chips per buy-in, default buy-in, blinds, rake %, and max players — Owner or Floor Manager can edit any table.
      </p>
      <p v-if="tablesLoading" class="muted">Loading…</p>
      <template v-else>
        <p v-if="!tables.length" class="muted">No tables yet.</p>
        <div v-for="t in tables" :key="t.id" class="table-block">
          <div class="row">
            <div class="row-info">
              <div class="row-name">{{ t.name }} <span class="row-sub">— {{ gameName(t.game) }}</span></div>
              <div class="row-sub">
                Buy-in {{ N(t.default_buy_in) }}
                <template v-if="t.max_chips_issuable != null"> &middot; max {{ N(t.max_chips_issuable) }} per buy-in</template>
                <template v-if="t.max_players">&middot; max {{ t.max_players }} players</template>
              </div>
            </div>
            <button v-if="editingTableId !== t.id" class="link-btn" type="button" @click="onStartEditTable(t)">Edit</button>
          </div>

          <form v-if="editingTableId === t.id" class="edit-form" @submit.prevent="onSaveTable(t)">
            <label class="field">
              <span class="field-label">Default buy-in</span>
              <input v-model="editForm.default_buy_in" type="number" min="0" step="1000" class="ff" required />
            </label>
            <label class="field">
              <span class="field-label">Max chips per buy-in</span>
              <input v-model="editForm.max_chips_issuable" type="number" min="0" step="1000" placeholder="No cap" class="ff" />
            </label>
            <label class="field">
              <span class="field-label">Max players</span>
              <input v-model="editForm.max_players" type="number" min="1" placeholder="Use the game's default" class="ff" />
            </label>
            <label class="field">
              <span class="field-label">Small blind</span>
              <input v-model="editForm.small_blind" type="number" min="0" step="100" placeholder="—" class="ff" />
            </label>
            <label class="field">
              <span class="field-label">Big blind</span>
              <input v-model="editForm.big_blind" type="number" min="0" step="100" placeholder="—" class="ff" />
            </label>
            <label class="field">
              <span class="field-label">Rake %</span>
              <input v-model="editForm.rake_percentage" type="number" min="0" max="100" step="0.5" placeholder="—" class="ff" />
            </label>
            <div class="edit-actions">
              <button class="btn btn--secondary" type="button" :disabled="tableSaving" @click="onCancelEditTable">Cancel</button>
              <button class="btn btn--primary" type="submit" :disabled="tableSaving">{{ tableSaving ? 'Saving…' : 'Save' }}</button>
            </div>
            <p v-if="tableError" class="form-error">{{ tableError }}</p>
          </form>
        </div>
      </template>
    </div>

    <div class="card section-card">
      <div class="section-title">Floor rules</div>
      <p class="section-note">Owner or Floor Manager can edit these.</p>
      <p v-if="!clubSettings.current" class="muted">Loading…</p>
      <div v-else class="toggle-list">
        <div class="toggle-row">
          <div class="row-info">
            <div class="row-name">Observe minimum player time</div>
            <div class="row-sub">
              A player can leave the table any time, but chips can't be returned for them until this long
              has passed since they sat down — a Floor Manager PIN overrides it early.
            </div>
          </div>
          <button
            class="switch" type="button" :class="{ 'switch--on': clubSettings.current.observe_min_player_time }"
            :disabled="floorRuleTogglingField === 'observe_min_player_time'" role="switch"
            :aria-checked="clubSettings.current.observe_min_player_time"
            @click="onToggleFloorRule('observe_min_player_time')"
          >
            <span class="switch-knob" />
          </button>
        </div>
        <form v-if="clubSettings.current.observe_min_player_time" class="sub-form" @submit.prevent="onSaveMinPlayerTime">
          <label class="field">
            <span class="field-label">Minimum player time (minutes)</span>
            <input v-model="minPlayerTimeInput" type="number" min="30" step="30" required class="ff" />
          </label>
          <button class="btn btn--secondary" type="submit" :disabled="minPlayerTimeSaving">
            {{ minPlayerTimeSaving ? 'Saving…' : 'Save' }}
          </button>
          <p v-if="minPlayerTimeError" class="form-error">{{ minPlayerTimeError }}</p>
        </form>

        <div class="toggle-row">
          <div class="row-info">
            <div class="row-name">Track away from table</div>
            <div class="row-sub">
              A player away longer than the max below has that extra time added to their own minimum player
              time — only while it hasn't already elapsed. Marking a player away/back on the Cashier screen
              isn't built yet; this just stores the setting ahead of that.
            </div>
          </div>
          <button
            class="switch" type="button" :class="{ 'switch--on': clubSettings.current.track_away_from_table }"
            :disabled="floorRuleTogglingField === 'track_away_from_table'" role="switch"
            :aria-checked="clubSettings.current.track_away_from_table"
            @click="onToggleFloorRule('track_away_from_table')"
          >
            <span class="switch-knob" />
          </button>
        </div>
        <form v-if="clubSettings.current.track_away_from_table" class="sub-form" @submit.prevent="onSaveAwayMax">
          <label class="field">
            <span class="field-label">Max time away (minutes)</span>
            <input v-model="awayMaxInput" type="number" min="1" step="1" required class="ff" />
          </label>
          <button class="btn btn--secondary" type="submit" :disabled="awayMaxSaving">
            {{ awayMaxSaving ? 'Saving…' : 'Save' }}
          </button>
          <p v-if="awayMaxError" class="form-error">{{ awayMaxError }}</p>
        </form>
      </div>
    </div>

    <template v-if="auth.user?.role === 'OWNER'">
      <div class="card section-card">
        <div class="section-title">Require approval</div>
        <p class="section-note">Off skips the PIN step for that action — a plain confirm still shows first.</p>
        <p v-if="!clubSettings.current" class="muted">Loading…</p>
        <div v-else class="toggle-list">
          <div v-for="t in APPROVAL_TOGGLES" :key="t.field" class="toggle-row">
            <div class="row-info">
              <div class="row-name">{{ t.label }}</div>
              <div v-if="t.note" class="row-sub">{{ t.note }}</div>
            </div>
            <button
              class="switch" type="button" :class="{ 'switch--on': clubSettings.current[t.field] }"
              :disabled="togglingField === t.field" role="switch" :aria-checked="clubSettings.current[t.field]"
              @click="onToggleApproval(t.field)"
            >
              <span class="switch-knob" />
            </button>
          </div>
        </div>
      </div>

      <div class="card section-card">
        <div class="section-title">Dashboard</div>
        <p class="section-note">Off by default — most clubs open/close a game-day from the Cashier device, not from here.</p>
        <p v-if="!clubSettings.current" class="muted">Loading…</p>
        <div v-else class="toggle-list">
          <div class="toggle-row">
            <div class="row-info">
              <div class="row-name">Open/operate a game-day from Dashboard</div>
              <div class="row-sub">Opens immediately under your own login — no PIN needed, regardless of the approval toggles above.</div>
            </div>
            <button
              class="switch" type="button" :class="{ 'switch--on': clubSettings.current.owner_dashboard_game_day_enabled }"
              :disabled="dashboardTogglingField === 'owner_dashboard_game_day_enabled'" role="switch"
              :aria-checked="clubSettings.current.owner_dashboard_game_day_enabled"
              @click="onToggleDashboardGameDay"
            >
              <span class="switch-knob" />
            </button>
          </div>
        </div>
      </div>

      <div class="card section-card">
        <div class="section-title">Cashier permissions</div>
        <p v-if="!clubSettings.current" class="muted">Loading…</p>
        <div v-else class="toggle-list">
          <div class="toggle-row">
            <div class="row-info">
              <div class="row-name">Cashier can initiate a payout</div>
              <div class="row-sub">Off hides/disables the Payout button on the Cashier's own screen — the Owner's own Players-page payout is unaffected.</div>
            </div>
            <button
              class="switch" type="button" :class="{ 'switch--on': clubSettings.current.cashier_can_initiate_payout }"
              :disabled="cashierPayoutToggling" role="switch"
              :aria-checked="clubSettings.current.cashier_can_initiate_payout"
              @click="onToggleCashierCanInitiatePayout"
            >
              <span class="switch-knob" />
            </button>
          </div>
        </div>



        <div class="section-title">Payout auto-approval</div>
        <p class="section-note">
          A Cashier-requested payout at or below this amount moves automatically — nothing to approve.
          <template v-if="clubSettings.current && !clubSettings.current.cashier_can_initiate_payout">
            Not applicable right now — the Cashier can't initiate a payout at all (see above). The Owner's own
            payouts from the Players page always move immediately, regardless of this threshold.
          </template>
        </p>
        <form
          class="create-form" :class="{ 'create-form--disabled': clubSettings.current && !clubSettings.current.cashier_can_initiate_payout }"
          @submit.prevent="onSaveThreshold"
        >
          <span class="amount-prefix">₦</span>
          <input
            v-model="thresholdInput" type="number" min="0" step="1000" class="ff" required
            :disabled="clubSettings.current && !clubSettings.current.cashier_can_initiate_payout"
          />
          <button
            class="btn btn--primary" type="submit"
            :disabled="thresholdSaving || (clubSettings.current && !clubSettings.current.cashier_can_initiate_payout)"
          >{{ thresholdSaving ? 'Saving…' : 'Save' }}</button>
        </form>
        <p v-if="thresholdError" class="form-error">{{ thresholdError }}</p>
      </div>

      <div class="card section-card">
        <div class="section-title">FX Rates</div>
        <p v-if="ratesLoading" class="muted">Loading…</p>
        <template v-else>
          <div class="rate-grid">
            <div v-for="(rate, currency) in standingByCurrency" :key="currency" class="rate-chip">
              <span class="rate-currency">{{ currency }}</span>
              <span class="rate-value">{{ Number(rate.rate_to_naira).toLocaleString() }} / ₦1</span>
            </div>
            <p v-if="!Object.keys(standingByCurrency).length" class="muted">No standing rate set yet.</p>
          </div>

          <form class="create-form" @submit.prevent="onSetRate">
            <select v-model="newRate.currency" class="ff">
              <option value="USD">USD</option>
              <option value="GBP">GBP</option>
              <option value="EUR">EUR</option>
              <option value="OTHER">Other</option>
            </select>
            <input v-model="newRate.rate_to_naira" type="number" min="0" step="0.0001" placeholder="Rate to ₦1" required class="ff" />
            <select v-model="newRate.game_day" class="ff">
              <option value="">Standing rate (no override)</option>
              <option v-for="gd in gameDaysForRates" :key="gd.id" :value="gd.id">Override for Game-Day #{{ gd.number }}</option>
            </select>
            <button class="btn btn--primary" type="submit" :disabled="rateSubmitting">{{ rateSubmitting ? 'Setting…' : 'Set rate' }}</button>
          </form>
          <p v-if="rateError" class="form-error">{{ rateError }}</p>

          <div class="rate-history">
            <div class="lbl--muted">Recent changes</div>
            <div v-for="r in recentRates" :key="r.id" class="rate-row">
              <span>{{ r.currency }} &middot; {{ Number(r.rate_to_naira).toLocaleString() }}{{ r.game_day ? ' (game-day override)' : ' (standing)' }}</span>
              <span class="rate-date">{{ formatDate(r.created_at) }}</span>
            </div>
          </div>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 900px; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }
.muted { color: var(--text-secondary); font-size: 13px; }

.section-card { padding: 18px 20px; margin-bottom: 16px; }
.section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.section-note { font-size: 12px; color: var(--text-tertiary); margin: 0 0 12px; line-height: 1.5; }

.table-block { border-bottom: 1px solid var(--border); padding: 4px 0 14px; margin-bottom: 10px; }
.table-block:last-child { border-bottom: none; margin-bottom: 0; }
.row { display: flex; align-items: center; gap: 12px; padding: 10px 0; }
.row-info { flex-grow: 1; min-width: 0; }
.row-name { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }
.row-sub { font-size: 11.5px; color: var(--text-tertiary); }
.link-btn { border: none; background: none; font-size: 12px; font-weight: 700; color: var(--accent-text); cursor: pointer; padding: 0; white-space: nowrap; }

.edit-form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; padding: 6px 0 4px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field-label { font-size: 11px; font-weight: 600; color: var(--text-tertiary); }
.edit-actions { grid-column: 1 / -1; display: flex; gap: 10px; margin-top: 4px; }
.edit-actions .btn { flex: 0 0 auto; padding: 0 18px; }

.ff {
  height: 36px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 10px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-primary);
  background: var(--surface);
}
.ff:focus { outline: none; border-color: var(--accent); }
.form-error {
  grid-column: 1 / -1;
  font-size: 12.5px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  margin-top: 4px;
}

.toggle-list { display: flex; flex-direction: column; }
.toggle-row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border); }
.toggle-row:last-child { border-bottom: none; }

/* The number field that appears directly under a toggle-row once it's on
   (min-player-time minutes, away-max minutes) — sits inside the same
   border-bottom rhythm as the toggle rows around it. */
.sub-form { display: flex; align-items: center; gap: 10px; padding: 4px 0 14px; border-bottom: 1px solid var(--border); }
.sub-form:last-child { border-bottom: none; }
.sub-form .field { flex-direction: row; align-items: center; gap: 8px; }
.sub-form .ff { width: 100px; }

.switch {
  width: 40px;
  height: 24px;
  border-radius: 12px;
  border: none;
  background: var(--border-strong);
  position: relative;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s;
}
.switch--on { background: var(--accent); }
.switch:disabled { opacity: 0.6; cursor: default; }
.switch-knob {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.15s;
}
.switch--on .switch-knob { transform: translateX(16px); }

.create-form { display: flex; align-items: center; gap: 8px; }
.create-form--disabled { opacity: 0.5; }
.amount-prefix { font-family: var(--font-mono); font-size: 13px; color: var(--text-secondary); }

/* FX Rates — carried over from the retired FX Rates section of
   AdminView.vue (2026-09-23), styles included. */
.rate-grid { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.rate-chip {
  display: flex;
  flex-direction: column;
  gap: 2px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  min-width: 110px;
}
.rate-currency { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; color: var(--text-tertiary); }
.rate-value { font-family: var(--font-mono); font-size: 14px; font-weight: 700; color: var(--text-primary); }

.rate-history { margin-top: 16px; border-top: 1px solid var(--border); padding-top: 12px; }
.lbl--muted { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 8px; }
.rate-row { display: flex; align-items: center; justify-content: space-between; padding: 6px 0; font-size: 12.5px; color: var(--text-primary); }
.rate-date { color: var(--text-tertiary); font-size: 11px; }
</style>
