<script setup lang="ts">
defineProps<{ label: string }>()
</script>

<template>
  <div class="flex min-w-0 flex-wrap items-center gap-2" role="group" :aria-label="label">
    <slot />
    <div v-if="$slots.secondary" class="flex flex-wrap items-center gap-2 sm:ml-auto">
      <slot name="secondary" />
    </div>
  </div>
</template>
