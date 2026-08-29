<script setup lang="ts">
/**
 * Import jadłospisów PDF (`/import`, BATCH_15) — wgranie pliku, lista importów
 * i podgląd raportu odczytu.
 *
 * Trzy decyzje warte zapisania:
 *
 * 1. **Ekranu review tu NIE MA i nie ma udawać, że będzie za chwilę.** Job
 *    kończy na statusie `Sparsowany`, a strona mówi wprost, że rozstrzyganie
 *    przychodzi w kolejnym etapie (karta B15 §Frontend). Przycisk prowadzący
 *    donikąd byłby gorszy niż jego brak.
 * 2. **Walidacja pliku po stronie klienta to WYŁĄCZNIE UX.** Rozmiar
 *    i rozszerzenie sprawdzamy, żeby nie wysyłać 40 MB w ciemno, ale prawdą
 *    jest serwer: on sniffuje treść (`%PDF`), a nie nazwę (07_SECURITY §6).
 * 3. **Raport jest stanem SERWERA**, więc żyje w TanStack Query pod
 *    `queryKeys.import.*`, a nie w Pinia (ADR-007). Upload unieważnia listę.
 *    Lista jobów celowo NIE niesie `parse_report` (`ImportJobSummary` ma tylko
 *    liczby zbiorcze) — pełny raport dociąga się z `GET /import/jobs/{id}`
 *    dopiero po rozwinięciu. Po uploadzie wkładamy odpowiedź mutacji wprost do
 *    cache'u szczegółu, więc świeży raport pokazuje się bez drugiego żądania.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref } from 'vue'

import { ApiError } from '@/api/client'
import type { ImportJobStatus, ImportJobSummary, ParseReport } from '@/api/pdfImport'
import {
  MAX_PDF_MB,
  deleteJob,
  exactMatchPercent,
  getJob,
  listJobs,
  parseReportOf,
  uploadPdf,
} from '@/api/pdfImport'
import { queryKeys } from '@/api/queryKeys'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { common, pdfImport as texts } from '@/lib/texts'

const queryClient = useQueryClient()

const fileInput = ref<HTMLInputElement | null>(null)
const errorMessage = ref<string | null>(null)
const openReportId = ref<number | null>(null)
const dragging = ref(false)

const jobs = useQuery({
  queryKey: queryKeys.import.jobs,
  queryFn: listJobs,
})

const upload = useMutation({
  mutationFn: uploadPdf,
  onSuccess: async (job) => {
    errorMessage.value = null
    // Odpowiedź uploadu JEST szczegółem joba — wkładamy ją do cache'u, żeby
    // rozwinięty raport nie czekał na drugie żądanie o to samo.
    queryClient.setQueryData(queryKeys.import.job(job.id), job)
    // Raport jest jedyną treścią, po którą użytkownik tu przyszedł — otwieramy
    // go od razu, zamiast kazać szukać świeżego wiersza na liście.
    openReportId.value = job.id
    await queryClient.invalidateQueries({ queryKey: queryKeys.import.jobs })
  },
  onError: (error: unknown) => {
    errorMessage.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

const remove = useMutation({
  mutationFn: deleteJob,
  onSuccess: async (_result, id) => {
    errorMessage.value = null
    if (openReportId.value === id) openReportId.value = null
    queryClient.removeQueries({ queryKey: queryKeys.import.job(id) })
    await queryClient.invalidateQueries({ queryKey: queryKeys.import.jobs })
  },
  onError: (error: unknown) => {
    errorMessage.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})

const items = computed<ImportJobSummary[]>(() => jobs.data.value?.items ?? [])
const isEmpty = computed(() => !jobs.isPending.value && items.value.length === 0)

/**
 * Szczegóły ROZWINIĘTEGO joba — jedyne miejsce, z którego bierze się raport.
 * Bez `openReportId` zapytanie jest wyłączone, więc lista nie ciąga po jednym
 * żądaniu na wiersz.
 */
const openJob = useQuery({
  queryKey: computed(() => queryKeys.import.job(openReportId.value ?? 0)),
  queryFn: () => getJob(openReportId.value as number),
  enabled: computed(() => openReportId.value !== null),
})

const openReport = computed<ParseReport | null>(() => parseReportOf(openJob.data.value ?? null))

