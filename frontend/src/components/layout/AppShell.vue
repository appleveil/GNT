<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useGameDayStore } from '@/stores/gameDay'
import { useCloseGameDay } from '@/composables/useCloseGameDay'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const gameDay = useGameDayStore()
const { openConfirm: onCloseGameDay } = useCloseGameDay()

onMounted(() => gameDay.fetchCurrent())

// "Close Game-Day" lives here, next to the status pill it acts on — was a
// small link buried at the bottom of the Cashier's ledger, easy to lose
// track of. Only Cashier/Owner can actually close one (gaming.views'
// GameDayViewSet.close: "Cashier, Owner, or a Floor Manager PIN" — Floor
// Manager's own PIN path isn't wired into any frontend button yet, and
// Accountant is read-only), so the button is gated the same way rather
// than shown to every role that merely sees the status pill. Added
// 2026-09-21, see the Cashier layout wireframe review this came out of.
const canCloseGameDay = computed(() => ['CASHIER', 'OWNER'].includes(auth.user?.role))

const initial = computed(() => (auth.user?.fullName || '?').trim().charAt(0).toUpperCase())

// Cashier has exactly one screen (Game Day) as of 2026-09-14 — no tab bar
// needed to navigate between one thing. Accountant gets the Phase B
// back-office nav (2026-09-14); Owner gets those same 4 plus two more of its
// own (Phase C, 2026-09-14) — "everything Accountant has, plus."
const tabs = computed(() => {
  const role = auth.user?.role
  if (role === 'CASHIER') return []
  if (role === 'FLOOR_MANAGER') return [{ name: 'service-staff', label: 'Service Staff', path: '/service-staff' }]
  const base = [
    { name: 'dashboard', label: 'Dashboard', path: '/dashboard' },
    { name: 'game-days', label: 'Game Days', path: '/game-days' },
    { name: 'outstanding', label: 'Outstanding', path: '/outstanding' },
    { name: 'roster', label: 'Players', path: '/roster' },
  ]
  if (role === 'OWNER') {
    base.push(
      { name: 'payouts', label: 'Payouts', path: '/payouts' },
      { name: 'main-account', label: 'Main Account', path: '/main-account' },
      { name: 'admin', label: 'Admin', path: '/admin' },
    )
  }
  return base
})

// Was a generic "LPC Cashier"/"LPC Owner"/... role label — both the
// original sketch and the lo-fi wireframe review used "Cashier Name" here
// instead, i.e. WHO is logged in, not a repeated app/role brand (the
// role is already legible from the accent color and the tab bar). Fixed
// 2026-09-21 for every role, not just Cashier, to keep "one shared
// system" actually consistent rather than fixing it in one place only.
const brand = computed(() => auth.user?.fullName || 'LPC')

function isActive(tab) {
  return route.path === tab.path || route.path.startsWith(tab.path + '/')
}

async function onLogout() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="stage">
    <div class="canvas">
      <div class="shell">
        <header class="topbar">
          <div class="brand">{{ brand }}</div>
          <div class="spacer" />
          <div v-if="gameDay.isOpen" class="status-pill">
            <span class="status-dot" />
            Game-Day #{{ gameDay.current.number }} · OPEN
          </div>
          <div v-else class="status-pill status-pill--closed">No game-day open</div>
          <button
            v-if="gameDay.isOpen && canCloseGameDay" class="close-gd-btn" type="button"
            @click="onCloseGameDay"
          >Close Game-Day</button>
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
    </div>
  </div>
</template>

<style scoped>
/* Three layers, matching the Ledger Directions review artifact's own
   page chrome, carried into the real app at the user's explicit
   request (2026-09-21) — not just the screens inside it:
     .stage  — the dark page background, full viewport (--stage)
     .canvas — a pale (--bg) mat/frame, FIXED width (1166px, matching
               the review artifact's own app width — not a responsive
               max-width)
     .shell  — the app's own structural frame, same pale tone as the
               canvas (its job is the rounded/shadowed edge, not a
               color change) — topbar is explicitly white so it still
               reads as a distinct bar; page content stays on the pale
               tone, and it's up to each screen which of its own
               sections (if any) go white — see ActiveGameDayView's
               .screen-frame for the "only some sections are boxed
               white" treatment the user asked for on the Cashier page.
   Every role shares this same frame — only --accent differs. */
.stage {
  min-height: 100vh;
  background: var(--stage);
  display: flex;
  max-width: 1180px;
  margin: 0 auto;
  overflow: hidden;
  border: 1px solid #22252A;
}
.canvas {
  flex: 1;
  min-width: 0;
  max-width: 100%;
  margin: 0 auto;
  background: var(--bg);
  border-radius: 24px;
  padding: 44px 6px 60px;
  display: flex;
}
.shell {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  border-radius: 16px;
  box-shadow: var(--shadow-md);
  overflow: hidden;
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
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}
.spacer { flex-grow: 1; }
/* A colored-ledger-tab shape (accent-left-border + asymmetric radius),
   not a plain neutral pill — this is the one place every role's own
   accent color is on screen at all times, so it's worth it actually
   reading as "your" color rather than a faint tint. Revised 2026-09-21,
   see the Ledger Directions review artifact this mirrors. */
.status-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--accent-bg);
  border-left: 4px solid var(--accent);
  border-radius: 6px 20px 20px 6px;
  padding: 8px 16px 8px 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-text);
}
.status-pill--closed {
  background: var(--bg);
  border-left-color: var(--border-strong);
  color: var(--text-tertiary);
  font-weight: 500;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
}
.close-gd-btn {
  height: 34px;
  padding: 0 14px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  font-family: var(--font-sans);
  font-size: 12.5px;
  font-weight: 700;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
}
.close-gd-btn:hover { border-color: var(--accent); color: var(--accent-text); }
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
