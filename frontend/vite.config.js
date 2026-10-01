import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const proxy = { '/api': { target: process.env.NOVEL_API_URL || 'http://127.0.0.1:5000', changeOrigin: true } }
export default defineConfig({ plugins: [vue()], server: { proxy }, preview: { proxy } })
