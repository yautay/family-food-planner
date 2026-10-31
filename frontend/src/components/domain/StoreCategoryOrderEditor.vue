<script setup lang="ts">
/**
 * Edytor kolejności kategorii w sklepie (widok „Sklepy" w Ustawieniach, B09).
 *
 * Kolejność to trasa przejścia po sklepie, więc podstawowym gestem jest
 * przeciąganie. Drag&drop realizuje **natywne HTML5 DnD** — bez biblioteki:
 * lista ma kilkanaście pozycji, jest jednokolumnowa i nie potrzebuje ani
 * animacji, ani list zagnieżdżonych, więc `dragstart`/`dragover`/`drop` to
 * kilkadziesiąt linii, a nie kolejna zależność do utrzymania (ADR-013 w duchu:
 * nie dokładamy bibliotek do rzeczy, które robimy sami).
 *
 * **Strzałki góra/dół są OBOWIĄZKOWE** (06_UIUX §2): na telefonie DnD jest
 * niewygodne, a dla klawiatury i czytnika ekranu — niedostępne. Każdy wiersz
 * ma więc dwa przyciski z `aria-label`, celami dotykowymi ≥44 px i tą samą
 * logiką przestawiania co przeciąganie.
 *
 * Komponent jest kontrolowany „w środku": trzyma szkic kolejności, a na
 * zewnątrz oddaje ją zdarzeniem `save` z listą `category_id`. Zapis (PUT całej
 * kolejności) należy do rodzica — dzięki temu ten sam edytor da się użyć
 * w innym kontekście bez przenoszenia mutacji.
 */
import { computed, ref, watch } from 'vue'

import type { Category } from '@/api/catalog'
import type { CategoryOrderEntry } from '@/api/stores'
import { Button } from '@/components/ui/button'
import { common, stores as texts } from '@/lib/texts'

const props = withDefaults(
  defineProps<{
    /** Pełny słownik kategorii (źródło nazw i listy „poza profilem"). */
    categories: readonly Category[]
    /** Aktualny profil sklepu w kolejności z serwera. */
    order: readonly CategoryOrderEntry[]
    pending?: boolean
  }>(),
  { pending: false },
)

const emit = defineEmits<{
  /** Nowa kolejność do zapisania (pełna podmiana, PUT). */
  (event: 'save', categoryIds: number[]): void
  (event: 'changed'): void
}>()

/** Szkic kolejności — lista id. Stan UI, więc mieszka w komponencie. */
const draft = ref<number[]>([])
const dragged = ref<number | null>(null)

/** Czy szkic odpowiada dokładnie tej kolejności (porównanie po id i pozycji). */
function sameAsDraft(entries: readonly CategoryOrderEntry[] | undefined): boolean {
  return (
    entries !== undefined &&
    draft.value.length === entries.length &&
    draft.value.every((id, index) => id === entries[index]?.category_id)
  )
}

watch(
  () => props.order,
  (entries, previous) => {
    // Refetch profilu (np. po archiwizacji INNEGO sklepu — `SklepySection`
    // unieważnia cały klucz `['stores']`) NIE MOŻE wyrzucić niezapisanych
    // przestawień: gdy szkic różni się od tego, co serwer mówił do tej pory,
    // zostawiamy go i czekamy na zapis albo zwinięcie edytora.
    if (previous !== undefined && !sameAsDraft(previous)) {
      return
    }
    draft.value = entries.map((entry) => entry.category_id)
  },
  { immediate: true, deep: true },
)

const names = computed(
  () => new Map(props.categories.map((category) => [category.id, category.name])),
)

function nameFor(categoryId: number): string {
  return names.value.get(categoryId) ?? `#${categoryId}`
}

/** Kategorie spoza profilu — te silnik listy (B11) umieści na końcu. */
const available = computed(() =>
  props.categories.filter((category) => !draft.value.includes(category.id)),
)

const isDirty = computed(
  () =>
    draft.value.length !== props.order.length ||
    draft.value.some((id, index) => id !== props.order[index]?.category_id),
)

