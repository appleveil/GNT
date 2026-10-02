<script setup>
import { ref } from 'vue'
import api from '@/api/axios'
import BankAccountFields from '@/components/shared/BankAccountFields.vue'
import { useToast } from '@/composables/useToast'
import { readApiError } from '@/utils/apiError'

// Replaces sending the Cashier to the old Player Detail page just to add a
// bank account before a payout — same add-bank-account capability that page
// had, as a modal instead of a full page nav (that page, PlayerDetailView.vue,
// was fully removed 2026-09-27 — this modal had already made it redundant).
// Opened from ActiveGameDayView's onPayoutClick when the selected player has
// no default bank account on file. Added 2026-09-22.
const props = defineProps({
  player: { type: Object, required: true }, // { id, display_name, bank_accounts }
})
const emit = defineEmits(['close', 'added'])
const toast = useToast()

const newBank = ref({ bank_name: '', bank_code: '', account_number: '', account_name: '' })
const error = ref('')
const submitting = ref(false)

async function onAddBank() {
  error.value = ''
  submitting.value = true
  try {
    await api.post(`/players/${props.player.id}/bank-accounts/`, {
      bank_name: newBank.value.bank_name,
      bank_code: newBank.value.bank_code,
      account_number: newBank.value.account_number,
      // Prefer the Paystack-resolved name; fall back to the player's own
      // name if resolution didn't complete (e.g. Paystack unreachable).
      account_name: newBank.value.account_name || props.player.display_name,
      is_default: (props.player.bank_accounts || []).length === 0,
    })
    emit('added')
  } catch (err) {
    error.value = readApiError(err, 'Could not add bank account.').message
  } finally {
    submitting.value = false
  }
}

async function onSetDefault(bank) {
  try {
    await api.patch(`/players/${props.player.id}/bank-accounts/${bank.id}/`, { is_default: true })
    emit('added')
  } catch {
    toast.error('Could not set this as the default bank account.')
  }
}
</script>

<template>
  <div class="overlay" @click.self="submitting || emit('close')">
    <div class="dialog card">
      <div class="head">
        <div class="eyebrow">{{ player.display_name }} &mdash; no bank account on file</div>
        <button class="close-btn" type="button" @click="emit('close')">&times;</button>
      </div>

      <div v-if="(player.bank_accounts || []).length" class="bank-list">
        <div v-for="bank in player.bank_accounts" :key="bank.id" class="bank-row">
          <div class="bank-info">
            <div class="bank-name">{{ bank.bank_name }} &middot; {{ bank.account_number }}</div>
            <div class="bank-account-name">{{ bank.account_name }}</div>
          </div>
          <div v-if="bank.is_default" class="default-badge">DEFAULT</div>
          <button v-else class="link-btn small" type="button" @click="onSetDefault(bank)">Set default</button>
        </div>
      </div>

      <form class="bank-form" @submit.prevent="onAddBank">
        <BankAccountFields v-model="newBank" />
        <p v-if="error" class="form-error">{{ error }}</p>
        <button
          class="btn btn--primary" type="submit"
          :disabled="submitting || newBank.account_number.length !== 10 || !newBank.bank_code"
        >
          {{ submitting ? 'Adding…' : 'Save bank account' }}
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
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.dialog { width: 480px; max-width: 92vw; max-height: 90vh; overflow-y: auto; box-shadow: var(--shadow-md); padding: 24px; }
.head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
.close-btn { border: none; background: none; font-size: 22px; line-height: 1; color: var(--text-tertiary); cursor: pointer; flex-shrink: 0; }
.bank-list { margin-bottom: 18px; }
.bank-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.bank-row:last-child { border-bottom: none; }
.bank-info { flex-grow: 1; min-width: 0; }
.bank-name { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }
.bank-account-name { font-size: 11.5px; color: var(--text-tertiary); }
.default-badge {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--success-text);
  background: var(--success-bg);
  border-radius: 10px;
  padding: 3px 9px;
  flex-shrink: 0;
}
.link-btn { border: none; background: none; font-size: 11.5px; font-weight: 700; color: var(--accent); cursor: pointer; flex-shrink: 0; }
.link-btn.small { font-size: 11px; }

.bank-form { display: flex; flex-direction: column; gap: 12px; }
</style>
