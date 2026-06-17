/// <reference lib="webworker" />
// Kurahia Owner service worker — injectManifest strategy.
declare const self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: (string | { url: string; revision: string | null })[]
}

import { precacheAndRoute, createHandlerBoundToURL } from 'workbox-precaching'
import { registerRoute, NavigationRoute } from 'workbox-routing'
import { NetworkFirst } from 'workbox-strategies'
import { ExpirationPlugin } from 'workbox-expiration'

// ── App shell: precached, version-keyed by the build ────────────────────────
precacheAndRoute(self.__WB_MANIFEST)
registerRoute(new NavigationRoute(createHandlerBoundToURL('index.html')))

self.skipWaiting()
self.addEventListener('activate', () => self.clients.claim())

// ── Runtime caching ──────────────────────────────────────────────────────────
// NEVER cached: /auth/*, /finance/*, /judge/*, /dashboard/* — owner numbers
// must always be live. Only fonts and the inbox get offline fallbacks.

// Fonts are self-hosted + precached — no Google Fonts runtime caching needed

registerRoute(
  ({ url, request }) => request.method === 'GET' && url.pathname.startsWith('/notifications/inbox'),
  new NetworkFirst({
    cacheName: 'inbox',
    plugins: [new ExpirationPlugin({ maxEntries: 5, maxAgeSeconds: 5 * 60 })],
  })
)
