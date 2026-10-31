<script setup lang="ts">
import { products } from '@/lib/texts'

defineProps<{ missing: readonly string[]; testid: string }>()
</script>

<template>
  <details class="min-w-0 text-sm" :data-testid="testid">
    <summary
      class="text-warning min-h-11 cursor-pointer rounded-md py-3 font-medium underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
      :data-testid="`${testid}-toggle`"
    >
      {{ products.incompleteData }} — szczegóły
    </summary>
    <ul
      class="text-muted-foreground grid min-w-0 list-disc gap-2 pl-5 pb-3"
      :data-testid="`${testid}-messages`"
    >
      <li v-for="(message, index) in missing" :key="index" class="break-words">{{ message }}</li>
    </ul>
  </details>
</template>
