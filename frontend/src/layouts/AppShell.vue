<script setup lang="ts">
/**
 * Szkielet aplikacji (06_UIUX §5): sidebar na desktopie, bottom-nav na mobile.
 *
 * Bottom-nav pokazuje trzy najczęstsze sekcje (Plan / Przepisy / Zakupy)
 * i przycisk „Więcej" rozwijający resztę — pozycje pochodzą z jednego rejestru
 * `lib/navigation.ts`, więc oba warianty nie mogą się rozjechać.
 */
import { LogOut } from '@lucide/vue'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { computed, ref } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'

import { Button } from '@/components/ui/button'
import { navGroups, visibleNavItems } from '@/lib/navigation'
import { APP_NAME, APP_TAGLINE, auth as authTexts } from '@/lib/texts'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const queryClient = useQueryClient()

const items = computed(() => visibleNavItems(auth.isAdmin))
const groups = computed(() => navGroups(auth.isAdmin))
const primaryItems = computed(() => items.value.filter((item) => item.primary))
const secondaryItems = computed(() => items.value.filter((item) => !item.primary))

const moreOpen = ref(false)

const logout = useMutation({
  mutationFn: () => auth.logout(),
  onSettled: async () => {
    moreOpen.value = false
    // Po zmianie tożsamości żadne dane serwera w cache nie są już nasze.
    queryClient.clear()
    await router.push({ name: 'login' })
  },
})
</script>

<template>
  <div class="bg-background text-foreground min-h-dvh md:flex" data-testid="app-shell">
    <!-- Sidebar (desktop) -->
    <aside
      class="border-border bg-card hidden w-64 shrink-0 border-r md:flex md:flex-col"
      data-testid="nav-sidebar"
    >
      <div class="border-border flex items-center gap-3 border-b px-4 py-4">
        <span class="bg-primary size-8 rounded-lg" aria-hidden="true" />
        <div>
          <p class="text-sm font-semibold">{{ APP_NAME }}</p>
          <p class="text-muted-foreground text-xs">{{ APP_TAGLINE }}</p>
        </div>
      </div>

      <nav class="flex-1 space-y-1 p-2" aria-label="Nawigacja główna">
        <template v-for="group in groups" :key="group.label ?? 'main'">
          <p
            v-if="group.label"
            class="text-muted-foreground px-3 pt-4 pb-1 text-xs font-medium uppercase"
            :data-testid="`nav-group-${group.label}`"
          >
            {{ group.label }}
          </p>
          <RouterLink
            v-for="item in group.items"
            :key="item.name"
            :to="{ name: item.name }"
            class="hover:bg-accent flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm"
            active-class="bg-accent text-accent-foreground font-medium"
            :data-testid="`nav-item-${item.name}`"
          >
            <component :is="item.icon" class="size-5 shrink-0" aria-hidden="true" />
            {{ item.label }}
          </RouterLink>
        </template>
      </nav>

      <div class="border-border border-t p-3">
        <p class="text-muted-foreground truncate px-1 pb-2 text-xs" data-testid="current-user">
          {{ auth.user?.display_name }}
        </p>
        <Button
          variant="outline"
          class="min-h-11 w-full justify-start gap-3"
          :disabled="logout.isPending.value"
          data-testid="logout-button"
          @click="logout.mutate()"
        >
          <LogOut class="size-5" aria-hidden="true" />
          {{ authTexts.logout }}
        </Button>
      </div>
    </aside>

    <div class="flex min-w-0 flex-1 flex-col">
      <!-- Nagłówek (mobile) -->
      <header class="border-border bg-card border-b px-4 py-3 md:hidden">
        <p class="text-base font-semibold">{{ APP_NAME }}</p>
      </header>

      <main class="mx-auto w-full max-w-5xl flex-1 px-4 py-6 pb-28 md:pb-8">
        <RouterView />
      </main>
    </div>

    <!-- Panel „Więcej" (mobile) -->
    <div
      v-if="moreOpen"
      class="border-border bg-card fixed inset-x-0 bottom-16 z-20 border-t p-2 md:hidden"
      data-testid="nav-more-panel"
    >
      <RouterLink
        v-for="item in secondaryItems"
        :key="item.name"
        :to="{ name: item.name }"
        class="hover:bg-accent flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm"
        :data-testid="`nav-more-item-${item.name}`"
        @click="moreOpen = false"
      >
        <component :is="item.icon" class="size-5 shrink-0" aria-hidden="true" />
        {{ item.label }}
      </RouterLink>
      <Button
        variant="ghost"
        class="min-h-11 w-full justify-start gap-3"
        :disabled="logout.isPending.value"
        data-testid="logout-button-mobile"
        @click="logout.mutate()"
      >
        <LogOut class="size-5" aria-hidden="true" />
        {{ authTexts.logout }}
      </Button>
    </div>

    <!-- Bottom-nav (mobile) -->
    <nav
      class="border-border bg-card fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t md:hidden"
      aria-label="Nawigacja główna (mobile)"
      data-testid="nav-bottom"
    >
      <RouterLink
        v-for="item in primaryItems"
        :key="item.name"
        :to="{ name: item.name }"
        class="flex min-h-16 flex-col items-center justify-center gap-1 text-xs"
        active-class="text-primary font-medium"
        :data-testid="`nav-bottom-${item.name}`"
        @click="moreOpen = false"
      >
        <component :is="item.icon" class="size-5" aria-hidden="true" />
        {{ item.label }}
      </RouterLink>
      <button
        type="button"
        class="flex min-h-16 flex-col items-center justify-center gap-1 text-xs"
        :aria-expanded="moreOpen"
        aria-label="Więcej sekcji"
        data-testid="nav-more-toggle"
        @click="moreOpen = !moreOpen"
      >
        <span class="text-lg leading-none" aria-hidden="true">•••</span>
        Więcej
      </button>
    </nav>
  </div>
</template>
