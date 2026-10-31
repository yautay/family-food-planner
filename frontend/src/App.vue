<script setup lang="ts">
import { useQueryClient } from '@tanstack/vue-query'
import { computed, onScopeDispose, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import { getPrivateOfflineScope, subscribePrivateOfflineScope } from '@/lib/offline/privateSession'
import { useAuthStore } from '@/stores/auth'
import SessionQueryBoundary from '@/components/SessionQueryBoundary.vue'
import { subscribeSessionGeneration } from '@/lib/sessionGeneration'

const auth = useAuthStore()
const route = useRoute()
const queryClient = useQueryClient()
const revision = ref(0)
const offlineScope = ref(getPrivateOfflineScope())
const protectedView = computed(() => route.meta.anonymous !== true && route.meta.public !== true)
const allowed = computed(() => {
  if (!protectedView.value) return true
  if (auth.isAuthenticated) return route.meta.admin !== true || auth.isAdmin
  return route.name === 'zakupy-lista' && auth.offlineSession && offlineScope.value !== null
})

function closePreviousView(): void {
  queryClient.clear()
  // clear() nie usuwa danych z istniejącego QueryObserver. Nowy klucz
  // odmontowuje cały chroniony widok wraz z observerami i lokalnymi refami.
  revision.value += 1
}

watch(
  () =>
    auth.user === null ? null : JSON.stringify([auth.user.id, auth.household?.id, auth.user.role]),
  closePreviousView,
  { flush: 'sync' },
)
onScopeDispose(
  subscribePrivateOfflineScope((scope) => {
    offlineScope.value = scope
    closePreviousView()
  }),
)
onScopeDispose(subscribeSessionGeneration(closePreviousView))
</script>

<template>
  <RouterView v-slot="{ Component }">
    <SessionQueryBoundary v-if="allowed && protectedView" :key="revision">
      <component :is="Component" />
    </SessionQueryBoundary>
    <component :is="Component" v-else-if="allowed" />
    <main v-else class="bg-background text-foreground mx-auto max-w-xl space-y-4 p-6" role="alert">
      <p>Sesja się zmieniła. Otwórz ponownie dostępny widok.</p>
      <RouterLink
        class="text-primary underline"
        :to="
          auth.isAuthenticated
            ? { name: 'plan-dnia' }
            : { name: 'login', query: { next: route.fullPath } }
        "
        >{{ auth.isAuthenticated ? 'Przejdź do planu' : 'Przejdź do logowania' }}</RouterLink
      >
    </main>
  </RouterView>
</template>
