<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ApiError } from '@/api/client'
import { fetchMyProfiles } from '@/api/households'
import { fetchPlanDays, planRecipe, updateItem } from '@/api/planning'
import type { PlanDay, PlanMeal, PlanItem } from '@/api/planning'
import { queryKeys } from '@/api/queryKeys'
import type { RecipeSummary } from '@/api/recipes'
import ActionPanel from '@/components/domain/ActionPanel.vue'
import RecipePicker from '@/components/domain/RecipePicker.vue'
import { Button } from '@/components/ui/button'
import { normalizeDecimalInput, sumDecimals, toDecimalInput } from '@/lib/decimal'
import { formatDecimal } from '@/lib/format'
import { validNavigationDate } from '@/lib/navigation'
import { portionRows, portionSplit, validPortion, type PortionRow } from './portions'

const props = defineProps<{
  open: boolean
  recipe: RecipeSummary | null
  date: string
  meal?: PlanMeal | null
  replaceItem?: PlanItem | null
}>()
const emit = defineEmits<{
  close: []
  saved: [result: { day: PlanDay; mealId: number; itemId: number; mode: 'add' | 'replace' }]
}>()
const client = useQueryClient()
const selectedDate = ref(props.date)
const selectedRecipe = ref<RecipeSummary | null>(null)
const mealId = ref('new')
const newMealName = ref('')
const family = ref(false)
const servings = ref('1')
const rows = ref<PortionRow[]>([])
const portionsChanged = ref(false)
const error = ref<string | null>(null)
const uncertain = ref(false)
const savedDate = ref('')
const replacing = computed(() => !!props.replaceItem)
const days = useQuery({
  queryKey: computed(() => queryKeys.planDays.range(selectedDate.value, selectedDate.value)),
  queryFn: () => fetchPlanDays(selectedDate.value, selectedDate.value),
  enabled: computed(() => props.open && !!validNavigationDate(selectedDate.value)),
  retry: false,
})
const profiles = useQuery({
  queryKey: queryKeys.households.profiles,
  queryFn: fetchMyProfiles,
  enabled: computed(() => props.open),
  retry: false,
})
const meals = computed(() => {
  const loaded = days.data.value?.items.find((day) => day.day === selectedDate.value)?.meals ?? []
  return props.meal &&
    selectedDate.value === props.date &&
    !loaded.some((m) => m.id === props.meal?.id)
    ? [props.meal, ...loaded]
    : loaded
})
const mealLabel = computed(() =>
  replacing.value
    ? props.meal?.name
    : mealId.value === 'new'
      ? newMealName.value.trim() || 'Nowy posiłek'
      : meals.value.find((meal) => String(meal.id) === mealId.value)?.name,
)

function reset(): void {
  selectedDate.value = props.date
  selectedRecipe.value = props.recipe
  mealId.value = props.meal ? String(props.meal.id) : 'new'
  newMealName.value = ''
  family.value = !!props.replaceItem?.servings_split.length
  servings.value = toDecimalInput(props.replaceItem?.servings ?? '1')
  rows.value = portionRows(
    profiles.data.value?.items ?? [],
    props.replaceItem?.servings_split ?? [],
  )
  portionsChanged.value = false
  error.value = null
  uncertain.value = false
}
watch(
  () => props.open,
  (open) => {
    if (open) reset()
  },
  { immediate: true },
)
watch(
  () => profiles.data.value,
  () => {
    if (!portionsChanged.value)
      rows.value = portionRows(
        profiles.data.value?.items ?? [],
        props.replaceItem?.servings_split ?? [],
      )
  },
)
watch(selectedDate, (value, previous) => {
  if (value !== previous && !replacing.value) mealId.value = 'new'
})

