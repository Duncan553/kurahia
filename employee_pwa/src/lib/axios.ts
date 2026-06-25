import axios from 'axios'
import type { InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '../stores/authStore'
import { useToastStore } from '@shared'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL as string,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,  // sends httpOnly refresh-token cookie automatically
})

// Inject the in-memory access token on every outgoing request
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Queue to hold requests that arrive while a token refresh is in-flight
let isRefreshing = false
let queue: { resolve: (token: string) => void; reject: (err: unknown) => void }[] = []

function drainQueue(error: unknown, token: string | null = null) {
  queue.forEach(({ resolve, reject }) => (error ? reject(error) : resolve(token!)))
  queue = []
}

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
    const status: number | undefined = error.response?.status

    // ── 401: try to refresh once, then retry the original request ──────────
    // Skip refresh for auth endpoints — a 401 there means wrong credentials, not expired token
    const isAuthEndpoint = original.url?.startsWith('/auth/')
    if (status === 401 && !original._retry && !isAuthEndpoint) {
      if (isRefreshing) {
        // Another refresh is already in flight — queue this request
        return new Promise<string>((resolve, reject) => {
          queue.push({ resolve, reject })
        }).then((token) => {
          original.headers.Authorization = `Bearer ${token}`
          return api(original)
        })
      }

      original._retry = true
      isRefreshing = true

      try {
        // Explicitly send the refresh token — the request interceptor would send
        // the expired access token instead, which the backend rejects.
        const refreshToken = useAuthStore.getState().refreshToken
        if (!refreshToken) throw new Error('No refresh token')
        const res = await api.post<{ access_token: string }>('/auth/refresh', {}, {
          headers: { Authorization: `Bearer ${refreshToken}` },
        })
        const newToken = res.data.access_token
        const { user } = useAuthStore.getState()
        // Keep the same refresh token — the endpoint only issues a new access token
        if (user) useAuthStore.getState().setAuth(user, newToken, refreshToken)
        drainQueue(null, newToken)
        original.headers.Authorization = `Bearer ${newToken}`
        return api(original)
      } catch (refreshErr) {
        drainQueue(refreshErr)
        useAuthStore.getState().clearAuth()
        window.location.href = '/login'
        return Promise.reject(refreshErr)
      } finally {
        isRefreshing = false
      }
    }

    // ── 403: two cases — session kill (deactivated/locked) vs permission denial ─
    if (status === 403) {
      const msg: string = (error.response?.data as { error?: string })?.error ?? ''
      const isKillSwitch =
        msg.toLowerCase().includes('deactivat') ||
        msg.toLowerCase().includes('not found') ||
        msg.toLowerCase().includes('locked')
      if (isKillSwitch) {
        useAuthStore.getState().clearAuth()
        useToastStore.getState().addToast({
          type: 'error',
          message: 'Your session was ended. Please log in again.',
        })
        window.location.href = '/login'
      }
      // Permission violation — just reject; the calling screen shows its own error
    }

    return Promise.reject(error)
  }
)

export default api
