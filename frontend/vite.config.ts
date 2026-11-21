import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist', sourcemap: false },
  server: {
    proxy: {
      '/admin': 'http://localhost:8080',
      '/api': 'http://localhost:8080',
      '/uploads': 'http://localhost:8080',
      '/setup': 'http://localhost:8080',
      '/health': 'http://localhost:8080',
    },
  },
})