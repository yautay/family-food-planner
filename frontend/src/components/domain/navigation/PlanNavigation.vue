<script setup lang="ts">
import { RouterLink } from 'vue-router'
import ActionArea from '@/components/domain/ActionArea.vue'
import { PLAN_VIEWS, planNavigationTarget, type PlanNavigationContext } from '@/lib/navigation'

defineProps<{ context: PlanNavigationContext; activeView: unknown }>()
</script>

<template>
  <ActionArea label="Planowanie" class="mb-6">
    <nav
      class="border-border bg-card flex max-w-full flex-wrap gap-1 rounded-xl border p-1"
      aria-label="Widok planu"
      data-testid="plan-navigation"
    >
      <RouterLink
        v-for="view in PLAN_VIEWS"
        :key="view.name"
        :to="planNavigationTarget(view.name, context)"
        class="flex min-h-11 items-center justify-center rounded-lg px-3 text-sm sm:px-4"
        :class="
          activeView === view.name
            ? 'bg-primary text-primary-foreground font-medium'
            : 'text-muted-foreground hover:bg-accent'
        "
        :aria-current="activeView === view.name ? 'page' : undefined"
        :data-testid="`plan-view-${view.name}`"
        >{{ view.label }}</RouterLink
      >
    </nav>
    <template #secondary>
      <RouterLink
        :to="planNavigationTarget('zakupy', context)"
        class="text-primary flex min-h-11 items-center rounded-lg px-3 text-sm font-medium hover:underline"
        data-testid="plan-shopping-link"
        >Zakupy z planu</RouterLink
      >
    </template>
  </ActionArea>
</template>
