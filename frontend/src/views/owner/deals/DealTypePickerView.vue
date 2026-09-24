<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/axios'
import { useAuthStore } from '@/stores/auth'
import LedgerTable from '@/components/shared/LedgerTable.vue'
import VoidEntryModal from '@/components/shared/VoidEntryModal.vue'
import { canVoidTransaction } from '@/utils/canVoid'
import { useToast } from '@/composables/useToast'

// Deal-type picker (2026-09-23) — mirrors the mobile app's
// DealTypePickerScreen.tsx: Fixed only makes sense against debt, Transfer
// only against a positive balance, Stake and Profit Splits is always
// available and shows an ACTIVE badge if one already exists. Eligibility
// here is a UX nicety only — record_transaction/record_deal_transfer both
// enforce the same caps server-side regardless.
//
// 2026-09-24: this player's own Deal history moved in here (below the type
// picker) once the standalone Deals list/history pages were retired — every
// player now reaches their deal page straight from the Players table's ⋮
// menu, so a club-wide feed elsewhere is no longer this page's neighbor.
// Same 4 types DealsHistoryView filtered to, just scoped to this player via
// GET /transactions/?player=<id> (no dedicated backend filter for "deal
// transactions", same accepted trade-off as PayoutsView.vue's own
// client-side filter).
const DEAL_TYPES = ['WRITE_OFF', 'DEAL_TRANSFER_OUT', 'DEAL_TRANSFER_IN', 'PROFIT_SPLIT_STAKE']

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const toast = useToast()

const player = ref(null)
const loading = ref(true)
const activeArrangement = ref(null)

const history = ref([])
const historyLoading = ref(true)
const voidTarget = ref(null)

async function load() {
  loading.value = true
  try {
    const [playerRes, arrangementRes] = await Promise.all([
      api.get(`/players/${route.params.playerId}/`),
      api.get(`/deals/profit-split/${route.params.playerId}/`),
    ])
    player.value = playerRes.data
    activeArrangement.value = arrangementRes.data
  } catch {
    toast.error('Could not load this player.')
  } finally {
    loading.value = false
  }
  loadHistory() // own try/catch, own toast — never blocks the picker above
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const { data } = await api.get('/transactions/', { params: { player: route.params.playerId } })
    history.value = data
      .filter(t => DEAL_TYPES.includes(t.type))
      .slice()
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  } catch {
    toast.error('Could not load this player’s deal history.')
  } finally {
    historyLoading.value = false
  }
}

onMounted(load)

const hasDebt = computed(() => player.value && Number(player.value.balance) < 0)
const hasFunds = computed(() => player.value && Number(player.value.balance) > 0)

function canVoid(row) {
  return canVoidTransaction(row, auth.user)
}
function onVoided() {
  voidTarget.value = null
  toast.success('Entry voided.')
  loadHistory()
}

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="page">
    <button class="back-btn" type="button" @click="router.push('/roster')">&larr; Players</button>

    <p v-if="loading" class="muted">Loading…</p>

    <template v-else-if="player">
      <div class="page-header">
        <h1>{{ player.display_name }}</h1>
        <p class="code">{{ player.account_code }}</p>
      </div>

      <div class="card balance-card">
        <div class="balance-label">Balance</div>
        <div class="balance-amount" :class="hasDebt ? 'money--neg' : hasFunds ? 'money--pos' : ''">{{ N(player.balance) }}</div>
      </div>

      <button
        class="deal-type" type="button" :class="{ 'deal-type--disabled': !hasDebt }"
        :disabled="!hasDebt" @click="router.push(`/deals/${player.id}/fixed`)"
      >
        <div class="deal-type-title-row">
          <span class="deal-type-title">Fixed</span>
        </div>
        <p class="deal-type-desc">
          {{ hasDebt ? "Reduce this player's outstanding debt by a fixed amount. Can't be reversed." : 'No outstanding balance to forgive.' }}
        </p>
      </button>

      <button
        class="deal-type" type="button" :class="{ 'deal-type--disabled': !hasFunds }"
        :disabled="!hasFunds" @click="router.push(`/deals/${player.id}/transfer`)"
      >
        <div class="deal-type-title-row">
          <span class="deal-type-title">Transfer</span>
        </div>
        <p class="deal-type-desc">
          {{ hasFunds ? "Use this player's excess balance to help settle another player's debt." : 'No available balance to transfer.' }}
        </p>
      </button>

      <button class="deal-type" type="button" @click="router.push(`/deals/${player.id}/profit-split`)">
        <div class="deal-type-title-row">
          <span class="deal-type-title">Stake and Profit splits</span>
          <span v-if="activeArrangement" class="badge badge--approved">ACTIVE</span>
        </div>
        <p class="deal-type-desc">A standing arrangement — house covers part of buy-in and/or takes a payout cut.</p>
      </button>

      <div class="section-heading">
        <h2>Deal history</h2>
      </div>
      <p v-if="historyLoading" class="muted">Loading…</p>
      <p v-else-if="!history.length" class="muted">Nothing recorded for {{ player.display_name }} yet.</p>
      <div v-else class="card history-card">
        <LedgerTable :rows="history" date-format="datetime" voidable :can-void-fn="canVoid" @void="voidTarget = $event" />
      </div>
    </template>

    <VoidEntryModal
      v-if="voidTarget" :transaction="voidTarget" :player-name="player?.display_name"
      :recorded-by-name="auth.user?.fullName" @close="voidTarget = null" @voided="onVoided"
    />
  </div>
</template>

<style scoped>
.page { max-width: 560px; }
.back-btn { border: none; background: none; font-size: 13.5px; font-weight: 600; color: var(--text-secondary); cursor: pointer; padding: 4px 0; margin-bottom: 16px; }
.back-btn:hover { color: var(--text-primary); }
.muted { color: var(--text-secondary); font-size: 13px; }

.page-header { margin-bottom: 20px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 2px; }
.code { font-family: var(--font-mono); font-size: 12.5px; color: var(--text-tertiary); margin: 0; }

.balance-card { padding: 22px; text-align: center; margin-bottom: 20px; }
.balance-label { font-size: 11px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 6px; }
.balance-amount { font-family: var(--font-mono); font-weight: 700; font-size: 30px; color: var(--text-primary); }
.money--pos { color: var(--success-text); }
.money--neg { color: var(--danger-text); }

.deal-type {
  display: block;
  width: 100%;
  text-align: left;
  border: 1.5px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
  padding: 16px 18px;
  margin-bottom: 10px;
  font-family: var(--font-sans);
  cursor: pointer;
}
.deal-type:hover { border-color: var(--accent); }
.deal-type--disabled { opacity: 0.45; cursor: default; }
.deal-type--disabled:hover { border-color: var(--border); }
.deal-type-title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
.deal-type-title { font-size: 14.5px; font-weight: 700; color: var(--text-primary); }
.deal-type-desc { font-size: 12.5px; color: var(--text-secondary); line-height: 1.5; margin: 0; }

.section-heading { margin: 24px 0 12px; }
.section-heading h2 { font-size: 15px; font-weight: 700; color: var(--text-primary); margin: 0; }
.history-card { padding: 8px 18px; }
</style>
