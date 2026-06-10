import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'path'

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
