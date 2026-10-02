<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// Sub-nav chrome for the "Ledgers" section (renamed from "Game Days"
// 2026-09-26) — children Game Days, Off-table (was Outstanding, moved off
// Dashboard the same day), and Deals (Owner-only placeholder, added
// 2026-10-02 — content pending from the Owner, see LedgersDealsView.vue).
// Just a small pill tab-strip + the matched child route; no data of its own.
const route = useRoute()
const auth = useAuthStore()

const ALL_TABS = [
  { name: 'ledgers-game-days', label: 'Game Days', path: '/ledgers/game-days' },
  { name: 'ledgers-off-table', label: 'Off-table', path: '/ledgers/off-table' },
  { name: 'ledgers-deals', label: 'Deals', path: '/ledgers/deals', ownerOnly: true },
]
const TABS = computed(() => ALL_TABS.filter(t => !t.ownerOnly || auth.isOwner))

function isActive(tab) {
  return route.name === tab.name
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Ledgers</h1>
      <p>Game-day activity, and everything recorded off the table.</p>
    </div>

    <div class="sub-tabs">
      <RouterLink
        v-for="tab in TABS" :key="tab.name" :to="tab.path" class="sub-tab"
        :class="{ 'sub-tab--active': isActive(tab) }"
      >{{ tab.label }}</RouterLink>
    </div>

    <router-view />
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.page-header { margin-bottom: 20px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }

.sub-tabs { display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid var(--border); }
.sub-tab {
  padding: 0 4px 10px;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-secondary);
  text-decoration: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.sub-tab:hover { color: var(--text-primary); }
.sub-tab--active { color: var(--accent-text); border-bottom-color: var(--accent); }
</style>
