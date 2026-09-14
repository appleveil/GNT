/**
 * src/stores/gameDay.js
 *
 * The currently open game-day (or null). Almost every Cashier screen is
 * scoped to this — the Players list, chip/payment entry, payouts — so it's
 * fetched once here and shared, not re-fetched by every view that needs it.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api/axios'
import { useToast } from '@/composables/useToast'

export const useGameDayStore = defineStore('gameDay', () => {
  const current = ref(null) // GameDay object, or null if none is open
  const loading = ref(false)
  const toast = useToast()

  const isOpen = computed(() => !!current.value)

  async function fetchCurrent() {
    loading.value = true
    try {
      const { data } = await api.get('/game-days/current/')
      current.value = data
    } catch (err) {
      // Found live 2026-09-14: this had no catch at all, so a failed call
      // here silently left `current` as null — indistinguishable from "no
      // game-day is actually open" to whoever's looking at the screen. A
      // toast here covers every caller uniformly, including AppShell's
      // fire-and-forget onMounted call and any view that doesn't wrap this
      // in its own try/catch; callers that DO have their own handling still
      // get the rethrow to act on.
      toast.error('Could not check whether a game-day is open — try refreshing.')
      throw err
    } finally {
      loading.value = false
    }
  }

  return { current, loading, isOpen, fetchCurrent }
})
