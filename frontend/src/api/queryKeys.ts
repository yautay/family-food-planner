/**
 * Centralny rejestr kluczy TanStack Query (05_FRONTEND §1).
 *
 * Każdy moduł dopisuje tu swoje klucze — dzięki temu `invalidateQueries`
 * w mutacjach odwołuje się do jednego źródła prawdy, a nie do literałów
 * rozsianych po komponentach.
 *
 * Wzorzec:
 *   recipes: {
 *     all: ['recipes'] as const,
 *     list: (filters: RecipeFilters) => ['recipes', 'list', filters] as const,
 *     detail: (id: number) => ['recipes', 'detail', id] as const,
 *   }
 *
 * BATCH_01 nie ma jeszcze żadnego zasobu — obiekt startuje pusty.
 */
export const queryKeys = {} as const
