<script setup lang="ts">
import { useQueries } from '@tanstack/vue-query'
import { computed, watch } from 'vue'
import { fetchPlanDays } from '@/api/planning'
import { queryKeys } from '@/api/queryKeys'
import { Button } from '@/components/ui/button'
import { formatDate, daysBetween } from '@/lib/dates'
import { isValidIsoDate } from '@/lib/schemas/template'
import { week as texts } from '@/lib/texts'

const props = withDefaults(
  defineProps<{
    dates: string[]
    sourceDates?: string[]
    sourceLabel?: string
    append?: boolean
  }>(),
  { append: true, sourceDates: () => [], sourceLabel: undefined },
)
const emit = defineEmits<{ ready: [ready: boolean] }>()
// Sparse dates may span years. Group only neighbouring dates, with the API's 366-day ceiling.
const ranges = computed(() => {
  const dates = [...new Set([...props.dates, ...(props.sourceDates ?? [])])]
    .filter(isValidIsoDate)
    .sort()
  const ranges: { from: string; to: string }[] = []
  for (const date of dates) {
    const last = ranges.at(-1)
    if (last && daysBetween(last.to, date) === 1 && daysBetween(last.from, date) < 366)
      last.to = date
    else ranges.push({ from: date, to: date })
  }
  return ranges
})
const queries = useQueries({
  queries: computed(() =>
    ranges.value.map(({ from, to }) => ({
      queryKey: queryKeys.planDays.range(from, to),
      queryFn: () => fetchPlanDays(from, to),
      retry: false,
      staleTime: 0,
    })),
  ),
})
const loading = computed(() => queries.value.some((q) => q.isPending || q.isFetching))
const failed = computed(() => queries.value.some((q) => q.isError))
const ready = computed(() => ranges.value.length > 0 && !loading.value && !failed.value)
watch(ready, (value) => emit('ready', value), { immediate: true })
const days = computed(() => queries.value.flatMap((q) => q.data?.items ?? []))
const count = (date: string): number =>
  days.value.find((day) => day.day === date)?.meals.length ?? 0
const emptySources = computed(() => props.sourceDates?.filter((date) => count(date) === 0) ?? [])
</script>

<template>
  <section
    class="border-border bg-muted/40 grid gap-2 rounded-xl border p-3 text-sm"
    data-testid="reuse-preview"
    aria-label="Podgląd operacji"
  >
    <p v-if="sourceLabel" class="break-words">
      <strong>{{ texts.source }}:</strong> {{ sourceLabel }}
    </p>
    <p v-if="append !== false">{{ texts.appendNotice }}</p>
    <p class="text-muted-foreground text-xs">{{ texts.visibleNotice }}</p>
    <p v-if="loading" role="status">{{ texts.previewLoading }}</p>
    <div v-else-if="failed" role="alert">
      <p>{{ texts.previewError }}</p>
      <Button
        type="button"
        variant="outline"
        class="mt-2 min-h-11"
        @click="queries.forEach((q) => q.refetch())"
        >{{ texts.retryPreview }}</Button
      >
    </div>
    <template v-else-if="ready">
      <p v-if="emptySources.length" class="text-warning" data-testid="reuse-empty-source">
        {{ texts.emptySources }}: {{ emptySources.map(formatDate).join(', ') }}.
      </p>
      <p v-if="sourceDates?.length" class="break-words">
        Posiłki w widocznym źródle:
        {{
          days
            .filter((day) => sourceDates?.includes(day.day))
            .flatMap((day) => day.meals.map((meal) => meal.name))
            .join(', ') || texts.dayEmpty
        }}.
      </p>
      <p v-if="append !== false" class="font-medium">{{ texts.targets }} ({{ dates.length }})</p>
      <ul v-if="append !== false" class="grid gap-1 tabular-nums" data-testid="reuse-targets">
        <li v-for="date in dates" :key="date">
          {{ formatDate(date) }} —
          {{ count(date) ? `${texts.existingMeals}: ${count(date)}` : texts.dayEmpty }}
        </li>
      </ul>
      <p v-if="!dates.length && append !== false">{{ texts.datesRequired }}</p>
    </template>
  </section>
</template>
