import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'path'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    port: 5174,
    proxy: {
      '/auth':          { target: 'http://localhost:5000', changeOrigin: true },
      '/hr':            { target: 'http://localhost:5000', changeOrigin: true },
      '/notifications': { target: 'http://localhost:5000', changeOrigin: true },
      '/conduct':       { target: 'http://localhost:5000', changeOrigin: true },
      '/suggestions':   { target: 'http://localhost:5000', changeOrigin: true },
      '/inventory':     { target: 'http://localhost:5000', changeOrigin: true },
      '/finance':       { target: 'http://localhost:5000', changeOrigin: true },
      '/gate':          { target: 'http://localhost:5000', changeOrigin: true },
      '/bookings':      { target: 'http://localhost:5000', changeOrigin: true },
      '/equipment':     { target: 'http://localhost:5000', changeOrigin: true },
      '/dashboard':     { target: 'http://localhost:5000', changeOrigin: true },
      '/judge':         { target: 'http://localhost:5000', changeOrigin: true },
      '/admin':         { target: 'http://localhost:5000', changeOrigin: true },
      '/health':        { target: 'http://localhost:5000', changeOrigin: true },
    },
  },
  resolve: {
    dedupe: ['react', 'react-dom', 'framer-motion', 'zustand'],
    alias: {
      '@shared': resolve(__dirname, '../shared_ui/src'),
    },
  },
})
