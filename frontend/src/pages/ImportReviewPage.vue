<script setup lang="ts">
/**
 * Ekran review importu PDF (`/import/jobs/:id/review`, BATCH_16).
 *
 * Trzy decyzje, które kształtują ten plik:
 *
 * 1. **Zapis jest PRZYROSTOWY.** Każda akcja (potwierdzenie mapowania, liczba
 *    porcji, zmiana decyzji o daniu) wysyła jedno `POST /resolve` z JEDNĄ
 *    zmianą i przyjmuje w odpowiedzi CAŁY nowy stan review. Backend przelicza
 *    przy okazji uwagi pochodne (`unmapped_product`, `kcal_mismatch`), więc
 *    front nie ma czego liczyć samodzielnie — i nie ma jak się rozjechać.
 * 2. **Stan review to stan SERWERA** (ADR-007): mieszka w TanStack Query pod
 *    `queryKeys.import.staged(id)`, a odpowiedź mutacji wkładamy wprost do
 *    cache'u zamiast unieważniać — po co drugie żądanie o to samo.
 * 3. **Blokady przychodzą z serwera, nie z sumowania w UI.** `blockers`
 *    w odpowiedzi to dokładnie ta sama lista, którą `approve` odesłałby w 409,
 *    więc tooltip przy nieczynnym przycisku mówi prawdę, a nie przybliżenie.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

import { ApiError } from '@/api/client'
import type {
  ImportApproveResponse,
  ImportResolveRequest,
  ImportScope,
  StagedJobResponse,
  StagedRecipeResolution,
} from '@/api/pdfImport'
import {
  aiSuggest,
  approveJob,
  getStaged,
  groupByMeal,
  mappedCount,
  rejectJob,
  resolveJob,
} from '@/api/pdfImport'
import { queryKeys } from '@/api/queryKeys'
import StagedRecipeCard from '@/components/domain/StagedRecipeCard.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuthStore } from '@/stores/auth'
import { common, importReview as texts, pdfImport as importTexts } from '@/lib/texts'

const route = useRoute()
const queryClient = useQueryClient()
const auth = useAuthStore()

const jobId = computed(() => Number(route.params.id))
const errorMessage = ref<string | null>(null)
const summary = ref<ImportApproveResponse | null>(null)
/** Domyślnie rodzina, gdy użytkownik ją ma — przepisy z diety są dla wszystkich. */
const scope = ref<ImportScope>(auth.user?.household ? 'household' : 'private')

const staged = useQuery({
  queryKey: computed(() => queryKeys.import.staged(jobId.value)),
  queryFn: () => getStaged(jobId.value),
})

function apply(next: StagedJobResponse): void {
  errorMessage.value = null
  queryClient.setQueryData(queryKeys.import.staged(jobId.value), next)
}

function onError(error: unknown): void {
  errorMessage.value = error instanceof ApiError ? error.message : common.unexpectedError
}

const resolve = useMutation({
  mutationFn: (payload: ImportResolveRequest) => resolveJob(jobId.value, payload),
  onSuccess: apply,
  onError,
})

const ai = useMutation({
  mutationFn: () => aiSuggest(jobId.value),
  onSuccess: apply,
  onError,
})

const approve = useMutation({
  mutationFn: () => approveJob(jobId.value, scope.value),
  onSuccess: async (result) => {
    errorMessage.value = null
    summary.value = result
    await queryClient.invalidateQueries({ queryKey: queryKeys.import.all })
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
    await queryClient.invalidateQueries({ queryKey: queryKeys.products.all })
  },
  onError,
})

const reject = useMutation({
  mutationFn: () => rejectJob(jobId.value),
  onSuccess: async () => {
    errorMessage.value = null
    await queryClient.invalidateQueries({ queryKey: queryKeys.import.all })
  },
  onError,
})

const job = computed<StagedJobResponse | null>(() => staged.data.value ?? null)
const groups = computed(() => (job.value ? groupByMeal(job.value) : []))
const progress = computed(() => (job.value ? mappedCount(job.value) : { mapped: 0, total: 0 }))
const blockers = computed(() => job.value?.blockers ?? [])
const openIssues = computed(
  () =>
    (job.value?.recipes ?? []).flatMap((recipe) =>
      (recipe.issues ?? []).filter((issue) => issue.resolved_at === null),
    ).length,
)
const busy = computed(
  () =>
    resolve.isPending.value ||
    ai.isPending.value ||
    approve.isPending.value ||
    reject.isPending.value,
)
/** Import rozstrzygnięty — ekran przechodzi w tryb podsumowania. */
const settled = computed(
  () => job.value?.job.status === 'approved' || job.value?.job.status === 'rejected',
)

