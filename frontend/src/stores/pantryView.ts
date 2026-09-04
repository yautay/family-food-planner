/**
 * Preferencja widoku spiżarni: kafelki czy lista (karta B08 §Frontend).
 *
 * To STAN UI, więc miejsce ma w Pinia (ADR-007, 05_FRONTEND §1) — w odróżnieniu
 * od samych pozycji spiżarni, które są stanem serwera i żyją w TanStack Query.
 * Zapisujemy go w `localStorage`, bo przełącznik widoku, który resetuje się po
 * odświeżeniu, jest gorszy niż jego brak.
 */

import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type PantryViewMode = 'grid' | 'list'

const STORAGE_KEY = 'pasnik.pantry.view'

function readStored(): PantryViewMode {
  if (typeof localStorage === 'undefined') {
    return 'grid'
  }
  return localStorage.getItem(STORAGE_KEY) === 'list' ? 'list' : 'grid'
}

export const usePantryViewStore = defineStore('pantryView', () => {
  const mode = ref<PantryViewMode>(readStored())

  watch(mode, (value) => {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, value)
    }
  })

  function setMode(value: PantryViewMode): void {
    mode.value = value
  }

  return { mode, setMode }
})
