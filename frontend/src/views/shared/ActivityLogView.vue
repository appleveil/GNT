<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ActivityLogList from '@/components/shared/ActivityLogList.vue'

// Route wrapper for the Floor Manager's sidebar tab and the Cashier's
// avatar-menu entry (added 2026-10-02) — Owner/Accountant get the same
// list inside AdminView.vue's own "Activity log" section instead, since
// Admin is already their shared page.
//
// Back link (2026-10-02) — Cashier-only: the Cashier has no sidebar at
// all (reaches this page from the avatar menu, not a persistent tab), so
// without one there's no way back except the avatar menu again or
// browser-back. The Floor Manager reaches this via their own sidebar tab,
// which stays visible here, so they don't need it — same reasoning as
// PlayerPayoutView.vue's back-btn, which is also only shown to a role
// that drilled in from a list with no other way back.
const router = useRouter()
const auth = useAuthStore()
</script>

<template>
  <div class="page">
    <button v-if="auth.isCashier" class="back-btn" type="button" @click="router.push('/game-day')">&larr; Game-day</button>
    <div class="page-header">
      <h1>Activity log</h1>
      <p>Who did what, and when.</p>
    </div>
    <ActivityLogList />
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.back-btn { border: none; background: none; font-size: 13.5px; font-weight: 600; color: var(--text-secondary); cursor: pointer; padding: 4px 0; margin-bottom: 16px; }
.back-btn:hover { color: var(--text-primary); }
.page-header { margin-bottom: 20px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }
</style>