function send(payload: ImportResolveRequest): void {
  resolve.mutate(payload)
}

function onRename(payload: { id: number; name: string }): void {
  send({ recipes: [{ staged_recipe_id: payload.id, name: payload.name }] })
}

function onServings(payload: { id: number; servings: number }): void {
  send({ recipes: [{ staged_recipe_id: payload.id, resolved_servings: payload.servings }] })
}

function onResolution(payload: { id: number; resolution: StagedRecipeResolution }): void {
  send({ recipes: [{ staged_recipe_id: payload.id, resolution: payload.resolution }] })
}

function onMergeTarget(payload: { id: number; recipeId: number }): void {
  send({
    recipes: [
      {
        staged_recipe_id: payload.id,
        resolution: 'merge_into_existing',
        target_recipe_id: payload.recipeId,
      },
    ],
  })
}

function onConfirm(payload: { ingredientId: number; productId: number }): void {
  send({
    ingredients: [
      {
        ingredient_id: payload.ingredientId,
        confirmed_product_id: payload.productId,
        create_new_product: false,
      },
    ],
  })
}

function onCreateNew(ingredientId: number): void {
  send({ ingredients: [{ ingredient_id: ingredientId, create_new_product: true }] })
}

function onClear(ingredientId: number): void {
  // Wyczyszczenie mapowania to `confirmed_product_id: null` + zdjęta flaga —
  // backend traktuje brak obu jako „jeszcze nie zdecydowano" i wraca blocker.
  send({
    ingredients: [
      { ingredient_id: ingredientId, confirmed_product_id: null, create_new_product: false },
    ],
  })
}

function onResolveIssue(payload: { issueId: number; resolution: string }): void {
  send({ issues: [{ issue_id: payload.issueId, resolution: payload.resolution }] })
}

function confirmReject(): void {
  if (window.confirm(texts.rejectConfirm)) reject.mutate()
}
</script>

