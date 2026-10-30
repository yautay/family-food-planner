<script setup lang="ts">
withDefaults(defineProps<{ title: string; description?: string; tone?: 'plain' | 'soft' }>(), {
  tone: 'soft',
  description: undefined,
})
</script>

<template>
  <section
    class="grid min-w-0 gap-4 rounded-xl p-4 sm:p-6"
    :class="tone === 'soft' ? 'bg-muted' : 'border-border bg-card border'"
  >
    <header class="grid gap-1">
      <h2 class="text-base font-semibold">{{ title }}</h2>
      <p v-if="description" class="text-muted-foreground text-sm">{{ description }}</p>
    </header>
    <slot />
    <footer v-if="$slots.actions" class="flex flex-wrap gap-2 border-t pt-4">
      <slot name="actions" />
    </footer>
  </section>
</template>
