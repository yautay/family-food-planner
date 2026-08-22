import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import { defineConfig } from 'vitest/config'

// Backend dla proxy /api. W compose to http://app:8000 (zmienna z serwisu
// frontend), lokalnie domyślnie uvicorn na 127.0.0.1:8000.
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'

// Bind mount z Windows/WSL2 nie generuje zdarzeń inotify — bez pollingu
// HMR nie widzi zmian w kontenerze (compose ustawia VITE_USE_POLLING).
const usePolling = process.env.VITE_USE_POLLING === 'true'

// Playwright zapisuje raport i artefakty do `test-results/` oraz
// `playwright-report/` WEWNĄTRZ katalogu frontendu, czyli wprost pod watcherem
// Vite. Każdy taki zapis w trakcie przebiegu wywoływał PEŁNE przeładowanie
// strony (w logach: „page reload playwright-report/index.html"), a reload gubi
// stan UI — spec listy zakupowej tracił w połowie otwarty panel udostępniania
// i padał bez winy aplikacji (ustalenie BATCH_11).
const watchIgnored = ['**/test-results/**', '**/playwright-report/**']

export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      // BATCH_01: wyłącznie manifest + precache shella z domyślnych ustawień.
      // Strategie cache dla /api i kolejka offline → BATCH_12 (ADR-009).
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,woff2}'],
        navigateFallbackDenylist: [/^\/api\//],
      },
      manifest: {
        name: 'Family Food Planner',
        short_name: 'Planer',
        description: 'Planowanie posiłków, wartości odżywczych i zakupów dla rodziny.',
        lang: 'pl',
        dir: 'ltr',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        scope: '/',
        background_color: '#FAF6EF',
        theme_color: '#E07A2F',
        // Ikony placeholder — komplet (PNG 192/512 + maskable) dostarcza BATCH_12.
        icons: [
          {
            src: '/icon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any',
          },
          {
            src: '/icon-maskable.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'maskable',
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    watch: { ignored: watchIgnored, ...(usePolling ? { usePolling: true, interval: 300 } : {}) },
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.spec.ts'],
    css: false,
    restoreMocks: true,
  },
})
