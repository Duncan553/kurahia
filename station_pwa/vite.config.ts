import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'path'
import { VitePWA } from 'vite-plugin-pwa'

// Same route/API-prefix collision guard as employee_pwa/owner_pwa's vite.config.ts —
// a JS-initiated API call (axios) sends Accept: application/json; a browser doing
// a full page load/refresh/deep-link sends Accept: text/html first. Bypass the
// proxy for the latter so Vite serves index.html (the SPA) instead of the request
// reaching Flask and getting its raw 404 page.
function bypassPageNavigations(req: { headers: Record<string, string | string[] | undefined> }) {
  const accept = req.headers.accept
  if (typeof accept === 'string' && accept.includes('text/html')) {
    return '/index.html'
  }
}

// Only the domains station_pwa's screens actually call — a narrower list than
// employee_pwa's, since this app has no personal HR/leave/payroll screens.
const PROXIED_PATHS = [
  '/auth', '/hr', '/notifications', '/inventory', '/gate', '/bookings',
  '/bookable-resources', '/booking-payments', '/front-desk', '/waivers', '/tabs', '/orders',
  '/order-items', '/receipts', '/menu', '/kitchen', '/bar', '/equipment',
  '/finance', '/housekeeping', '/incidents', '/events', '/uploads', '/suggestions',
]

const proxyConfig = Object.fromEntries(
  PROXIED_PATHS.map(p => [p, {
    target: 'http://localhost:5000',
    changeOrigin: true,
    bypass: bypassPageNavigations,
  }])
)

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      // generateSW, not injectManifest: this app has no push handlers of its
      // own, so there is nothing that needs to live inside a hand-written
      // service worker. employee_pwa uses injectManifest for exactly that
      // reason and does not apply here.
      registerType: 'autoUpdate',
      workbox: {
        // Precache the SHELL only — the JS, CSS, fonts and icons that make the
        // app open instantly and survive a flaky LAN link.
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],

        // And nothing else. These are the POS and kitchen tablets: a cached
        // order queue is not a convenience, it is a cook plating a dish that
        // was cancelled two minutes ago. Every API path is NetworkOnly, so the
        // app shell loads offline but live data never comes from a cache.
        runtimeCaching: [{
          urlPattern: ({ url }: { url: URL }) =>
            /^\/(kitchen|bar|tabs|orders|order-items|gate|front-desk|inventory|menu|auth|hr|receipts|booking-payments|bookings|bookable-resources|waivers|equipment|housekeeping|incidents|events|finance|notifications|suggestions)\b/
              .test(url.pathname),
          handler: 'NetworkOnly',
        }],

        // A stale shell against a newer API is its own failure mode, so take
        // control as soon as a new build is available rather than waiting for
        // every tab to close.
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,

        // Deep links must fall through to the SPA, but API paths must NOT be
        // answered with index.html when the network is down — a JSON caller
        // receiving HTML fails in a much more confusing way than a clean error.
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/(kitchen|bar|tabs|orders|order-items|gate|front-desk|inventory|menu|auth|hr|receipts|booking-payments|bookings|bookable-resources|waivers|equipment|housekeeping|incidents|events|finance|notifications|suggestions)\b/],
      },
      manifest: {
        name: 'Kurahia Station',
        short_name: 'Station',
        description: 'Kurahia Resort — POS, kitchen, bar and gate stations',
        theme_color: '#171717',
        background_color: '#171717',
        display: 'standalone',
        start_url: '/',
        // Landscape: these run on wall-mounted and counter tablets, unlike the
        // portrait phone apps.
        orientation: 'landscape',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
  resolve: {
    dedupe: ['react', 'react-dom', 'framer-motion', 'zustand'],
    alias: {
      '@shared': resolve(__dirname, '../shared_ui/src'),
    },
  },
  preview: {
    proxy: proxyConfig,
    port: 5176,
  },
  server: {
    proxy: proxyConfig,
    port: 5176,
  },
})
