<script setup lang="ts">
/**
 * Wybór sklepu z create-in-context (05_FRONTEND §4, 06_UIUX §3.1).
 *
 * Kontrakt powtarza `ProductPicker` z prefiksem testid `store-picker-`, ale
 * różni się w dwóch miejscach, i te różnice są celowe:
 *
 * 1. **Sklepów jest kilka, nie tysiące** — lista przychodzi w całości jednym
 *    zapytaniem (`/stores` nie ma paginacji), a filtrowanie idzie po stronie
 *    klienta. Debounce byłby tu opóźnieniem bez powodu.
 * 2. **Sklep jest OPCJONALNY** (03_DATABASE §3): wariant retail bez sklepu to
 *    dozwolony stan, więc picker ma jawną pozycję „Bez sklepu" zamiast kazać
 *    użytkownikowi szukać sposobu na wyczyszczenie wyboru.
 *
 * Nowy sklep tworzy się bez opuszczania formularza: wpisana fraza staje się
 * nazwą, a po zapisie sklep jest od razu wybrany.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { Store } from '@/api/stores'
import { createStore, fetchStores } from '@/api/stores'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { common, storePicker as texts } from '@/lib/texts'

withDefaults(
  defineProps<{
    /** Wybrany sklep (kontrolowany przez rodzica) albo `null` = bez sklepu. */
    modelValue?: Store | null
    label?: string
    disabled?: boolean
  }>(),
  { modelValue: null, label: texts.label, disabled: false },
)

const emit = defineEmits<{
  (event: 'update:modelValue', store: Store | null): void
  (event: 'selected', store: Store): void
}>()

const queryClient = useQueryClient()

const search = ref('')
const open = ref(false)
const errorMessage = ref<string | null>(null)

const filters = computed(() => ({ include_archived: false }))
const stores = useQuery({
  queryKey: computed(() => queryKeys.stores.list(filters.value)),
  queryFn: () => fetchStores(filters.value),
})

const phrase = computed(() => search.value.trim())
const items = computed<Store[]>(() => {
  const all = stores.data.value?.items ?? []
  if (!phrase.value) {
    return all
  }
  const needle = phrase.value.toLocaleLowerCase('pl-PL')
  return all.filter((store) => store.name.toLocaleLowerCase('pl-PL').includes(needle))
})

/** „+ Dodaj sklep" pokazujemy dopiero, gdy wiemy, że takiego sklepu nie ma. */
const canCreate = computed(
  () =>
    phrase.value.length > 0 &&
    !stores.isFetching.value &&
    !items.value.some(
      (store) => store.name.toLocaleLowerCase('pl-PL') === phrase.value.toLocaleLowerCase('pl-PL'),
    ),
)

function choose(store: Store | null): void {
  emit('update:modelValue', store)
  if (store) {
    emit('selected', store)
  }
  search.value = ''
  open.value = false
  errorMessage.value = null
}

/** Id sklepu z `details.existing` odpowiedzi 409 (albo `null`). */
function existingStoreId(error: ApiError): number | null {
  const existing = error.details.existing
  if (error.status !== 409 || typeof existing !== 'object' || existing === null) {
    return null
  }
  const id = (existing as { id?: unknown }).id
  return typeof id === 'number' ? id : null
}

const create = useMutation({
  mutationFn: () => createStore({ name: phrase.value }),
  onSuccess: async (store) => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.stores.all })
    choose(store)
  },
  onError: async (error: unknown) => {
    if (!(error instanceof ApiError)) {
      errorMessage.value = common.unexpectedError
      return
    }
    errorMessage.value = error.message

    // 409 z `details.existing`: sklep już jest, więc wybieramy istniejący zamiast
    // zostawiać użytkownika z komunikatem o błędzie (06_UIUX §3.1). Dociągamy go
    // z API (także z archiwum) — nie składamy encji z okrawków odpowiedzi błędu.
    const id = existingStoreId(error)
    if (id === null) {
      return
    }
    const all = await fetchStores({ include_archived: true })
    const match = all.items.find((store) => store.id === id)
    if (match) {
      await queryClient.invalidateQueries({ queryKey: queryKeys.stores.all })
      choose(match)
    }
  },
})
</script>

<template>
  <div class="grid gap-2" data-testid="store-picker">
    <label class="text-sm font-medium" for="store-picker-input">{{ label }}</label>

    <!-- Stan „wybrany": pokazujemy wynik, nie puste pole wyszukiwania. -->
    <div
      v-if="modelValue && !open"
      class="border-border flex min-h-11 items-center justify-between gap-2 rounded-lg border px-3"
      data-testid="store-picker-selected"
    >
      <span class="min-w-0 truncate text-sm">{{ modelValue.name }}</span>
      <Button
        type="button"
        variant="ghost"
        class="min-h-11"
        :disabled="disabled"
        data-testid="store-picker-change"
        @click="open = true"
      >
        {{ texts.change }}
      </Button>
    </div>

    <template v-else>
      <Input
        id="store-picker-input"
        v-model="search"
        role="combobox"
        aria-expanded="true"
        aria-controls="store-picker-results"
        :placeholder="texts.placeholder"
        :disabled="disabled"
        class="min-h-11"
        data-testid="store-picker-input"
        @focus="open = true"
      />

      <ul
        id="store-picker-results"
        class="border-border grid gap-1 rounded-lg border p-1"
        role="listbox"
        data-testid="store-picker-results"
      >
        <li>
          <button
            type="button"
            class="hover:bg-muted text-muted-foreground flex min-h-11 w-full items-center rounded-lg px-2 text-left text-sm"
            data-testid="store-picker-none"
            @click="choose(null)"
          >
            {{ texts.none }}
          </button>
        </li>

        <li v-for="store in items" :key="store.id" role="option" :aria-selected="false">
          <button
            type="button"
            class="hover:bg-muted flex min-h-11 w-full items-center justify-between gap-2 rounded-lg px-2 text-left text-sm"
            :data-testid="`store-picker-option-${store.id}`"
            @click="choose(store)"
          >
            <span class="min-w-0 truncate">{{ store.name }}</span>
          </button>
        </li>

        <li v-if="canCreate" class="grid gap-1">
          <button
            type="button"
            class="text-primary hover:bg-muted min-h-11 rounded-lg px-2 text-left text-sm font-medium"
            :disabled="create.isPending.value"
            data-testid="store-picker-create"
            @click="create.mutate()"
          >
            {{ texts.createPrefix }} „{{ phrase }}”
          </button>
        </li>
      </ul>
    </template>

    <p
      v-if="errorMessage"
      class="text-destructive text-sm"
      role="alert"
      data-testid="store-picker-error"
    >
      {{ errorMessage }}
    </p>
  </div>
</template>
