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

  // ── Restore session on app boot from a still-valid stored access token ───
  function init() {
    const token = localStorage.getItem('access_token')
    if (!token) return
    try {
      const decoded = decodeUser(token)
      if (decoded.exp * 1000 < Date.now()) {
        // Expired — leave user unset. The axios interceptor's refresh flow
        // handles this transparently on the first real API call instead.
        return
      }
      user.value = decoded
    } catch {
      clearAuth()
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
      const msg = err.response?.data?.detail
        || Object.values(err.response?.data || {})[0]?.[0]
        || 'Login failed. Check your username and password.'
      return { ok: false, error: msg }
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
