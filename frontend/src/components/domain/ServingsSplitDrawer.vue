<script setup lang="ts">
/**
 * Rozkład rodzinny pozycji planu — kto ile porcji zjada (02_DOMAIN §7).
 *
 * Suma mnożników MUSI równać się liczbie porcji pozycji; walidacja serwera jest
 * prawdą (422), a formularz zapisuje jednocześnie podział i jego sumę jako
 * servings. Nie wymaga ręcznego dopasowania drugiej liczby (UX03).
 *
 * Suma liczona jest na stringach dziesiętnych przez `sumDecimals` — nie przez
 * `Number`, bo 1,1 + 1,1 + 1,1 na floatach nie równa się 3,3 (ADR-008).
 *
 * Domyślne mnożniki biorą się z `default_multiplier` profili (B03): otwarcie
 * drawera na pozycji bez rozkładu od razu proponuje sensowny podział.
 */
import { computed, ref, watch } from 'vue'

import type { MemberProfile } from '@/api/households'
import type { PlanServingSplit, PlanServingSplitInput } from '@/api/planning'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { sumDecimals } from '@/lib/decimal'
import { portionRows, portionSplit, validPortion, type PortionRow } from './planning/portions'
import { formatDecimal } from '@/lib/format'
import { common, plan as texts } from '@/lib/texts'

const props = defineProps<{
  open: boolean
  profiles: MemberProfile[]
  /** Aktualny rozkład pozycji (pusty = pozycja bez rozkładu). */
  split: PlanServingSplit[]
  /** Poprzednia liczba porcji pozycji jako string dziesiętny. */
  servings: string
  pending?: boolean
  profilesError?: boolean
  profilesPending?: boolean
}>()

const emit = defineEmits<{
  (event: 'apply', split: PlanServingSplitInput[], servings: string): void
  (event: 'clear'): void
  (event: 'close'): void
  (event: 'retry'): void
}>()

/** Wpisy formularza: profil → tekst mnożnika (pusty = osoba nie je tej pozycji). */
const rows = ref<PortionRow[]>([])
const dirty = ref(false)

function reset(): void {
  rows.value = portionRows(props.profiles, props.split)
  dirty.value = false
}

watch(
  () => props.open,
  (open) => {
    if (open) reset()
  },
  { immediate: true },
)
watch(
  () => [props.split, props.profiles],
  () => {
    if (!dirty.value) reset()
  },
  { deep: true },
)

const entries = computed(() => portionSplit(rows.value))
const total = computed(() =>
  entries.value === null ? null : sumDecimals(entries.value.map((entry) => entry.multiplier)),
)
const canApply = computed(
  () =>
    !props.profilesError &&
    !props.profilesPending &&
    entries.value !== null &&
    entries.value.length > 0 &&
    entries.value.length <= 20 &&
    total.value !== null &&
    validPortion(total.value, '9999.99'),
)

/** Porcje pozycji są zawsze sumą poprawnych wpisów rozkładu. */
function applyWithSum(): void {
  if (canApply.value && entries.value && total.value) emit('apply', entries.value, total.value)
}
</script>

<template>
  <section
    v-if="open"
    class="border-border bg-card grid gap-3 rounded-xl border p-3"
    data-testid="servings-split-drawer"
    @input="dirty = true"
  >
    <header class="grid gap-1">
      <h3 class="text-sm font-medium">{{ texts.splitTitle }}</h3>
      <p class="text-muted-foreground text-xs">
        Porcje sumują się automatycznie. 0 lub puste pole oznacza, że osoba nie je tego dania.
      </p>
    </header>

    <p
      v-if="!profilesError && !profilesPending && rows.length === 0"
      class="text-muted-foreground text-sm"
      data-testid="split-no-profiles"
    >
      {{ texts.splitEmptyProfiles }}
    </p>

    <div v-if="profilesError" class="grid gap-2" data-testid="split-profiles-error">
      <p role="alert" class="text-destructive text-sm">
        Nie udało się pobrać profili. Ponów ich pobieranie, aby zapisać podział.
      </p>
      <Button
        type="button"
        variant="outline"
        class="justify-self-start"
        :disabled="pending || profilesPending"
        data-testid="split-profiles-retry"
        @click="emit('retry')"
        >Ponów pobieranie profili</Button
      >
    </div>
    <p
      v-if="profilesPending"
      role="status"
      class="text-muted-foreground text-sm"
      data-testid="split-profiles-loading"
    >
      Pobieranie profili…
    </p>
    <ul v-if="rows.length" class="grid gap-2">
      <li v-for="row in rows" :key="row.id" class="grid grid-cols-[1fr_7rem] items-center gap-2">
        <label class="text-sm break-words" :for="`split-${row.id}`">
          {{ row.name }} <span v-if="!row.active">(historyczny / nieaktywny)</span>
        </label>
        <Input
          :id="`split-${row.id}`"
          v-model="row.value"
          :disabled="pending"
          inputmode="decimal"
          class="min-h-11 tabular-nums"
          :aria-invalid="row.value !== '' && !validPortion(row.value, '99.99', true)"
          :data-testid="`split-input-${row.id}`"
        />
      </li>
    </ul>

    <p class="text-sm tabular-nums" data-testid="split-total">
      {{ texts.splitSum }}: <strong>{{ total === null ? '—' : formatDecimal(total) }}</strong>
      <span aria-hidden="true"> · </span>
      Poprzednio: {{ formatDecimal(servings) }}
    </p>

    <p
      v-if="!canApply && rows.length"
      class="text-warning text-sm"
      role="alert"
      data-testid="split-mismatch"
    >
      Podaj dodatni podział, do 99,99 na osobę i maksymalnie 20 osób.
    </p>

    <div class="flex flex-wrap gap-2">
      <Button
        type="button"
        class="min-h-11"
        :disabled="!canApply || pending"
        data-testid="split-apply"
        @click="applyWithSum()"
      >
        {{ texts.splitApply }}
      </Button>
      <Button
        v-if="split.length > 0"
        type="button"
        variant="outline"
        class="min-h-11"
        :disabled="pending"
        data-testid="split-clear"
        @click="emit('clear')"
      >
        {{ texts.splitClear }}
      </Button>
      <Button
        type="button"
        variant="ghost"
        class="min-h-11"
        :disabled="pending"
        data-testid="split-cancel"
        @click="emit('close')"
      >
        {{ common.cancel }}
      </Button>
    </div>
  </section>
</template>
