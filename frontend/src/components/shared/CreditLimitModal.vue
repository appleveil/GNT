<script setup>
import { ref, computed } from 'vue'
import api from '@/api/axios'
import { formatAmountForDisplay, parseAmountInput } from '@/utils/amountInput'
import { useToast } from '@/composables/useToast'

// Owner-only "Credit limit" action (2026-09-24, relabeled 2026-09-25 — see
// PLAN.md), reached from the Players page's ⋮ menu — same PATCH
// /players/{id}/ {chips_limit} RosterDetailView's own inline edit already
// used (Owner-gated server-side in PlayerSerializer.validate_chips_limit),
// just as a modal so it's reachable straight from the list, no page nav
// required. The API field is still `chips_limit` (not renamed — a DB/API
// change, not what was asked); only the user-facing label changed. This is
// NOT the same thing as a table's own max_chips_issuable (Settings screen,
// per-buy-in cap) — this caps how much a player can owe (unpaid chips) at
// once before they have to settle up, see services.record_transaction's
// CHIPS_OUT branch.
const props = defineProps({
  player: { type: Object, required: true }, // { id, display_name, chips_limit }
})
const emit = defineEmits(['close', 'saved'])
const toast = useToast()

const limitInput = ref(props.player.chips_limit != null ? String(props.player.chips_limit) : '')
const displayLimitInput = computed(() => formatAmountForDisplay(limitInput.value))
const submitting = ref(false)
const error = ref('')

async function onSubmit() {
  error.value = ''
  submitting.value = true
  try {
    const { data } = await api.patch(`/players/${props.player.id}/`, {
      chips_limit: limitInput.value === '' ? null : limitInput.value,
    })
    toast.success('Credit limit updated.')
    emit('saved', data)
  } catch (err) {
    error.value = err.response?.data?.chips_limit?.[0] || 'Could not update the credit limit.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="dialog card">
      <div class="head">
        <div class="eyebrow">{{ player.display_name }} &mdash; credit limit</div>
        <button class="close-btn" type="button" @click="emit('close')">&times;</button>
      </div>

      <form class="form" @submit.prevent="onSubmit">
        <label class="field">
          <span class="field-label">Max unpaid chips before settling up</span>
          <input
            :value="displayLimitInput" type="text" inputmode="numeric" placeholder="No cap" class="ff"
            @input="e => (limitInput = parseAmountInput(e.target.value))"
          />
          <span class="field-hint">Resets each game-day — not the same as a table's own per-buy-in chip cap (set in Settings).</span>
        </label>
        <p v-if="error" class="form-error">{{ error }}</p>
        <div class="actions">
          <button class="btn btn--secondary" type="button" :disabled="submitting" @click="emit('close')">Cancel</button>
          <button class="btn btn--primary" type="submit" :disabled="submitting">{{ submitting ? 'Saving…' : 'Save' }}</button>
        </div>
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
.dialog { width: 400px; max-width: 92vw; box-shadow: var(--shadow-md); padding: 24px; }
.head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 16px; }
.eyebrow { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.close-btn { border: none; background: none; font-size: 22px; line-height: 1; color: var(--text-tertiary); cursor: pointer; flex-shrink: 0; }

.form { display: flex; flex-direction: column; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 12px; font-weight: 600; color: var(--text-secondary); }
.field-hint { font-size: 11.5px; color: var(--text-tertiary); line-height: 1.4; }
.ff {
  height: var(--control-row-min);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 12px;
  font-family: var(--font-mono);
  font-size: 14px;
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
}
.actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 4px; }
</style>
