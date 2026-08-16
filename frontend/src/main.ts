import './assets/tailwind.css'

import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import { setUnauthorizedHandler } from './api/client'
import App from './App.vue'
import { router } from './router'
import { useAuthStore } from './stores/auth'

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
