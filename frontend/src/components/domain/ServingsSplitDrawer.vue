<script setup lang="ts">
/**
 * Rozkład rodzinny pozycji planu — kto ile porcji zjada (02_DOMAIN §7).
 *
 * Suma mnożników MUSI równać się liczbie porcji pozycji; walidacja serwera jest
 * prawdą (422), a tutaj liczymy ją na żywo, żeby użytkownik nie zapisywał
 * czegoś, co i tak zostanie odrzucone (05_FRONTEND §5).
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
import {
  decimalsEqual,
  isValidDecimal,
  normalizeDecimalInput,
  sumDecimals,
  toDecimalInput,
} from '@/lib/decimal'
import { formatDecimal } from '@/lib/format'
import { common, plan as texts } from '@/lib/texts'

const props = defineProps<{
  open: boolean
  profiles: MemberProfile[]
  /** Aktualny rozkład pozycji (pusty = pozycja bez rozkładu). */
  split: PlanServingSplit[]
  /** Liczba porcji pozycji jako string dziesiętny — cel sumy. */
  servings: string
  pending?: boolean
}>()

const emit = defineEmits<{
  (event: 'apply', split: PlanServingSplitInput[], servings: string): void
  (event: 'clear'): void
  (event: 'close'): void
}>()

/** Wpisy formularza: profil → tekst mnożnika (pusty = osoba nie je tej pozycji). */
const draft = ref<Record<number, string>>({})

function reset(): void {
  const current = new Map(props.split.map((row) => [row.member_profile_id, row.multiplier]))
  const next: Record<number, string> = {}
  for (const profile of props.profiles) {
    const existing = current.get(profile.id)
    // Bez rozkładu proponujemy domyślny mnożnik profilu (B03), nie pustkę.
    next[profile.id] = toDecimalInput(existing ?? profile.default_multiplier)
  }
  draft.value = next
}

watch(() => [props.open, props.split, props.profiles], reset, { immediate: true, deep: true })

interface DraftRow {
  profile: MemberProfile
  value: string
  valid: boolean
}

const rows = computed<DraftRow[]>(() =>
  props.profiles.map((profile) => {
    const value = draft.value[profile.id] ?? ''
    return {
      profile,
      value,
      valid: value.trim() === '' || isValidDecimal(value, { decimalPlaces: 2, positive: true }),
    }
  }),
)

const entries = computed(() =>
  rows.value
    .filter((row) => row.valid && row.value.trim() !== '')
    .map((row) => ({
      member_profile_id: row.profile.id,
      multiplier: normalizeDecimalInput(row.value),
    })),
)

const total = computed(() => sumDecimals(entries.value.map((entry) => entry.multiplier)))
const matches = computed(() => decimalsEqual(total.value, props.servings))
const canApply = computed(
  () => rows.value.every((row) => row.valid) && entries.value.length > 0 && matches.value,
)

/** „Dopasuj porcje do sumy": ustawiamy servings pozycji na sumę rozkładu. */
function applyWithSum(): void {
  emit('apply', entries.value, total.value)
}
</script>

<template>
  <section
    v-if="open"
    class="border-border bg-card grid gap-3 rounded-xl border p-3"
    data-testid="servings-split-drawer"
  >
    <header class="grid gap-1">
      <h3 class="text-sm font-medium">{{ texts.splitTitle }}</h3>
      <p class="text-muted-foreground text-xs">{{ texts.splitSubtitle }}</p>
    </header>

    <p
      v-if="profiles.length === 0"
      class="text-muted-foreground text-sm"
      data-testid="split-no-profiles"
    >
      {{ texts.splitEmptyProfiles }}
    </p>

    <ul v-else class="grid gap-2">
      <li
        v-for="row in rows"
        :key="row.profile.id"
        class="grid grid-cols-[1fr_7rem] items-center gap-2"
      >
        <label class="truncate text-sm" :for="`split-${row.profile.id}`">
          {{ row.profile.name }}
        </label>
        <Input
          :id="`split-${row.profile.id}`"
          v-model="draft[row.profile.id]"
          inputmode="decimal"
          class="min-h-11 tabular-nums"
          :aria-invalid="!row.valid"
          :data-testid="`split-input-${row.profile.id}`"
        />
      </li>
    </ul>

    <p class="text-sm tabular-nums" data-testid="split-total">
      {{ texts.splitSum }}: <strong>{{ formatDecimal(total) }}</strong>
      <span aria-hidden="true"> · </span>
      {{ texts.splitTarget }}: {{ formatDecimal(servings) }}
    </p>

    <p v-if="!matches" class="text-warning text-sm" role="alert" data-testid="split-mismatch">
      {{ texts.splitMismatch }}
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
        data-testid="split-cancel"
        @click="emit('close')"
      >
        {{ common.cancel }}
      </Button>
    </div>
  </section>
</template>
