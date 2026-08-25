import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import { resolve } from 'path'

// A handful of these proxy prefixes are also real frontend routes
// (/gate/hub the page vs /gate/issue-band the API; /notifications,
// /conduct, /calendar, /disputes, /incidents, /housekeeping, /events are
// exact-path collisions). A JS-initiated API call (axios) sends
// Accept: application/json; a browser doing a full page load/refresh/
// deep-link/PWA-relaunch sends Accept: text/html first — bypass the proxy
// for the latter so Vite's own SPA handling serves index.html instead of
// this request reaching Flask and getting its raw (unstyled) 404 page.
function bypassPageNavigations(req: { headers: Record<string, string | string[] | undefined> }) {
  const accept = req.headers.accept
  if (typeof accept === 'string' && accept.includes('text/html')) {
    return '/index.html'
  }
}

const PROXIED_PATHS = [
  '/auth', '/hr', '/notifications', '/conduct', '/suggestions', '/health', '/inventory',
  '/gate', '/bookings', '/bookable-resources', '/booking-payments', '/front-desk',
  '/waivers', '/tabs', '/orders', '/order-items', '/receipts',
  '/menu', '/kitchen', '/bar', '/equipment', '/finance', '/feedback', '/admin',
  '/calendar', '/disputes', '/dashboard', '/events', '/event-types',
  '/guest-records', '/housekeeping', '/incidents', '/judge',
  '/lost-found', '/reports', '/suppliers', '/uploads',
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
      // injectManifest: hand-written src/sw.ts gets the precache list injected.
      // Chosen over generateSW because push handlers must live in the same SW file.
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'autoUpdate',
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,png,svg,ico,woff2,wav}'],
      },
      manifest: {
        name: 'Kurahia Staff',
        short_name: 'Kurahia',
        theme_color: '#40534C',
        background_color: '#E4D2B0',
        display: 'standalone',
        start_url: '/',
        orientation: 'portrait',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icon-maskable-192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
          { src: '/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
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
  // vite preview needs the same proxy — SW verification runs against the built app
  preview: {
    proxy: proxyConfig,
  },
  server: {
    proxy: proxyConfig,
  },
})
