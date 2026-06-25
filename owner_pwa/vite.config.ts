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
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'autoUpdate',
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,png,svg,ico,woff2}'],
      },
      manifest: {
        name: 'Kurahia Owner',
        short_name: 'Kurahia O',
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
  preview: {
    port: 5175,
    proxy: Object.fromEntries(
      ['/auth','/hr','/notifications','/conduct','/suggestions','/inventory','/finance',
       '/gate','/bookings','/bookable-resources','/booking-payments',
       '/waivers','/tabs','/orders','/order-items','/receipts',
       '/menu','/equipment','/dashboard','/judge','/admin','/health',
       '/calendar','/disputes','/events','/event-types','/guest-records',
       '/housekeeping','/incidents','/lost-found','/reports','/suppliers','/uploads',
       '/feedback','/front-desk']
        .map(p => [p, { target: 'http://localhost:5000', changeOrigin: true }])
    ),
  },
  server: {
    port: 5174,
    proxy: {
      '/auth':              { target: 'http://localhost:5000', changeOrigin: true },
      '/hr':                { target: 'http://localhost:5000', changeOrigin: true },
      '/notifications':     { target: 'http://localhost:5000', changeOrigin: true },
      '/conduct':           { target: 'http://localhost:5000', changeOrigin: true },
      '/suggestions':       { target: 'http://localhost:5000', changeOrigin: true },
      '/inventory':         { target: 'http://localhost:5000', changeOrigin: true },
      '/finance':           { target: 'http://localhost:5000', changeOrigin: true },
      '/gate':              { target: 'http://localhost:5000', changeOrigin: true },
      '/bookings':          { target: 'http://localhost:5000', changeOrigin: true },
      '/bookable-resources':{ target: 'http://localhost:5000', changeOrigin: true },
      '/booking-payments':  { target: 'http://localhost:5000', changeOrigin: true },
      '/waivers':           { target: 'http://localhost:5000', changeOrigin: true },
      '/tabs':              { target: 'http://localhost:5000', changeOrigin: true },
      '/orders':            { target: 'http://localhost:5000', changeOrigin: true },
      '/order-items':       { target: 'http://localhost:5000', changeOrigin: true },
      '/receipts':          { target: 'http://localhost:5000', changeOrigin: true },
      '/menu':              { target: 'http://localhost:5000', changeOrigin: true },
      '/equipment':         { target: 'http://localhost:5000', changeOrigin: true },
      '/dashboard':         { target: 'http://localhost:5000', changeOrigin: true },
      '/judge':             { target: 'http://localhost:5000', changeOrigin: true },
      '/admin':             { target: 'http://localhost:5000', changeOrigin: true },
      '/health':            { target: 'http://localhost:5000', changeOrigin: true },
      '/calendar':          { target: 'http://localhost:5000', changeOrigin: true },
      '/disputes':          { target: 'http://localhost:5000', changeOrigin: true },
      '/events':            { target: 'http://localhost:5000', changeOrigin: true },
      '/event-types':       { target: 'http://localhost:5000', changeOrigin: true },
      '/guest-records':     { target: 'http://localhost:5000', changeOrigin: true },
      '/housekeeping':      { target: 'http://localhost:5000', changeOrigin: true },
      '/incidents':         { target: 'http://localhost:5000', changeOrigin: true },
      '/lost-found':        { target: 'http://localhost:5000', changeOrigin: true },
      '/reports':           { target: 'http://localhost:5000', changeOrigin: true },
      '/suppliers':         { target: 'http://localhost:5000', changeOrigin: true },
      '/uploads':           { target: 'http://localhost:5000', changeOrigin: true },
      '/feedback':          { target: 'http://localhost:5000', changeOrigin: true },
      '/front-desk':        { target: 'http://localhost:5000', changeOrigin: true },
    },
  },
  resolve: {
    dedupe: ['react', 'react-dom', 'framer-motion', 'zustand'],
    alias: {
      '@shared': resolve(__dirname, '../shared_ui/src'),
    },
  },
})