/** Raport ma wyłącznie job, który przeszedł parsowanie — reszta nie ma czego pokazać. */
function hasReport(job: ImportJobSummary): boolean {
  return job.status === 'parsed'
}

function statusLabel(status: ImportJobStatus): string {
  return texts.status[status]
}

/** Plakietka statusu — kolory z tokens, nigdy hex w komponencie (06_UIUX §1). */
function statusClass(status: ImportJobStatus): string {
  if (status === 'failed' || status === 'rejected') return 'bg-destructive/10 text-destructive'
  if (status === 'approved' || status === 'parsed') return 'bg-primary/10 text-primary'
  return 'bg-muted text-muted-foreground'
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'short' })
}

function submit(file: File | null | undefined): void {
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    errorMessage.value = texts.fileNotPdf
    return
  }
  if (file.size > MAX_PDF_MB * 1024 * 1024) {
    errorMessage.value = texts.fileTooLarge
    return
  }
  errorMessage.value = null
  upload.mutate(file)
}

function onFileChosen(event: Event): void {
  const input = event.target as HTMLInputElement
  submit(input.files?.[0])
  // Bez tego wybór TEGO SAMEGO pliku drugi raz nie odpaliłby `change`.
  input.value = ''
}

function onDrop(event: DragEvent): void {
  dragging.value = false
  submit(event.dataTransfer?.files?.[0])
}

function confirmDelete(id: number): void {
  if (window.confirm(texts.deleteConfirm)) remove.mutate(id)
}

function toggleReport(id: number): void {
  openReportId.value = openReportId.value === id ? null : id
}
</script>

