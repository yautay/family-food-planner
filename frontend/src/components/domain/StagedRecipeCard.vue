<script setup lang="ts">
/**
 * Karta jednego dania w review importu.
 *
 * Zawiera to, co człowiek musi rozstrzygnąć przy TYM daniu: nazwę (3 ze 103 są
 * ucięte przez zawijanie kolumn — errata 01_PDF_AUDIT §9.5), liczbę porcji
 * (`multi_portion_suspect`), decyzję „utwórz / scal / pomiń", mapowania
 * składników i uwagi.
 *
 * **Kalorie pokazujemy PER POSIŁEK.** `pdf_kcal` w jadłospisie opisuje posiłek,
 * a posiłek bywa dwudaniowy (errata §9.1) — dlatego obie liczby stoją przy
 * karcie z etykietą posiłku, a nie udają wartości pojedynczego dania.
 */
import { computed } from 'vue'

import type { RecipeSummary } from '@/api/recipes'
import type { StagedRecipeRead, StagedRecipeResolution } from '@/api/pdfImport'
import RecipePicker from '@/components/domain/RecipePicker.vue'
import StagedIngredientRow from '@/components/domain/StagedIngredientRow.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { importReview as texts } from '@/lib/texts'

const props = defineProps<{
  recipe: StagedRecipeRead
  disabled?: boolean
}>()

const emit = defineEmits<{
  (event: 'rename', payload: { id: number; name: string }): void
  (event: 'servings', payload: { id: number; servings: number }): void
  (event: 'resolution', payload: { id: number; resolution: StagedRecipeResolution }): void
  (event: 'merge-target', payload: { id: number; recipeId: number }): void
  (event: 'confirm', payload: { ingredientId: number; productId: number }): void
  (event: 'create-new', ingredientId: number): void
  (event: 'clear', ingredientId: number): void
  (event: 'resolve-issue', payload: { issueId: number; resolution: string }): void
}>()

const dish = computed(() => props.recipe)
const issues = computed(() => dish.value.issues ?? [])
const openIssues = computed(() => issues.value.filter((issue) => issue.resolved_at === null))

/** Czy danie prosi o liczbę porcji (blocker `multi_portion_suspect`). */
const needsServings = computed(() =>
  openIssues.value.some((issue) => issue.kind === 'multi_portion_suspect'),
)

/** Podpowiedź AI leży w `details` uwagi — NIGDY w polu porcji (ADR-011). */
const servingsHint = computed<number | null>(() => {
  const issue = openIssues.value.find((item) => item.kind === 'multi_portion_suspect')
  const value = issue?.details?.['propozycja_ai_porcje']
  return typeof value === 'number' ? value : null
})

const duplicateIssue = computed(() =>
  openIssues.value.find((issue) => issue.kind === 'duplicate_recipe'),
)

const hasKcalMismatch = computed(() =>
  openIssues.value.some((issue) => issue.kind === 'kcal_mismatch'),
)

const resolution = computed<StagedRecipeResolution>(() => dish.value.resolution ?? 'create')

const mergeTarget = computed<RecipeSummary | null>(() =>
  dish.value.target_recipe_id === null
    ? null
    : ({ id: dish.value.target_recipe_id, name: '' } as RecipeSummary),
)

function onName(event: Event): void {
  const value = (event.target as HTMLInputElement).value.trim()
  if (value && value !== dish.value.name) emit('rename', { id: dish.value.id, name: value })
}

function onServings(event: Event): void {
  const value = Number.parseInt((event.target as HTMLInputElement).value, 10)
  if (Number.isFinite(value) && value >= 1) emit('servings', { id: dish.value.id, servings: value })
}

function issueLabel(kind: string): string {
  return texts.issueKind[kind as keyof typeof texts.issueKind] ?? kind
}
</script>

