/**
 * src/stores/payoutRequests.js
 *
 * Just the Owner's pending-payout COUNT (added 2026-09-25) — feeds the
 * "Payout requests" sidebar tab's superscript badge in AppShell.vue.
 * Deliberately not the full payout list (PayoutsView.vue already owns
 * that, via its own fetch) — this store exists purely so the nav badge has
 * something to read shell-wide, without every page paying for the full
 * /transactions/ fetch PayoutsView's own client-side filter needs.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api/axios'

export const usePayoutRequestsStore = defineStore('payoutRequests', () => {
  const pendingCount = ref(0)
  const loading = ref(false)

  async function fetchPendingCount() {
    loading.value = true
    try {
      const { data } = await api.get('/transactions/pending-payouts-count/')
      pendingCount.value = data.count
    } catch {
      // Silent — a stale/missing badge is a minor cosmetic gap, not worth a
      // toast on every shell mount (matches gameDay.fetchCurrent()'s own
      // "own try/catch, no user-facing noise" convention at call sites).
    } finally {
      loading.value = false
    }
  }

  return { pendingCount, loading, fetchPendingCount }
})
