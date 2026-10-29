import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8700',
      '/ws': { target: 'ws://localhost:8700', ws: true },
      '/media': 'http://localhost:8700',
      '/uploads': 'http://localhost:8700',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
