<script setup lang="ts">
import { CheckCircle2, Info, TriangleAlert } from '@lucide/vue'
withDefaults(defineProps<{ message: string; tone?: 'success' | 'warning' | 'info' }>(), {
  tone: 'info',
})
</script>

<template>
  <!-- Sukces wyświetla konsument dopiero po potwierdzonej operacji serwera. -->
  <p
    role="status"
    class="flex items-start gap-2 rounded-lg p-3 text-sm leading-relaxed"
    :class="tone === 'warning' ? 'bg-recipe-honey text-warning' : 'bg-muted text-primary'"
  >
    <TriangleAlert v-if="tone === 'warning'" aria-hidden="true" class="mt-0.5 size-4 shrink-0" />
    <CheckCircle2
      v-else-if="tone === 'success'"
      aria-hidden="true"
      class="mt-0.5 size-4 shrink-0"
    />
    <Info v-else aria-hidden="true" class="mt-0.5 size-4 shrink-0" />
    {{ message }}
  </p>
</template>
