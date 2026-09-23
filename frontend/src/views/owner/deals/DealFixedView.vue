<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/axios'
import { useGameDayStore } from '@/stores/gameDay'
import { formatAmountForDisplay, parseAmountInput } from '@/utils/amountInput'
import { useToast } from '@/composables/useToast'

// "Deals" Fixed write-off (2026-09-23) — mirrors mobile's FixedScreen.tsx,
// wired to the real backend: POST /transactions/ {type: 'WRITE_OFF'}.
// gaming/services.py's record_transaction enforces the same cap this form
// previews client-side (can't exceed the player's current outstanding
// lifetime balance) and requires a reason — both re-checked server-side
// regardless of what this form allows submitting.
//
// game_day: attached to whichever game-day is open right now (AppShell
// already keeps gameDay.current fresh), same as any other live entry —
// else left null (Outstanding), matching RosterDetailView.vue's own
// Deal/Write-off mini-form logic, minus its "attach to the just-closed
// game-day" opt-in checkbox (a narrower, simpler default here; that fuller
// control still exists on the player's Roster page for anyone who needs it).
const route = useRoute()
const router = useRouter()
const gameDay = useGameDayStore()
const toast = useToast()

const player = ref(null)
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const { data } = await api.get(`/players/${route.params.playerId}/`)
    player.value = data
  } catch {
    toast.error('Could not load this player.')
  } finally {
    loading.value = false
  }
}
onMounted(load)

const outstanding = computed(() => (player.value ? Math.max(-Number(player.value.balance), 0) : 0))

const amount = ref('') // plain numeric string, no commas
const displayAmount = computed(() => formatAmountForDisplay(amount.value))
const reason = ref('')
const submitting = ref(false)
const error = ref('')

const amountNumber = computed(() => Number(amount.value) || 0)
const over = computed(() => amountNumber.value > outstanding.value)
const canSubmit = computed(() => amountNumber.value > 0 && !over.value && reason.value.trim().length > 0 && outstanding.value > 0)

async function onSubmit() {
  if (!canSubmit.value) return
  error.value = ''
  submitting.value = true
  try {
    await api.post('/transactions/', {
      type: 'WRITE_OFF',
      player: player.value.id,
      amount: amountNumber.value.toFixed(0),
      notes: reason.value.trim(),
      ...(gameDay.isOpen ? { game_day: gameDay.current.id } : {}),
    })
    toast.success(`₦${amountNumber.value.toLocaleString()} cleared from ${player.value.display_name}'s outstanding balance.`)
    router.push('/deals')
  } catch (err) {
    error.value = Object.values(err.response?.data || {})[0]?.[0] || err.response?.data?.detail || 'Could not save this write-off.'
  } finally {
    submitting.value = false
  }
}

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="page">
    <button class="back-btn" type="button" @click="router.push(`/deals/${route.params.playerId}`)">&larr; {{ player?.display_name || 'Back' }}</button>

    <p v-if="loading" class="muted">Loading…</p>

    <template v-else-if="player">
      <div class="page-header">
        <h1>Fixed write-off</h1>
        <p>{{ player.display_name }} &middot; {{ player.account_code }}</p>
      </div>

      <div class="card balance-card">
        <div class="balance-label">Outstanding</div>
        <div class="balance-amount" :class="outstanding > 0 ? 'money--neg' : ''">{{ N(outstanding) }}</div>
      </div>

      <label class="field">
        <span class="field-label">Clear balance by <span class="req">*</span></span>
        <input
          :value="displayAmount" type="text" inputmode="numeric" placeholder="0" class="ff"
          @input="e => { amount = parseAmountInput(e.target.value); e.target.value = displayAmount }"
        />
        <span v-if="over" class="field-error">Can't enter more than the outstanding balance.</span>
      </label>
      <button type="button" class="link-btn" @click="amount = String(outstanding)">Clear all ({{ N(outstanding) }})</button>

      <label class="field">
        <span class="field-label">Reason <span class="req">*</span></span>
        <textarea v-model="reason" class="ff ff--area" placeholder="Why is this being written off?" rows="3" />
      </label>

      <div class="banner banner--warn">This can't be reversed once submitted.</div>

      <p v-if="error" class="form-error">{{ error }}</p>

      <button class="btn btn--primary submit-btn" type="button" :disabled="!canSubmit || submitting" @click="onSubmit">
        {{ submitting ? 'Applying…' : 'Apply write-off' }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 560px; }
.back-btn { border: none; background: none; font-size: 13.5px; font-weight: 600; color: var(--text-secondary); cursor: pointer; padding: 4px 0; margin-bottom: 16px; }
.back-btn:hover { color: var(--text-primary); }
.muted { color: var(--text-secondary); font-size: 13px; }

.page-header { margin-bottom: 20px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 2px; }
.page-header p { font-size: 12.5px; color: var(--text-tertiary); margin: 0; }

.balance-card { padding: 22px; text-align: center; margin-bottom: 20px; }
.balance-label { font-size: 11px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 6px; }
.balance-amount { font-family: var(--font-mono); font-weight: 700; font-size: 30px; color: var(--text-primary); }
.money--neg { color: var(--danger-text); }

.field { display: block; margin-bottom: 6px; }
.field-label { display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
.req { color: var(--danger-text); }
.ff {
  width: 100%;
  height: var(--control-row-min);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 14px;
  font-family: var(--font-sans);
  font-size: 15px;
  color: var(--text-primary);
  background: var(--surface);
}
.ff:focus { outline: none; border-color: var(--accent); }
.ff--area { height: auto; padding: 12px 14px; resize: vertical; font-size: 13.5px; }
.field-error { display: block; font-size: 11.5px; color: var(--danger-text); margin-top: 4px; }

.link-btn { border: none; background: none; font-size: 12.5px; font-weight: 700; color: var(--accent-text); cursor: pointer; padding: 0; margin: 8px 0 20px; display: block; }
.link-btn:hover { text-decoration: underline; }

.banner {
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  font-size: 12.5px;
  margin-bottom: 20px;
}
.banner--warn { background: var(--warning-bg); color: var(--warning-text); }

.form-error {
  font-size: 12.5px;
  color: var(--danger);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  margin-bottom: 16px;
}

.submit-btn { width: 100%; }
</style>