const split = computed(() => portionSplit(rows.value))
const total = computed(() =>
  split.value === null ? null : sumDecimals(split.value.map((row) => row.multiplier)),
)
const invalidContext = computed(
  () =>
    replacing.value &&
    (selectedDate.value !== props.date ||
      !props.meal ||
      !props.replaceItem?.recipe_id ||
      !props.meal.items.some((item) => item.id === props.replaceItem?.id)),
)
const validation = computed(() => {
  if (invalidContext.value) return 'Kontekst zamiany jest niespójny. Otwórz danie ponownie z planu.'
  if (!validNavigationDate(selectedDate.value)) return 'Wybierz poprawną datę.'
  if (!selectedRecipe.value) return 'Wybierz danie z przepisów.'
  if (!replacing.value && mealId.value === 'new' && !newMealName.value.trim())
    return 'Podaj nazwę nowego posiłku.'
  if (
    !replacing.value &&
    mealId.value !== 'new' &&
    !meals.value.some((meal) => String(meal.id) === mealId.value)
  )
    return 'Wybierz posiłek dla tej daty.'
  if (replacing.value && !portionsChanged.value) return null
  if (family.value) {
    if (profiles.isError.value && !profiles.data.value)
      return 'Nie udało się pobrać profili. Ponów odczyt albo wybierz samą liczbę porcji.'
    if (
      !split.value ||
      !total.value ||
      !validPortion(total.value, '9999.99') ||
      split.value.length > 20
    )
      return 'Podaj dodatni podział: do 99,99 porcji na osobę, maksymalnie 20 osób. 0 pomija osobę.'
  } else if (!validPortion(servings.value, '9999.99'))
    return 'Podaj liczbę porcji większą od 0, do 9999,99 (dwa miejsca po przecinku).'
  return null
})
const unknownDay = computed(
  () => !days.data.value && !(props.meal && selectedDate.value === props.date),
)
const mutation = useMutation({
  retry: false,
  mutationFn: async () => {
    if (validation.value || !selectedRecipe.value || uncertain.value)
      throw new Error('Niepoprawny formularz.')
    error.value = null
    const portions = {
      servings: family.value ? total.value! : normalizeDecimalInput(servings.value),
      servings_split: family.value ? split.value! : [],
    }
    savedDate.value = selectedDate.value
    if (props.replaceItem && props.meal) {
      const itemId = props.replaceItem.id
      const recipeId = selectedRecipe.value.id
      const day = await updateItem(itemId, {
        recipe_id: recipeId,
        ...(portionsChanged.value ? portions : {}),
      })
      const meal = day.meals.find((meal) => meal.id === props.meal?.id)
      if (
        day.day !== savedDate.value ||
        !meal?.items.some((item) => item.id === itemId && item.recipe_id === recipeId)
      ) {
        throw new Error('Nie udało się potwierdzić zamiany w odpowiedzi serwera.')
      }
      return { day, mealId: meal.id, itemId, mode: 'replace' as const }
    }
    const result = await planRecipe(savedDate.value, {
      recipe_id: selectedRecipe.value.id,
      ...portions,
      ...(mealId.value === 'new'
        ? { new_meal_name: newMealName.value.trim() }
        : { meal_id: Number(mealId.value) }),
    })
    if (
      result.day.day !== savedDate.value ||
      !result.day.meals.some(
        (meal) =>
          meal.id === result.meal_id &&
          meal.items.some(
            (item) => item.id === result.item_id && item.recipe_id === selectedRecipe.value?.id,
          ),
      )
    ) {
      throw new Error('Nie udało się potwierdzić zapisu w odpowiedzi serwera.')
    }
    return { day: result.day, mealId: result.meal_id, itemId: result.item_id, mode: 'add' as const }
  },
  onSuccess: async (result) => {
    // Cache pozostaje źródłem prawdy. Nie podmieniamy świeższej odpowiedzi odczytu starszą mutacją.
    await Promise.all([
      client.invalidateQueries({ queryKey: queryKeys.planDays.all }),
      client.invalidateQueries({ queryKey: queryKeys.stats.all }),
    ])
    emit('saved', result)
  },
  onError: async (reason: unknown) => {
    if (reason instanceof ApiError && reason.status >= 400 && reason.status < 500) {
      error.value = reason.message
      return
    }
    uncertain.value = true
    error.value =
      'Nie udało się potwierdzić zapisu. Sprawdzamy rzeczywisty plan. Nie wysyłamy zapisu ponownie; podobne danie nie potwierdza tej operacji.'
    await Promise.all([
      client.invalidateQueries({ queryKey: queryKeys.planDays.all }),
      client.invalidateQueries({ queryKey: queryKeys.stats.all }),
    ])
  },
})

