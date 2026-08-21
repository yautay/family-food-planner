/**
 * Szkic generacji zakupów — WYŁĄCZNIE stan UI (ADR-007, 05_FRONTEND §1).
 *
 * Co tu jest: zakres dat formularza, odpowiedź na pytanie o spiżarnię, wybór
 * tur, id aktualnie oglądanej generacji i rozwinięte sekcje podglądu.
 * Czego tu NIE MA: samego podglądu. Podgląd liczy silnik na serwerze z `params`
 * generacji, więc jest stanem serwera i mieszka w TanStack Query — kopiowanie
 * go do Pinia dałoby dwa źródła prawdy.
 *
 * **`usePantry` startuje jako `false` i NIGDY nie jest zapamiętywane** między
 * generacjami (02_DOMAIN §8): pytanie „Uwzględnić stan domowy?" ma być zadane
 * za każdym razem, bo spiżarnia bywa nieaktualna. Dlatego ten store świadomie
 * nie sięga do `localStorage`, choć `pantryView` (preferencja widoku) to robi.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { addDays, isoDate, startOfWeek } from '@/lib/dates'

export const usePantryDefault = false

export const useShoppingDraftStore = defineStore('shoppingDraft', () => {
  /** Domyślnie najbliższy tydzień planu, licząc od poniedziałku (06_UIUX §2). */
  const monday = startOfWeek(isoDate(new Date()))

  const dateFrom = ref(monday)
  const dateTo = ref(addDays(monday, 6))
  /** Jawna decyzja użytkownika — nigdy nie zaznaczamy tego za niego. */
  const usePantry = ref(usePantryDefault)
  /** `null` = wszystkie tury z konfiguracji; lista = wybór użytkownika. */
  const roundConfigIds = ref<number[] | null>(null)
  /** Id generacji, której podgląd jest otwarty (klucz zapytania w Query). */
  const generationId = ref<number | null>(null)
  /** Zwinięte sekcje tur — klucz tury z podglądu. */
  const collapsedRounds = ref<string[]>([])

  const rangeValid = computed(() => dateFrom.value !== '' && dateFrom.value <= dateTo.value)

  function setWeek(start: string): void {
    dateFrom.value = start
    dateTo.value = addDays(start, 6)
  }

  function toggleRound(key: string): void {
    collapsedRounds.value = collapsedRounds.value.includes(key)
      ? collapsedRounds.value.filter((item) => item !== key)
      : [...collapsedRounds.value, key]
  }

  function isCollapsed(key: string): boolean {
    return collapsedRounds.value.includes(key)
  }

  function openGeneration(id: number | null): void {
    generationId.value = id
    collapsedRounds.value = []
  }

  /** Po finalizacji (albo odrzuceniu) wracamy do formularza z czystym pytaniem. */
  function reset(): void {
    generationId.value = null
    collapsedRounds.value = []
    usePantry.value = usePantryDefault
  }

  return {
    dateFrom,
    dateTo,
    usePantry,
    roundConfigIds,
    generationId,
    collapsedRounds,
    rangeValid,
    setWeek,
    toggleRound,
    isCollapsed,
    openGeneration,
    reset,
  }
})
