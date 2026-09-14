<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/api/axios'
import { useToast } from '@/composables/useToast'

// Owner-only admin page (Phase C, 2026-09-14) — three CRUD-lite sections on
// one page rather than three separate nav tabs, since each is small: Staff
// accounts, Floor Managers, FX Rates. See PLAN.md's Phase C for why each
// backend piece here is either already-built (Floor Manager PIN reset,
// chips_limit... not here, that's RosterDetailView) or the one genuinely new
// backend addition (staff password reset — StaffUserSerializer used for
// update has no password field at all; POST /staff-users/{id}/reset-password/
// is new).
const toast = useToast()

// ── Staff accounts ────────────────────────────────────────────────────────
const staff = ref([])
const staffLoading = ref(true)
const newStaff = ref({ username: '', first_name: '', last_name: '', role: 'CASHIER', password: '' })
const staffCreating = ref(false)
const staffError = ref('')
const resetTargetId = ref(null) // staff user id currently showing the reset-password inline form
const resetPassword = ref('')
const resetSubmitting = ref(false)

async function loadStaff() {
  staffLoading.value = true
  try {
    const { data } = await api.get('/staff-users/')
    staff.value = data
  } catch {
    toast.error('Could not load staff accounts.')
  } finally {
    staffLoading.value = false
  }
}

async function onCreateStaff() {
  staffError.value = ''
  staffCreating.value = true
  try {
    await api.post('/staff-users/', newStaff.value)
    newStaff.value = { username: '', first_name: '', last_name: '', role: 'CASHIER', password: '' }
    await loadStaff()
    toast.success('Staff account created.')
  } catch (err) {
    staffError.value = Object.values(err.response?.data || {})[0]?.[0] || 'Could not create this account.'
  } finally {
    staffCreating.value = false
  }
}

async function onToggleStaffActive(user) {
  try {
    const { data } = await api.patch(`/staff-users/${user.id}/`, { is_active: !user.is_active })
    Object.assign(user, data)
  } catch {
    toast.error('Could not update that account.')
  }
}

function onStartReset(user) {
  resetTargetId.value = user.id
  resetPassword.value = ''
}

async function onSubmitReset(user) {
  resetSubmitting.value = true
  try {
    await api.post(`/staff-users/${user.id}/reset-password/`, { password: resetPassword.value })
    resetTargetId.value = null
    toast.success(`${user.username}'s password was reset.`)
  } catch (err) {
    toast.error(err.response?.data?.password?.[0] || 'Could not reset that password.')
  } finally {
    resetSubmitting.value = false
  }
}

// ── Floor Managers ────────────────────────────────────────────────────────
const floorManagers = ref([])
const fmLoading = ref(true)
const newFm = ref({ name: '', pin: '' })
const fmCreating = ref(false)
const fmError = ref('')
const fmResetTargetId = ref(null)
const fmResetPin = ref('')
const fmResetSubmitting = ref(false)

async function loadFloorManagers() {
  fmLoading.value = true
  try {
    const { data } = await api.get('/floor-managers/')
    floorManagers.value = data
  } catch {
    toast.error('Could not load Floor Managers.')
  } finally {
    fmLoading.value = false
  }
}

async function onCreateFm() {
  fmError.value = ''
  fmCreating.value = true
  try {
    await api.post('/floor-managers/', newFm.value)
    newFm.value = { name: '', pin: '' }
    await loadFloorManagers()
    toast.success('Floor Manager added.')
  } catch (err) {
    fmError.value = Object.values(err.response?.data || {})[0]?.[0] || 'Could not add this Floor Manager.'
  } finally {
    fmCreating.value = false
  }
}

async function onToggleFmActive(fm) {
  try {
    const { data } = await api.patch(`/floor-managers/${fm.id}/`, { is_active: !fm.is_active })
    Object.assign(fm, data)
  } catch {
    toast.error('Could not update that Floor Manager.')
  }
}

function onStartFmReset(fm) {
  fmResetTargetId.value = fm.id
  fmResetPin.value = ''
}

async function onSubmitFmReset(fm) {
  fmResetSubmitting.value = true
  try {
    await api.patch(`/floor-managers/${fm.id}/`, { pin: fmResetPin.value })
    fmResetTargetId.value = null
    toast.success(`${fm.name}'s PIN was reset.`)
  } catch (err) {
    toast.error(err.response?.data?.pin?.[0] || 'Could not reset that PIN.')
  } finally {
    fmResetSubmitting.value = false
  }
}

// ── FX Rates ───────────────────────────────────────────────────────────────
const rates = ref([])
const ratesLoading = ref(true)
const gameDays = ref([])
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
    gameDays.value = gameDaysRes.data
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

