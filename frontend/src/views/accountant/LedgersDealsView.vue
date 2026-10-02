<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import api from '@/api/axios'
import ProfitSplitSummary from '@/components/shared/ProfitSplitSummary.vue'
import { useToast } from '@/composables/useToast'
import { readApiError } from '@/utils/apiError'

// Owner-only Ledgers -> Deals page (filled in 2026-10-02, replacing the
// "Details to follow" placeholder) — Profit Split performance, copying
// GameDaysListView.vue's own master/detail-on-one-page pattern exactly:
// a summary table up top (one row per game-day with any Profit Split
// activity), and clicking a row loads a detail table inline below it (no
// navigation), same scroll-into-view and 5-per-page pagination. See
// backend/gaming/selectors.py's deals_ledger_summary/deals_ledger_detail
// for the figures this reads, and PLAN.md's dated entry for the
// "Stake / Split" column's interpretation (two values in one cell: the
// deal's buy-in-side house_stake_pct, and the payout-side split term).
const toast = useToast()

const rows = ref([])
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/deals/ledger/')
    rows.value = data
    if (data.length) await openGameDay(data[0])
  } catch {
    toast.error('Could not load the Deals ledger.')
  } finally {
    loading.value = false
  }
}
onMounted(load)

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
const N = n => `₦${Number(n).toLocaleString()}`

// ── Pagination — same PAGE_SIZE as GameDaysListView.vue ───────────────────
const PAGE_SIZE = 5
const page = ref(1)
const totalPages = computed(() => Math.max(1, Math.ceil(rows.value.length / PAGE_SIZE)))
const pagedRows = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE
  return rows.value.slice(start, start + PAGE_SIZE)
})
const rangeLabel = computed(() => {
  if (!rows.value.length) return ''
  const start = (page.value - 1) * PAGE_SIZE + 1
  const end = Math.min(page.value * PAGE_SIZE, rows.value.length)
  return `Showing ${start}–${end} of ${rows.value.length} game-days`
})
function goToPage(n) {
  page.value = Math.min(Math.max(1, n), totalPages.value)
}

// ── Detail (opens inline below the list) ──────────────────────────────────
const detailId = ref(null)
const detailLoading = ref(false)
const detailRows = ref([])

async function loadDetail(gameDayId) {
  detailLoading.value = true
  try {
    const { data } = await api.get(`/deals/ledger/${gameDayId}/`)
    detailRows.value = data
  } catch {
    toast.error('Could not load this game-day.')
  } finally {
    detailLoading.value = false
  }
}

async function openGameDay(row) {
  detailId.value = row.game_day_id
  await loadDetail(row.game_day_id)
}

