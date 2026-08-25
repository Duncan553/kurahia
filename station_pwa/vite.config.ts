import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'path'

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
  '/bookable-resources', '/front-desk', '/waivers', '/tabs', '/orders',
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
