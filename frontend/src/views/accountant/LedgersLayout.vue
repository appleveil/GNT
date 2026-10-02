<script setup>
// Page chrome for the "Ledgers" section (renamed from "Game Days"
// 2026-09-26) — children Game Days, Off-table (was Outstanding, moved off
// Dashboard the same day), Deals (Owner-only, see LedgersDealsView.vue),
// and Main Account (moved in from its own top-level sidebar tab, same
// date — see AppShell.vue's nav list and router/index.js's
// `/main-account` redirect). Navigating between them is the sidebar's own
// indented Ledgers children (AppShell.vue) — this file's own in-page
// sub-tab strip was removed 2026-10-02 as duplicate chrome. Just the
// header + the matched child route; no data of its own.
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Ledgers</h1>
      <p>Game-day activity, and everything recorded off the table.</p>
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
