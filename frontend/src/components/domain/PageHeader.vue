<script setup lang="ts">
import HeaderDecoration from '@/components/domain/HeaderDecoration.vue'

withDefaults(
  defineProps<{
    title: string
    description?: string
    eyebrow?: string
    titleTestid?: string
    decoration?: 'plate' | 'herbs' | 'wheat' | 'pot' | false
  }>(),
  { decoration: false, description: undefined, eyebrow: undefined, titleTestid: undefined },
)
</script>

<template>
  <header
    class="relative isolate flex min-w-0 items-center gap-6"
    :class="
      decoration
        ? 'bg-header rounded-2xl rounded-bl-md px-4 py-6 sm:px-6 print:bg-transparent print:p-0'
        : 'py-2'
    "
  >
    <div class="relative z-10 grid min-w-0 flex-1 gap-4">
      <div class="grid gap-2">
        <p
          v-if="eyebrow"
          class="text-muted-foreground text-xs font-medium tracking-widest uppercase"
        >
          {{ eyebrow }}
        </p>
        <h1
          class="font-serif text-page sm:text-page-lg font-normal tracking-tight break-words"
          :data-testid="titleTestid"
        >
          {{ title }}
        </h1>
        <p v-if="description" class="text-muted-foreground max-w-prose text-sm leading-relaxed">
          {{ description }}
        </p>
        <slot />
      </div>
      <div v-if="$slots.actions" class="flex min-w-0 flex-wrap items-center gap-2">
        <slot name="actions" />
      </div>
    </div>
    <div
      v-if="decoration"
      aria-hidden="true"
      class="kitchen-check pointer-events-none absolute inset-y-0 right-0 w-4 rounded-r-2xl opacity-[0.055] select-none sm:w-16 print:hidden"
    />
    <HeaderDecoration v-if="decoration" :motif="decoration" />
  </header>
</template>
