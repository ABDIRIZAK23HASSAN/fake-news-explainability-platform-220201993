import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The frontend talks to the backend ONLY through the REST API (/api, /media).
const backend = process.env.VITE_BACKEND_URL || 'http://localhost:8000'
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': backend, '/media': backend } },
  preview: { port: 5173, proxy: { '/api': backend, '/media': backend } },
})
