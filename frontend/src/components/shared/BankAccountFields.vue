<script setup>
import { ref, onMounted, watch } from 'vue'
import api from '@/api/axios'

// v-model is { bank_name, bank_code, account_number, account_name } — account_name
// is the Paystack-resolved name once looked up, blank until then. The bank_code
// field is never shown/typed directly; it rides along on the selected bank.
const model = defineModel({
  default: () => ({ bank_name: '', bank_code: '', account_number: '', account_name: '' }),
})

const banks = ref([])
const banksLoading = ref(true)
const banksError = ref('')

const selectedBankCode = ref(model.value.bank_code || '')
const accountNumber = ref(model.value.account_number || '')
const resolving = ref(false)
const resolvedName = ref(model.value.account_name || '')
const resolveError = ref('')

onMounted(async () => {
  try {
    const { data } = await api.get('/payments/banks/')
    banks.value = data
      .filter(b => b.active && b.currency === 'NGN' && b.country === 'Nigeria')
      .sort((a, b) => a.name.localeCompare(b.name))
  } catch {
    banksError.value = 'Could not load the bank list.'
  } finally {
    banksLoading.value = false
  }
})

function onAccountNumberInput(e) {
  accountNumber.value = e.target.value.replace(/\D/g, '').slice(0, 10)
  e.target.value = accountNumber.value
}

let resolveTimer = null
watch([selectedBankCode, accountNumber], () => {
  resolvedName.value = ''
  resolveError.value = ''
  emitModel()
  clearTimeout(resolveTimer)
  if (selectedBankCode.value && accountNumber.value.length === 10) {
    // Small debounce so a still-typing cashier doesn't fire a lookup per keystroke.
    resolveTimer = setTimeout(resolveAccount, 350)
  }
})

async function resolveAccount() {
  resolving.value = true
  resolveError.value = ''
  try {
    const { data } = await api.get('/payments/resolve-account/', {
      params: { account_number: accountNumber.value, bank_code: selectedBankCode.value },
    })
    resolvedName.value = data.account_name
    emitModel()
  } catch (err) {
    resolveError.value = err.response?.data?.detail || "Could not verify this account — check the number and bank."
  } finally {
    resolving.value = false
  }
}

function emitModel() {
  const bank = banks.value.find(b => b.code === selectedBankCode.value)
  model.value = {
    bank_name: bank?.name || '',
    bank_code: selectedBankCode.value,
    account_number: accountNumber.value,
    account_name: resolvedName.value,
  }
}
</script>

<template>
  <div class="bank-fields">
    <label class="field">
      <span class="eyebrow">Bank</span>
      <select v-model="selectedBankCode" :disabled="banksLoading">
        <option value="" disabled>{{ banksLoading ? 'Loading banks…' : 'Select bank' }}</option>
        <option v-for="b in banks" :key="b.code" :value="b.code">{{ b.name }}</option>
      </select>
    </label>
    <p v-if="banksError" class="form-error">{{ banksError }}</p>

    <label class="field">
      <span class="eyebrow">Account number</span>
      <input
        :value="accountNumber" type="text" inputmode="numeric" maxlength="10"
        placeholder="10-digit account number" @input="onAccountNumberInput"
      />
    </label>

    <p v-if="resolving" class="resolve-status">Checking account…</p>
    <p v-else-if="resolvedName" class="resolve-status resolve-status--ok">
      &#10003; {{ resolvedName }} <span class="resolve-hint">— confirm this with the player</span>
    </p>
    <p v-else-if="resolveError" class="resolve-status resolve-status--error">{{ resolveError }}</p>
  </div>
</template>

<style scoped>
.bank-fields { display: flex; flex-direction: column; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
select, input {
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text-primary);
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  height: 42px;
}
select:disabled { color: var(--text-tertiary); }

.resolve-status {
  font-size: 12.5px;
  color: var(--text-secondary);
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  background: var(--surface);
  border: 1px solid var(--border);
}
.resolve-status--ok {
  color: var(--success-text);
  background: var(--success-bg);
  border-color: transparent;
  font-weight: 600;
}
.resolve-hint { font-weight: 400; color: var(--text-tertiary); }
.resolve-status--error, .form-error {
  color: var(--danger);
  background: var(--danger-bg);
  border-color: transparent;
}
</style>
