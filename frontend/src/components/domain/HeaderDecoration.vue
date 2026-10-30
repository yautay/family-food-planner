<script setup lang="ts">
import { CookingPot, Leaf, Soup, Wheat } from '@lucide/vue'

withDefaults(defineProps<{ motif?: 'plate' | 'herbs' | 'wheat' | 'pot' }>(), { motif: 'plate' })
</script>

<template>
  <div
    aria-hidden="true"
    class="pointer-events-none relative hidden h-32 w-28 shrink-0 select-none sm:block print:hidden"
    data-testid="header-decoration"
  >
    <div
      class="border-herb/25 bg-background absolute inset-x-1 top-5 bottom-2 grid -rotate-6 place-items-center rounded-[48%] border"
    >
      <div class="border-herb/20 absolute inset-2 rounded-[48%] border" />
      <CookingPot v-if="motif === 'pot'" class="text-primary size-11" :stroke-width="1.2" />
      <Leaf v-else-if="motif === 'herbs'" class="text-primary size-11" :stroke-width="1.2" />
      <Wheat v-else-if="motif === 'wheat'" class="text-primary size-11" :stroke-width="1.2" />
      <Soup v-else class="text-primary size-11" :stroke-width="1.2" />
    </div>
    <Leaf class="text-herb absolute -top-1 right-0 size-10 rotate-12" :stroke-width="1.2" />
    <Wheat
      class="text-terracotta absolute bottom-0 -left-2 size-9 -rotate-12"
      :stroke-width="1.2"
    />
  </div>
</template>
