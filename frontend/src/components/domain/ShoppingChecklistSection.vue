<script
  setup
  lang="ts"
  generic="TItem extends { id: number; checked: boolean; already_have: boolean }"
>
import { ChevronDown } from '@lucide/vue'
import { computed, nextTick, ref, useId, watch } from 'vue'

const props = defineProps<{ name: string; items: TItem[] }>()
const id = useId()
const expanded = ref(false)
const toggle = ref<HTMLButtonElement>()
const list = ref<HTMLElement>()
let changedControl: HTMLInputElement | null = null
const purchased = computed(() => props.items.filter((item) => item.checked && !item.already_have))

function collapsed(item: TItem): boolean {
  return !expanded.value && item.checked && !item.already_have
}

function rememberControl(event: Event): void {
  // requestToggle wyłącza checkbox przed await onMutate. Przeglądarka może
  // już wtedy oddać fokus body, zanim nowa wartość checked zwinie wiersz.
  if (event.target instanceof HTMLInputElement && document.activeElement === event.target)
    changedControl = event.target
}

// Po odhaczeniu wiersz znika. Fokus pozostaje przy jego kategorii, skąd
// można rozwinąć kupione i cofnąć decyzję także samą klawiaturą.
watch(purchased, async () => {
  const active = document.activeElement
  const control = changedControl ?? active
  changedControl = null
  if (!(control instanceof HTMLElement) || !list.value?.contains(control)) return
  await nextTick()
  if (
    control.closest('.shopping-item-collapsed') &&
    (document.activeElement === control || document.activeElement === document.body)
  )
    toggle.value?.focus()
})
</script>

<template>
  <section class="shopping-category grid gap-1">
    <header
      class="bg-background sticky top-0 z-10 flex flex-wrap items-center justify-between gap-x-3 py-2 print:static"
    >
      <h2 class="text-base font-semibold">{{ name }}</h2>
      <button
        v-if="purchased.length"
        ref="toggle"
        type="button"
        class="text-muted-foreground hover:text-foreground focus-visible:ring-ring inline-flex min-h-11 items-center gap-2 rounded-md px-2 text-sm focus-visible:ring-2 focus-visible:outline-none print:hidden"
        :aria-expanded="expanded"
        :aria-controls="id"
        :aria-label="`${expanded ? 'Zwiń' : 'Pokaż'} kupione: ${name} (${purchased.length})`"
        data-testid="shopping-purchased-toggle"
        @click="expanded = !expanded"
      >
        Kupione ({{ purchased.length }})
        <ChevronDown aria-hidden="true" class="size-4" :class="expanded && 'rotate-180'" />
      </button>
    </header>
    <!-- Nie przenosimy kupionych na koniec ani do innej kategorii. Wszystkie
         wiersze pozostają w kolejności serwera; druk pomija samo zwinięcie. -->
    <ul :id="id" ref="list" class="border-border grid border-t" @change.capture="rememberControl">
      <template v-for="item in items" :key="item.id">
        <slot name="item" :item="item" :collapsed="collapsed(item)" />
      </template>
    </ul>
  </section>
</template>

<style scoped>
:deep(.shopping-item-collapsed) {
  display: none;
}
@media print {
  :deep(.shopping-item-collapsed) {
    display: list-item;
  }
}
</style>
