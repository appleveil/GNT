/**
 * src/stores/clubSettings.js
 *
 * The club's Owner-configurable settings (added 2026-09-23, GET
 * /club-settings/): 5 require_approval_* toggles + the payout
 * auto-approval threshold. Fetched once and shared — every role needs
 * the toggles to decide PIN-vs-plain-confirm for a gated action (see
 * usePlainConfirm.js and its call sites), not just the Owner who edits
 * them. Mirrors stores/gameDay.js's own shape.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api/axios'
import { useToast } from '@/composables/useToast'

export const useClubSettingsStore = defineStore('clubSettings', () => {
  const current = ref(null) // the settings object, or null until loaded
  const loading = ref(false)
  const toast = useToast()

  async function fetchCurrent() {
    loading.value = true
    try {
      const { data } = await api.get('/club-settings/')
      current.value = data
    } catch (err) {
      // A gated action falls back to its PIN sheet (the safer default)
      // whenever `current` is still null — see each call site's own
      // `=== false` check, which only ever short-circuits on an explicit
      // false, never on a missing/failed fetch.
      toast.error('Could not load club settings — sign-off will default to requiring a PIN.')
      throw err
    } finally {
      loading.value = false
    }
  }

  return { current, loading, fetchCurrent }
})