/** Przestawia pozycję o `offset` miejsc; poza zakresem nie robi nic. */
function move(index: number, offset: number): void {
  if (props.pending) return
  const target = index + offset
  if (target < 0 || target >= draft.value.length) {
    return
  }
  const next = [...draft.value]
  const [item] = next.splice(index, 1)
  next.splice(target, 0, item as number)
  draft.value = next
  emit('changed')
}

function add(categoryId: number): void {
  if (props.pending) return
  draft.value = [...draft.value, categoryId]
  emit('changed')
}

function remove(categoryId: number): void {
  if (props.pending) return
  draft.value = draft.value.filter((id) => id !== categoryId)
  emit('changed')
}

function onDragStart(categoryId: number): void {
  if (props.pending) return
  dragged.value = categoryId
}

/** Upuszczenie na wiersz `index` wstawia przeciąganą kategorię na jego miejsce. */
function onDrop(index: number): void {
  const source = dragged.value
  dragged.value = null
  if (source === null) {
    return
  }
  const from = draft.value.indexOf(source)
  if (from === -1 || from === index) {
    return
  }
  move(from, index - from)
}
</script>

<template>
  <section class="grid gap-3" data-testid="category-order-editor">
    <header class="grid gap-1">
      <h3 class="text-sm font-semibold">{{ texts.orderTitle }}</h3>
      <p class="text-muted-foreground text-sm">{{ texts.orderSubtitle }}</p>
    </header>

    <p v-if="draft.length === 0" class="text-muted-foreground text-sm" data-testid="order-empty">
      {{ texts.orderEmpty }}
    </p>

    <ol v-else class="grid gap-2" data-testid="order-list">
      <li
        v-for="(categoryId, index) in draft"
        :key="categoryId"
        class="border-border bg-card grid gap-2 rounded-lg border p-3 sm:flex sm:items-center sm:justify-between"
        :draggable="!pending"
        :data-testid="`order-row-${categoryId}`"
        @dragstart="onDragStart(categoryId)"
        @dragover.prevent
        @drop.prevent="onDrop(index)"
      >
        <span class="flex min-w-0 items-center gap-2">
          <span class="text-muted-foreground text-sm tabular-nums">{{ index + 1 }}.</span>
          <span class="min-w-0 text-sm [overflow-wrap:anywhere]">{{ nameFor(categoryId) }}</span>
        </span>

        <span class="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            variant="outline"
            class="min-h-11 min-w-11"
            :disabled="pending || index === 0"
            :aria-label="`${texts.orderMoveUp}: ${nameFor(categoryId)}`"
            :data-testid="`order-up-${categoryId}`"
            @click="move(index, -1)"
          >
            ↑
          </Button>
          <Button
            type="button"
            variant="outline"
            class="min-h-11 min-w-11"
            :disabled="pending || index === draft.length - 1"
            :aria-label="`${texts.orderMoveDown}: ${nameFor(categoryId)}`"
            :data-testid="`order-down-${categoryId}`"
            @click="move(index, 1)"
          >
            ↓
          </Button>
          <Button
            type="button"
            variant="ghost"
            class="min-h-11"
            :disabled="pending"
            :aria-label="`${texts.orderRemove}: ${nameFor(categoryId)}`"
            :data-testid="`order-remove-${categoryId}`"
            @click="remove(categoryId)"
          >
            {{ common.remove }}
          </Button>
        </span>
      </li>
    </ol>

    <template v-if="available.length">
      <h4 class="text-sm font-medium">{{ texts.orderAvailable }}</h4>
      <ul class="flex flex-wrap gap-2" data-testid="order-available">
        <li v-for="category in available" :key="category.id" class="min-w-0 max-w-full">
          <Button
            type="button"
            variant="outline"
            class="min-h-11 max-w-full h-auto whitespace-normal text-left [overflow-wrap:anywhere]"
            :disabled="pending"
            :aria-label="`${texts.orderAdd}: ${category.name}`"
            :data-testid="`order-add-${category.id}`"
            @click="add(category.id)"
          >
            + {{ category.name }}
          </Button>
        </li>
      </ul>
    </template>

    <Button
      type="button"
      class="min-h-11 justify-self-start"
      :disabled="!isDirty || pending"
      data-testid="order-save"
      @click="emit('save', [...draft])"
    >
      {{ pending ? 'Zapisywanie…' : texts.orderSave }}
    </Button>
  </section>
</template>
