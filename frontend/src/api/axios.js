/**
 * src/api/axios.js
 *
 * Single Axios instance for all API calls.
 * - Attaches Bearer token from localStorage on every request
 * - On 401: attempts silent token refresh, retries original request once
 * - On second 401: clears tokens and redirects to /login
 *
 * NOTE: this backend rotates refresh tokens (SIMPLE_JWT ROTATE_REFRESH_TOKENS
 * + BLACKLIST_AFTER_ROTATION — see backend/lpc_backend/settings/base.py), so
 * every successful /auth/refresh/ call returns a NEW refresh token too, and
 * blacklists the one just used. Both must be persisted, not just the access
 * token — reusing a stale refresh token here would fail on the next refresh.
 */
import axios from 'axios'
import router from '@/router'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: { 'Content-Type': 'application/json' },
})

// ── Request interceptor — attach access token ─────────────────────────────
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ── Response interceptor — handle 401, refresh token ──────────────────────
let isRefreshing = false
let failedQueue = []

function processQueue(error, token = null) {
  failedQueue.forEach(({ resolve, reject }) => {
    error ? reject(error) : resolve(token)
  })
  failedQueue = []
}

api.interceptors.response.use(
  response => response,
  async error => {
    const original = error.config

    if (error.response?.status === 401 && !original._retry) {
      // Don't retry auth endpoints themselves (login, refresh) — a 401 there
      // means bad credentials or a dead refresh token, not an expired access token.
      if (original.url?.includes('/auth/')) {
        clearAuth()
        router.push('/login')
        return Promise.reject(error)
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then(token => {
          original.headers.Authorization = `Bearer ${token}`
          return api(original)
        })
      }

      original._retry = true
      isRefreshing = true

      const refresh = localStorage.getItem('refresh_token')
      if (!refresh) {
        clearAuth()
        router.push('/login')
        return Promise.reject(error)
      }

      try {
        const { data } = await api.post('/auth/refresh/', { refresh })
        localStorage.setItem('access_token', data.access)
        if (data.refresh) localStorage.setItem('refresh_token', data.refresh) // rotated — see note above
        api.defaults.headers.common.Authorization = `Bearer ${data.access}`
        processQueue(null, data.access)
        original.headers.Authorization = `Bearer ${data.access}`
        return api(original)
      } catch (refreshError) {
        processQueue(refreshError, null)
        clearAuth()
        router.push('/login')
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)

export function clearAuth() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

export default api
