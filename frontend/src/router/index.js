/**
 * src/router/index.js
 *
 * Auth guard: unauthenticated -> /login; already-logged-in users hitting
 * /login -> their role's home. Role homes: CASHIER -> /game-day (the live
 * working screen), FLOOR_MANAGER -> /masseuses, ACCOUNTANT/OWNER ->
 * /dashboard (the read-only back-office reporting surface, Phase B —
 * 2026-09-14). Masseuse/Dealer/Service (added 2026-09-23) briefly had a
 * login here too (a placeholder /staff-home) before it was clarified none
 * of the three ever actually log in — see accounts.StaffUser.Role's own
 * comment; they're accounts.StaffMember records now, not StaffUser.
 *
 * meta.roles is a defense-in-depth check mirroring what the API itself would
 * 403 for the wrong role. It's set on /dashboard, /game-days, /roster
 * (ACCOUNTANT + OWNER — the "back office" surface Cashier has no use for)
 * and, OWNER-only, on /admin, /payouts (Phase C, 2026-09-14), and /deals/:playerId
 * (2026-09-23). /outstanding was in this same group until 2026-09-23, when
 * it was folded into /dashboard and retired as its own route. The standalone
 * /deals (player picker) and /deals/history pages were retired the same way
 * on 2026-09-24 — Deal is now one of the Players table's own ⋮ actions
 * (jumps straight to /deals/:playerId), and deal history moved onto each
 * player's own deal page.
 *
 * The original Cashier routes (/game-day, /game-day/:id/ledger, /players/:id)
 * are deliberately left unrestricted: Owner still has no dedicated
 * operational UI of its own for opening/recording (Phase C gave Owner a
 * direct Open-Game-Day trigger on Dashboard, but not a full working screen),
 * so Owner must keep reaching them unblocked.
 */
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

function homeRouteFor(role) {
  if (role === 'CASHIER') return '/game-day'
  if (role === 'FLOOR_MANAGER') return '/masseuses'
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
// GameDaysListView now carries a game-day's whole detail inline (opens below
// the paginated list on click, 2026-09-23) — GameDayDetailView.vue and its
// standalone /game-days/:id route are gone; nothing else in the app linked
// to that route (confirmed by search before removing it).
const GameDaysListView = () => import('@/views/accountant/GameDaysListView.vue')
// OutstandingView is gone (2026-09-23) — its whole content (feed + by-player
// summary) now lives inline on DashboardView, and the standalone /outstanding
// route below went with it.
const RosterListView = () => import('@/views/accountant/RosterListView.vue')
const RosterDetailView = () => import('@/views/accountant/RosterDetailView.vue')

// Floor Manager's own screen (2026-09-17) — a real logged-in role now,
// managing the Masseuse roster (named "Service Staff" until the
// 2026-09-23 rename).
const MasseuseListView = () => import('@/views/floor-manager/MasseuseListView.vue')

// Table/ClubSettings "Settings" screen (added 2026-09-23) — shared between
// Owner and Floor Manager, same FLOOR_MANAGER_ROLES visibility as Masseuses;
// the Owner-only half of the page (approval toggles, payout threshold) is
// hidden inline via v-if, not by a second route.
const ClubSettingsView = () => import('@/views/shared/ClubSettingsView.vue')

// Owner-only additions (Phase C, 2026-09-14).
const AdminView = () => import('@/views/owner/AdminView.vue')
const PayoutsView = () => import('@/views/owner/PayoutsView.vue')
// Main Account ledger (2026-09-17) — a second, focused view of real bank-
// account activity (deposits sweeping in, payouts going out), separate from
// the Game-Day ledger's own narrative of a night. Owner-only, matching
// gaming/views.py's MainAccountLedgerView permission and CONCEPT.md's rule
// that Main Account visibility excludes the Accountant.
const MainAccountLedgerView = () => import('@/views/owner/MainAccountLedgerView.vue')

// "Deals" web version (2026-09-23) — the backend (Fixed write-off, Transfer,
// Stake and Profit Split) has existed since 2026-09-20; the Expo mobile app
// built against it is deliberately local-only for now (no backend calls on
// any write — see PLAN.md's mobile-app entries), a stopgap explicitly
// waiting on "the rest of the Owner app" existing. It does now, so this is
// the real, backend-wired version: every action here creates actual
// Transaction/ProfitSplitArrangement rows immediately, same endpoints the
// mobile app's local-only build never called. Owner-only throughout,
// matching every "Deals" backend permission (IsOwner) exactly. Same
// player-picker -> deal-type-picker -> form flow as the mobile app's own
// navigation stack.
const DealTypePickerView = () => import('@/views/owner/deals/DealTypePickerView.vue')
const DealFixedView = () => import('@/views/owner/deals/DealFixedView.vue')
const DealTransferView = () => import('@/views/owner/deals/DealTransferView.vue')
const DealProfitSplitView = () => import('@/views/owner/deals/DealProfitSplitView.vue')

const BACK_OFFICE_ROLES = ['ACCOUNTANT', 'OWNER']
const OWNER_ONLY_ROLES = ['OWNER']
// Owner can also reach Masseuses (MasseuseViewSet allows both) even
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
      { path: 'roster', name: 'roster', component: RosterListView, meta: { roles: BACK_OFFICE_ROLES } },
      { path: 'roster/:id', name: 'roster-detail', component: RosterDetailView, meta: { roles: BACK_OFFICE_ROLES } },

      { path: 'admin', name: 'admin', component: AdminView, meta: { roles: OWNER_ONLY_ROLES } },
      { path: 'payouts', name: 'payouts', component: PayoutsView, meta: { roles: OWNER_ONLY_ROLES } },
      { path: 'main-account', name: 'main-account', component: MainAccountLedgerView, meta: { roles: OWNER_ONLY_ROLES } },
      { path: 'deals/:playerId', name: 'deal-type-picker', component: DealTypePickerView, meta: { roles: OWNER_ONLY_ROLES } },
      { path: 'deals/:playerId/fixed', name: 'deal-fixed', component: DealFixedView, meta: { roles: OWNER_ONLY_ROLES } },
      { path: 'deals/:playerId/transfer', name: 'deal-transfer', component: DealTransferView, meta: { roles: OWNER_ONLY_ROLES } },
      { path: 'deals/:playerId/profit-split', name: 'deal-profit-split', component: DealProfitSplitView, meta: { roles: OWNER_ONLY_ROLES } },
      { path: 'masseuses', name: 'masseuses', component: MasseuseListView, meta: { roles: FLOOR_MANAGER_ROLES } },
      { path: 'settings', name: 'club-settings', component: ClubSettingsView, meta: { roles: FLOOR_MANAGER_ROLES } },
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
