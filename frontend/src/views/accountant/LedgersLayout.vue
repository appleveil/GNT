<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

// Page chrome for the "Ledgers" section (renamed from "Game Days"
// 2026-09-26) — children Game Days, Off-table (was Outstanding, moved off
// Dashboard the same day), Deals (Owner-only, see LedgersDealsView.vue),
// and Main Account (moved in from its own top-level sidebar tab, same
// date — see AppShell.vue's nav list and router/index.js's
// `/main-account` redirect). Navigating between them is the sidebar's own
// indented Ledgers children (AppShell.vue) — this file's own in-page
// sub-tab strip was removed 2026-10-02 as duplicate chrome.
//
// The header below is per-CHILD page (revised 2026-10-02 — it used to say
// "Ledgers" and a two-ledger description no matter which sub-page was
// open, stale once Deals/Main Account joined Game Days/Off-table here).
// Titles match AppShell.vue's own Ledgers children labels exactly;
// descriptions summarize each ledger's own scope per CONCEPT.md.
const route = useRoute()
const PAGES = {
  'ledgers-game-days': {
    title: 'Game Days',
    description: "Every game-day's chips, payments, and rake — click a night for the full player-by-player detail.",
  },
  'ledgers-off-table': {
    title: 'Off-table',
    description: 'Activity recorded outside any game-day — deals, write-offs, and direct payments.',
  },
  'ledgers-deals': {
    title: 'Deals',
    description: 'Profit-Split performance — SPA Out, SPA In, and ROI for every game-day with an active deal.',
  },
  'ledgers-main-account': {
    title: 'Main Account',
    description: "The club's own bank account — deposits in, payouts out, no chip activity.",
  },
}
const page = computed(() => PAGES[route.name] || { title: 'Ledgers', description: '' })
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>{{ page.title }}</h1>
      <p>{{ page.description }}</p>
    </div>

    <router-view />
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.page-header { margin-bottom: 20px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }
</style>
