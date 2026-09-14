<script setup>
import { useAuthorizerConfirm } from '@/composables/useAuthorizerConfirm'

const {
  isOpen, step, title, subtitle, mode, people, peopleLoading, selected, pin, error, submitting,
  selectPerson, backToSelect, appendDigit, backspace, cancel, submit,
} = useAuthorizerConfirm()

const keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9']
</script>

<template>
  <div v-if="isOpen" class="overlay">
    <div class="sheet">
      <div class="grip" />

      <!-- Step 1: select who's authorizing -->
      <template v-if="step === 'select'">
        <div class="sheet-title">{{ title }}</div>
        <div v-if="subtitle" class="sheet-subtitle">{{ subtitle }}</div>

        <div class="notice">
          {{
            mode === 'fm-only'
              ? 'A Floor Manager must confirm this physical count — they already witnessed it, this just records who.'
              : "Only the Owner or a Floor Manager can authorize this — a Cashier cannot."
          }}
        </div>

        <div class="lbl">Who's authorizing?</div>
        <p v-if="peopleLoading" class="muted">Loading…</p>
        <div v-else class="people">
          <button
            v-for="p in people" :key="`${p.type}-${p.id}`" type="button"
            class="person-row" :class="{ 'person-row--selected': selected?.id === p.id && selected?.type === p.type }"
            @click="selectPerson(p)"
          >
            <div class="person-avatar">{{ p.name.charAt(0).toUpperCase() }}</div>
            <div class="person-info">
              <div class="person-name">{{ p.name }}</div>
              <div class="person-role">{{ p.roleLabel }}</div>
            </div>
          </button>
          <p v-if="!people.length" class="muted">
            {{ mode === 'fm-only' ? 'No Floor Manager available.' : 'No Owner or Floor Manager available.' }}
          </p>
        </div>

        <div class="spacer" />
        <div class="actions">
          <button class="btn btn--secondary" type="button" @click="cancel">Cancel</button>
        </div>
      </template>

      <!-- Step 2: PIN -->
      <template v-else>
        <button class="back-link" type="button" @click="backToSelect">&larr; back to select user</button>

        <div class="pin-avatar">{{ selected?.name.charAt(0).toUpperCase() }}</div>
        <div class="sheet-title" style="text-align: center;">Confirm as {{ selected?.name }}</div>
        <div class="sheet-subtitle" style="text-align: center; font-style: italic;">
          {{ title }} · {{ selected?.roleLabel }}
        </div>

        <div class="pin-dots">
          <span v-for="i in Math.max(pin.length, 4)" :key="i" class="pin-dot" :class="{ 'pin-dot--filled': i <= pin.length }" />
        </div>

        <p v-if="error" class="pin-error">{{ error }}</p>
        <p v-else-if="submitting" class="pin-status">Verifying…</p>

        <div class="spacer" />

        <div class="keypad" :class="{ 'keypad--disabled': submitting }">
          <button v-for="k in keys" :key="k" type="button" class="keypad-btn" @click="appendDigit(k)">{{ k }}</button>
          <div />
          <button type="button" class="keypad-btn" @click="appendDigit('0')">0</button>
          <button type="button" class="keypad-btn keypad-btn--icon" @click="backspace">⌫</button>
        </div>

        <div class="actions">
          <button class="btn btn--secondary" type="button" @click="cancel">Cancel</button>
          <button class="btn btn--primary" type="button" :disabled="!pin.length || submitting" @click="submit">
            {{ submitting ? 'Verifying…' : 'Confirm' }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
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
.sheet-subtitle { font-size: 13px; color: var(--text-secondary); text-align: center; margin: 4px 0 16px; }
.notice {
  display: flex;
  gap: 10px;
  border: 1px solid var(--border);
  background: var(--bg);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  margin-bottom: 20px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}
.lbl { font-size: 11px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 10px; }
.people { overflow-y: auto; }
.person-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 10px;
  background: var(--surface);
  cursor: pointer;
  font-family: var(--font-sans);
  text-align: left;
}
.person-row--selected { border: 1.5px solid var(--accent); background: var(--accent-bg); }
.person-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--status-closed-bg);
  color: var(--text-secondary);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}
.person-row--selected .person-avatar { background: var(--accent); color: #fff; }
.person-name { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.person-role { font-size: 11.5px; color: var(--text-tertiary); }
.muted { color: var(--text-secondary); font-size: 13px; }
.spacer { flex-grow: 1; min-height: 12px; }
.actions { display: flex; gap: 14px; margin-top: 22px; }
.actions .btn { flex: 1; }

.back-link {
  border: none;
  background: none;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  text-align: center;
  cursor: pointer;
  margin-bottom: 10px;
}
.pin-avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  align-self: center;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 20px;
  margin-bottom: 12px;
}
.pin-dots { display: flex; gap: 12px; justify-content: center; margin-top: 22px; }
.pin-dot { width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--border-strong); }
.pin-dot--filled { background: var(--accent); border-color: var(--accent); }
.pin-error {
  text-align: center;
  font-size: 12.5px;
  color: var(--danger);
  margin-top: 12px;
}
.pin-status {
  text-align: center;
  font-size: 12.5px;
  color: var(--text-tertiary);
  margin-top: 12px;
}
.keypad { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.keypad--disabled { opacity: 0.5; pointer-events: none; }
.keypad-btn {
  height: var(--control-height-keypad);
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  font-family: var(--font-mono);
  font-size: 22px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
}
.keypad-btn--icon { font-size: 18px; }
</style>
