<script setup lang="ts">
import { Sprout } from '@lucide/vue'
import { Button } from '@/components/ui/button'

withDefaults(
  defineProps<{ title: string; description: string; actionLabel?: string; pending?: boolean }>(),
  { pending: false, actionLabel: undefined },
)
const emit = defineEmits<{ action: [] }>()
</script>

<template>
  <section
    class="border-border grid justify-items-start gap-4 rounded-xl border border-dashed p-6 sm:p-8"
  >
    <Sprout
      aria-hidden="true"
      class="text-herb pointer-events-none size-8 print:hidden"
      :stroke-width="1.5"
    />
    <div class="grid gap-2">
      <h2 class="text-lg font-semibold">{{ title }}</h2>
      <p class="text-muted-foreground max-w-prose text-sm leading-relaxed">{{ description }}</p>
    </div>
    <!-- Slot akcji pozwala użyć Button as-child + RouterLink przy nawigacji. -->
    <slot name="action">
      <Button
        v-if="actionLabel"
        type="button"
        :disabled="pending"
        :aria-busy="pending"
        @click="emit('action')"
        >{{ actionLabel }}</Button
      >
    </slot>
  </section>
</template>
