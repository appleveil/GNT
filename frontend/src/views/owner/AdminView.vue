<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/api/axios'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { useFormValidation, required, minLength } from '@/composables/useFormValidation'
import { readApiError } from '@/utils/apiError'
import ActivityLogList from '@/components/shared/ActivityLogList.vue'

// Admin page (Phase C, 2026-09-14) — CRUD-lite sections on one page rather
// than separate nav tabs, since each is small: Staff accounts, Other Staff
// (added 2026-09-23), Floor Managers. See PLAN.md's Phase C for why each
// backend piece here is either already-built (Floor Manager PIN reset,
// chips_limit... not here, that's the Players table's own ⋮ menu) or the one genuinely
// new backend addition (staff password reset — StaffUserSerializer used
// for update has no password field at all; POST
// /staff-users/{id}/reset-password/ is new).
//
// FX Rates lived here as a 4th section until 2026-09-23, when it moved to
// the Settings page's own Owner-only block (ClubSettingsView.vue) — same
// data/endpoints, just grouped with the club's other Owner-tunable numbers
// instead of the staff-roster sections here.
//
// 2026-09-25: this page is no longer Owner-only (see router/index.js — the
// route now allows BACK_OFFICE_ROLES) so the Accountant can reach the new
// "Account Codes" section below. Every OTHER section here still needs a
// real login/PIN and stays wrapped in `v-if="auth.isOwner"` — broadening
// the route doesn't mean broadening what an Accountant can see on it.
const auth = useAuthStore()
const toast = useToast()

// ── Staff accounts ────────────────────────────────────────────────────────
const staff = ref([])
const staffLoading = ref(true)
const newStaff = ref({ username: '', first_name: '', last_name: '', role: 'CASHIER', password: '' })
const staffCreating = ref(false)
const resetTargetId = ref(null) // staff user id currently showing the reset-password inline form
const resetPassword = ref('')
const resetSubmitting = ref(false)

const newStaffUsername = computed({ get: () => newStaff.value.username, set: v => { newStaff.value.username = v } })
const newStaffPassword = computed({ get: () => newStaff.value.password, set: v => { newStaff.value.password = v } })
const {
  touched: staffTouched, errors: staffErrors, isValid: staffIsValid, formError: staffFormError,
  touch: touchStaff, touchAll: touchAllStaff, applyServerErrors: applyStaffServerErrors, reset: resetStaffValidation,
} = useFormValidation({
  username: { value: newStaffUsername, rules: [required('A username is required.')] },
  password: { value: newStaffPassword, rules: [required('A password is required.'), minLength(8)] },
})

const {
  touched: resetTouched, errors: resetErrors, isValid: resetIsValid, formError: resetFormError,
  touch: touchResetPassword, touchAll: touchAllReset, applyServerErrors: applyResetServerErrors, reset: resetResetValidation,
} = useFormValidation({
  password: { value: resetPassword, rules: [required('A password is required.'), minLength(8)] },
})

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
  touchAllStaff()
  if (!staffIsValid.value) return
  staffCreating.value = true
  try {
    await api.post('/staff-users/', newStaff.value)
    newStaff.value = { username: '', first_name: '', last_name: '', role: 'CASHIER', password: '' }
    resetStaffValidation()
    await loadStaff()
    toast.success('Staff account created.')
  } catch (err) {
    applyStaffServerErrors(err)
  } finally {
    staffCreating.value = false
  }
}

async function onToggleStaffActive(user) {
  try {
    const { data } = await api.patch(`/staff-users/${user.id}/`, { is_active: !user.is_active })
    Object.assign(user, data)
  } catch (err) {
    toast.error(readApiError(err, 'Could not update that account.').message)
  }
}

function onStartReset(user) {
  resetTargetId.value = user.id
  resetPassword.value = ''
  resetResetValidation()
}

