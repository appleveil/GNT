/**
 * src/router/index.js
 *
 * Cashier app routes. Auth guard: unauthenticated -> /login; already-logged-in
 * users hitting /login -> the main working screen.
 *
 * meta.roles is a defense-in-depth check for routes the API itself would
 * 403 for the wrong role (e.g. a future Outstanding Ledger view, Owner/
 * Accountant-only per CONCEPT.md) — omit it for anything all three staff
 * roles can reach. Nothing needs it yet since every route below is Cashier
 * territory, but the mechanism is here for when Owner/Accountant views land.
 */
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const LoginView = () => import('@/views/auth/LoginView.vue')

const AppShell = () => import('@/components/layout/AppShell.vue')

const ActiveGameDayView = () => import('@/views/game-day/ActiveGameDayView.vue')
const GameDayLedgerView = () => import('@/views/game-day/GameDayLedgerView.vue')

const PlayersListView = () => import('@/views/players/PlayersListView.vue')
const PlayerFormView = () => import('@/views/players/PlayerFormView.vue')
const PlayerDetailView = () => import('@/views/players/PlayerDetailView.vue')

const routes = [
  { path: '/login', component: LoginView, meta: { public: true } },

  {
    path: '/',
    component: AppShell,
    redirect: '/game-day',
    children: [
      { path: 'game-day', name: 'game-day', component: ActiveGameDayView },
      { path: 'game-day/:id/ledger', name: 'game-day-ledger', component: GameDayLedgerView },
      { path: 'players', name: 'players', component: PlayersListView },
      { path: 'players/new', name: 'player-new', component: PlayerFormView },
      { path: 'players/:id', name: 'player-detail', component: PlayerDetailView },
    ],
  },

  { path: '/:pathMatch(.*)*', redirect: '/game-day' },
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
    if (auth.isAuthenticated) return '/game-day'
    return true
  }

  if (!auth.isAuthenticated) return '/login'

  if (to.meta.roles && !to.meta.roles.includes(auth.user.role)) {
    return '/game-day'
  }

  return true
})

export default router
