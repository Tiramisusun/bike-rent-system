import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 开发时将 /api 请求转发到 Flask
      '/api': 'http://localhost:5000'
    }
  },
  build: {
    // 构建输出到 Flask 可以直接托管的目录
    outDir: '../frontend/dist',
    emptyOutDir: true,
  }
})