<template>
  <article
    class="border-border grid gap-4 rounded-xl border p-4"
    :class="resolution === 'skip' ? 'opacity-60' : ''"
    data-testid="staged-recipe"
  >
    <header class="grid gap-2">
      <label class="grid gap-1">
        <span class="text-muted-foreground text-xs">{{ texts.nameLabel }}</span>
        <Input
          :model-value="dish.name"
          class="min-h-11"
          :disabled="disabled"
          :data-testid="`staged-recipe-name-${dish.id}`"
          @change="onName"
        />
      </label>

      <div class="flex flex-wrap items-center gap-2 text-sm">
        <span class="bg-muted text-muted-foreground rounded-full px-3 py-1 text-xs">
          {{ dish.day_label }} · {{ dish.meal_label }}
        </span>
        <span
          v-if="hasKcalMismatch"
          class="bg-destructive/10 text-destructive rounded-full px-3 py-1 text-xs font-medium"
          data-testid="staged-recipe-kcal-badge"
        >
          {{ texts.kcalMismatchBadge }}
        </span>
      </div>

      <dl class="text-sm" data-testid="staged-recipe-kcal">
        <div class="flex flex-wrap gap-x-4 gap-y-1">
          <div>
            <dt class="text-muted-foreground text-xs">{{ texts.kcalPdf }}</dt>
            <dd>{{ dish.meal.pdf_kcal ?? '—' }} kcal</dd>
          </div>
          <div>
            <dt class="text-muted-foreground text-xs">{{ texts.kcalComputed }}</dt>
            <dd>
              <template v-if="dish.meal.computed_kcal">
                {{ dish.meal.computed_kcal }} kcal
                <span v-if="dish.meal.delta_pct" class="text-muted-foreground text-xs">
                  ({{ texts.kcalDelta }} {{ dish.meal.delta_pct }}%)
                </span>
              </template>
              <span v-else class="text-muted-foreground">{{ dish.meal.reason || '—' }}</span>
            </dd>
          </div>
        </div>
      </dl>
    </header>

    <section v-if="needsServings" class="bg-muted/40 grid gap-1 rounded-lg p-3">
      <label class="grid gap-1">
        <span class="text-sm font-medium">{{ texts.servingsLabel }}</span>
        <Input
          type="number"
          min="1"
          max="100"
          :model-value="dish.resolved_servings ?? ''"
          class="min-h-11 max-w-32"
          :disabled="disabled"
          :data-testid="`staged-recipe-servings-${dish.id}`"
          @change="onServings"
        />
      </label>
      <p class="text-muted-foreground text-xs">{{ texts.servingsHint }}</p>
      <p v-if="servingsHint !== null" class="text-primary text-xs" data-testid="servings-ai-hint">
        {{ texts.servingsAiHint }}: {{ servingsHint }}
      </p>
    </section>

    <p
      v-else-if="dish.declared_servings"
      class="text-muted-foreground text-sm"
      :data-testid="`staged-recipe-declared-${dish.id}`"
    >
      {{ texts.servingsLabel }} {{ dish.resolved_servings ?? dish.declared_servings }}
      <span class="text-xs">({{ texts.servingsFromPdf }})</span>
    </p>

    <section class="grid gap-2">
      <span class="text-muted-foreground text-xs">{{ texts.resolutionLabel }}</span>
      <div class="flex flex-wrap gap-2">
        <Button
          v-for="option in ['create', 'merge_into_existing', 'skip'] as const"
          :key="option"
          type="button"
          class="min-h-11"
          :variant="resolution === option ? 'default' : 'outline'"
          :disabled="disabled"
          :data-testid="`staged-recipe-resolution-${option}-${dish.id}`"
          @click="emit('resolution', { id: dish.id, resolution: option })"
        >
          {{
            option === 'create'
              ? texts.resolutionCreate
              : option === 'merge_into_existing'
                ? texts.resolutionMerge
                : texts.resolutionSkip
          }}
        </Button>
      </div>

      <div v-if="resolution === 'merge_into_existing'" class="max-w-md">
        <RecipePicker
          :model-value="mergeTarget"
          :label="texts.mergeTargetLabel"
          :disabled="disabled"
          @selected="emit('merge-target', { id: dish.id, recipeId: $event.id })"
        />
      </div>
    </section>

    <section
      v-if="duplicateIssue"
      class="bg-muted/40 grid gap-2 rounded-lg p-3"
      data-testid="staged-recipe-duplicate"
    >
      <p class="text-sm font-medium">{{ texts.duplicateTitle }}</p>
      <p class="text-sm">„{{ duplicateIssue.details?.['przepis_nazwa'] }}”</p>
      <div class="flex flex-wrap gap-2">
        <Button
          type="button"
          class="min-h-11"
          :disabled="disabled"
          :data-testid="`staged-recipe-merge-duplicate-${dish.id}`"
          @click="
            emit('merge-target', {
              id: dish.id,
              recipeId: Number(duplicateIssue.details?.['przepis_id']),
            })
          "
        >
          {{ texts.resolutionMerge }}
        </Button>
        <Button
          type="button"
          variant="outline"
          class="min-h-11"
          :disabled="disabled"
          :data-testid="`staged-recipe-duplicate-separate-${dish.id}`"
          @click="
            emit('resolve-issue', {
              issueId: duplicateIssue.id,
              resolution: texts.duplicateSeparate,
            })
          "
        >
          {{ texts.duplicateSeparate }}
        </Button>
      </div>
    </section>

    <section v-if="openIssues.length" class="grid gap-1">
      <h3 class="text-xs font-semibold">{{ texts.issuesTitle }}</h3>
      <ul class="grid gap-1 text-sm" data-testid="staged-recipe-issues">
        <li v-for="issue in openIssues" :key="issue.id" class="flex flex-wrap items-center gap-2">
          <span
            class="rounded-full px-2 py-0.5 text-xs"
            :class="
              issue.severity === 'blocker'
                ? 'bg-destructive/10 text-destructive'
                : 'bg-muted text-muted-foreground'
            "
          >
            {{ texts.severity[issue.severity] }}
          </span>
          <span>{{ issueLabel(issue.kind) }}</span>
          <span class="text-muted-foreground text-xs">{{ issue.details?.['powód'] }}</span>
        </li>
      </ul>
    </section>

    <section v-if="resolution !== 'skip'" class="grid gap-2">
      <h3 class="text-xs font-semibold">{{ texts.ingredientsTitle }}</h3>
      <ul class="grid gap-2">
        <StagedIngredientRow
          v-for="item in dish.ingredients ?? []"
          :key="item.id"
          :ingredient="item"
          :disabled="disabled"
          @confirm="emit('confirm', $event)"
          @create-new="emit('create-new', $event)"
          @clear="emit('clear', $event)"
        />
      </ul>
    </section>
  </article>
</template>
