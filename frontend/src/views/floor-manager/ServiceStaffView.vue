<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api/axios'
import { useToast } from '@/composables/useToast'

// Floor Manager's own screen (2026-09-17) — managing the named tipped-
// Service-staff roster (see gaming.models.Transaction.service_staff/
// tip_category) is one of a Floor Manager's own functions now that they
// have a real login. Owner can do this too (ServiceStaffViewSet allows
// both), but this page lives under the Floor Manager's own nav/role, not
// Owner's — copies AdminView.vue's Floor-Managers-section pattern exactly
// (the one proven CRUD-list pattern in this codebase), minus a PIN (a
// Service Staff record is a named recipient, not a witness/authorizer).
const toast = useToast()

const people = ref([])
const loading = ref(true)
const newName = ref('')
const creating = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/service-staff/')
    people.value = data
  } catch {
    toast.error('Could not load Service Staff.')
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function onCreate() {
  error.value = ''
  creating.value = true
  try {
    await api.post('/service-staff/', { name: newName.value })
    newName.value = ''
    await load()
    toast.success('Service Staff added.')
  } catch (err) {
    error.value = Object.values(err.response?.data || {})[0]?.[0] || 'Could not add this person.'
  } finally {
    creating.value = false
  }
}

async function onToggleActive(person) {
  try {
    const { data } = await api.patch(`/service-staff/${person.id}/`, { is_active: !person.is_active })
    Object.assign(person, data)
  } catch {
    toast.error('Could not update this person.')
  }
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Service Staff</h1>
      <p>Named people Service tips get attributed to — Dealer tips stay anonymous and don't need anyone added here.</p>
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

        <form class="create-form" @submit.prevent="onCreate">
          <input v-model="newName" type="text" placeholder="Name" required class="ff" />
          <button class="btn btn--primary" type="submit" :disabled="creating">{{ creating ? 'Adding…' : '+ Add Service Staff' }}</button>
        </form>
        <p v-if="error" class="form-error">{{ error }}</p>
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

.create-form { display: flex; gap: 10px; margin-top: 16px; }
.ff {
  flex: 1;
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
.form-error {
  font-size: 12.5px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  margin-top: 10px;
}
</style>