<template>
  <section class="grid gap-6" data-testid="import-page">
    <header class="grid gap-1">
      <h1 class="text-2xl font-semibold">{{ texts.title }}</h1>
      <p class="text-muted-foreground text-sm">{{ texts.subtitle }}</p>
    </header>

    <p v-if="errorMessage" class="text-destructive text-sm" role="alert" data-testid="import-error">
      {{ errorMessage }}
    </p>

    <Card class="rounded-xl">
      <CardContent class="pt-6">
        <div
          class="border-muted-foreground/40 grid place-items-center gap-2 rounded-xl border-2 border-dashed p-8 text-center"
          :class="dragging ? 'border-primary bg-primary/5' : ''"
          data-testid="import-dropzone"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
        >
          <p class="text-sm font-medium">{{ texts.dropzone }}</p>
          <p class="text-muted-foreground text-xs">{{ texts.dropzoneHint }}</p>
          <input
            ref="fileInput"
            type="file"
            accept="application/pdf,.pdf"
            class="sr-only"
            data-testid="import-file-input"
            @change="onFileChosen"
          />
          <Button
            type="button"
            class="min-h-11"
            :disabled="upload.isPending.value"
            data-testid="import-choose"
            @click="fileInput?.click()"
          >
            {{ upload.isPending.value ? texts.uploading : texts.choose }}
          </Button>
        </div>
      </CardContent>
    </Card>

    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ texts.jobsTitle }}</CardTitle>
        <CardDescription>{{ texts.reviewSoon }}</CardDescription>
      </CardHeader>

      <CardContent class="grid gap-3">
        <p v-if="isEmpty" class="text-muted-foreground text-sm" data-testid="import-empty">
          {{ texts.emptyState }}
        </p>

        <article
          v-for="job in items"
          :key="job.id"
          class="border-border grid gap-3 rounded-xl border p-4"
          data-testid="import-job"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="grid gap-1">
              <p class="font-medium" data-testid="import-job-filename">{{ job.filename }}</p>
              <p class="text-muted-foreground text-xs">
                {{ texts.columnDate }}: {{ formatDate(job.created_at) }}
              </p>
            </div>
            <span
              class="rounded-full px-3 py-1 text-xs font-medium"
              :class="statusClass(job.status)"
              data-testid="import-job-status"
            >
              {{ statusLabel(job.status) }}
            </span>
          </div>

          <p v-if="job.error" class="text-destructive text-sm" data-testid="import-job-error">
            {{ job.error }}
          </p>

          <p
            v-if="job.staged_recipes !== null && job.staged_recipes !== undefined"
            class="text-muted-foreground text-sm"
            data-testid="import-job-numbers"
          >
            {{ texts.reportDays }}: {{ job.days }} · {{ texts.reportMeals }}: {{ job.meals }} ·
            {{ texts.reportRecipes }}: {{ job.staged_recipes }} · {{ texts.reportIngredients }}:
            {{ job.ingredients }}
          </p>

          <div class="flex flex-wrap gap-2">
            <Button
              v-if="hasReport(job)"
              type="button"
              variant="outline"
              class="min-h-11"
              data-testid="import-job-toggle-report"
              @click="toggleReport(job.id)"
            >
              {{ openReportId === job.id ? texts.hideReport : texts.showReport }}
            </Button>
            <Button
              type="button"
              variant="outline"
              class="min-h-11"
              :disabled="remove.isPending.value"
              data-testid="import-job-delete"
              @click="confirmDelete(job.id)"
            >
              {{ texts.deleteAction }}
            </Button>
          </div>

          <div
            v-if="openReportId === job.id && openReport"
            class="bg-muted/40 grid gap-3 rounded-xl p-4"
            data-testid="import-job-report"
          >
            <h2 class="text-sm font-semibold">{{ texts.reportTitle }}</h2>

            <dl class="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
              <div>
                <dt class="text-muted-foreground text-xs">{{ texts.reportPages }}</dt>
                <dd>
                  {{ openReport!.pages.days }} / {{ openReport!.pages.total }}
                  <span class="text-muted-foreground text-xs">
                    ({{ texts.reportPagesDetail }}: {{ openReport!.pages.skipped_shopping }} +
                    {{ openReport!.pages.skipped_exchanges }})
                  </span>
                </dd>
              </div>
              <div>
                <dt class="text-muted-foreground text-xs">{{ texts.reportMeals }}</dt>
                <dd>{{ openReport!.meals }}</dd>
              </div>
              <div>
                <dt class="text-muted-foreground text-xs">{{ texts.reportRecipes }}</dt>
                <dd>{{ openReport!.staged_recipes }}</dd>
              </div>
              <div>
                <dt class="text-muted-foreground text-xs">{{ texts.reportMatched }}</dt>
                <dd data-testid="import-report-match">
                  {{ openReport!.match.exact }} / {{ openReport!.ingredients }}
                  <span v-if="exactMatchPercent(openReport) !== null">
                    ({{ exactMatchPercent(openReport) }}%)
                  </span>
                </dd>
              </div>
            </dl>

            <div class="grid gap-1">
              <h3 class="text-xs font-semibold">{{ texts.issuesTitle }}</h3>
              <p
                v-if="openReport!.issues.blocker === 0 && openReport!.issues.warning === 0"
                class="text-muted-foreground text-sm"
                data-testid="import-report-issues"
              >
                {{ texts.issuesNone }}
              </p>
              <p v-else class="text-sm" data-testid="import-report-issues">
                {{ openReport!.issues.blocker }} {{ texts.issuesBlockers }} ·
                {{ openReport!.issues.warning }} {{ texts.issuesWarnings }}
              </p>
            </div>

            <div class="grid gap-1">
              <h3 class="text-xs font-semibold">{{ texts.reportChecksums }}</h3>
              <ul class="grid gap-1 text-sm" data-testid="import-report-checksums">
                <li
                  v-for="checksum in openReport!.day_checksums"
                  :key="checksum.day"
                  class="flex flex-wrap items-center gap-2"
                >
                  <span class="font-medium">{{ checksum.day }}</span>
                  <span class="text-muted-foreground text-xs">
                    {{ checksum.computed }} / {{ checksum.expected ?? '—' }} kcal
                  </span>
                  <span
                    class="rounded-full px-2 py-0.5 text-xs"
                    :class="
                      checksum.ok
                        ? 'bg-primary/10 text-primary'
                        : 'bg-destructive/10 text-destructive'
                    "
                  >
                    {{ checksum.ok ? texts.checksumOk : texts.checksumMismatch }}
                  </span>
                </li>
              </ul>
            </div>

            <ul
              v-if="openReport!.warnings.length"
              class="text-muted-foreground grid gap-1 text-xs"
              data-testid="import-report-warnings"
            >
              <li v-for="warning in openReport!.warnings" :key="warning">{{ warning }}</li>
            </ul>

            <p class="text-muted-foreground text-xs">{{ texts.reviewSoon }}</p>
          </div>
        </article>
      </CardContent>
    </Card>
  </section>
</template>
