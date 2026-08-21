<script setup lang="ts">
/**
 * Sekcja „Tury zakupów" na stronie Zakupy (karta B10 §Frontend).
 *
 * Tury to KONFIGURACJA, nie wynik: lista, edycja inline, kolejność strzałkami
 * (bez DnD — tur jest kilka, a strzałki działają też na telefonie i z klawiatury,
 * 06_UIUX §2). Preset niedziela/środa zasiewa backend przy pierwszym GET, więc
 * ta sekcja nigdy nie jest pusta przy pierwszym wejściu — pusty stan zobaczy
 * dopiero ten, kto usunie wszystkie tury.
 *
 * Stan serwera trzyma TanStack Query; w komponencie żyje tylko szkic formularza.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, reactive, ref } from 'vue'

import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { RoundConfig, RoundMode } from '@/api/shopping'
import {
  createRoundConfig,
  deleteRoundConfig,
  fetchRoundConfigs,
  updateRoundConfig,
} from '@/api/shopping'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { common, shopping as texts } from '@/lib/texts'

/** 0 = poniedziałek, jak `date.weekday()` w Pythonie (kontrakt API). */
const WEEKDAYS = [
  'poniedziałek',
  'wtorek',
  'środa',
  'czwartek',
  'piątek',
  'sobota',
  'niedziela',
] as const

const MODE_LABELS: Record<RoundMode, string> = {
  all: texts.roundModeAll,
  durable_plus_fresh_window: texts.roundModeDurablePlusFresh,
  fresh_only: texts.roundModeFreshOnly,
}

const queryClient = useQueryClient()
const actionError = ref<string | null>(null)

/**
 * Flagi czyszczenia kolumn NULLABLE w PATCH-u. Kontrakt wymaga ich zawsze
 * (mają wartość domyślną po stronie API, ale w typach są obowiązkowe), a `null`
 * w PATCH-u nie odróżniłby „wyczyść" od „nie zmieniaj".
 */
const noClears = { clear_shopping_weekday: false, clear_fresh_days: false } as const

const configs = useQuery({
  queryKey: queryKeys.shopping.roundConfigs,
  queryFn: fetchRoundConfigs,
})
const items = computed(() => configs.data.value?.items ?? [])

const draft = reactive({
  id: null as number | null,
  name: '',
  mode: 'durable_plus_fresh_window' as RoundMode,
  coversDays: '7',
  freshDays: '4',
  weekday: '' as string,
})
const formOpen = ref(false)

const formValid = computed(
  () => draft.name.trim().length > 0 && Number.parseInt(draft.coversDays, 10) > 0,
)
const needsFreshWindow = computed(() => draft.mode === 'durable_plus_fresh_window')

function reportError(error: unknown): void {
  actionError.value = error instanceof ApiError ? error.message : common.unexpectedError
}

async function refresh(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: queryKeys.shopping.all })
}

function openCreate(): void {
  draft.id = null
  draft.name = ''
  draft.mode = 'durable_plus_fresh_window'
  draft.coversDays = '7'
  draft.freshDays = '4'
  draft.weekday = ''
  actionError.value = null
  formOpen.value = true
}

function openEdit(config: RoundConfig): void {
  draft.id = config.id
  draft.name = config.name
  draft.mode = config.mode
  draft.coversDays = String(config.covers_days)
  draft.freshDays = config.fresh_days === null ? '' : String(config.fresh_days)
  draft.weekday = config.shopping_weekday === null ? '' : String(config.shopping_weekday)
  actionError.value = null
  formOpen.value = true
}

const save = useMutation({
  mutationFn: () => {
    const coversDays = Number.parseInt(draft.coversDays, 10)
    const freshDays =
      needsFreshWindow.value && draft.freshDays.trim() !== ''
        ? Number.parseInt(draft.freshDays, 10)
        : null
    const weekday = draft.weekday === '' ? null : Number.parseInt(draft.weekday, 10)
    if (draft.id !== null) {
      return updateRoundConfig(draft.id, {
        name: draft.name.trim(),
        mode: draft.mode,
        covers_days: coversDays,
        // Kolumny NULLABLE czyścimy flagą, nie `null`-em (kontrakt PATCH).
        fresh_days: freshDays ?? undefined,
        clear_fresh_days: freshDays === null,
        shopping_weekday: weekday ?? undefined,
        clear_shopping_weekday: weekday === null,
      })
    }
    return createRoundConfig({
      name: draft.name.trim(),
      mode: draft.mode,
      covers_days: coversDays,
      fresh_days: freshDays,
      shopping_weekday: weekday,
    })
  },
  onSuccess: async () => {
    formOpen.value = false
    actionError.value = null
    await refresh()
  },
  onError: reportError,
})

const remove = useMutation({
  mutationFn: (config: RoundConfig) => deleteRoundConfig(config.id),
  onSuccess: refresh,
  onError: reportError,
})

const move = useMutation({
  mutationFn: async ({ config, delta }: { config: RoundConfig; delta: number }) => {
    const ordered = [...items.value]
    const index = ordered.findIndex((row) => row.id === config.id)
    const neighbour = ordered[index + delta]
    if (index < 0 || neighbour === undefined) {
      return
    }
    // Zamiana pozycji dwóch tur: `position` steruje kolejnością liczenia okien
    // w silniku, więc kolejność na ekranie MUSI być tą samą kolejnością w bazie.
    await updateRoundConfig(config.id, { ...noClears, position: index + delta })
    await updateRoundConfig(neighbour.id, { ...noClears, position: index })
  },
  onSuccess: refresh,
  onError: reportError,
})

