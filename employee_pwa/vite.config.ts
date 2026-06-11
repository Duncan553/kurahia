import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import { resolve } from 'path'

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
      manifest: {
        name: 'Kurahia Staff',
        short_name: 'Kurahia',
        theme_color: '#B4533C',
        background_color: '#F4EDDF',
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
    proxy: Object.fromEntries(
      ['/auth','/hr','/notifications','/conduct','/suggestions','/health','/inventory',
       '/gate','/bookings','/front-desk','/waivers','/tabs','/orders','/order-items',
       '/menu','/kitchen','/bar','/equipment','/finance','/feedback','/admin']
        .map(p => [p, { target: 'http://localhost:5000', changeOrigin: true }])
    ),
  },
  server: {
    proxy: {
      // All API routes → Flask on :5000. Browser sees same origin → no CORS.
      '/auth':          { target: 'http://localhost:5000', changeOrigin: true },
      '/hr':            { target: 'http://localhost:5000', changeOrigin: true },
      '/notifications': { target: 'http://localhost:5000', changeOrigin: true },
      '/conduct':       { target: 'http://localhost:5000', changeOrigin: true },
      '/suggestions':   { target: 'http://localhost:5000', changeOrigin: true },
      '/health':        { target: 'http://localhost:5000', changeOrigin: true },
      '/inventory':     { target: 'http://localhost:5000', changeOrigin: true },
      '/gate':          { target: 'http://localhost:5000', changeOrigin: true },
      '/bookings':      { target: 'http://localhost:5000', changeOrigin: true },
      '/front-desk':    { target: 'http://localhost:5000', changeOrigin: true },
      '/waivers':       { target: 'http://localhost:5000', changeOrigin: true },
      '/tabs':          { target: 'http://localhost:5000', changeOrigin: true },
      '/orders':        { target: 'http://localhost:5000', changeOrigin: true },
      '/order-items':   { target: 'http://localhost:5000', changeOrigin: true },
      '/menu':          { target: 'http://localhost:5000', changeOrigin: true },
      '/kitchen':       { target: 'http://localhost:5000', changeOrigin: true },
      '/bar':           { target: 'http://localhost:5000', changeOrigin: true },
      '/equipment':     { target: 'http://localhost:5000', changeOrigin: true },
      '/finance':       { target: 'http://localhost:5000', changeOrigin: true },
      '/feedback':      { target: 'http://localhost:5000', changeOrigin: true },
      '/admin':         { target: 'http://localhost:5000', changeOrigin: true },
    },
  },
})
