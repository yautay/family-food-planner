<script setup lang="ts">
import { CookingPot, Leaf, Wheat } from '@lucide/vue'
import { ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    src?: string | null
    alt: string
    tone?: 'herb' | 'honey' | 'terracotta'
    loading?: 'lazy' | 'eager'
  }>(),
  { src: null, tone: 'herb', loading: 'lazy' },
)

const failed = ref(false)
watch(
  () => props.src,
  () => {
    failed.value = false
  },
)
const tones = {
  herb: 'bg-recipe-herb text-primary',
  honey: 'bg-recipe-honey text-honey',
  terracotta: 'bg-recipe-terracotta text-terracotta',
} as const
</script>

<template>
  <div class="relative isolate aspect-[4/3] overflow-hidden" :class="tones[tone]">
    <img
      v-if="src && !failed"
      :src="src"
      :alt="alt"
      :loading="loading"
      class="size-full object-cover"
      @error="failed = true"
    />
    <div
      v-else
      class="grid size-full place-items-center"
      role="img"
      aria-label="Ilustracja zastępcza — brak zdjęcia przepisu"
      data-testid="recipe-image-fallback"
    >
      <div aria-hidden="true" class="pointer-events-none absolute inset-0 select-none print:hidden">
        <div
          class="bg-card/70 absolute top-1/2 left-1/2 size-28 -translate-1/2 -rotate-12 rounded-[45%]"
        />
        <CookingPot
          class="absolute top-1/2 left-1/2 size-14 -translate-1/2 -rotate-6"
          :stroke-width="1.2"
        />
        <Leaf class="absolute top-6 left-6 size-8 rotate-12" :stroke-width="1.2" />
        <Wheat class="absolute right-6 bottom-8 size-9 -rotate-12" :stroke-width="1.2" />
        <div class="kitchen-check absolute right-0 bottom-0 h-8 w-16 opacity-[0.055]" />
      </div>
    </div>
    <slot />
  </div>
</template>