async function onViewGameDay(row) {
  if (detailId.value === row.game_day_id) return
  await openGameDay(row)
  await nextTick()
  document.getElementById('deals-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// Stake/Split column — see this file's own header comment: Stake is the
// deal's own buy-in-side house_stake_pct; Split is the payout-side term,
// a percentage for either ratio method, the fixed amount for Fixed, or
// "—" once that figure is 0 (how a "payout off" deal is stored — see
// DealProfitSplitView.vue's own onSubmit).
function splitDisplay(row) {
  if (row.payout_split_method === 'FIXED') {
    return row.fixed_amount && Number(row.fixed_amount) > 0 ? N(row.fixed_amount) : '—'
  }
  const pct = row.payout_split_method === 'STAKE_RATIO' ? row.house_stake_pct : row.custom_ratio_pct
  return pct && Number(pct) > 0 ? `${pct}%` : '—'
}

// ── Deal ID -> summary pop-up (no navigation) ─────────────────────────────
const dealSummaryOpen = ref(false)
const dealSummaryLoading = ref(false)
const dealSummary = ref(null)
const dealSummaryError = ref('')

async function onViewDeal(row) {
  dealSummaryOpen.value = true
  dealSummaryLoading.value = true
  dealSummaryError.value = ''
  try {
    const { data } = await api.get(`/deals/profit-split/arrangement/${row.arrangement_id}/`)
    dealSummary.value = data
  } catch (err) {
    dealSummaryError.value = readApiError(err, 'Could not load this deal.').message
  } finally {
    dealSummaryLoading.value = false
  }
}
function closeDealSummary() {
  dealSummaryOpen.value = false
  dealSummary.value = null
}
</script>

<template>
  <div class="page">
    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!rows.length" class="muted">No Profit Split activity recorded yet.</p>

    <template v-else>
      <div class="table">
        <div class="t-head">
          <span>Date</span><span>Stake</span><span>ROI</span><span>Net</span>
        </div>
        <div
          v-for="row in pagedRows" :key="row.game_day_id" class="t-row"
          :class="{ 't-row--selected': detailId === row.game_day_id }"
          @click="onViewGameDay(row)"
        >
          <span>{{ formatDate(row.date) }}</span>
          <span class="money">{{ N(row.stake_total) }}</span>
          <span class="money">{{ N(row.roi_total) }}</span>
          <span class="money" :class="Number(row.net) <= 0 ? 'money--pos' : 'money--neg'">{{ N(row.net) }}</span>
        </div>

        <div v-if="totalPages > 1" class="pagination">
          <span class="range-label">{{ rangeLabel }}</span>
          <div class="page-btns">
            <button class="page-btn" type="button" :disabled="page === 1" @click="goToPage(page - 1)">&larr; Prev</button>
            <button
              v-for="n in totalPages" :key="n" class="page-btn" type="button"
              :class="{ 'page-btn--current': page === n }" @click="goToPage(n)"
            >{{ n }}</button>
            <button class="page-btn" type="button" :disabled="page === totalPages" @click="goToPage(page + 1)">Next &rarr;</button>
          </div>
        </div>
      </div>

      <div v-if="detailId" id="deals-detail" class="detail">
        <p v-if="detailLoading" class="muted">Loading…</p>
        <template v-else>
          <p v-if="!detailRows.length" class="muted">No Profit Split activity for this game-day.</p>
          <div v-else class="detail-table">
            <div class="dt-head">
              <span>Player</span><span>Chips</span><span>Deal ID</span><span>Stake / Split</span>
              <span>SPA (₦)</span><span>Cash-out</span><span>ROI</span>
            </div>
            <div v-for="row in detailRows" :key="row.arrangement_id + '-' + row.player_id" class="dt-row">
              <span>{{ row.player_name }}</span>
              <span class="money">{{ N(row.chips) }}</span>
              <button class="deal-id-btn" type="button" @click="onViewDeal(row)">PS-{{ row.arrangement_id }}</button>
              <span>{{ row.house_stake_pct }}% / {{ splitDisplay(row) }}</span>
              <span class="money">{{ N(row.spa) }}</span>
              <span class="money">{{ N(row.cash_out) }}</span>
              <span class="money">{{ N(row.roi) }}</span>
            </div>
          </div>
        </template>
      </div>
    </template>

    <div v-if="dealSummaryOpen" class="overlay" @click.self="closeDealSummary">
      <div class="dialog">
        <button class="close-btn" type="button" @click="closeDealSummary">&times;</button>
        <p v-if="dealSummaryLoading" class="muted">Loading…</p>
        <p v-else-if="dealSummaryError" class="form-error">{{ dealSummaryError }}</p>
        <ProfitSplitSummary v-else-if="dealSummary" :status="dealSummary" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.muted { color: var(--text-secondary); font-size: 13px; }

.table { border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; background: var(--surface); }
.t-head, .t-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr;
  align-items: center;
  padding: 0 20px;
  gap: 8px;
}
.t-head { height: var(--control-row-min); background: var(--bg); border-bottom: 1px solid var(--border); }
.t-head span { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.t-row { height: var(--control-row-max); border-bottom: 1px solid var(--border); font-size: 13.5px; color: var(--text-primary); cursor: pointer; }
.t-row:last-child { border-bottom: none; }
.t-row:hover { background: var(--bg); }
.t-row--selected { background: var(--accent-bg); }
.t-row--selected:hover { background: var(--accent-bg); }
.money { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.money.money--pos { color: var(--success-text); }
.money.money--neg { color: var(--danger-text); }

.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
  background: var(--bg);
  font-size: 12px;
  color: var(--text-tertiary);
}
.page-btns { display: flex; gap: 6px; }
.page-btn {
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  padding: 5px 11px;
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
}
.page-btn:disabled { opacity: 0.45; cursor: default; }
.page-btn--current { border-color: var(--accent); color: var(--accent-text); font-weight: 700; }

/* ── Detail panel — opens inline below the list, same rhythm as
   GameDaysListView.vue's own ── */
.detail { margin-top: 26px; }
.detail-table { border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; background: var(--surface); }
.dt-head, .dt-row {
  display: grid;
  grid-template-columns: 1.4fr 1fr 0.9fr 1.3fr 1fr 1fr 1fr;
  align-items: center;
  padding: 0 20px;
  gap: 8px;
}
.dt-head { height: var(--control-row-min); background: var(--bg); border-bottom: 1px solid var(--border); }
.dt-head span { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
.dt-row { height: var(--control-row-max); border-bottom: 1px solid var(--border); font-size: 13.5px; color: var(--text-primary); }
.dt-row:last-child { border-bottom: none; }

.deal-id-btn {
  border: none;
  background: none;
  padding: 0;
  font-family: var(--font-mono);
  font-size: 12.5px;
  font-weight: 700;
  color: var(--accent-text);
  cursor: pointer;
  text-align: left;
  width: fit-content;
}
.deal-id-btn:hover { text-decoration: underline; }

.overlay { position: fixed; inset: 0; background: rgba(20, 25, 32, 0.5); display: flex; align-items: center; justify-content: center; z-index: 100; }
.dialog { position: relative; width: 480px; max-width: 92vw; }
.close-btn {
  position: absolute;
  top: -12px;
  right: -12px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-secondary);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  z-index: 1;
}
.close-btn:hover { color: var(--text-primary); }
.form-error { font-size: 13px; color: var(--danger-text); background: var(--danger-bg); border-radius: var(--radius-sm); padding: 10px 14px; }

@media (max-width: 860px) {
  .t-head, .dt-head { display: none; }
  .t-row { grid-template-columns: 1fr; height: auto; padding: 14px 20px; gap: 4px; }
  .dt-row { grid-template-columns: 1fr; height: auto; padding: 14px 20px; gap: 4px; }
}
</style>
