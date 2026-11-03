import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// GitHub Pages 프로젝트 페이지 경로: https://gaeun1961.github.io/emergency-policy-clustering-analysis/
export default defineConfig({
  base: '/emergency-policy-clustering-analysis/',
  plugins: [react()],
})
