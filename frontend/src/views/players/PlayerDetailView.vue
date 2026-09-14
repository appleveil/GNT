<script setup>
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <div class="card placeholder">
    <div class="eyebrow">Player #{{ route.params.id }}</div>
    <p class="muted">Not built yet — balance, bank accounts, payout initiation.</p>
  </div>
</template>

<style scoped>
.placeholder { padding: 24px; display: flex; flex-direction: column; gap: 10px; }
.muted { color: var(--text-secondary); font-size: 13px; }
</style>
