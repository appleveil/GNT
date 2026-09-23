<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useGameDayStore } from '@/stores/gameDay'
import { useClubSettingsStore } from '@/stores/clubSettings'
import { useCloseGameDay } from '@/composables/useCloseGameDay'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const gameDay = useGameDayStore()
const clubSettings = useClubSettingsStore()
const { openConfirm: onCloseGameDay } = useCloseGameDay()

onMounted(() => {
  gameDay.fetchCurrent()
  clubSettings.fetchCurrent()
})

// "Close Game-Day" lives here, next to the status pill it acts on — was a
// small link buried at the bottom of the Cashier's ledger, easy to lose
// track of. Only Cashier/Owner can actually close one (gaming.views'
// GameDayViewSet.close: "Cashier, Owner, or a Floor Manager PIN" — Floor
// Manager's own PIN path isn't wired into any frontend button yet, and
// Accountant is read-only), so the button is gated the same way rather
// than shown to every role that merely sees the status pill. Added
// 2026-09-21, see the Cashier layout wireframe review this came out of.
const canCloseGameDay = computed(() => ['CASHIER', 'OWNER'].includes(auth.user?.role))

// The game-day status pill only means something on the screen that actually
// works a game-day — the Cashier's live view (route 'game-day', which Owner
// can also reach per router/index.js's comment on why that route stays
// unrestricted). Everywhere else (Dashboard, Payouts, Admin, ...) it was
// showing in every role's topbar regardless of what they were looking at;
// narrowed 2026-09-23 per the lo-fi nav review.
const showGameDayStatus = computed(() => route.name === 'game-day')

const initial = computed(() => (auth.user?.fullName || '?').trim().charAt(0).toUpperCase())

