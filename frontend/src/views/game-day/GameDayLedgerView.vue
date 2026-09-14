<script setup>
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <div class="placeholder card">
    <div class="eyebrow">Game-Day Ledger — #{{ route.params.id }}</div>
    <p class="muted">Not built yet — shares a LedgerTable component with the Outstanding Ledger.</p>
  </div>
</template>

<style scoped>
.placeholder { padding: 24px; display: flex; flex-direction: column; gap: 10px; }
.muted { color: var(--text-secondary); font-size: 13px; }
</style>