async function onSubmitReset(user) {
  touchAllReset()
  if (!resetIsValid.value) return
  resetSubmitting.value = true
  try {
    await api.post(`/staff-users/${user.id}/reset-password/`, { password: resetPassword.value })
    resetTargetId.value = null
    toast.success(`${user.username}'s password was reset.`)
  } catch (err) {
    applyResetServerErrors(err)
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
const OTHER_STAFF_ROLE_LABEL = { MASSEUSE: 'Masseuse', DEALER: 'Dealer', SERVICE: 'Service' }

const newOtherStaffName = computed({ get: () => newOtherStaff.value.name, set: v => { newOtherStaff.value.name = v } })
const {
  touched: otherStaffTouched, errors: otherStaffErrors, isValid: otherStaffIsValid, formError: otherStaffFormError,
  touch: touchOtherStaff, touchAll: touchAllOtherStaff, applyServerErrors: applyOtherStaffServerErrors, reset: resetOtherStaffValidation,
} = useFormValidation({
  name: { value: newOtherStaffName, rules: [required('A name is required.')] },
})

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
  touchAllOtherStaff()
  if (!otherStaffIsValid.value) return
  otherStaffCreating.value = true
  try {
    await api.post('/staff-members/', newOtherStaff.value)
    newOtherStaff.value = { name: '', role: newOtherStaff.value.role }
    resetOtherStaffValidation()
    await loadOtherStaff()
    toast.success('Staff member added.')
  } catch (err) {
    applyOtherStaffServerErrors(err)
  } finally {
    otherStaffCreating.value = false
  }
}

async function onToggleOtherStaffActive(person) {
  try {
    const { data } = await api.patch(`/staff-members/${person.id}/`, { is_active: !person.is_active })
    Object.assign(person, data)
  } catch (err) {
    toast.error(readApiError(err, 'Could not update this person.').message)
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
const fmResetTargetId = ref(null)
const fmResetPin = ref('')
const fmResetSubmitting = ref(false)

const maxLength = (n, message = `Must be at most ${n} characters.`) => value => (value && String(value).length > n ? message : null)

const newFmName = computed({ get: () => newFm.value.name, set: v => { newFm.value.name = v } })
const newFmPin = computed({ get: () => newFm.value.pin, set: v => { newFm.value.pin = v } })
const {
  touched: fmTouched, errors: fmErrors, isValid: fmIsValid, formError: fmFormError,
  touch: touchFm, touchAll: touchAllFm, applyServerErrors: applyFmServerErrors, reset: resetFmValidation,
} = useFormValidation({
  name: { value: newFmName, rules: [required('A name is required.')] },
  pin: { value: newFmPin, rules: [required('A PIN is required.'), minLength(4), maxLength(8)] },
})

const {
  touched: fmResetTouched, errors: fmResetErrors, isValid: fmResetIsValid, formError: fmResetFormError,
  touch: touchFmResetPin, touchAll: touchAllFmReset, applyServerErrors: applyFmResetServerErrors, reset: resetFmResetValidation,
} = useFormValidation({
  pin: { value: fmResetPin, rules: [required('A PIN is required.'), minLength(4), maxLength(8)] },
})

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
  touchAllFm()
  if (!fmIsValid.value) return
  fmCreating.value = true
  try {
    await api.post('/floor-managers/', { ...newFm.value, staff_user: newFm.value.staff_user || null })
    newFm.value = { name: '', pin: '', staff_user: '' }
    resetFmValidation()
    await loadFloorManagers()
    toast.success('Floor Manager added.')
  } catch (err) {
    applyFmServerErrors(err)
  } finally {
    fmCreating.value = false
  }
}

async function onToggleFmActive(fm) {
  try {
    const { data } = await api.patch(`/floor-managers/${fm.id}/`, { is_active: !fm.is_active })
    Object.assign(fm, data)
  } catch (err) {
    toast.error(readApiError(err, 'Could not update that Floor Manager.').message)
  }
}

function onStartFmReset(fm) {
  fmResetTargetId.value = fm.id
  fmResetPin.value = ''
  resetFmResetValidation()
}

async function onSubmitFmReset(fm) {
  touchAllFmReset()
  if (!fmResetIsValid.value) return
  fmResetSubmitting.value = true
  try {
    await api.patch(`/floor-managers/${fm.id}/`, { pin: fmResetPin.value })
    fmResetTargetId.value = null
    toast.success(`${fm.name}'s PIN was reset.`)
  } catch (err) {
    applyFmResetServerErrors(err)
  } finally {
    fmResetSubmitting.value = false
  }
}

// ── Account Codes (DVAs) — Owner or Accountant ──────────────────────────
// Added 2026-09-25: the pool AddPlayerModal.vue's new-player flow
// auto-consumes from (see gaming.services._assign_next_account_code)
// instead of a Cashier typing a code in by hand. Extended 2026-09-26 with
// the real bank details each code stands for (account_number,
// account_name) — a "staging area" pattern: rows collect in `stagedRows`
// from either the manual "+ Add row" form or a parsed file upload, shown
// in one review table, and submitted together as one batch. Matches how a
// club actually gets these — a bank hands over a spreadsheet of dedicated
// accounts, not one at a time.
const accountCodes = ref([])
const accountCodesLoading = ref(true)
const accountCodesCreating = ref(false)
const accountCodesError = ref('')

const stagedRows = ref([]) // [{ code, account_number, account_name }]
const manualRow = ref({ code: '', account_number: '', account_name: '' })
const fileError = ref('') // fatal — nothing in the file could be read at all
const fileWarnings = ref([]) // per-row issues from a file that otherwise parsed fine — added rows still got staged
const stageError = ref('') // manual "+ Add row" rejection (missing field / duplicate)
const fileInputEl = ref(null)

const availableCodesCount = computed(() => accountCodes.value.filter(c => !c.is_linked).length)

async function loadAccountCodes() {
  accountCodesLoading.value = true
  try {
    const { data } = await api.get('/account-codes/')
    accountCodes.value = data
  } catch {
    toast.error('Could not load account codes.')
  } finally {
    accountCodesLoading.value = false
  }
}

// Shared by the manual "+ Add row" form and a parsed file upload — both
// funnel through here so a duplicate or missing field is caught the same
// way either source. Checks against the already-loaded pool (accountCodes)
// AND whatever's already staged (stagedRows, plus any file rows already
// accepted earlier in the same pass), since two staged rows would otherwise
// collide silently until the backend's own batch check rejected them.
function validateRow(row, label) {
  if (!(row.code && row.account_number && row.account_name)) {
    return `${label}: code, account number, and account name are all required.`
  }
  if (!/^\d{10}$/.test(row.account_number)) {
    return `${label}: account number must be exactly 10 digits.`
  }
  const dupeInPool = accountCodes.value.some(c => c.code === row.code || c.account_number === row.account_number)
  if (dupeInPool) {
    return `${label}: already exists in the pool.`
  }
  const dupeStaged = stagedRows.value.some(r => r.code === row.code || r.account_number === row.account_number)
  if (dupeStaged) {
    return `${label}: already staged below.`
  }
  return null
}

function onAddManualRow() {
  const row = {
    code: manualRow.value.code.trim(),
    account_number: manualRow.value.account_number.trim(),
    account_name: manualRow.value.account_name.trim(),
  }
  const error = validateRow(row, row.code || row.account_number || 'New row')
  if (error) {
    stageError.value = error
    return
  }
  stageError.value = ''
  stagedRows.value.push(row)
  manualRow.value = { code: '', account_number: '', account_name: '' }
}

function onRemoveStagedRow(index) {
  stagedRows.value.splice(index, 1)
}

// Column headers vary by whoever built the spreadsheet ("Account No" vs
// "account_number" vs "Number") — matched case/space/underscore-insensitive
// against a few likely spellings rather than requiring one exact header.
function normalizeUploadedRow(raw) {
  const find = (...keys) => {
    for (const rawKey of Object.keys(raw)) {
      const norm = rawKey.toLowerCase().replace(/[\s_-]/g, '')
      if (keys.includes(norm)) return String(raw[rawKey] ?? '').trim()
    }
    return ''
  }
  return {
    code: find('code', 'accountcode'),
    account_number: find('accountnumber', 'number', 'acctnumber', 'accountno'),
    account_name: find('accountname', 'name', 'acctname'),
  }
}

// Scans every parsed row rather than stopping at the first problem — a
// spreadsheet with one bad row shouldn't cost the other 49 good ones. Valid
// rows get staged immediately (in file order), so a later row's duplicate
// check against stagedRows also catches two rows within the SAME file
// colliding with each other, not just against the already-loaded pool.
// Blank rows (no fields at all — common as spreadsheet padding) are skipped
// silently; anything with at least one field but not all three, or a real
// collision, is reported by its actual spreadsheet row number.
async function onFileSelected(e) {
  const file = e.target.files[0]
  if (fileInputEl.value) fileInputEl.value.value = '' // allow re-selecting the same file later
  if (!file) return
  fileError.value = ''
  fileWarnings.value = []
  try {
    const XLSX = await import('xlsx')
    const buffer = await file.arrayBuffer()
    const workbook = XLSX.read(buffer, { type: 'array' })
    const sheet = workbook.Sheets[workbook.SheetNames[0]]
    const raw = XLSX.utils.sheet_to_json(sheet, { defval: '' })
    if (!raw.length) {
      fileError.value = 'No rows found — the first row should be a header: Code, Account Number, Account Name.'
      return
    }
    const warnings = []
    let addedCount = 0
    raw.forEach((rawRow, i) => {
      const row = normalizeUploadedRow(rawRow)
      if (!(row.code || row.account_number || row.account_name)) return // blank padding row — not an error
      const rowNumber = i + 2 // +1 for the header row, +1 to go from 0- to 1-indexed
      const error = validateRow(row, `Row ${rowNumber}`)
      if (error) {
        warnings.push(error)
        return
      }
      stagedRows.value.push(row)
      addedCount += 1
    })
    if (!addedCount && !warnings.length) {
      fileError.value = 'No rows found — the first row should be a header: Code, Account Number, Account Name.'
      return
    }
    fileWarnings.value = warnings
  } catch {
    fileError.value = 'Could not read this file — check it’s a valid CSV, XLS, or XLSX.'
  }
}

async function onSubmitStagedRows() {
  accountCodesError.value = ''
  if (!stagedRows.value.length) return
  accountCodesCreating.value = true
  try {
    const { data } = await api.post('/account-codes/', { codes: stagedRows.value })
    stagedRows.value = []
    fileWarnings.value = []
    await loadAccountCodes()
    toast.success(`${data.created.length} code${data.created.length === 1 ? '' : 's'} added.`)
    if (data.errors?.length) accountCodesError.value = data.errors.join(' ')
  } catch (err) {
    accountCodesError.value = err.response?.data?.errors?.join(' ') || readApiError(err, 'Could not add these codes.').message
  } finally {
    accountCodesCreating.value = false
  }
}

onMounted(() => {
  loadAccountCodes()
  if (auth.isOwner) {
    loadStaff()
    loadOtherStaff()
    loadFloorManagers()
  }
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Admin</h1>
      <p>{{ auth.isOwner ? 'Staff accounts, other staff, Floor Managers, and account codes.' : 'Account codes.' }}</p>
    </div>

    <div class="card section-card">
      <div class="section-title">Account Codes</div>
      <p class="section-note">
        Real DVAs staged ahead of time — the next available one here is auto-assigned to every new
        player registered, so a Cashier never types one in by hand.
        <template v-if="!accountCodesLoading"> {{ availableCodesCount }} available of {{ accountCodes.length }}.</template>
      </p>
      <p v-if="accountCodesLoading" class="muted">Loading…</p>
      <template v-else>
        <p v-if="!accountCodes.length" class="muted">No codes added yet.</p>
        <div v-for="c in accountCodes" :key="c.id" class="row">
          <div class="row-info">
            <div class="row-name">{{ c.code }} <span class="row-sub">— {{ c.account_number }} &middot; {{ c.account_name }}</span></div>
            <div v-if="c.linked_player_name" class="row-sub">linked to {{ c.linked_player_name }}</div>
          </div>
          <span class="badge" :class="c.is_linked ? 'badge--closed' : 'badge--approved'">{{ c.is_linked ? 'linked' : 'available' }}</span>
        </div>

        <div class="stage-block">
          <div class="stage-block-title">Add codes</div>

          <div class="upload-row">
            <label class="btn btn--secondary upload-btn">
              Upload CSV / XLS / XLSX
              <input ref="fileInputEl" type="file" accept=".csv,.xls,.xlsx" class="file-input" @change="onFileSelected" />
            </label>
            <a href="/samples/account-codes-sample.csv" download class="sample-link">Download sample CSV</a>
            <span class="upload-hint">Header row: Code, Account Number, Account Name (any order)</span>
          </div>
          <p v-if="fileError" class="form-error">{{ fileError }}</p>
          <div v-if="fileWarnings.length" class="form-warning">
            <div class="form-warning-title">
              {{ fileWarnings.length }} row{{ fileWarnings.length === 1 ? '' : 's' }} skipped from that file:
            </div>
            <ul class="form-warning-list">
              <li v-for="(w, i) in fileWarnings" :key="i">{{ w }}</li>
            </ul>
          </div>

          <form class="manual-row-form" @submit.prevent="onAddManualRow">
            <input v-model="manualRow.code" type="text" placeholder="Code (e.g. WWI 20)" class="ff" />
            <input v-model="manualRow.account_number" type="text" placeholder="Account number" class="ff" />
            <input v-model="manualRow.account_name" type="text" placeholder="Account name" class="ff" />
            <button class="btn btn--secondary" type="submit">+ Add row</button>
          </form>
          <p v-if="stageError" class="form-error">{{ stageError }}</p>

          <template v-if="stagedRows.length">
            <div class="staged-list">
              <div v-for="(r, i) in stagedRows" :key="i" class="staged-row">
                <span class="staged-code">{{ r.code }}</span>
                <span class="row-sub">{{ r.account_number }} &middot; {{ r.account_name }}</span>
                <button class="remove-btn" type="button" title="Remove" @click="onRemoveStagedRow(i)">&times;</button>
              </div>
            </div>
            <button class="btn btn--primary" type="button" :disabled="accountCodesCreating" @click="onSubmitStagedRows">
              {{ accountCodesCreating ? 'Adding…' : `+ Add ${stagedRows.length} code${stagedRows.length === 1 ? '' : 's'}` }}
            </button>
          </template>
        </div>
        <p v-if="accountCodesError" class="form-error">{{ accountCodesError }}</p>
      </template>
    </div>

    <!-- Visible to both roles, like Account Codes above — Owner sees every
         entry, Accountant sees every Cashier's plus their own (see
         gaming.selectors.visible_activity). -->
    <div class="card section-card">
      <div class="section-title">Activity log</div>
      <ActivityLogList />
    </div>

    <template v-if="auth.isOwner">
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
          <div class="field">
            <input
              v-model="resetPassword" type="password" placeholder="New password (min 8 chars)" class="inline-input"
              :class="{ 'input--invalid': resetTouched.password && resetErrors.password }"
              @blur="touchResetPassword('password')"
            />
            <p v-if="resetTouched.password && resetErrors.password" class="field-error">{{ resetErrors.password }}</p>
          </div>
          <button class="btn btn--secondary" type="button" :disabled="resetSubmitting || !resetIsValid" @click="onSubmitReset(staff.find(u => u.id === resetTargetId))">
            {{ resetSubmitting ? 'Saving…' : 'Save' }}
          </button>
          <button class="link-btn link-btn--muted" type="button" @click="resetTargetId = null">Cancel</button>
        </div>
        <p v-if="resetTargetId && resetFormError" class="form-error">{{ resetFormError }}</p>

        <form class="create-form" novalidate @submit.prevent="onCreateStaff">
          <div class="field">
            <input
              v-model="newStaff.username" type="text" placeholder="Username" class="ff"
              :class="{ 'input--invalid': staffTouched.username && staffErrors.username }"
              @blur="touchStaff('username')"
            />
            <p v-if="staffTouched.username && staffErrors.username" class="field-error">{{ staffErrors.username }}</p>
          </div>
          <input v-model="newStaff.first_name" type="text" placeholder="First name" class="ff" />
          <input v-model="newStaff.last_name" type="text" placeholder="Last name" class="ff" />
          <select v-model="newStaff.role" class="ff">
            <option value="CASHIER">Cashier</option>
            <option value="ACCOUNTANT">Accountant</option>
            <option value="OWNER">Owner</option>
            <option value="FLOOR_MANAGER">Floor Manager</option>
          </select>
          <div class="field">
            <input
              v-model="newStaff.password" type="password" placeholder="Password" class="ff"
              :class="{ 'input--invalid': staffTouched.password && staffErrors.password }"
              @blur="touchStaff('password')"
            />
            <p v-if="staffTouched.password && staffErrors.password" class="field-error">{{ staffErrors.password }}</p>
          </div>
          <button class="btn btn--primary" type="submit" :disabled="staffCreating || !staffIsValid">{{ staffCreating ? 'Adding…' : '+ Add staff' }}</button>
        </form>
        <p v-if="staffFormError" class="form-error">{{ staffFormError }}</p>
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

        <form class="create-form" novalidate @submit.prevent="onCreateOtherStaff">
          <div class="field">
            <input
              v-model="newOtherStaff.name" type="text" placeholder="Name" class="ff"
              :class="{ 'input--invalid': otherStaffTouched.name && otherStaffErrors.name }"
              @blur="touchOtherStaff('name')"
            />
            <p v-if="otherStaffTouched.name && otherStaffErrors.name" class="field-error">{{ otherStaffErrors.name }}</p>
          </div>
          <select v-model="newOtherStaff.role" class="ff">
            <option value="MASSEUSE">Masseuse</option>
            <option value="DEALER">Dealer</option>
            <option value="SERVICE">Service</option>
          </select>
          <button class="btn btn--primary" type="submit" :disabled="otherStaffCreating || !otherStaffIsValid">{{ otherStaffCreating ? 'Adding…' : '+ Add' }}</button>
        </form>
        <p v-if="otherStaffFormError" class="form-error">{{ otherStaffFormError }}</p>
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
          <div class="field">
            <input
              v-model="fmResetPin" type="password" placeholder="New PIN (4-8 chars)" class="inline-input"
              :class="{ 'input--invalid': fmResetTouched.pin && fmResetErrors.pin }"
              @blur="touchFmResetPin('pin')"
            />
            <p v-if="fmResetTouched.pin && fmResetErrors.pin" class="field-error">{{ fmResetErrors.pin }}</p>
          </div>
          <button class="btn btn--secondary" type="button" :disabled="fmResetSubmitting || !fmResetIsValid" @click="onSubmitFmReset(floorManagers.find(f => f.id === fmResetTargetId))">
            {{ fmResetSubmitting ? 'Saving…' : 'Save' }}
          </button>
          <button class="link-btn link-btn--muted" type="button" @click="fmResetTargetId = null">Cancel</button>
        </div>
        <p v-if="fmResetTargetId && fmResetFormError" class="form-error">{{ fmResetFormError }}</p>

        <form class="create-form" novalidate @submit.prevent="onCreateFm">
          <div class="field">
            <input
              v-model="newFm.name" type="text" placeholder="Name" class="ff"
              :class="{ 'input--invalid': fmTouched.name && fmErrors.name }"
              @blur="touchFm('name')"
            />
            <p v-if="fmTouched.name && fmErrors.name" class="field-error">{{ fmErrors.name }}</p>
          </div>
          <div class="field">
            <input
              v-model="newFm.pin" type="password" placeholder="PIN (4-8 chars)" class="ff"
              :class="{ 'input--invalid': fmTouched.pin && fmErrors.pin }"
              @blur="touchFm('pin')"
            />
            <p v-if="fmTouched.pin && fmErrors.pin" class="field-error">{{ fmErrors.pin }}</p>
          </div>
          <select v-model="newFm.staff_user" class="ff">
            <option value="">No linked login</option>
            <option v-for="u in floorManagerLogins" :key="u.id" :value="u.id">Link to {{ u.username }}</option>
          </select>
          <button class="btn btn--primary" type="submit" :disabled="fmCreating || !fmIsValid">{{ fmCreating ? 'Adding…' : '+ Add Floor Manager' }}</button>
        </form>
        <p v-if="fmFormError" class="form-error">{{ fmFormError }}</p>
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
.section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; }

.section-note { font-size: 12px; color: var(--text-tertiary); margin-bottom: 12px; line-height: 1.5; }
.row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border); }
.row-info { flex-grow: 1; min-width: 0; }
.row-name { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }
.row-sub { font-size: 11.5px; color: var(--text-tertiary); }
.link-btn { border: none; background: none; font-size: 12px; font-weight: 700; color: var(--accent-text); cursor: pointer; padding: 0; white-space: nowrap; }
.link-btn--muted { color: var(--text-tertiary); font-weight: 500; }

