/**
 * src/composables/useToast.js
 *
 * Minimal shared toast/snackbar — module-level state (like useAuthorizerConfirm),
 * one <AppToast /> mounted once in App.vue. Just success/error variants; this
 * app doesn't need anything fancier yet.
 */
import { ref } from 'vue'

export const toasts = ref([]) // [{ id, message, variant }]

let nextId = 1

function push(message, variant = 'success', timeoutMs = 3500) {
  const id = nextId++
  toasts.value.push({ id, message, variant })
  setTimeout(() => dismiss(id), timeoutMs)
}

function dismiss(id) {
  toasts.value = toasts.value.filter(t => t.id !== id)
}

export function useToast() {
  return {
    toasts,
    success: message => push(message, 'success'),
    error: message => push(message, 'error'),
    dismiss,
  }
}
