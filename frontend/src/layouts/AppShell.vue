<script setup lang="ts">
import { Sprout } from '@lucide/vue'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import AccountNavigation from '@/components/domain/navigation/AccountNavigation.vue'
import PlanNavigation from '@/components/domain/navigation/PlanNavigation.vue'
import {
  isNavItemActive,
  isPlanView,
  planNavigationContext,
  planNavigationTarget,
  visibleNavItems,
} from '@/lib/navigation'
import { APP_NAME, navigation as texts } from '@/lib/texts'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()
const main = ref<HTMLElement | null>(null)
const items = computed(() => visibleNavItems(auth.isAdmin))
const primaryItems = computed(() => items.value.filter((item) => item.primary))
const library = computed(() => items.value.find((item) => item.name === 'produkty')!)
// Pamięć kontekstu kalendarza przy krótkiej wizycie w innym obszarze to stan UI.
const context = ref(planNavigationContext(route))
watch(
  () => route.fullPath,
  () => {
    if (isPlanView(route.name)) context.value = planNavigationContext(route)
  },
  { immediate: true },
)

// Query zmienia filtry/wybór dnia w tygodniu, nie cały widok. Nie zabieramy fokusu.
watch(
  () => route.path,
  async () => {
    await nextTick()
    main.value?.focus({ preventScroll: true })
  },
)
watch(
  () => route.meta.title,
  (title) => {
    document.title = typeof title === 'string' ? `${title} · ${APP_NAME}` : APP_NAME
  },
  { immediate: true },
)

const logout = useMutation({
  mutationFn: () => auth.logout(),
  onSettled: async () => {
    queryClient.clear()
    await router.push({ name: 'login' })
  },
})
</script>

<template>
  <div class="bg-background text-foreground min-h-dvh md:flex" data-testid="app-shell">
    <a
      href="#main-content"
      class="bg-primary text-primary-foreground sr-only fixed top-3 left-3 z-50 rounded-lg px-4 py-3 focus:not-sr-only print:hidden"
      data-testid="skip-link"
      >{{ texts.skipToContent }}</a
    >
    <aside
      class="border-border bg-navigation hidden w-52 shrink-0 border-r md:flex md:flex-col lg:w-56 print:hidden"
      data-testid="nav-sidebar"
    >
      <div class="sticky top-0 flex h-dvh flex-col overflow-y-auto px-4 py-7">
        <RouterLink
          :to="planNavigationTarget('plan-dnia', context)"
          class="mb-10 flex min-h-11 items-center gap-3 px-2"
          :aria-label="`${APP_NAME} — Plan`"
        >
          <span
            class="bg-primary text-primary-foreground flex size-9 items-center justify-center rounded-xl"
            ><Sprout class="size-6" aria-hidden="true"
          /></span>
          <span class="font-serif text-3xl tracking-tight">{{ APP_NAME }}</span>
        </RouterLink>
        <nav class="space-y-2" aria-label="Nawigacja główna">
          <RouterLink
            v-for="item in primaryItems"
            :key="item.name"
            :to="planNavigationTarget(item.name, context)"
            class="flex min-h-12 items-center gap-3 rounded-xl px-3 text-sm"
            :class="
              isNavItemActive(item, route.name)
                ? 'bg-primary text-primary-foreground font-medium shadow-sm'
                : 'hover:bg-accent'
            "
            :aria-current="isNavItemActive(item, route.name) ? 'page' : undefined"
            :data-testid="`nav-item-${item.name}`"
          >
            <component :is="item.icon" class="size-5 shrink-0" aria-hidden="true" />{{ item.label }}
          </RouterLink>
        </nav>
        <div class="mt-auto space-y-4 pt-10">
          <div class="kitchen-check mx-2 h-2 rounded opacity-15" aria-hidden="true" />
          <RouterLink
            :to="{ name: library.name }"
            class="hover:bg-accent flex min-h-11 items-center gap-3 rounded-xl px-2 text-sm"
            :class="
              isNavItemActive(library, route.name)
                ? 'bg-accent text-primary font-medium'
                : 'text-muted-foreground'
            "
            :aria-current="isNavItemActive(library, route.name) ? 'page' : undefined"
            data-testid="nav-item-produkty"
            ><component :is="library.icon" class="size-5 shrink-0" aria-hidden="true" />{{
              library.label
            }}</RouterLink
          >
          <AccountNavigation
            :display-name="auth.user?.display_name"
            :household-name="auth.user?.household?.name"
            :is-admin="auth.isAdmin"
            :pending="logout.isPending.value"
            @logout="logout.mutate()"
          />
        </div>
      </div>
    </aside>
    <div class="flex min-w-0 flex-1 flex-col">
      <header
        class="border-border bg-card flex items-center justify-between border-b px-4 py-2 md:hidden print:hidden"
      >
        <RouterLink
          :to="planNavigationTarget('plan-dnia', context)"
          class="flex min-h-11 items-center gap-2 font-serif text-2xl"
          ><Sprout class="text-primary size-6" aria-hidden="true" />{{ APP_NAME }}</RouterLink
        >
        <AccountNavigation
          mobile
          :display-name="auth.user?.display_name"
          :household-name="auth.user?.household?.name"
          :is-admin="auth.isAdmin"
          :pending="logout.isPending.value"
          @logout="logout.mutate()"
        />
      </header>
      <main
        id="main-content"
        ref="main"
        tabindex="-1"
        class="mx-auto w-full max-w-5xl flex-1 px-4 py-6 pb-[calc(6rem+env(safe-area-inset-bottom))] md:px-6 md:pb-8 lg:px-8 print:max-w-none print:p-0"
      >
        <PlanNavigation
          v-if="isPlanView(route.name)"
          :context="context"
          :active-view="route.name"
          class="print:hidden"
        />
        <RouterView />
      </main>
    </div>
    <nav
      class="border-border bg-card fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t px-1 pb-[env(safe-area-inset-bottom)] md:hidden print:hidden"
      aria-label="Nawigacja główna (mobile)"
      data-testid="nav-bottom"
    >
      <RouterLink
        v-for="item in primaryItems"
        :key="item.name"
        :to="planNavigationTarget(item.name, context)"
        class="flex min-h-16 min-w-0 flex-col items-center justify-center gap-1 rounded-lg px-1 text-xs"
        :class="
          isNavItemActive(item, route.name)
            ? 'text-primary font-semibold'
            : 'text-muted-foreground hover:bg-accent'
        "
        :aria-current="isNavItemActive(item, route.name) ? 'page' : undefined"
        :data-testid="`nav-bottom-${item.name}`"
      >
        <component :is="item.icon" class="size-5" aria-hidden="true" />{{ item.label }}
      </RouterLink>
    </nav>
  </div>
</template>
