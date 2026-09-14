/**
 * src/router/index.js
 *
 * Auth guard: unauthenticated -> /login; already-logged-in users hitting
 * /login -> their role's home. Role homes: CASHIER -> /game-day (the live
 * working screen), ACCOUNTANT/OWNER -> /dashboard (the read-only back-office
 * reporting surface, Phase B — 2026-09-14).
 *
 * meta.roles is a defense-in-depth check mirroring what the API itself would
 * 403 for the wrong role. It's only set on the new /dashboard, /game-days,
 * /outstanding, /roster routes below (ACCOUNTANT + OWNER — the "back office"
 * surface Cashier has no use for). The original Cashier routes (/game-day,
 * /game-day/:id/ledger, /players/:id) are deliberately left unrestricted:
 * Owner has no dedicated operational UI yet (that's Phase C), so Owner must
 * keep reaching them unblocked until then.
 */
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

function homeRouteFor(role) {
  return role === 'CASHIER' ? '/game-day' : '/dashboard'
}

const LoginView = () => import('@/views/auth/LoginView.vue')

const AppShell = () => import('@/components/layout/AppShell.vue')

const ActiveGameDayView = () => import('@/views/game-day/ActiveGameDayView.vue')
const GameDayLedgerView = () => import('@/views/game-day/GameDayLedgerView.vue')

// The Players list + "add player" page are gone (2026-09-14) — a Cashier's
// only screen is Game Day now; players are picked as pills there and added
// via AddPlayerModal (a bottom sheet, not a route). PlayerDetailView stays
// routed since the Payout action-grid button still navigates to it.
const PlayerDetailView = () => import('@/views/players/PlayerDetailView.vue')

// Accountant/Owner back-office surface (Phase B, 2026-09-14) — a distinct,
// read-only reporting nav namespaced under its own paths so it never
// collides with Cashier's live-view routes above.
const DashboardView = () => import('@/views/accountant/DashboardView.vue')
const GameDaysListView = () => import('@/views/accountant/GameDaysListView.vue')
const GameDayDetailView = () => import('@/views/accountant/GameDayDetailView.vue')
const OutstandingView = () => import('@/views/accountant/OutstandingView.vue')
const RosterListView = () => import('@/views/accountant/RosterListView.vue')
const RosterDetailView = () => import('@/views/accountant/RosterDetailView.vue')

const BACK_OFFICE_ROLES = ['ACCOUNTANT', 'OWNER']

const routes = [
  { path: '/login', component: LoginView, meta: { public: true } },

  {
    path: '/',
    component: AppShell,
    redirect: to => {
      const auth = useAuthStore()
      return homeRouteFor(auth.user?.role)
    },
    children: [
      { path: 'game-day', name: 'game-day', component: ActiveGameDayView },
      { path: 'game-day/:id/ledger', name: 'game-day-ledger', component: GameDayLedgerView },
      { path: 'players/:id', name: 'player-detail', component: PlayerDetailView },

      { path: 'dashboard', name: 'dashboard', component: DashboardView, meta: { roles: BACK_OFFICE_ROLES } },
      { path: 'game-days', name: 'game-days', component: GameDaysListView, meta: { roles: BACK_OFFICE_ROLES } },
      { path: 'game-days/:id', name: 'game-day-detail', component: GameDayDetailView, meta: { roles: BACK_OFFICE_ROLES } },
      { path: 'outstanding', name: 'outstanding', component: OutstandingView, meta: { roles: BACK_OFFICE_ROLES } },
      { path: 'roster', name: 'roster', component: RosterListView, meta: { roles: BACK_OFFICE_ROLES } },
      { path: 'roster/:id', name: 'roster-detail', component: RosterDetailView, meta: { roles: BACK_OFFICE_ROLES } },
    ],
  },

  { path: '/:pathMatch(.*)*', redirect: to => homeRouteFor(useAuthStore().user?.role) },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(to => {
  const auth = useAuthStore()

  // Restore session from a stored token before the very first guarded navigation.
  if (!auth.isAuthenticated && localStorage.getItem('access_token')) {
    auth.init()
  }

  if (to.meta.public) {
    if (auth.isAuthenticated) return homeRouteFor(auth.user?.role)
    return true
  }

  if (!auth.isAuthenticated) return '/login'

  if (to.meta.roles && !to.meta.roles.includes(auth.user.role)) {
    return homeRouteFor(auth.user?.role)
  }

  return true
})

export default router
