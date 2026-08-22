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
      // Dev server NIE rejestruje SW (BATCH_12, Implementation Notes): precache
      // w trakcie pracy zatruwa cache i zwraca stary chunk po każdej zmianie.
      // Service worker testuje się na buildzie (`task fe-build` + `vite preview`).
      devOptions: { enabled: false },
      includeAssets: ['icons/apple-touch-icon.png', 'icon.svg'],
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        // `/api/` i `/uploads/` obsługuje BACKEND (ADR-014) — fallback nawigacyjny
        // na `index.html` zamieniłby 404 API w stronę SPA, a plik z uploadów w HTML.
        navigateFallbackDenylist: [/^\/api\//, /^\/uploads\//],
        // Publiczna strona listy jest trasą LENIWĄ i poza `AppShell` (B11), więc
        // jej chunk nie wchodzi do precache przez shell — ale wchodzi przez
        // `globPatterns` (każdy `.js` z `dist`). Nic tu nie wykluczamy.
        runtimeCaching: [
          {
            // Listy zakupowe i reszta API: NetworkFirst z KRÓTKIM timeoutem.
            // Bez `networkTimeoutSeconds` offline UX to 30 s spinnera, zanim
            // przeglądarka odpuści połączenie (karta B12, Implementation Notes).
            urlPattern: ({ url }: { url: URL }) =>
              url.pathname.startsWith('/api/') && !url.pathname.startsWith('/api/v1/auth/'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'ffp-api',
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 },
              cacheableResponse: { statuses: [200] },
            },
          },
          {
            // Uploady (zdjęcia przepisów) — statyczne i adresowane ścieżką pliku.
            urlPattern: ({ url }: { url: URL }) => url.pathname.startsWith('/uploads/'),
            handler: 'CacheFirst',
            options: {
              cacheName: 'ffp-uploads',
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 30 },
              cacheableResponse: { statuses: [200] },
            },
          },
        ],
      },
      manifest: {
        name: 'Family Food Planner',
        short_name: 'FFP',
        description: 'Planowanie posiłków, wartości odżywczych i zakupów dla rodziny.',
        lang: 'pl',
        dir: 'ltr',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        scope: '/',
        background_color: '#FAF6EF',
        theme_color: '#E07A2F',
        // Splash na Androidzie składa przeglądarka z ikony 512 + `background_color`
        // + `name`; iOS bierze `apple-touch-icon` z `index.html` (brak wsparcia
        // dla manifestu w tym zakresie) — stąd oba warianty.
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          {
            src: '/icons/icon-maskable-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'maskable',
          },
          {
            src: '/icons/icon-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
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
