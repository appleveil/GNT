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

export const useGameDayStore = defineStore('gameDay', () => {
  const current = ref(null) // GameDay object, or null if none is open
  const loading = ref(false)

  const isOpen = computed(() => !!current.value)

  async function fetchCurrent() {
    loading.value = true
    try {
      const { data } = await api.get('/game-days/current/')
      current.value = data
    } finally {
      loading.value = false
    }
  }

  return { current, loading, isOpen, fetchCurrent }
})
