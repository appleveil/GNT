/**
 * src/composables/useCloseGameDay.js
 *
 * Shared "Close Game-Day" flow — module-level state (same pattern as
 * useAuthorizerConfirm/useToast), one <CloseGameDayModal /> mounted once in
 * App.vue. Moved out of ActiveGameDayView.vue (2026-09-21) so the trigger
 * can live in AppShell's topbar, next to the "Game-Day #N · OPEN" status
 * pill it acts on, instead of a small link buried at the bottom of the
 * ledger — see the Cashier layout wireframe review this came out of.
 */
import { ref } from 'vue'
import api from '@/api/axios'
import { useGameDayStore } from '@/stores/gameDay'

export const preview = ref(null) // null = dialog closed; the close-preview payload otherwise
export const closing = ref(false)
export const error = ref('')

export function useCloseGameDay() {
  const gameDay = useGameDayStore()

  async function openConfirm() {
    error.value = ''
    try {
      const { data } = await api.get(`/game-days/${gameDay.current.id}/close-preview/`)
      preview.value = data
    } catch {
      error.value = 'Could not load game-day totals.'
    }
  }

  async function confirm() {
    closing.value = true
    error.value = ''
    try {
      await api.post(`/game-days/${gameDay.current.id}/close/`, {})
      preview.value = null
      gameDay.current = null
    } catch (err) {
      error.value = err.response?.data?.detail || 'Could not close the game-day.'
    } finally {
      closing.value = false
    }
  }

  function cancel() {
    preview.value = null
    error.value = ''
  }

  return { preview, closing, error, openConfirm, confirm, cancel }
}
