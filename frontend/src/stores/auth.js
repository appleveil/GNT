/**
 * src/stores/auth.js
 *
 * Cashier app auth store.
 *
 * Unlike a typical setup, this backend has no /me endpoint — StaffLoginSerializer
 * embeds `role` and `full_name` as claims directly inside the JWT access token
 * (see backend/accounts/serializers.py), so the frontend decodes them
 * client-side instead of making a second call after login.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { jwtDecode } from 'jwt-decode'
import api, { clearAuth } from '@/api/axios'
import { readApiError } from '@/utils/apiError'

function decodeUser(accessToken) {
  const claims = jwtDecode(accessToken)
  return { id: claims.user_id, role: claims.role, fullName: claims.full_name, exp: claims.exp }
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null) // { id, role, fullName } or null
  const loading = ref(false)

  const isAuthenticated = computed(() => !!user.value)
  const isOwner = computed(() => user.value?.role === 'OWNER')
  const isAccountant = computed(() => user.value?.role === 'ACCOUNTANT')
  const isCashier = computed(() => user.value?.role === 'CASHIER')
  const isFloorManager = computed(() => user.value?.role === 'FLOOR_MANAGER')

  // ── Restore session on app boot ───────────────────────────────────────
  // The access token is short-lived (30min, SIMPLE_JWT.ACCESS_TOKEN_LIFETIME)
  // by design, but the refresh token lasts 7 days — a page refresh should
  // only ever land on /login once that 7-day window is actually up, not
  // every time the 30-minute access token happens to have expired since the
  // last load. Previously this just bailed when the access token was
  // expired ("the axios interceptor's refresh flow handles it on the first
  // real API call instead") — but the router guard checks
  // auth.isAuthenticated synchronously against `user`, BEFORE any API call
  // ever fires, so that never happened: an expired access token meant an
  // instant bounce to /login regardless of a perfectly valid refresh token
  // sitting right next to it. Fixed 2026-09-21 — attempt the same silent
  // refresh here that the interceptor does mid-session.
  async function init() {
    const token = localStorage.getItem('access_token')
    if (!token) return
    try {
      const decoded = decodeUser(token)
      if (decoded.exp * 1000 < Date.now()) {
        await refreshSession()
        return
      }
      user.value = decoded
    } catch {
      await refreshSession()
    }
  }

  async function refreshSession() {
    const refresh = localStorage.getItem('refresh_token')
    if (!refresh) {
      clearAuth()
      return
    }
    try {
      const { data } = await api.post('/auth/refresh/', { refresh })
      localStorage.setItem('access_token', data.access)
      if (data.refresh) localStorage.setItem('refresh_token', data.refresh) // rotated — see axios.js's note
      user.value = decodeUser(data.access)
    } catch {
      clearAuth()
      user.value = null
    }
  }

  // ── Login ──────────────────────────────────────────────────────────────
  async function login(username, password) {
    loading.value = true
    try {
      const { data } = await api.post('/auth/login/', { username, password })
      localStorage.setItem('access_token', data.access)
      localStorage.setItem('refresh_token', data.refresh)
      user.value = decodeUser(data.access)
      return { ok: true }
    } catch (err) {
      return { ok: false, error: readApiError(err, 'Login failed. Check your username and password.').message }
    } finally {
      loading.value = false
    }
  }

  // ── Logout ─────────────────────────────────────────────────────────────
  async function logout() {
    try {
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) await api.post('/auth/logout/', { refresh })
    } catch {
      /* ignore — local state is cleared regardless */
    } finally {
      clearAuth()
      user.value = null
    }
  }

  return { user, loading, isAuthenticated, isOwner, isAccountant, isCashier, isFloorManager, init, login, logout }
})
