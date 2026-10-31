import './assets/tailwind.css'
// Wariant do druku listy zakupowej (06_UIUX §6) — reguły wyłącznie w `@media print`.
import './assets/print.css'

import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import { setUnauthorizedHandler } from './api/client'
import App from './App.vue'
import { registerServiceWorker } from './lib/offline/registerSW'
import { removeLegacyPrivateCaches } from './lib/offline/privateSession'
import { ensureIsolatedServiceWorker } from './lib/offline/workerIsolation'
import { router } from './router'
import { useAuthStore } from './stores/auth'
import { useOfflineQueueStore } from './stores/offlineQueue'

const app = createApp(App)

// Pinia = WYŁĄCZNIE stan UI (sesja, szkice, kolejka offline) — ADR-007.
app.use(createPinia())

// TanStack Query = cały stan serwera (cache, invalidacja) — ADR-007.
const queryClient = new QueryClient({
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
})
app.use(VueQueryPlugin, { queryClient })
const auth = useAuthStore()

// Sesja wygasła albo została odwołana z innego urządzenia: czyścimy stan i
// pozwalamy guardowi routera odesłać użytkownika na /login (ADR-003).
setUnauthorizedHandler(() => {
  auth.clear()
  queryClient.clear()
  if (router.currentRoute.value.meta.anonymous !== true) {
    void router.push({ name: 'login' })
  }
})

async function bootstrap(): Promise<void> {
  if (import.meta.env.PROD) await ensureIsolatedServiceWorker()
  // Usuwamy stare, nieskopowane odpowiedzi ZANIM router/komponent wykona GET.
  // Nie ignorujemy odmowy kasowania: prywatnego ekranu nie wolno wtedy otworzyć
  // z potencjalnie cudzym cache. Nowy SW nie zapisuje API ani uploadów.
  await removeLegacyPrivateCaches()
  app.use(router)
  await router.isReady()
  app.mount('#app')
  useOfflineQueueStore().start()
  registerServiceWorker()
}

void bootstrap().catch(() => {
  const root = document.getElementById('app')
  if (!root) return
  const message = document.createElement('p')
  message.setAttribute('role', 'alert')
  message.textContent = 'Nie udało się uruchomić aplikacji. Odśwież stronę i spróbuj ponownie.'
  root.replaceChildren(message)
})
