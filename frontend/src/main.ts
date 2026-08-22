import './assets/tailwind.css'
// Wariant do druku listy zakupowej (06_UIUX §6) — reguły wyłącznie w `@media print`.
import './assets/print.css'

import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import { setUnauthorizedHandler } from './api/client'
import App from './App.vue'
import { registerServiceWorker } from './lib/offline/registerSW'
import { router } from './router'
import { useAuthStore } from './stores/auth'
import { useOfflineQueueStore } from './stores/offlineQueue'

const app = createApp(App)

// Pinia = WYŁĄCZNIE stan UI (sesja, szkice, kolejka offline) — ADR-007.
app.use(createPinia())

// TanStack Query = cały stan serwera (cache, invalidacja) — ADR-007.
app.use(VueQueryPlugin, {
  queryClientConfig: {
    defaultOptions: {
      queries: {
        // Dane rodzinne zmieniają się rzadko; brak refetchu przy każdym
        // powrocie do okna oszczędza migotanie UI (06_UIUX §3 pkt 4).
        refetchOnWindowFocus: false,
        staleTime: 30_000,
        retry: 1,
        // Patrz komentarz przy `mutations` niżej — ten sam powód: offline
        // obsługuje NASZA warstwa (snapshot w IndexedDB), a nie wewnętrzna
        // pauza TanStack, po której zapytanie wisi w `paused` bez błędu.
        networkMode: 'always',
      },
      // `networkMode: 'always'` jest WARUNKIEM działania kolejki offline (B12).
      //
      // Domyślny tryb `'online'` PAUZUJE mutację, gdy `navigator.onLine` jest
      // fałszywe: `onMutate` się wykonuje (więc optimistic update wygląda
      // poprawnie), ale `mutationFn` NIE JEST wołane aż do powrotu sieci.
      // Nasza kolejka nigdy by więc nie zobaczyła odhaczenia — a to ona, a nie
      // pamięć karty, ma je przechować (ADR-009: kolejka przeżywa reload
      // i zamknięcie aplikacji, wewnętrzna pauza TanStack nie przeżywa żadnego
      // z nich). Wyłapało to dopiero E2E z `context.setOffline(true)`.
      mutations: {
        networkMode: 'always',
      },
    },
  },
})

app.use(router)

// Sesja wygasła albo została odwołana z innego urządzenia: czyścimy stan i
// pozwalamy guardowi routera odesłać użytkownika na /login (ADR-003).
setUnauthorizedHandler(() => {
  const auth = useAuthStore()
  if (auth.isAuthenticated) {
    auth.clear()
    void router.push({ name: 'login' })
  }
})

app.mount('#app')

// Kolejka offline: nasłuch `online`/`offline`/powrotu do karty + flush zaległości
// (ADR-009). Wołane PO `mount`, bo dopiero wtedy pinia z `app.use` jest aktywna.
useOfflineQueueStore().start()

// Service worker: rejestracja i prompt „dostępna nowa wersja" (patrz plik).
registerServiceWorker()