onMounted(() => {
  loadStaff()
  loadFloorManagers()
  loadRates()
})

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Admin</h1>
      <p>Staff accounts, Floor Managers, and FX rates.</p>
    </div>

    <div class="card section-card">
      <div class="section-title">Staff accounts</div>
      <p v-if="staffLoading" class="muted">Loading…</p>
      <template v-else>
        <div v-for="u in staff" :key="u.id" class="row">
          <div class="row-info">
            <div class="row-name">{{ u.first_name || u.username }} {{ u.last_name }}</div>
            <div class="row-sub">{{ u.username }} &middot; {{ u.role }}</div>
          </div>
          <span class="badge" :class="u.is_active ? 'badge--approved' : 'badge--closed'">{{ u.is_active ? 'active' : 'inactive' }}</span>
          <button class="link-btn" type="button" @click="onToggleStaffActive(u)">{{ u.is_active ? 'Deactivate' : 'Activate' }}</button>
          <button class="link-btn" type="button" @click="onStartReset(u)">Reset password</button>
        </div>
        <div v-if="resetTargetId" class="inline-form">
          <input v-model="resetPassword" type="password" placeholder="New password (min 8 chars)" class="inline-input" />
          <button class="btn btn--secondary" type="button" :disabled="resetSubmitting || resetPassword.length < 8" @click="onSubmitReset(staff.find(u => u.id === resetTargetId))">
            {{ resetSubmitting ? 'Saving…' : 'Save' }}
          </button>
          <button class="link-btn link-btn--muted" type="button" @click="resetTargetId = null">Cancel</button>
        </div>

        <form class="create-form" @submit.prevent="onCreateStaff">
          <input v-model="newStaff.username" type="text" placeholder="Username" required class="ff" />
          <input v-model="newStaff.first_name" type="text" placeholder="First name" class="ff" />
          <input v-model="newStaff.last_name" type="text" placeholder="Last name" class="ff" />
          <select v-model="newStaff.role" class="ff">
            <option value="CASHIER">Cashier</option>
            <option value="ACCOUNTANT">Accountant</option>
            <option value="OWNER">Owner</option>
          </select>
          <input v-model="newStaff.password" type="password" placeholder="Password" required class="ff" />
          <button class="btn btn--primary" type="submit" :disabled="staffCreating">{{ staffCreating ? 'Adding…' : '+ Add staff' }}</button>
        </form>
        <p v-if="staffError" class="form-error">{{ staffError }}</p>
      </template>
    </div>

    <div class="card section-card">
      <div class="section-title">Floor Managers</div>
      <p v-if="fmLoading" class="muted">Loading…</p>
      <template v-else>
        <div v-for="fm in floorManagers" :key="fm.id" class="row">
          <div class="row-info">
            <div class="row-name">{{ fm.name }}</div>
          </div>
          <span class="badge" :class="fm.is_active ? 'badge--approved' : 'badge--closed'">{{ fm.is_active ? 'active' : 'inactive' }}</span>
          <button class="link-btn" type="button" @click="onToggleFmActive(fm)">{{ fm.is_active ? 'Deactivate' : 'Activate' }}</button>
          <button class="link-btn" type="button" @click="onStartFmReset(fm)">Reset PIN</button>
        </div>
        <div v-if="fmResetTargetId" class="inline-form">
          <input v-model="fmResetPin" type="password" placeholder="New PIN (4-8 chars)" class="inline-input" />
          <button class="btn btn--secondary" type="button" :disabled="fmResetSubmitting || fmResetPin.length < 4" @click="onSubmitFmReset(floorManagers.find(f => f.id === fmResetTargetId))">
            {{ fmResetSubmitting ? 'Saving…' : 'Save' }}
          </button>
          <button class="link-btn link-btn--muted" type="button" @click="fmResetTargetId = null">Cancel</button>
        </div>

        <form class="create-form" @submit.prevent="onCreateFm">
          <input v-model="newFm.name" type="text" placeholder="Name" required class="ff" />
          <input v-model="newFm.pin" type="password" placeholder="PIN (4-8 chars)" required class="ff" />
          <button class="btn btn--primary" type="submit" :disabled="fmCreating">{{ fmCreating ? 'Adding…' : '+ Add Floor Manager' }}</button>
        </form>
        <p v-if="fmError" class="form-error">{{ fmError }}</p>
      </template>
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
            <option v-for="gd in gameDays" :key="gd.id" :value="gd.id">Override for Game-Day #{{ gd.number }}</option>
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
  </div>
</template>

<style scoped>
.page { max-width: 900px; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }
.muted { color: var(--text-secondary); font-size: 13px; }

.section-card { padding: 18px 20px; margin-bottom: 16px; }
.section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; }

.row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border); }
.row-info { flex-grow: 1; min-width: 0; }
.row-name { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }
.row-sub { font-size: 11.5px; color: var(--text-tertiary); }
.link-btn { border: none; background: none; font-size: 12px; font-weight: 700; color: var(--accent-text); cursor: pointer; padding: 0; white-space: nowrap; }
.link-btn--muted { color: var(--text-tertiary); font-weight: 500; }

.inline-form { display: flex; align-items: center; gap: 8px; padding: 12px 0; border-bottom: 1px solid var(--border); }
.inline-input {
  height: 36px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 10px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-primary);
  background: var(--surface);
}
.inline-input:focus { outline: none; border-color: var(--accent); }

.create-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 14px; }
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
  font-size: 12.5px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  margin-top: 8px;
}

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
