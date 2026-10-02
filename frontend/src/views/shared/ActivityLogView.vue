<script setup>
import ActivityLogList from '@/components/shared/ActivityLogList.vue'

// Route wrapper for the Floor Manager's sidebar tab and the Cashier's
// avatar-menu entry (added 2026-10-02) — Owner/Accountant get the same
// list inside AdminView.vue's own "Activity log" section instead, since
// Admin is already their shared page.
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Activity log</h1>
      <p>Who did what, and when.</p>
    </div>
    <ActivityLogList />
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.page-header { margin-bottom: 20px; }
.page-header h1 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; }
.page-header p { font-size: 13.5px; color: var(--text-secondary); margin: 0; }
</style>
