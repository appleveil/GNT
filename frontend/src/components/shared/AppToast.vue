<script setup>
import { useToast } from '@/composables/useToast'

const { toasts, dismiss } = useToast()
</script>

<template>
  <div class="toast-stack">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="`toast--${t.variant}`" @click="dismiss(t.id)">
      {{ t.message }}
    </div>
  </div>
</template>

<style scoped>
.toast-stack {
  position: fixed;
  bottom: 108px; /* clears AppShell's bottom tab bar */
  left: 50%;
  transform: translateX(-50%);
  z-index: 200;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  width: 100%;
  max-width: 480px;
  padding: 0 20px;
}
.toast {
  width: 100%;
  border-radius: var(--radius-sm);
  padding: 12px 16px;
  font-size: 13.5px;
  font-weight: 600;
  text-align: center;
  box-shadow: var(--shadow-md);
  cursor: pointer;
}
.toast--success { background: var(--success); color: #fff; }
.toast--error { background: var(--danger); color: #fff; }
</style>
