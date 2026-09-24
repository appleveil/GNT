<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/api/axios'
import RejectPayoutModal from '@/components/shared/RejectPayoutModal.vue'
import { usePayoutRequestsStore } from '@/stores/payoutRequests'
import { useToast } from '@/composables/useToast'

// Owner-only payout approval queue (Phase C, 2026-09-14). No "list pending"
// endpoint exists server-side (TransactionViewSet has no filter backend
// configured) — an accepted trade-off at this club's scale, so this fetches
// the full transaction list and filters client-side, same pattern as
// Roster's search. approve_payout (gaming/services.py) handles both a first
// approval (PENDING_APPROVAL) and retrying a failed transfer
// (TRANSFER_FAILED) via the same call.
//
// Rejection (2026-09-15, RejectPayoutModal) reuses void's fields under the
// hood (reject_payout sets is_voided=True so the amount drops out of every
// balance sum) — so a rejected row's status is REJECTED *and* is_voided is
// true. Check status first in the history badge below, or every rejected
// payout would render as a bare "VOIDED" instead of "Declined" with its reason.
//
// Auto-approval (2026-09-23, ClubSettings.payout_auto_approve_threshold):
// initiate_payout/initiate_direct_payout immediately approve a payout at or
// under the threshold, with approved_by left null as the marker that no one
// manually signed off (see _execute_payout_transfer in gaming/services.py).
// A status of APPROVED with no approved_by is what distinguishes an
// auto-approval from a manual "Approved" in the history badge below — never
// inferred from amount here, since the threshold can change after the fact.
// Labeled "Auto-<Cashier Name>" (recorded_by_name, 2026-09-25) rather than a
// generic "Auto-approved" — names who actually initiated it.
const toast = useToast()
const payoutRequests = usePayoutRequestsStore()

const players = ref([])
const transactions = ref([])
const loading = ref(true)
const approvingId = ref(null)
const rejectTarget = ref(null)

async function load() {
  loading.value = true
  try {
    const [playersRes, txRes] = await Promise.all([
      api.get('/players/'),
      api.get('/transactions/'),
    ])
    players.value = playersRes.data
    transactions.value = txRes.data.filter(t => t.type === 'PAYOUT')
  } catch {
    toast.error('Could not load payouts.')
  } finally {
    loading.value = false
  }
  payoutRequests.fetchPendingCount() // keeps the sidebar badge in step with whatever changed here
}

onMounted(load)

function playerName(playerId) {
  return players.value.find(p => p.id === playerId)?.display_name || ''
}

const pending = computed(() =>
  transactions.value.filter(t => ['PENDING_APPROVAL', 'TRANSFER_FAILED'].includes(t.status)),
)
const history = computed(() =>
  transactions.value
    .filter(t => !['PENDING_APPROVAL', 'TRANSFER_FAILED'].includes(t.status))
    .slice()
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    .slice(0, 15),
)

async function onApprove(t) {
  approvingId.value = t.id
  try {
    await api.post(`/transactions/${t.id}/approve/`)
    toast.success(`${playerName(t.player)}'s payout approved.`)
    load()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Could not approve this payout.')
  } finally {
    approvingId.value = null
  }
}

function onRejected() {
  toast.success(`${playerName(rejectTarget.value.player)}'s payout declined.`)
  rejectTarget.value = null
  load()
}

function formatTime(iso) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}
function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Payouts</h1>
      <p>Approve a pending payout, or retry one whose transfer failed.</p>
    </div>

    <p v-if="loading" class="muted">Loading…</p>

    <template v-else>
      <div class="card section-card">
        <div class="section-title">Pending</div>
        <p v-if="!pending.length" class="muted">Nothing waiting on approval.</p>
        <div v-for="t in pending" :key="t.id" class="row">
          <div class="row-info">
            <div class="row-name">
              <RouterLink :to="`/roster/${t.player}`" class="player-link">{{ playerName(t.player) }}</RouterLink>
              <span class="badge" :class="t.status === 'TRANSFER_FAILED' ? 'badge--rejected' : 'badge--pending'">{{ t.status.replace('_', ' ') }}</span>
            </div>
            <div class="row-sub">{{ formatDate(t.created_at) }} &middot; {{ formatTime(t.created_at) }}</div>
          </div>
          <div class="money">{{ N(t.amount) }}</div>
          <div class="row-actions">
            <button
              class="btn btn--primary" type="button" :disabled="approvingId === t.id"
              @click="onApprove(t)"
            >
              {{ approvingId === t.id ? 'Working…' : t.status === 'TRANSFER_FAILED' ? 'Retry transfer' : 'Approve' }}
            </button>
            <button class="btn btn--danger" type="button" :disabled="approvingId === t.id" @click="rejectTarget = t">Decline</button>
          </div>
        </div>
      </div>

      <div class="card section-card">
        <div class="section-title">Recent history</div>
        <p v-if="!history.length" class="muted">No approved or declined payouts yet.</p>
        <div v-for="t in history" :key="t.id" class="row">
          <div class="row-info">
            <div class="row-name">
              <RouterLink :to="`/roster/${t.player}`" class="player-link">{{ playerName(t.player) }}</RouterLink>
              <span v-if="t.status === 'REJECTED'" class="badge badge--rejected">Declined</span>
              <span v-else-if="t.is_voided" class="badge badge--voided">VOIDED</span>
              <span v-else-if="t.status === 'APPROVED' && !t.approved_by" class="badge badge--auto-approved">Auto-{{ t.recorded_by_name || 'Cashier' }}</span>
              <span v-else class="badge badge--approved">{{ t.status.replace('_', ' ') }}</span>
            </div>
            <div class="row-sub">
              {{ formatDate(t.created_at) }} &middot; {{ formatTime(t.created_at) }}
              <template v-if="t.status === 'REJECTED' && t.void_reason"> &middot; "{{ t.void_reason }}"</template>
            </div>
          </div>
          <div class="money">{{ N(t.amount) }}</div>
        </div>
      </div>
    </template>

    <RejectPayoutModal
      v-if="rejectTarget" :transaction="rejectTarget" :player-name="playerName(rejectTarget.player)"
      @close="rejectTarget = null" @rejected="onRejected"
    />
  </div>
</template>

<style scoped>
.page { max-width: 900px; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }
.muted { color: var(--text-secondary); font-size: 13px; }

.section-card { padding: 18px 20px; margin-bottom: 16px; }
.section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; }

.row { display: flex; align-items: center; gap: 14px; padding: 12px 0; border-bottom: 1px solid var(--border); }
.row:last-child { border-bottom: none; }
.row-info { flex-grow: 1; min-width: 0; }
.row-name { font-size: 13.5px; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.player-link { color: var(--text-primary); text-decoration: none; }
.player-link:hover { color: var(--accent-text); text-decoration: underline; }
.row-sub { font-size: 11.5px; color: var(--text-tertiary); margin-top: 2px; }
.money { font-family: var(--font-mono); font-weight: 700; font-size: 14px; color: var(--text-primary); flex-shrink: 0; }
.row-actions { display: flex; gap: 8px; flex-shrink: 0; }
</style>
