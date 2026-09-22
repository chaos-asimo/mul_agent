import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  root: __dirname,
  // 绝对根路径：资源从 /assets/... 加载（不依赖 URL 解析）。
  // 后端额外挂载 /assets → web/static/v3/assets，使 /v3 和 /clow 两入口都能加载资源。
  // basename 仍由后端注入的 window.__BASE__ 动态控制（"/v3" 或 "/clow"）。
  base: '/',
  build: {
    outDir: path.resolve(__dirname, '../web/static/v3'),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8888',
    },
  },
})
