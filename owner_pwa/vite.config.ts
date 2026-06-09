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
  },
  resolve: {
    dedupe: ['react', 'react-dom', 'framer-motion', 'zustand'],
    alias: {
      '@shared': resolve(__dirname, '../shared_ui/src'),
    },
  },
})
