import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  root: __dirname,
  base: '/v3/',
  build: {
    outDir: '../web/static/v3',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8888',
    },
  },
})