function editPortions(): void {
  portionsChanged.value = true
}
function submit(): void {
  if (!mutation.isPending.value && !uncertain.value && !validation.value && !unknownDay.value)
    mutation.mutate()
}
</script>

<template>
  <ActionPanel
    :open="open"
    :title="replacing ? 'Zamień danie' : 'Zaplanuj danie'"
    :description="
      replacing
        ? 'Zamiana zachowa posiłek, kolejność i zapisane porcje. Możesz jawnie zmienić podział.'
        : 'Wybierz dzień, posiłek i porcje. Zapisz wszystko jednym potwierdzeniem.'
    "
    :submit-label="replacing ? 'Zamień danie' : 'Dodaj do planu'"
    :submit-disabled="unknownDay || uncertain"
    :pending="mutation.isPending.value"
    :error="error"
    :validation-message="validation"
    testid="recipe-planning"
    @close="emit('close')"
    @submit="submit"
  >
    <template #context>
      <p class="text-muted-foreground text-sm break-words" data-testid="planning-context">
        {{ selectedDate }} · {{ mealLabel }}
      </p>
      <p v-if="selectedRecipe" class="text-sm font-medium break-words">{{ selectedRecipe.name }}</p>
    </template>
    <template #default="{ formId }">
      <!-- Zerowe minimum ścieżki i elementów pozwala kontrolkom oraz fieldsetowi
           zmieścić się w scrollporcie modala także po fokusie błędu. -->
      <div class="grid min-w-0 max-w-full grid-cols-1 gap-4" data-testid="planning-fields">
        <label class="grid min-w-0 grid-cols-1 gap-2 text-sm font-medium"
          >Dzień
          <input
            v-model="selectedDate"
            :form="formId"
            type="date"
            required
            :disabled="replacing || uncertain"
            class="border-input bg-background min-h-11 w-full min-w-0 max-w-full rounded-md border px-3"
            data-testid="planning-date"
          />
        </label>
        <p v-if="days.isPending.value" role="status" class="text-muted-foreground text-sm">
          Pobieranie planu…
        </p>
        <div
          v-if="days.isError.value"
          role="alert"
          class="text-destructive grid min-w-0 grid-cols-1 gap-2 text-sm break-words"
          data-testid="planning-day-error"
        >
          {{
            days.data.value
              ? 'Nie udało się odświeżyć planu. Pokazujemy ostatnio pobrane dane.'
              : 'Nie udało się pobrać planu. Nie wiemy, czy ten dzień jest pusty.'
          }}
          <Button type="button" variant="outline" @click="days.refetch()"
            >Ponów odczyt planu</Button
          >
        </div>
        <template v-if="replacing"
          ><p class="min-w-0 text-sm break-words" data-testid="planning-fixed-meal">
            {{ meal?.name }} · {{ replaceItem?.recipe_name }}
          </p></template
        >
        <template v-else>
          <label class="grid min-w-0 grid-cols-1 gap-2 text-sm font-medium"
            >Posiłek
            <select
              v-model="mealId"
              :form="formId"
              class="border-input bg-background min-h-11 w-full min-w-0 max-w-full rounded-md border px-3"
              :disabled="unknownDay || uncertain"
              data-testid="planning-meal"
            >
              <option value="new">Nowy posiłek</option>
              <option v-for="entry in meals" :key="entry.id" :value="String(entry.id)">
                {{ entry.name }}
              </option>
            </select>
          </label>
          <label v-if="mealId === 'new'" class="grid min-w-0 grid-cols-1 gap-2 text-sm font-medium"
            >Nazwa nowego posiłku
            <input
              v-model="newMealName"
              :form="formId"
              required
              maxlength="100"
              :disabled="uncertain"
              class="border-input bg-background min-h-11 w-full min-w-0 max-w-full rounded-md border px-3"
              data-testid="planning-meal-name"
            />
          </label>
        </template>
        <RecipePicker v-model="selectedRecipe" :disabled="uncertain" />
        <p
          v-if="selectedRecipe && !selectedRecipe.nutrition.complete"
          class="text-warning min-w-0 text-sm break-words"
        >
          Niepełne wartości odżywcze: {{ selectedRecipe.nutrition.missing.join(', ') }}
        </p>
        <p
          v-if="profiles.isError.value"
          role="alert"
          class="text-destructive min-w-0 text-sm break-words"
          data-testid="planning-profiles-error"
        >
          Nie udało się {{ profiles.data.value ? 'odświeżyć' : 'pobrać' }} profili.
          <Button type="button" variant="outline" @click="profiles.refetch()">Ponów</Button>
        </p>
        <fieldset
          class="grid min-w-0 max-w-full grid-cols-1 gap-3"
          :disabled="uncertain"
          @input="editPortions"
          @change="editPortions"
        >
          <legend class="mb-2 font-medium">Porcje</legend>
          <label class="flex min-h-11 items-center gap-2 text-sm"
            ><input v-model="family" :form="formId" type="checkbox" data-testid="planning-family" />
            Podział na osoby</label
          >
          <template v-if="family">
            <p v-if="profiles.isPending.value" role="status" class="text-sm">Pobieranie profili…</p>
            <p
              v-if="profiles.isSuccess.value && rows.length === 0"
              class="text-muted-foreground text-sm"
              data-testid="planning-no-profiles"
            >
              Nie masz profili. Możesz zaplanować samą liczbę porcji.
            </p>
            <label
              v-for="row in rows"
              :key="row.id"
              class="grid min-w-0 grid-cols-[minmax(0,1fr)_6rem] items-center gap-3 text-sm"
            >
              <span class="min-w-0 break-words"
                >{{ row.name
                }}<span v-if="!row.active" class="text-muted-foreground">
                  (historyczny / nieaktywny)</span
                ></span
              >
              <input
                v-model="row.value"
                :form="formId"
                inputmode="decimal"
                :aria-invalid="row.value !== '' && !validPortion(row.value, '99.99', true)"
                class="border-input bg-background min-h-11 w-full min-w-0 max-w-full rounded-md border px-3 tabular-nums"
                :data-testid="`planning-split-${row.id}`"
              />
            </label>
            <p class="bg-muted rounded-md p-3 text-sm" data-testid="planning-total">
              Przygotujesz <strong>{{ total === null ? '—' : formatDecimal(total) }}</strong> porcji
              łącznie. 0 lub puste pole pomija osobę.
            </p>
          </template>
          <label v-else class="grid min-w-0 grid-cols-1 gap-2 text-sm font-medium"
            >Liczba porcji
            <input
              v-model="servings"
              :form="formId"
              inputmode="decimal"
              required
              class="border-input bg-background min-h-11 w-full min-w-0 max-w-full rounded-md border px-3 tabular-nums"
              data-testid="planning-servings"
            />
          </label>
        </fieldset>
        <div
          v-if="uncertain"
          class="border-border grid min-w-0 grid-cols-1 gap-2 rounded-md border p-3 text-sm break-words"
          data-testid="planning-uncertain"
        >
          <p>Rzeczywisty plan na {{ savedDate }}:</p>
          <p v-if="days.isFetching.value" role="status">Sprawdzanie…</p>
          <ul v-else-if="days.data.value">
            <li v-for="entry in days.data.value.items.flatMap((day) => day.meals)" :key="entry.id">
              {{ entry.name }}:
              {{ entry.items.map((item) => item.recipe_name ?? item.product_name).join(', ') }}
            </li>
          </ul>
          <p v-if="days.isSuccess.value && days.data.value?.items.length === 0">
            Odczyt nie zwrócił planu. Wynik żądania nadal nie jest potwierdzony.
          </p>
          <Button type="button" variant="outline" @click="days.refetch()"
            >Sprawdź plan ponownie</Button
          >
          <RouterLink
            :to="{ name: 'plan-dnia', params: { date: savedDate } }"
            class="text-primary inline-flex min-h-11 items-center underline"
            @click="emit('close')"
            >Otwórz rzeczywisty plan</RouterLink
          >
          <p>Szkic pozostaje w panelu. Przed nową próbą sprawdź plan i zamknij ten panel.</p>
        </div>
      </div>
    </template>
  </ActionPanel>
</template>
