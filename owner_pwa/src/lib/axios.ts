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

// ── UTC normaliser ────────────────────────────────────────────────────────
// The API stamps every time in UTC (engineering invariant 8) but serialises it
// with `.isoformat()` on a naive datetime, so the wire carries
// "2026-09-10T20:09:27.633387" — no Z, no offset. `new Date()` reads a string
// like that as LOCAL time, so in Kenya every timestamp in all three apps
// rendered three hours early: a wristband issued at 23:09 showed 20:09, and
// near midnight it showed the wrong DAY.
//
// Fixed here, at the one place every response passes through, rather than at
// the 123 `.isoformat()` call sites across 50 backend files — several of which
// are real DATE fields (hire_date, roster_date) that must not gain a time zone.
//
// The regex deliberately requires a time component and no existing offset, so
// "2026-09-10" is left alone and a correct "…+00:00" (what Postgres will send
// in production) is left alone too.
const NAIVE_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$/

function markUtc(value: unknown): unknown {
  if (typeof value === 'string') return NAIVE_UTC.test(value) ? value + 'Z' : value
  if (Array.isArray(value)) return value.map(markUtc)
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) out[k] = markUtc(v)
    return out
  }
  return value
}

api.interceptors.response.use(
  (res) => { res.data = markUtc(res.data); return res },

  async (error) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
    const status: number | undefined = error.response?.status

    // ── 401: try to refresh once, then retry the original request ──────────
    //
    // The refresh call goes out on THIS instance, so without this guard a
    // failed refresh re-entered the interceptor as just another 401: _retry
    // was unset on it, isRefreshing was already true, and it got pushed onto
    // the queue — the queue that only this try/catch ever drains, and which
    // was at that moment awaiting the very promise it had just parked.
    //
    // Deadlock. The catch never ran, so clearAuth() and the redirect to
    // /login never ran either, and every other request sat in the queue
    // forever. The owner opened the app in the morning with an expired
    // session and got their dashboard stuck on "Last updated: loading…" with
    // two blank cards — no error, no sign-in prompt, nothing to do but guess.
    //
    // A 401 from /auth/* means the credentials are wrong or the refresh token
    // is spent. There is nothing to refresh WITH, so it must fall through to
    // the caller rather than try.
    //
    // shared_ui/src/lib/axios.ts — the copy the station and employee apps use
    // — has had this guard all along. This file is the fork that never got it.
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