// The game-day's own date wasn't shown anywhere in the app at all — added
// into the status pill itself (2026-09-22, per the Cashier layout review)
// rather than a separate element, so every "which game-day am I in" fact
// (number, date, status) reads from the one pill everyone already checks.
// `started_at` was already on GameDaySerializer — no backend change needed.
const gameDayDate = computed(() => {
  if (!gameDay.current?.started_at) return ''
  return new Date(gameDay.current.started_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
})

// Cashier has exactly one screen (Game Day) as of 2026-09-14 — no tab bar
// needed to navigate between one thing. Accountant gets the Phase B
// back-office nav (2026-09-14); Owner gets those same 3 plus its own
// Payouts/Main Account/Admin/Settings (Phase C, 2026-09-14) — "everything
// Accountant has, plus." Outstanding was its own 4th base tab until
// 2026-09-23, when its whole page was folded into Dashboard and this tab
// (and the standalone route) were retired.
const tabs = computed(() => {
  const role = auth.user?.role
  if (role === 'CASHIER') return []
  if (role === 'FLOOR_MANAGER') {
    return [
      { name: 'masseuses', label: 'Masseuses', path: '/masseuses' },
      { name: 'club-settings', label: 'Settings', path: '/settings' },
    ]
  }
  const base = [
    { name: 'dashboard', label: 'Dashboard', path: '/dashboard' },
    { name: 'game-days', label: 'Game Days', path: '/game-days' },
    { name: 'roster', label: 'Players', path: '/roster' },
  ]
  if (role === 'OWNER') {
    base.push(
      { name: 'payouts', label: 'Payouts', path: '/payouts' },
      { name: 'main-account', label: 'Main Account', path: '/main-account' },
      { name: 'admin', label: 'Admin', path: '/admin' },
      { name: 'club-settings', label: 'Settings', path: '/settings' },
    )
  }
  return base
})

// Settings is visually pinned to the bottom of the sidebar (2026-09-23 hi-fi
// pass, per the lo-fi nav review sketch) — everything else in `tabs` renders
// in its declared order above a spacer, Settings renders on its own below
// it. Splitting the one `tabs` array here (rather than changing what tabs()
// returns) keeps isActive/tabs a single source of truth for both the sidebar
// and anything else that reads it later.
const mainTabs = computed(() => tabs.value.filter(t => t.name !== 'club-settings'))
const settingsTab = computed(() => tabs.value.find(t => t.name === 'club-settings'))

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

// Logging out never closes a game-day (it just ends this browser session —
// the game-day itself stays open for whoever logs back in, or another
// device). That's easy to mistake for "wrapping up the night," so a
// still-open game-day gets one confirmation step first. Added 2026-09-22.
const logoutConfirmOpen = ref(false)
function onLogoutClick() {
  if (gameDay.isOpen) logoutConfirmOpen.value = true
  else doLogout()
}
function onCancelLogout() {
  logoutConfirmOpen.value = false
}
async function doLogout() {
  logoutConfirmOpen.value = false
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
          <template v-if="showGameDayStatus">
            <div v-if="gameDay.isOpen" class="status-pill">
              <span class="status-dot" />
              Game-Day #{{ gameDay.current.number }}<template v-if="gameDayDate"> · {{ gameDayDate }}</template> · OPEN
            </div>
            <div v-else class="status-pill status-pill--closed">No game-day open</div>
            <button
              v-if="gameDay.isOpen && canCloseGameDay" class="close-gd-btn" type="button"
              @click="onCloseGameDay"
            >Close Game-Day</button>
          </template>
          <div class="user" :title="auth.user?.fullName">
            <div class="avatar">{{ initial }}</div>
            <button class="logout" type="button" @click="onLogoutClick">Log out</button>
          </div>
        </header>

        <div class="below-topbar">
          <nav v-if="tabs.length" class="sidebar">
            <RouterLink
              v-for="tab in mainTabs" :key="tab.name" :to="tab.path"
              class="side-tab" :class="{ 'side-tab--active': isActive(tab) }"
            >
              {{ tab.label }}
            </RouterLink>
            <div class="sidebar-spacer" />
            <RouterLink
              v-if="settingsTab" :to="settingsTab.path"
              class="side-tab side-tab--settings" :class="{ 'side-tab--active': isActive(settingsTab) }"
            >
              {{ settingsTab.label }}
            </RouterLink>
          </nav>

          <main class="content">
            <router-view />
          </main>
        </div>
      </div>
    </div>

    <!-- Logout while a game-day is open — see onLogoutClick's own comment. -->
    <div v-if="logoutConfirmOpen" class="overlay">
      <div class="dialog card">
        <div class="eyebrow">Log out with Game-Day #{{ gameDay.current?.number }} still open?</div>
        <p class="muted">Logging out doesn't close the game-day — it stays open for whoever logs back in.</p>
        <div class="actions">
          <button class="btn btn--secondary" type="button" @click="onCancelLogout">Cancel</button>
          <button class="btn btn--primary" type="button" @click="doLogout">Log Out</button>
        </div>
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
  /* Was min-height — a box that can only grow taller than the viewport
     never actually triggers .content's own overflow-y:auto below, so the
     whole document scrolled (topbar and tabbar included) instead of just
     the content between them. height (capped, not floored) plus the
     overflow:hidden already here is what makes .content the one scrolling
     region, so the topbar and tabbar stay put. Fixed 2026-09-23. */
  height: 100vh;
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
  display: flex;
}
.shell {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  /* Square top corners (where the topbar sits) — bottom stays rounded. */
  border-radius: 0 0 16px 16px;
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

/* Below the topbar: sidebar + content, side by side — replaces the old
   bottom .tabbar (2026-09-23 hi-fi pass, per the lo-fi nav review sketch:
   a left sidebar reads as the desktop back-office pattern Accountant/Owner/
   Floor Manager actually are, vs. the bottom tab strip that made more sense
   for Cashier's touch tablet — which never had a tab bar to begin with,
   tabs.length === 0 for that role either way). min-height: 0 is load-bearing
   here — without it a flex child ignores its parent's height and .content's
   own overflow-y:auto below never actually triggers. */
.below-topbar {
  flex-grow: 1;
  min-height: 0;
  display: flex;
}
.sidebar {
  width: 208px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 20px 0;
  overflow-y: auto;
}
.side-tab {
  padding: 12px 24px;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--text-secondary);
  text-decoration: none;
  position: relative;
}
.side-tab:hover { color: var(--text-primary); }
.side-tab--active {
  font-weight: 700;
  color: var(--accent-text);
  background: var(--accent-bg);
}
.side-tab--active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--accent);
}
.sidebar-spacer { flex-grow: 1; }
.side-tab--settings {
  border-top: 1px solid var(--border);
  padding-top: 16px;
  margin-top: 8px;
}

.content {
  flex-grow: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 20px;
}

/* Logout confirm — same overlay/dialog shape every other confirmation in
   the app uses (Close Game-Day, Leave Table, ...); this is the first one
   AppShell itself needs, so it's defined here rather than shared, matching
   how every other confirmation dialog in the app defines its own copy. */
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(20, 25, 32, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.dialog { width: 440px; max-width: 92vw; box-shadow: var(--shadow-md); padding: 24px; }
.eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
.muted { color: var(--text-secondary); font-size: 13px; line-height: 1.6; margin: 8px 0 0; }
.actions { display: flex; gap: 14px; margin-top: 20px; }
.actions .btn { flex: 1; }
</style>
