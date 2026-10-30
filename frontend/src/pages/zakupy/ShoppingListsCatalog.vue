<script setup lang="ts">
import { PAGE_SIZE, usePaginatedList } from '@/api/pagination'
import { queryKeys } from '@/api/queryKeys'
import { fetchShoppingLists } from '@/api/shoppingLists'
import EmptyState from '@/components/domain/EmptyState.vue'
import ErrorState from '@/components/domain/ErrorState.vue'
import FeedbackMessage from '@/components/domain/FeedbackMessage.vue'
import LoadingState from '@/components/domain/LoadingState.vue'
import { Button } from '@/components/ui/button'
import { isoDate, formatDate } from '@/lib/dates'
import { shopping as texts } from '@/lib/texts'

const emit = defineEmits<{ create: [] }>()

// Offset jest pageParam. UX06 unieważnia wszystkie strony prefiksem listsIndex.
// Brak filtra statusu: wygaśnięcie linku nie kończy zakupów ani nie usuwa listy.
const lists = usePaginatedList({
  queryKey: queryKeys.shopping.listsIndexFiltered({ limit: PAGE_SIZE }),
  fetchPage: fetchShoppingLists,
})
function dateLabel(value: string): string {
  return formatDate(isoDate(new Date(value)))
}
</script>

<template>
  <section
    class="grid min-w-0 gap-4"
    aria-labelledby="saved-lists-title"
    data-testid="shopping-catalog"
  >
    <header class="flex flex-wrap items-baseline justify-between gap-2">
      <h2 id="saved-lists-title" class="text-xl font-semibold">Zapisane listy</h2>
      <p
        v-if="!lists.isPending.value && !lists.isError.value"
        class="text-muted-foreground text-sm"
        data-testid="shopping-catalog-count"
      >
        {{ lists.loaded.value }} z {{ lists.total.value }}
      </p>
    </header>
    <LoadingState
      v-if="lists.isPending.value"
      label="Wczytywanie zapisanych list…"
      data-testid="shopping-catalog-loading"
    />
    <ErrorState
      v-else-if="lists.isError.value"
      message="Nie udało się wczytać zapisanych list. Spróbuj ponownie."
      :pending="lists.isRefreshing.value"
      data-testid="shopping-catalog-error"
      @retry="lists.refresh()"
    />
    <template v-else>
      <ErrorState
        v-if="lists.refreshFailed.value"
        compact
        title="Nie udało się odświeżyć list"
        message="Pokazujemy ostatnio wczytane dane. Możesz nadal otworzyć swoje listy."
        :pending="lists.isRefreshing.value"
        data-testid="shopping-catalog-refresh-error"
        @retry="lists.refresh()"
      />
      <FeedbackMessage
        v-else-if="lists.isRefreshing.value"
        message="Odświeżanie zapisanych list…"
        data-testid="shopping-catalog-refreshing"
      />
      <EmptyState
        v-if="lists.loaded.value === 0"
        title="Pierwsza lista czeka na Twój plan"
        description="Wybierz dni planu i sprawdź podgląd zakupów przed zapisaniem listy."
        :action-label="texts.newListFromPlan"
        data-testid="shopping-catalog-empty"
        @action="emit('create')"
      />
      <ul v-else class="grid gap-3" data-testid="shopping-catalog-list">
        <li
          v-for="(list, index) in lists.items.value"
          :key="list.id"
          :data-testid="`shopping-list-${list.id}`"
          class="border-border bg-card grid min-w-0 gap-4 rounded-2xl border p-4 sm:flex sm:items-center sm:justify-between sm:p-6"
          :class="index === 0 && 'bg-header rounded-bl-md'"
        >
          <div class="grid min-w-0 gap-2">
            <p
              v-if="index === 0"
              class="text-muted-foreground text-xs font-medium tracking-widest uppercase"
            >
              Ostatnia lista
            </p>
            <h3 class="text-lg font-semibold break-words">{{ list.name }}</h3>
            <p class="text-muted-foreground text-sm break-words">
              {{ list.store_name ?? 'Bez wybranego sklepu' }}
              <span v-if="list.round_name"> · {{ list.round_name }}</span>
            </p>
            <p class="text-muted-foreground text-xs">
              Utworzona {{ dateLabel(list.created_at) }} · Ważność linku do
              {{ dateLabel(list.expires_at) }}
            </p>
            <p class="text-sm" :data-testid="`shopping-list-count-${list.id}`">
              Odhaczone {{ list.items_checked }} z {{ list.items_total }} pozycji
            </p>
          </div>
          <Button as-child variant="outline" class="h-fit shrink-0 justify-self-start">
            <RouterLink
              :to="{ name: 'zakupy-lista', params: { id: list.id } }"
              :data-testid="`shopping-list-link-${list.id}`"
              :aria-label="`Otwórz listę: ${list.name}`"
              >Otwórz listę</RouterLink
            >
          </Button>
        </li>
      </ul>
      <div
        v-if="lists.hasMore.value || lists.nextPageFailed.value"
        class="grid justify-items-start gap-3"
      >
        <p
          v-if="lists.nextPageFailed.value"
          class="text-destructive text-sm"
          role="alert"
          data-testid="shopping-catalog-more-error"
        >
          Nie udało się wczytać kolejnych list. Wczytane listy pozostają dostępne.
        </p>
        <Button
          variant="outline"
          :disabled="lists.isLoadingMore.value || lists.isRefreshing.value"
          :aria-busy="lists.isLoadingMore.value"
          data-testid="shopping-catalog-more"
          @click="lists.loadMore()"
        >
          {{
            lists.isLoadingMore.value
              ? 'Wczytywanie…'
              : lists.nextPageFailed.value
                ? 'Ponów wczytywanie kolejnych list'
                : 'Pokaż więcej list'
          }}
        </Button>
      </div>
    </template>
  </section>
</template>
