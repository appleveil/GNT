<script setup>
import { ref } from 'vue'
import api from '@/api/axios'
import { readApiError } from '@/utils/apiError'

// Owner-only payout rejection (2026-09-15) — same centered-dialog/
// reason-textarea pattern as VoidEntryModal.vue, but its own component:
// rejecting is a specific step in the payout-approval workflow ("decline
// this request"), not the generic "undo a posted entry" void is, and
// reject_payout (gaming/services.py) posts to a different endpoint.
const props = defineProps({
  transaction: { type: Object, required: true },
  playerName: { type: String, default: '' },
})
const emit = defineEmits(['close', 'rejected'])

const reason = ref('')
const submitting = ref(false)
const error = ref('')

const N = n => `₦${Number(n).toLocaleString()}`

async function onSubmit() {
  if (!reason.value.trim() || submitting.value) return
  submitting.value = true
  error.value = ''
  try {
    const { data } = await api.post(`/transactions/${props.transaction.id}/reject/`, {
      reason: reason.value.trim(),
    })
    emit('rejected', data)
  } catch (err) {
    error.value = readApiError(err, 'Could not reject this payout.').message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="overlay">
    <div class="dialog card">
      <div class="title">Decline this payout?</div>
      <p class="subtitle">The player is told nothing moved — this stays visible in their history, marked declined, with your reason.</p>

      <div class="summary">
        <div class="summary-title">{{ playerName }}</div>
        <div class="summary-meta">{{ N(transaction.amount) }} &middot; requested {{ new Date(transaction.created_at).toLocaleString() }}</div>
      </div>

      <div class="lbl">Reason <span class="required">*required</span></div>
      <textarea v-model="reason" rows="3" placeholder="Why is this being declined?" />

      <p v-if="error" class="form-error">{{ error }}</p>

      <div class="actions">
        <button class="btn btn--secondary" type="button" :disabled="submitting" @click="emit('close')">Cancel</button>
        <button class="btn btn--void" type="button" :disabled="!reason.trim() || submitting" @click="onSubmit">
          {{ submitting ? 'Declining…' : 'Decline Payout' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(20, 25, 32, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 20px;
}
.dialog { width: 480px; max-width: 100%; box-shadow: var(--shadow-md); padding: 24px; }
.title { font-size: 18px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.subtitle { font-size: 13px; color: var(--text-secondary); margin-bottom: 16px; line-height: 1.4; }

.summary {
  border: 1px solid var(--border);
  background: var(--bg);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  margin-bottom: 18px;
}
.summary-title { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }
.summary-meta { font-family: var(--font-mono); font-size: 12px; color: var(--text-tertiary); margin-top: 2px; }

.lbl {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}
.required { color: var(--danger); text-transform: none; font-weight: 500; }
textarea {
  width: 100%;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  font-family: var(--font-sans);
  font-size: 13.5px;
  color: var(--text-primary);
  resize: vertical;
  margin-bottom: 16px;
}
textarea:focus { outline: none; border-color: var(--accent); }

.form-error { margin-bottom: 12px; }

.actions { display: flex; gap: 14px; }
.actions .btn { flex: 1; }
.btn--void {
  background: var(--surface);
  border: 1.5px solid var(--danger);
  color: var(--danger);
}
.btn--void:not(:disabled):active { opacity: 0.85; }
</style>
