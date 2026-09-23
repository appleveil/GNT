<script setup>
import { usePlainConfirm } from '@/composables/usePlainConfirm'

const { isOpen, title, subtitle, submitting, error, cancel, submit } = usePlainConfirm()
</script>

<template>
  <div v-if="isOpen" class="overlay">
    <div class="sheet">
      <div class="grip" />
      <div class="sheet-title">{{ title }}</div>
      <div v-if="subtitle" class="sheet-subtitle">{{ subtitle }}</div>
      <p v-if="error" class="pin-error">{{ error }}</p>
      <div class="spacer" />
      <div class="actions">
        <button class="btn btn--secondary" type="button" :disabled="submitting" @click="cancel">Cancel</button>
        <button class="btn btn--primary" type="button" :disabled="submitting" @click="submit">
          {{ submitting ? 'Working…' : 'Confirm' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Same tier as AuthorizerConfirmModal — the two are mutually exclusive
   per gated action (see ClubSettings.require_approval_*), never both
   open at once, so which one sits "on top" never actually matters. */
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(20, 25, 32, 0.5);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  z-index: 100;
}
.sheet {
  width: 100%;
  max-width: 480px;
  background: var(--surface);
  border-radius: 20px 20px 0 0;
  box-shadow: 0 -6px 28px rgba(20, 25, 32, 0.25);
  padding: 16px 28px 28px;
  display: flex;
  flex-direction: column;
  max-height: 90vh;
}
.grip {
  width: 44px;
  height: 5px;
  border-radius: 3px;
  background: var(--border);
  align-self: center;
  margin-bottom: 18px;
}
.sheet-title { font-size: 18px; font-weight: 700; color: var(--text-primary); text-align: center; }
.sheet-subtitle { font-size: 13px; color: var(--text-secondary); text-align: center; margin: 4px 0 0; }
.pin-error {
  text-align: center;
  font-size: 12.5px;
  color: var(--danger);
  margin-top: 12px;
}
.spacer { flex-grow: 1; min-height: 20px; }
.actions { display: flex; gap: 14px; margin-top: 8px; }
.actions .btn { flex: 1; }
</style>
