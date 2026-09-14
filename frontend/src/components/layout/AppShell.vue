<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useGameDayStore } from '@/stores/gameDay'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const gameDay = useGameDayStore()

onMounted(() => gameDay.fetchCurrent())

const initial = computed(() => (auth.user?.fullName || '?').trim().charAt(0).toUpperCase())

// Cashier has exactly one screen (Game Day) as of 2026-09-14 — no tab bar
// needed to navigate between one thing. Role-conditional (not a flat
// constant) so Owner/Accountant can get their own tabs here later without
// redoing this — see PLAN.md's Phase B/C.
const tabs = computed(() => {
  if (auth.user?.role === 'CASHIER') return []
  return [
    { name: 'game-day', label: 'Game Day', path: '/game-day' },
  ]
})

function isActive(tab) {
  return route.path === tab.path || route.path.startsWith(tab.path + '/')
}

async function onLogout() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand">LPC Cashier</div>
      <div class="spacer" />
      <div v-if="gameDay.isOpen" class="status-pill">
        <span class="status-dot" />
        Game-Day #{{ gameDay.current.number }} · OPEN
      </div>
      <div v-else class="status-pill status-pill--closed">No game-day open</div>
      <div class="user" :title="auth.user?.fullName">
        <div class="avatar">{{ initial }}</div>
        <button class="logout" type="button" @click="onLogout">Log out</button>
      </div>
    </header>

    <main class="content">
      <router-view />
    </main>

    <nav v-if="tabs.length" class="tabbar">
      <RouterLink
        v-for="tab in tabs" :key="tab.name" :to="tab.path"
        class="tab" :class="{ 'tab--active': isActive(tab) }"
      >
        {{ tab.label }}
      </RouterLink>
    </nav>
  </div>
</template>

<style scoped>
.shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}
.topbar {
  height: 72px;
  flex-shrink: 0;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 20px 0 24px;
  gap: 16px;
}
.brand {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}
.spacer { flex-grow: 1; }
.status-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--border-strong);
  background: var(--accent-bg);
  border-radius: 20px;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.status-pill--closed {
  background: var(--bg);
  color: var(--text-tertiary);
  font-weight: 500;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
}
.user {
  display: flex;
  align-items: center;
  gap: 12px;
}
.avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
}
.logout {
  border: none;
  background: none;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
}
.logout:hover { color: var(--text-primary); }

.content {
  flex-grow: 1;
  overflow-y: auto;
  padding: 20px;
}

.tabbar {
  height: 92px;
  flex-shrink: 0;
  background: var(--surface);
  border-top: 1px solid var(--border);
  display: flex;
  align-items: stretch;
  padding-bottom: 8px;
}
.tab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary);
  text-decoration: none;
  position: relative;
}
.tab--active {
  font-weight: 700;
  color: var(--accent);
}
.tab--active::before {
  content: '';
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 32px;
  height: 3px;
  background: var(--accent);
  border-radius: 2px;
}
</style>
