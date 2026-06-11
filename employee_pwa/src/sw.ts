/// <reference lib="webworker" />
// Kurahia Staff service worker — injectManifest strategy.
// Workbox injects the precache list; push handlers live here too (Part E).
declare const self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: (string | { url: string; revision: string | null })[]
}

import { precacheAndRoute, createHandlerBoundToURL } from 'workbox-precaching'
import { registerRoute, NavigationRoute } from 'workbox-routing'
import { CacheFirst, NetworkFirst } from 'workbox-strategies'
import { ExpirationPlugin } from 'workbox-expiration'
import { routeFor } from './lib/notificationRoutes'

// ── App shell: precached, version-keyed by the build ────────────────────────
precacheAndRoute(self.__WB_MANIFEST)

// SPA navigations fall back to the precached index.html (works offline)
registerRoute(new NavigationRoute(createHandlerBoundToURL('index.html')))

// Take over immediately on update — shared tablets must not run stale code
self.skipWaiting()
self.addEventListener('activate', () => self.clients.claim())

// ── Runtime caching ──────────────────────────────────────────────────────────
// NEVER cached (no route registered → always straight to network):
//   /auth/*, /finance/*  — tokens and money are never stale
//   /kitchen/queue, /bar/queue — a stale prep queue is worse than no queue

// Google Fonts: CacheFirst, 1 year
registerRoute(
  ({ url }) => url.origin === 'https://fonts.googleapis.com' || url.origin === 'https://fonts.gstatic.com',
  new CacheFirst({
    cacheName: 'google-fonts',
    plugins: [new ExpirationPlugin({ maxEntries: 20, maxAgeSeconds: 365 * 24 * 3600 })],
  })
)

// Menu: NetworkFirst, 1 hour fallback
registerRoute(
  ({ url, request }) => request.method === 'GET' && url.pathname.startsWith('/menu/items'),
  new NetworkFirst({
    cacheName: 'menu',
    plugins: [new ExpirationPlugin({ maxEntries: 10, maxAgeSeconds: 3600 })],
  })
)

// Today's bookings: NetworkFirst, 15 min fallback
registerRoute(
  ({ url, request }) => request.method === 'GET' && url.pathname.startsWith('/bookings/today'),
  new NetworkFirst({
    cacheName: 'bookings-today',
    plugins: [new ExpirationPlugin({ maxEntries: 5, maxAgeSeconds: 15 * 60 })],
  })
)

// Notification inbox: NetworkFirst, 5 min fallback
registerRoute(
  ({ url, request }) => request.method === 'GET' && url.pathname.startsWith('/notifications/inbox'),
  new NetworkFirst({
    cacheName: 'inbox',
    plugins: [new ExpirationPlugin({ maxEntries: 5, maxAgeSeconds: 5 * 60 })],
  })
)

// ── Web Push ──────────────────────────────────────────────────────────────────

self.addEventListener('push', (event: PushEvent) => {
  if (!event.data) return
  const payload = event.data.json() as { title?: string; body?: string; reference_type?: string }
  event.waitUntil(
    self.registration.showNotification(payload.title ?? 'Kurahia', {
      body: payload.body ?? '',
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      data: { reference_type: payload.reference_type ?? '' },
    })
  )
})

self.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close()
  // Same routing map as the in-app inbox — one shared module, can't drift
  const route = routeFor((event.notification.data?.reference_type as string) ?? '')
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      const open = clients[0]
      if (open) { open.navigate(route); return open.focus() }
      return self.clients.openWindow(route)
    })
  )
})
