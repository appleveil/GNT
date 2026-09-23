<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/api/axios'
import { useToast } from '@/composables/useToast'

// Owner-only admin page (Phase C, 2026-09-14) — CRUD-lite sections on one
// page rather than separate nav tabs, since each is small: Staff accounts,
// Other Staff (added 2026-09-23), Floor Managers. See PLAN.md's Phase C for
// why each backend piece here is either already-built (Floor Manager PIN
// reset, chips_limit... not here, that's RosterDetailView) or the one
// genuinely new backend addition (staff password reset —
// StaffUserSerializer used for update has no password field at all; POST
// /staff-users/{id}/reset-password/ is new).
//
// FX Rates lived here as a 4th section until 2026-09-23, when it moved to
// the Settings page's own Owner-only block (ClubSettingsView.vue) — same
// data/endpoints, just grouped with the club's other Owner-tunable numbers
// instead of the staff-roster sections here.
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

// ── Other Staff (Masseuse/Dealer/Service) ───────────────────────────────────
// Added 2026-09-23, per the Owner's request to add these three as staff
// types from this page — briefly built as real StaffUser logins (see
// "Staff accounts" above), then corrected the same day once it was
// clarified none of the three ever actually log in. accounts.StaffMember
// is the same named-recipient roster the Masseuse tip category uses (see
// gaming.models.Transaction.masseuse) generalized with a `role` field —
// Dealer/Service are pure record-keeping here, not wired into anything
// else yet. No username/password, no dashboard.
const otherStaff = ref([])
const otherStaffLoading = ref(true)
const newOtherStaff = ref({ name: '', role: 'MASSEUSE' })
const otherStaffCreating = ref(false)
const otherStaffError = ref('')
const OTHER_STAFF_ROLE_LABEL = { MASSEUSE: 'Masseuse', DEALER: 'Dealer', SERVICE: 'Service' }

async function loadOtherStaff() {
  otherStaffLoading.value = true
  try {
    const { data } = await api.get('/staff-members/')
    otherStaff.value = data
  } catch {
    toast.error('Could not load staff.')
  } finally {
    otherStaffLoading.value = false
  }
}

async function onCreateOtherStaff() {
  otherStaffError.value = ''
  otherStaffCreating.value = true
  try {
    await api.post('/staff-members/', newOtherStaff.value)
    newOtherStaff.value = { name: '', role: newOtherStaff.value.role }
    await loadOtherStaff()
    toast.success('Staff member added.')
  } catch (err) {
    otherStaffError.value = Object.values(err.response?.data || {})[0]?.[0] || 'Could not add this person.'
  } finally {
    otherStaffCreating.value = false
  }
}

async function onToggleOtherStaffActive(person) {
  try {
    const { data } = await api.patch(`/staff-members/${person.id}/`, { is_active: !person.is_active })
    Object.assign(person, data)
  } catch {
    toast.error('Could not update this person.')
  }
}

// ── Floor Managers ────────────────────────────────────────────────────────
const floorManagers = ref([])
const fmLoading = ref(true)
// staff_user (added 2026-09-17) optionally links this PIN-witness record to
// that same person's real Floor Manager login — created separately, above,
// via the Staff accounts section (role: Floor Manager); '' = unlinked,
// same as before.
const newFm = ref({ name: '', pin: '', staff_user: '' })
const floorManagerLogins = computed(() => staff.value.filter(u => u.role === 'FLOOR_MANAGER'))
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
    await api.post('/floor-managers/', { ...newFm.value, staff_user: newFm.value.staff_user || null })
    newFm.value = { name: '', pin: '', staff_user: '' }
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

onMounted(() => {
  loadStaff()
  loadOtherStaff()
  loadFloorManagers()
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Admin</h1>
      <p>Staff accounts, other staff, and Floor Managers.</p>
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
            <option value="FLOOR_MANAGER">Floor Manager</option>
          </select>
          <input v-model="newStaff.password" type="password" placeholder="Password" required class="ff" />
          <button class="btn btn--primary" type="submit" :disabled="staffCreating">{{ staffCreating ? 'Adding…' : '+ Add staff' }}</button>
        </form>
        <p v-if="staffError" class="form-error">{{ staffError }}</p>
      </template>
    </div>

    <div class="card section-card">
      <div class="section-title">Other Staff</div>
      <p class="section-note">Masseuse, Dealer, Service — named records only, no login or dashboard of their own.</p>
      <p v-if="otherStaffLoading" class="muted">Loading…</p>
      <template v-else>
        <p v-if="!otherStaff.length" class="muted">No one added yet.</p>
        <div v-for="p in otherStaff" :key="p.id" class="row">
          <div class="row-info">
            <div class="row-name">{{ p.name }}</div>
            <div class="row-sub">{{ OTHER_STAFF_ROLE_LABEL[p.role] }}</div>
          </div>
          <span class="badge" :class="p.is_active ? 'badge--approved' : 'badge--closed'">{{ p.is_active ? 'active' : 'inactive' }}</span>
          <button class="link-btn" type="button" @click="onToggleOtherStaffActive(p)">{{ p.is_active ? 'Deactivate' : 'Activate' }}</button>
        </div>

        <form class="create-form" @submit.prevent="onCreateOtherStaff">
          <input v-model="newOtherStaff.name" type="text" placeholder="Name" required class="ff" />
          <select v-model="newOtherStaff.role" class="ff">
            <option value="MASSEUSE">Masseuse</option>
            <option value="DEALER">Dealer</option>
            <option value="SERVICE">Service</option>
          </select>
          <button class="btn btn--primary" type="submit" :disabled="otherStaffCreating">{{ otherStaffCreating ? 'Adding…' : '+ Add' }}</button>
        </form>
        <p v-if="otherStaffError" class="form-error">{{ otherStaffError }}</p>
      </template>
    </div>

    <div class="card section-card">
      <div class="section-title">Floor Managers</div>
      <p class="section-note">
        This is the physical-count PIN-witness credential — separate from a Floor Manager's own login
        (create that above, role: Floor Manager), optionally linked to it below for the same person.
      </p>
      <p v-if="fmLoading" class="muted">Loading…</p>
      <template v-else>
        <div v-for="fm in floorManagers" :key="fm.id" class="row">
          <div class="row-info">
            <div class="row-name">{{ fm.name }}</div>
            <div v-if="fm.staff_user" class="row-sub">linked to {{ staff.find(u => u.id === fm.staff_user)?.username || 'a login' }}</div>
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
          <select v-model="newFm.staff_user" class="ff">
            <option value="">No linked login</option>
            <option v-for="u in floorManagerLogins" :key="u.id" :value="u.id">Link to {{ u.username }}</option>
          </select>
          <button class="btn btn--primary" type="submit" :disabled="fmCreating">{{ fmCreating ? 'Adding…' : '+ Add Floor Manager' }}</button>
        </form>
        <p v-if="fmError" class="form-error">{{ fmError }}</p>
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

.section-note { font-size: 12px; color: var(--text-tertiary); margin-bottom: 12px; line-height: 1.5; }
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
</style>
