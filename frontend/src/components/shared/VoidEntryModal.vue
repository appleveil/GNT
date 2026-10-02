<script setup>
import { ref } from 'vue'
import api from '@/api/axios'
import { TRANSACTION_TYPES } from '@/constants/transactionTypes'
import { readApiError } from '@/utils/apiError'

// Centered confirm dialog (not a bottom sheet — matches the Close-Game-Day
// confirm's .overlay/.dialog pattern, per HiFiVoidEntry.dc.html). The caller
// is responsible for only rendering this when canVoidTransaction() says so.
const props = defineProps({
  transaction: { type: Object, required: true },
  playerName: { type: String, default: '' },
  recordedByName: { type: String, default: '' },
})
const emit = defineEmits(['close', 'voided'])

const reason = ref('')
const submitting = ref(false)
const error = ref('')

function formatTime(iso) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}
const N = n => `₦${Number(n).toLocaleString()}`

async function onSubmit() {
  if (!reason.value.trim() || submitting.value) return
  submitting.value = true
  error.value = ''
  try {
    const { data } = await api.post(`/transactions/${props.transaction.id}/void/`, {
      reason: reason.value.trim(),
    })
    emit('voided', data)
  } catch (err) {
    error.value = readApiError(err, 'Could not void this entry.').message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="overlay" @click.self="submitting || emit('close')">
    <div class="dialog card">
      <div class="title">Void this entry?</div>
      <p class="subtitle">This stays visible in the ledger, marked voided, for audit — it isn't deleted.</p>

      <div class="summary">
        <div class="summary-title">
          <template v-if="playerName">{{ playerName }} &middot; </template>{{ TRANSACTION_TYPES[transaction.type]?.label || transaction.type }}
        </div>
        <div class="summary-meta">
          {{ N(transaction.amount) }} &middot; recorded {{ formatTime(transaction.created_at) }}<template v-if="recordedByName"> by {{ recordedByName }}</template>
        </div>
      </div>

      <div class="lbl">Reason <span class="required">*required</span></div>
      <textarea v-model="reason" rows="3" placeholder="Why is this being voided?" />

      <p v-if="error" class="form-error">{{ error }}</p>

      <div class="actions">
        <button class="btn btn--secondary" type="button" :disabled="submitting" @click="emit('close')">Cancel</button>
        <button class="btn btn--void" type="button" :disabled="!reason.trim() || submitting" @click="onSubmit">
          {{ submitting ? 'Voiding…' : 'Void Entry' }}
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
