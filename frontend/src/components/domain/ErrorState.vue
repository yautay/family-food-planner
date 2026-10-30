<script setup lang="ts">
import { AlertCircle, LoaderCircle } from '@lucide/vue'
import { Button } from '@/components/ui/button'

withDefaults(
  defineProps<{
    message: string
    title?: string
    retryLabel?: string
    pending?: boolean
    compact?: boolean
  }>(),
  {
    title: 'Nie udało się pobrać danych',
    retryLabel: 'Spróbuj ponownie',
    pending: false,
    compact: false,
  },
)
const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <section
    class="border-destructive/30 bg-card flex flex-wrap items-start gap-3 rounded-xl border p-4"
    :class="!compact && 'sm:p-6'"
    :aria-busy="pending"
  >
    <div role="alert" class="flex min-w-0 flex-1 gap-3">
      <AlertCircle aria-hidden="true" class="text-destructive mt-0.5 size-5 shrink-0" />
      <div class="grid min-w-0 gap-1">
        <h2 class="font-semibold">{{ title }}</h2>
        <p class="text-muted-foreground text-sm break-words">{{ message }}</p>
        <slot />
      </div>
    </div>
    <Button type="button" variant="outline" :disabled="pending" @click="emit('retry')">
      <LoaderCircle
        v-if="pending"
        aria-hidden="true"
        class="size-4 animate-spin motion-reduce:animate-none"
      />
      {{ pending ? 'Ponawianie…' : retryLabel }}
    </Button>
  </section>
</template>