<template>
  <section class="grid gap-6" data-testid="import-review-page">
    <header class="grid gap-2">
      <Button as-child variant="outline" class="min-h-11 justify-self-start">
        <RouterLink :to="{ name: 'import' }" data-testid="import-review-back">
          {{ texts.back }}
        </RouterLink>
      </Button>
      <h1 class="text-2xl font-semibold">{{ texts.title }}</h1>
      <p v-if="job" class="text-muted-foreground text-sm" data-testid="import-review-filename">
        {{ job.job.filename }}
      </p>
    </header>

    <p
      v-if="errorMessage"
      class="text-destructive text-sm"
      role="alert"
      data-testid="import-review-error"
    >
      {{ errorMessage }}
    </p>

    <p v-if="staged.isPending.value" class="text-muted-foreground text-sm">{{ common.loading }}</p>

    <!-- Podsumowanie po zatwierdzeniu — jedyny ekran, który mówi „gotowe". -->
    <Card v-else-if="summary" class="rounded-xl" data-testid="import-review-summary">
      <CardHeader>
        <CardTitle>{{ texts.doneTitle }}</CardTitle>
      </CardHeader>
      <CardContent class="grid gap-3">
        <dl class="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt class="text-muted-foreground text-xs">{{ texts.doneRecipes }}</dt>
            <dd data-testid="summary-recipes">{{ summary.created_recipe_ids?.length ?? 0 }}</dd>
          </div>
          <div>
            <dt class="text-muted-foreground text-xs">{{ texts.doneProducts }}</dt>
            <dd>{{ summary.created_product_ids?.length ?? 0 }}</dd>
          </div>
          <div>
            <dt class="text-muted-foreground text-xs">{{ texts.doneMerged }}</dt>
            <dd>{{ summary.merged_count }}</dd>
          </div>
          <div>
            <dt class="text-muted-foreground text-xs">{{ texts.doneSkipped }}</dt>
            <dd>{{ summary.skipped_count }}</dd>
          </div>
          <div>
            <dt class="text-muted-foreground text-xs">{{ texts.doneUnitWeights }}</dt>
            <dd>{{ summary.unit_weight_rows }}</dd>
          </div>
        </dl>
        <Button as-child class="min-h-11 justify-self-start">
          <RouterLink :to="{ name: 'przepisy' }" data-testid="summary-go-to-recipes">
            {{ texts.doneGoToRecipes }}
          </RouterLink>
        </Button>
      </CardContent>
    </Card>

    <template v-else-if="job">
      <Card class="rounded-xl">
        <CardContent class="grid gap-3 pt-6">
          <dl class="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <div>
              <dt class="text-muted-foreground text-xs">{{ texts.progressMapped }}</dt>
              <dd data-testid="import-review-progress">
                {{ progress.mapped }} / {{ progress.total }}
              </dd>
            </div>
            <div>
              <dt class="text-muted-foreground text-xs">{{ texts.progressIssues }}</dt>
              <dd data-testid="import-review-issues">{{ openIssues }}</dd>
            </div>
          </dl>

          <p
            v-if="settled"
            class="text-muted-foreground text-sm"
            data-testid="import-review-settled"
          >
            {{ importTexts.resolvedInfo }}
          </p>

          <template v-else>
            <label class="grid max-w-md gap-1">
              <span class="text-muted-foreground text-xs">{{ texts.scopeLabel }}</span>
              <select
                v-model="scope"
                class="border-border bg-background min-h-11 rounded-lg border px-3"
                data-testid="import-review-scope"
              >
                <option value="private">{{ texts.scopePrivate }}</option>
                <option value="household">{{ texts.scopeHousehold }}</option>
              </select>
              <span class="text-muted-foreground text-xs">{{ texts.scopeHint }}</span>
            </label>

            <div
              v-if="blockers.length"
              class="bg-destructive/10 grid gap-1 rounded-lg p-3"
              data-testid="import-review-blockers"
            >
              <p class="text-destructive text-sm font-medium">{{ texts.blockersTitle }}</p>
              <ul class="grid gap-1 text-sm">
                <li v-for="(blocker, index) in blockers" :key="index">
                  <span class="font-medium">{{ blocker.recipe_name }}</span
                  ><span v-if="blocker.recipe_name">: </span>{{ blocker.message }}
                </li>
              </ul>
              <p class="text-muted-foreground text-xs">{{ texts.blockersHint }}</p>
            </div>
            <p v-else class="text-sm" data-testid="import-review-ready">{{ texts.noBlockers }}</p>

            <div class="flex flex-wrap gap-2">
              <Button
                v-if="job.ai_available"
                type="button"
                variant="outline"
                class="min-h-11"
                :disabled="busy"
                data-testid="import-review-ai"
                @click="ai.mutate()"
              >
                {{ ai.isPending.value ? texts.aiRunning : texts.aiSuggest }}
              </Button>
              <Button
                type="button"
                class="min-h-11"
                :disabled="busy || blockers.length > 0"
                :title="blockers.length ? texts.blockersHint : undefined"
                data-testid="import-review-approve"
                @click="approve.mutate()"
              >
                {{ approve.isPending.value ? texts.approving : texts.approve }}
              </Button>
              <Button
                type="button"
                variant="outline"
                class="min-h-11"
                :disabled="busy"
                data-testid="import-review-reject"
                @click="confirmReject"
              >
                {{ texts.reject }}
              </Button>
            </div>
            <p v-if="job.ai_available" class="text-muted-foreground text-xs">{{ texts.aiHint }}</p>
          </template>
        </CardContent>
      </Card>

      <div v-if="job.job_issues?.length" class="grid gap-1">
        <h2 class="text-sm font-semibold">{{ texts.jobIssuesTitle }}</h2>
        <ul class="text-muted-foreground grid gap-1 text-xs" data-testid="import-review-job-issues">
          <li v-for="issue in job.job_issues" :key="issue.id">
            {{ issue.details?.['powód'] }}
            <span v-if="issue.details?.['linia']">— „{{ issue.details['linia'] }}”</span>
          </li>
        </ul>
      </div>

      <p
        v-if="!groups.length"
        class="text-muted-foreground text-sm"
        data-testid="import-review-empty"
      >
        {{ texts.emptyState }}
      </p>

      <section v-for="group in groups" :key="`${group.day}-${group.meal}`" class="grid gap-3">
        <h2 class="text-lg font-semibold">{{ group.day }} · {{ group.meal }}</h2>
        <StagedRecipeCard
          v-for="recipe in group.recipes"
          :key="recipe.id"
          :recipe="recipe"
          :disabled="busy || settled"
          @rename="onRename"
          @servings="onServings"
          @resolution="onResolution"
          @merge-target="onMergeTarget"
          @confirm="onConfirm"
          @create-new="onCreateNew"
          @clear="onClear"
          @resolve-issue="onResolveIssue"
        />
      </section>
    </template>
  </section>
</template>
