<script setup>
import { watchEffect } from 'vue'
import AuthorizerConfirmModal from '@/components/shared/AuthorizerConfirmModal.vue'
import CloseGameDayModal from '@/components/shared/CloseGameDayModal.vue'
import AppToast from '@/components/shared/AppToast.vue'
import { useAuthStore } from '@/stores/auth'

// "One shared system, differing only by accent color" (Ledger Book,
// 2026-09-21) — every --accent/--accent-bg/--accent-text token is
// resolved per-role via tokens.css's [data-role="..."] blocks; this is
// the one place that attribute gets set, from whichever role is
// actually logged in. Logged out (e.g. the Login screen) leaves no
// data-role attribute, so :root's own fallback accent applies instead.
//
// data-density alongside it is the one non-color difference (touch
// tablet vs desktop mouse) — see tokens.css's [data-density] block.
// Cashier is the only touch-first role; replaces the old
// AppShell.vue isBackOffice/.theme-accountant boolean, computed the
// same way that was (every role except Cashier).
const auth = useAuthStore()
watchEffect(() => {
  const role = auth.user?.role
  const html = document.documentElement
  if (role) {
    html.setAttribute('data-role', role)
    html.setAttribute('data-density', role === 'CASHIER' ? 'comfortable' : 'compact')
  } else {
    html.removeAttribute('data-role')
    html.removeAttribute('data-density')
  }
})
</script>

<template>
  <router-view />
  <AuthorizerConfirmModal />
  <CloseGameDayModal />
  <AppToast />
</template>
