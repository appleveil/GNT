/**
 * src/router/index.js
 *
 * Auth guard: unauthenticated -> /login; already-logged-in users hitting
 * /login -> their role's home. Role homes: CASHIER -> /game-day (the live
 * working screen), ACCOUNTANT/OWNER -> /dashboard (the read-only back-office
 * reporting surface, Phase B — 2026-09-14).
 *
 * meta.roles is a defense-in-depth check mirroring what the API itself would
 * 403 for the wrong role. It's set on /dashboard, /game-days, /outstanding,
 * /roster (ACCOUNTANT + OWNER — the "back office" surface Cashier has no use
 * for) and, OWNER-only, on /admin and /payouts (Phase C, 2026-09-14). The
 * original Cashier routes (/game-day, /game-day/:id/ledger, /players/:id)
 * are deliberately left unrestricted: Owner still has no dedicated
 * operational UI of its own for opening/recording (Phase C gave Owner a
 * direct Open-Game-Day trigger on Dashboard, but not a full working screen),
 * so Owner must keep reaching them unblocked.
 */
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

function homeRouteFor(role) {
  if (role === 'CASHIER') return '/game-day'
  if (role === 'FLOOR_MANAGER') return '/service-staff'
  return '/dashboard'
}

const LoginView = () => import('@/views/auth/LoginView.vue')

const AppShell = () => import('@/components/layout/AppShell.vue')

const ActiveGameDayView = () => import('@/views/game-day/ActiveGameDayView.vue')

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

// Floor Manager's own screen (2026-09-17) — a real logged-in role now,
// managing the Service Staff roster.
const ServiceStaffView = () => import('@/views/floor-manager/ServiceStaffView.vue')

// Owner-only additions (Phase C, 2026-09-14).
const AdminView = () => import('@/views/owner/AdminView.vue')
const PayoutsView = () => import('@/views/owner/PayoutsView.vue')
// Main Account ledger (2026-09-17) — a second, focused view of real bank-
// account activity (deposits sweeping in, payouts going out), separate from
// the Game-Day ledger's own narrative of a night. Owner-only, matching
// gaming/views.py's MainAccountLedgerView permission and CONCEPT.md's rule
// that Main Account visibility excludes the Accountant.
const MainAccountLedgerView = () => import('@/views/owner/MainAccountLedgerView.vue')

const BACK_OFFICE_ROLES = ['ACCOUNTANT', 'OWNER']
const OWNER_ONLY_ROLES = ['OWNER']
// Owner can also reach Service Staff (ServiceStaffViewSet allows both) even
// though it's primarily the Floor Manager's own screen/nav entry.
const FLOOR_MANAGER_ROLES = ['FLOOR_MANAGER', 'OWNER']

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
      { path: 'players/:id', name: 'player-detail', component: PlayerDetailView },

      { path: 'dashboard', name: 'dashboard', component: DashboardView, meta: { roles: BACK_OFFICE_ROLES } },
      { path: 'game-days', name: 'game-days', component: GameDaysListView, meta: { roles: BACK_OFFICE_ROLES } },
      { path: 'game-days/:id', name: 'game-day-detail', component: GameDayDetailView, meta: { roles: BACK_OFFICE_ROLES } },
      { path: 'outstanding', name: 'outstanding', component: OutstandingView, meta: { roles: BACK_OFFICE_ROLES } },
      { path: 'roster', name: 'roster', component: RosterListView, meta: { roles: BACK_OFFICE_ROLES } },
      { path: 'roster/:id', name: 'roster-detail', component: RosterDetailView, meta: { roles: BACK_OFFICE_ROLES } },

      { path: 'admin', name: 'admin', component: AdminView, meta: { roles: OWNER_ONLY_ROLES } },
      { path: 'payouts', name: 'payouts', component: PayoutsView, meta: { roles: OWNER_ONLY_ROLES } },
      { path: 'main-account', name: 'main-account', component: MainAccountLedgerView, meta: { roles: OWNER_ONLY_ROLES } },
      { path: 'service-staff', name: 'service-staff', component: ServiceStaffView, meta: { roles: FLOOR_MANAGER_ROLES } },
    ],
  },

  { path: '/:pathMatch(.*)*', redirect: to => homeRouteFor(useAuthStore().user?.role) },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async to => {
  const auth = useAuthStore()

  // Restore session from a stored token before the very first guarded
  // navigation. auth.init() is async now (it may silently refresh an
  // expired access token via the refresh token) — must be awaited, or the
  // isAuthenticated check right below runs before it's finished and every
  // refresh looks logged-out for the split second that mattered.
  if (!auth.isAuthenticated && localStorage.getItem('access_token')) {
    await auth.init()
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
