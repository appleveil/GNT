<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api/axios'
import { useToast } from '@/composables/useToast'
import { useFormValidation, required } from '@/composables/useFormValidation'
import { readApiError } from '@/utils/apiError'

// Floor Manager's own screen (2026-09-17 as "Service Staff", renamed
// 2026-09-23 — see gaming.models.Transaction.masseuse/TipCategory's own
// comment) — managing the named tipped-Masseuse roster is one of a Floor
// Manager's own functions now that they have a real login. Owner can do
// this too (StaffMemberViewSet allows both), but this page lives under the
// Floor Manager's own nav/role, not Owner's — copies AdminView.vue's
// Floor-Managers-section pattern exactly (the one proven CRUD-list pattern
// in this codebase), minus a PIN (a named recipient, not a witness/
// authorizer).
//
// Backs onto accounts.StaffMember (generalized 2026-09-23 to also cover
// Dealer/Service — see that model's own docstring), always scoped to
// role=MASSEUSE here: this page is specifically the named tip-recipient
// roster, not the general staff directory (that's the Owner's Admin page,
// "Other Staff" section).
const toast = useToast()

const people = ref([])
const loading = ref(true)
const newName = ref('')
const creating = ref(false)
const formError = ref('')

const { touched, errors, isValid, touch, touchAll } = useFormValidation({
  newName: { value: newName, rules: [required('A name is required.')] },
})

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/staff-members/?role=MASSEUSE')
    people.value = data
  } catch {
    toast.error('Could not load Masseuses.')
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function onCreate() {
  touchAll()
  if (!isValid.value) return
  formError.value = ''
  creating.value = true
  try {
    await api.post('/staff-members/', { name: newName.value, role: 'MASSEUSE' })
    newName.value = ''
    await load()
    toast.success('Masseuse added.')
  } catch (err) {
    formError.value = readApiError(err, 'Could not add this person.').message
  } finally {
    creating.value = false
  }
}

async function onToggleActive(person) {
  try {
    const { data } = await api.patch(`/staff-members/${person.id}/`, { is_active: !person.is_active })
    Object.assign(person, data)
  } catch {
    toast.error('Could not update this person.')
  }
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Masseuses</h1>
      <p>Named people Masseuse tips get attributed to — Service staff tips stay anonymous and don't need anyone added here.</p>
    </div>

    <div class="card section-card">
      <p v-if="loading" class="muted">Loading…</p>
      <template v-else>
        <p v-if="!people.length" class="muted">No one added yet.</p>
        <div v-for="p in people" :key="p.id" class="row">
          <div class="row-info">
            <div class="row-name">{{ p.name }}</div>
          </div>
          <span class="badge" :class="p.is_active ? 'badge--approved' : 'badge--closed'">{{ p.is_active ? 'active' : 'inactive' }}</span>
          <button class="link-btn" type="button" @click="onToggleActive(p)">{{ p.is_active ? 'Deactivate' : 'Activate' }}</button>
        </div>

        <form class="create-form" novalidate @submit.prevent="onCreate">
          <div class="field">
            <input
              v-model="newName" type="text" placeholder="Name" class="ff"
              :class="{ 'input--invalid': touched.newName && errors.newName }" @blur="touch('newName')"
            />
            <p v-if="touched.newName && errors.newName" class="field-error">{{ errors.newName }}</p>
          </div>
          <button class="btn btn--primary" type="submit" :disabled="creating || !isValid">{{ creating ? 'Adding…' : '+ Add Masseuse' }}</button>
        </form>
        <p v-if="formError" class="form-error">{{ formError }}</p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 700px; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }
.muted { color: var(--text-secondary); font-size: 13px; }

.section-card { padding: 18px 20px; }
.row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border); }
.row:last-child { border-bottom: none; }
.row-info { flex-grow: 1; min-width: 0; }
.row-name { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }
.link-btn { border: none; background: none; font-size: 12px; font-weight: 700; color: var(--accent-text); cursor: pointer; padding: 0; white-space: nowrap; }

.create-form { display: flex; gap: 10px; margin-top: 16px; align-items: flex-start; }
.create-form .field { flex: 1; }
.ff {
  width: 100%;
  height: var(--control-row-min);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 12px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-primary);
  background: var(--surface);
}
.ff:focus { outline: none; border-color: var(--accent); }
.form-error { margin-top: 10px; }
</style>