.inline-form { display: flex; align-items: flex-start; gap: 8px; padding: 12px 0; border-bottom: 1px solid var(--border); }
.field { display: flex; flex-direction: column; gap: 4px; }
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
.stage-block { border-top: 1px solid var(--border); margin-top: 10px; padding-top: 14px; }
.stage-block-title { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 10px; }

.upload-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.upload-btn { position: relative; cursor: pointer; }
.file-input { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; }
.sample-link { font-size: 12.5px; font-weight: 600; color: var(--accent-text); text-decoration: none; }
.sample-link:hover { text-decoration: underline; }
.upload-hint { font-size: 11.5px; color: var(--text-tertiary); width: 100%; }

.manual-row-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
.manual-row-form .ff { flex: 1 1 160px; }

.staged-list { border: 1px solid var(--border); border-radius: var(--radius-sm); margin-bottom: 10px; overflow: hidden; }
.staged-row { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-bottom: 1px solid var(--border); font-size: 12.5px; }
.staged-row:last-child { border-bottom: none; }
.staged-code { font-family: var(--font-mono); font-weight: 700; color: var(--text-primary); flex-shrink: 0; }
.remove-btn { margin-left: auto; border: none; background: none; font-size: 16px; line-height: 1; color: var(--text-tertiary); cursor: pointer; flex-shrink: 0; }
.remove-btn:hover { color: var(--danger); }
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
.form-error { margin-top: 8px; }
.form-warning {
  font-size: 12.5px;
  color: var(--warning-text);
  background: var(--warning-bg);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  margin-bottom: 12px;
}
.form-warning-title { font-weight: 600; }
.form-warning-list { margin: 4px 0 0; padding-left: 18px; }
.form-warning-list li { margin-top: 2px; }
</style>
