<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/axios'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import RowActionsMenu from '@/components/shared/RowActionsMenu.vue'
import ChipsLimitModal from '@/components/shared/ChipsLimitModal.vue'
import PlayerLedgerModal from '@/components/shared/PlayerLedgerModal.vue'
import DirectPayoutModal from '@/components/shared/DirectPayoutModal.vue'

// Player roster (Phase B, 2026-09-14) — GET /api/players/, IsAuthenticated.
// PlayerSerializer's `balance` is the unmasked lifetime figure (Cashier's own
// player list had a negative-balance masking rule that doesn't apply to
// Accountant/Owner — see accounts/serializers.py's get_balance).
//
// 2026-09-24: trimmed to Code/DVA, Name, Balance, Chips limit + a ⋮ actions
// column (Deal / Chips limit / View ledger / Payout) — "Chips used today"
// and the old "View →" link are gone from the table itself; the row itself
// still navigates to the full profile on click, same as before. Deal jumps
// straight to /deals/:id (the standalone Deals list page is retired — see
// PLAN.md); Chips limit and View ledger open a modal in place; Payout opens
// the new Owner-only direct-payout modal. Deal/Chips limit/Payout are
// Owner-only, matching RosterDetailView's own gating for the same actions;
// View ledger has no role restriction (read-only).
const router = useRouter()
const auth = useAuthStore()
const toast = useToast()

const players = ref([])
const loading = ref(true)
const search = ref('')

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/players/')
    players.value = data
  } catch {
    toast.error('Could not load the player roster.')
  } finally {
    loading.value = false
  }
}

onMounted(load)

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return players.value
  return players.value.filter(
    p => p.account_code.toLowerCase().includes(q) || p.display_name.toLowerCase().includes(q),
  )
})

function actionsFor(player) {
  if (!auth.isOwner) return [{ key: 'ledger', label: 'View ledger' }]
  return [
    { key: 'deal', label: 'Deal' },
    { key: 'chips-limit', label: 'Chips limit' },
    { key: 'ledger', label: 'View ledger' },
    { key: 'payout', label: 'Payout', disabled: !(Number(player.balance) > 0) },
  ]
}

const chipsLimitTarget = ref(null)
const ledgerTarget = ref(null)
const payoutTarget = ref(null)

function onSelectAction(player, key) {
  if (key === 'deal') router.push(`/deals/${player.id}`)
  else if (key === 'chips-limit') chipsLimitTarget.value = player
  else if (key === 'ledger') ledgerTarget.value = player
  else if (key === 'payout') payoutTarget.value = player
}

function onChipsLimitSaved() {
  chipsLimitTarget.value = null
  load()
}
function onPayoutSent() {
  payoutTarget.value = null
  load()
}

const N = n => `₦${Number(n).toLocaleString()}`
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Players</h1>
      <p>Full club roster — lifetime balance across every game-day and outstanding entry.</p>
    </div>

    <input v-model="search" type="text" placeholder="Search by name or account code…" class="search-input" />

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!filtered.length" class="muted">No players match.</p>

    <div v-else class="table">
      <div class="t-head">
        <span>Code/DVA</span><span>Name</span><span>Balance</span><span>Chips limit</span><span></span>
      </div>
      <div
        v-for="p in filtered" :key="p.id" class="t-row"
        @click="router.push(`/roster/${p.id}`)"
      >
        <span class="mono">{{ p.account_code }}</span>
        <span>{{ p.display_name }}<span v-if="!p.is_active" class="badge badge--closed inactive-badge">inactive</span></span>
        <span class="money" :class="p.balance > 0 ? 'money--pos' : p.balance < 0 ? 'money--neg' : ''">{{ N(p.balance) }}</span>
        <span class="money">{{ N(p.chips_limit) }}</span>
        <span class="actions-cell">
          <RowActionsMenu :items="actionsFor(p)" @select="key => onSelectAction(p, key)" />
        </span>
      </div>
    </div>

    <ChipsLimitModal
      v-if="chipsLimitTarget" :player="chipsLimitTarget"
      @close="chipsLimitTarget = null" @saved="onChipsLimitSaved"
    />
    <PlayerLedgerModal v-if="ledgerTarget" :player="ledgerTarget" @close="ledgerTarget = null" />
    <DirectPayoutModal
      v-if="payoutTarget" :player-id="payoutTarget.id" :player-name="payoutTarget.display_name"
      @close="payoutTarget = null" @paid="onPayoutSent"
    />
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.page-header { margin-bottom: 20px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }
.muted { color: var(--text-secondary); font-size: 13px; }

.search-input {
  width: 100%;
  max-width: 360px;
  height: var(--control-row-min);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 14px;
  font-family: var(--font-sans);
  font-size: 13.5px;
  color: var(--text-primary);
  background: var(--surface);
  margin-bottom: 16px;
}
.search-input:focus { outline: none; border-color: var(--accent); }

.table { border: 1px solid var(--border); border-radius: var(--radius-md); overflow: visible; background: var(--surface); }
.t-head, .t-row {
  display: grid;
  grid-template-columns: 110px 1.4fr 1fr 1fr 44px;
  align-items: center;
  padding: 0 20px;
  gap: 8px;
}
.t-head { height: var(--control-row-min); background: var(--bg); border-bottom: 1px solid var(--border); border-radius: var(--radius-md) var(--radius-md) 0 0; }
.t-head span { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.t-row { height: var(--control-row-max); border-bottom: 1px solid var(--border); font-size: 13.5px; color: var(--text-primary); cursor: pointer; }
.t-row:last-child { border-bottom: none; border-radius: 0 0 var(--radius-md) var(--radius-md); }
.t-row:hover { background: var(--bg); }
.mono { font-family: var(--font-mono); color: var(--text-secondary); }
.money--pos { color: var(--success-text); }
.money--neg { color: var(--danger-text); }
.inactive-badge { margin-left: 8px; }
.actions-cell { display: flex; justify-content: flex-end; }

@media (max-width: 860px) {
  .t-head { display: none; }
  .t-row { grid-template-columns: 1fr auto; height: auto; padding: 14px 20px; gap: 4px; }
  .t-row .mono, .t-row .money { grid-column: 1; }
}
</style>