function confirmRemove(config: RoundConfig): void {
  if (window.confirm(texts.confirmRoundDelete)) {
    remove.mutate(config)
  }
}

function weekdayLabel(config: RoundConfig): string {
  if (config.shopping_weekday === null) {
    return texts.roundWeekdayAny
  }
  return WEEKDAYS[config.shopping_weekday] ?? texts.roundWeekdayAny
}
</script>

<template>
  <Card class="rounded-xl" data-testid="round-configs">
    <CardHeader>
      <CardTitle>{{ texts.roundsTitle }}</CardTitle>
      <CardDescription>{{ texts.roundsSubtitle }}</CardDescription>
    </CardHeader>

    <CardContent class="grid gap-4">
      <p v-if="configs.isPending.value" class="text-muted-foreground text-sm">
        {{ common.loading }}
      </p>
      <p
        v-else-if="items.length === 0"
        class="text-muted-foreground text-sm"
        data-testid="round-configs-empty"
      >
        {{ texts.roundsEmpty }}
      </p>

      <ul v-else class="grid gap-2" data-testid="round-configs-list">
        <li
          v-for="(config, index) in items"
          :key="config.id"
          class="border-border flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2"
          :data-testid="`round-config-${config.id}`"
        >
          <div class="grid gap-0.5">
            <span class="font-medium">{{ config.name }}</span>
            <span class="text-muted-foreground text-xs">
              {{ weekdayLabel(config) }} · {{ MODE_LABELS[config.mode] }} ·
              {{ texts.roundDays(config.covers_days) }}
              <template v-if="config.fresh_days !== null">
                · {{ texts.roundFreshDays }}: {{ config.fresh_days }}
              </template>
            </span>
          </div>

          <div class="flex flex-wrap items-center gap-1">
            <Button
              variant="outline"
              class="min-h-11"
              :aria-label="texts.roundMoveUp"
              :disabled="index === 0 || move.isPending.value"
              :data-testid="`round-up-${config.id}`"
              @click="move.mutate({ config, delta: -1 })"
            >
              ↑
            </Button>
            <Button
              variant="outline"
              class="min-h-11"
              :aria-label="texts.roundMoveDown"
              :disabled="index === items.length - 1 || move.isPending.value"
              :data-testid="`round-down-${config.id}`"
              @click="move.mutate({ config, delta: 1 })"
            >
              ↓
            </Button>
            <Button
              variant="outline"
              class="min-h-11"
              :data-testid="`round-edit-${config.id}`"
              @click="openEdit(config)"
            >
              {{ common.edit }}
            </Button>
            <Button
              variant="outline"
              class="min-h-11"
              :data-testid="`round-remove-${config.id}`"
              @click="confirmRemove(config)"
            >
              {{ common.remove }}
            </Button>
          </div>
        </li>
      </ul>

      <div>
        <Button class="min-h-11" data-testid="round-add" @click="openCreate()">
          + {{ texts.addRound }}
        </Button>
      </div>

      <div
        v-if="formOpen"
        class="border-border grid gap-3 rounded-lg border p-3 md:grid-cols-2"
        data-testid="round-form"
      >
        <label class="grid gap-1 text-sm">
          {{ texts.roundName }}
          <Input v-model="draft.name" class="min-h-11" data-testid="round-name" />
        </label>

        <label class="grid gap-1 text-sm">
          {{ texts.roundMode }}
          <select
            v-model="draft.mode"
            class="border-border bg-card min-h-11 rounded-lg border px-3 text-sm"
            data-testid="round-mode"
          >
            <option value="all">{{ texts.roundModeAll }}</option>
            <option value="durable_plus_fresh_window">
              {{ texts.roundModeDurablePlusFresh }}
            </option>
            <option value="fresh_only">{{ texts.roundModeFreshOnly }}</option>
          </select>
        </label>

        <label class="grid gap-1 text-sm">
          {{ texts.roundWeekday }}
          <select
            v-model="draft.weekday"
            class="border-border bg-card min-h-11 rounded-lg border px-3 text-sm"
            data-testid="round-weekday"
          >
            <option value="">{{ texts.roundWeekdayAny }}</option>
            <option v-for="(label, index) in WEEKDAYS" :key="label" :value="String(index)">
              {{ label }}
            </option>
          </select>
        </label>

        <label class="grid gap-1 text-sm">
          {{ texts.roundCoversDays }}
          <Input
            v-model="draft.coversDays"
            type="number"
            min="1"
            max="366"
            class="min-h-11"
            data-testid="round-covers-days"
          />
        </label>

        <label v-if="needsFreshWindow" class="grid gap-1 text-sm">
          {{ texts.roundFreshDays }}
          <Input
            v-model="draft.freshDays"
            type="number"
            min="1"
            max="366"
            class="min-h-11"
            data-testid="round-fresh-days"
          />
        </label>

        <div class="flex flex-wrap items-end gap-2 md:col-span-2">
          <Button
            class="min-h-11"
            :disabled="!formValid || save.isPending.value"
            data-testid="round-submit"
            @click="save.mutate()"
          >
            {{ save.isPending.value ? common.loading : common.save }}
          </Button>
          <Button
            variant="outline"
            class="min-h-11"
            data-testid="round-cancel"
            @click="formOpen = false"
          >
            {{ common.cancel }}
          </Button>
        </div>
      </div>

      <p v-if="actionError" class="text-destructive text-sm" role="alert" data-testid="round-error">
        {{ actionError }}
      </p>
    </CardContent>
  </Card>
</template>
