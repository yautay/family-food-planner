<script setup lang="ts">
withDefaults(defineProps<{ label?: string }>(), { label: 'Wczytywanie…' })
</script>

<template>
  <!-- Konsument pokazuje ten stan tylko przed pierwszą zakończoną odpowiedzią. -->
  <div role="status" aria-busy="true" class="grid gap-3 py-4">
    <span class="text-muted-foreground text-sm">{{ label }}</span>
    <div
      aria-hidden="true"
      class="pointer-events-none grid animate-pulse gap-3 motion-reduce:animate-none print:hidden"
    >
      <div class="bg-muted h-5 w-2/3 rounded-md" />
      <div class="bg-muted h-16 rounded-xl" />
      <div class="bg-muted h-16 rounded-xl" />
    </div>
  </div>
</template>
