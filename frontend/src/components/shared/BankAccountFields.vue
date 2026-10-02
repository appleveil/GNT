<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import api from '@/api/axios'
import { readApiError } from '@/utils/apiError'

// v-model is { bank_name, bank_code, account_number, account_name } — account_name
// is the Paystack-resolved name once looked up, blank until then. The bank_code
// field is never shown/typed directly; it rides along on whichever bank is picked.
const model = defineModel({
  default: () => ({ bank_name: '', bank_code: '', account_number: '', account_name: '' }),
})

const banks = ref([])
const banksLoading = ref(true)
const banksError = ref('')

// Bank combobox — a text field the cashier types into to filter the bank
// list, rather than scrolling a plain <select> through 280+ banks.
const bankQuery = ref(model.value.bank_name || '')
const selectedBankCode = ref(model.value.bank_code || '')
const dropdownOpen = ref(false)
const highlightIndex = ref(-1)
const MAX_VISIBLE_MATCHES = 40

const filteredBanks = computed(() => {
  const q = bankQuery.value.trim().toLowerCase()
  const matches = q ? banks.value.filter(b => b.name.toLowerCase().includes(q)) : banks.value
  return matches.slice(0, MAX_VISIBLE_MATCHES)
})

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

function onBankInput(e) {
  bankQuery.value = e.target.value
  dropdownOpen.value = true
  highlightIndex.value = -1
  // Typing anything invalidates whatever was previously picked — the cashier
  // must choose from the (now-filtered) list again before this counts as a
  // real bank selection.
  if (selectedBankCode.value) selectedBankCode.value = ''
}

function selectBank(bank) {
  selectedBankCode.value = bank.code
  bankQuery.value = bank.name
  dropdownOpen.value = false
  highlightIndex.value = -1
}

function onBankFocus() {
  dropdownOpen.value = true
}

function onBankBlur() {
  // Options select on mousedown (before blur fires), so this only ever
  // closes the dropdown when focus leaves without a pick being made.
  dropdownOpen.value = false
}

function moveHighlight(delta) {
  dropdownOpen.value = true
  const max = filteredBanks.value.length - 1
  highlightIndex.value = Math.min(max, Math.max(0, highlightIndex.value + delta))
}

function chooseHighlighted() {
  const bank = filteredBanks.value[highlightIndex.value]
  if (bank) selectBank(bank)
}

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
    resolveError.value = readApiError(err, "Could not verify this account — check the number and bank.").message
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
    <div class="field combobox">
      <span class="eyebrow">Bank</span>
      <input
        type="text" :value="bankQuery" autocomplete="off"
        :disabled="banksLoading" :placeholder="banksLoading ? 'Loading banks…' : 'Type to search…'"
        @input="onBankInput" @focus="onBankFocus" @blur="onBankBlur"
        @keydown.down.prevent="moveHighlight(1)" @keydown.up.prevent="moveHighlight(-1)"
        @keydown.enter.prevent="chooseHighlighted" @keydown.esc="dropdownOpen = false"
      />
      <ul v-if="dropdownOpen && !banksLoading" class="combobox-list">
        <li
          v-for="(b, i) in filteredBanks" :key="b.code" class="combobox-option"
          :class="{ 'combobox-option--active': i === highlightIndex }"
          @mousedown.prevent="selectBank(b)"
        >
          {{ b.name }}
        </li>
        <li v-if="!filteredBanks.length" class="combobox-empty">No matching banks</li>
      </ul>
    </div>
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
input {
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text-primary);
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  height: 42px;
}
input:disabled { color: var(--text-tertiary); }

.combobox { position: relative; }
.combobox-list {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: 20;
  max-height: 220px;
  overflow-y: auto;
  list-style: none;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.12);
}
.combobox-option {
  padding: 10px 12px;
  font-size: 13.5px;
  color: var(--text-primary);
  cursor: pointer;
  border-bottom: 1px solid var(--border);
}
.combobox-option:last-child { border-bottom: none; }
.combobox-option:hover, .combobox-option--active { background: var(--accent-bg); color: var(--accent-text); }
.combobox-empty { padding: 10px 12px; font-size: 13px; color: var(--text-tertiary); }

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
