import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  // GitHub Pages: "/gsaxctf/" on the project URL, "/" once gsaxctf.com is
  // attached (the deploy workflow sets BASE_PATH).
  base: process.env.BASE_PATH || '/',
  plugins: [react()],
  server: {
    port: 5174
  }
})
