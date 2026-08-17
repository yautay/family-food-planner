/**
 * Wywołania modułu przepisów: `/recipes`, `/tags`, zdjęcie przepisu.
 * Typy z `generated.ts` (05_FRONTEND §2) — ręcznych interfejsów nie piszemy.
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'

export type RecipeSummary = components['schemas']['RecipeSummary']
export type RecipeDetail = components['schemas']['RecipeDetail']
export type RecipeList = components['schemas']['RecipeListResponse']
export type RecipePayload = components['schemas']['RecipePayload']
export type RecipeIngredientInput = components['schemas']['RecipeIngredientInput']
export type RecipeIngredientRead = components['schemas']['RecipeIngredientRead']
export type NutritionRead = components['schemas']['NutritionRead']
export type RatingResponse = components['schemas']['RatingResponse']
export type Tag = components['schemas']['TagRead']
export type TagList = components['schemas']['TagListResponse']
export type RecipeScope = components['schemas']['Scope']

export interface RecipeFilters {
  limit: number
  offset: number
  q?: string
  /** Identyfikatory tagów — filtr jest koniunkcją (przepis ma WSZYSTKIE). */
  tag?: number[]
  prep_time_max?: number
  difficulty_max?: number
  rating_min?: number
  scope?: RecipeScope
  include_archived?: boolean
}

export function fetchRecipes(filters: RecipeFilters): Promise<RecipeList> {
  return apiFetch<RecipeList>('/recipes', { query: { ...filters } })
}

export function fetchRecipe(id: number, servings?: string): Promise<RecipeDetail> {
  return apiFetch<RecipeDetail>(`/recipes/${id}`, {
    query: { servings },
  })
}

export function createRecipe(payload: RecipePayload): Promise<RecipeDetail> {
  return apiFetch<RecipeDetail>('/recipes', { method: 'POST', json: payload })
}

export function updateRecipe(id: number, payload: RecipePayload): Promise<RecipeDetail> {
  return apiFetch<RecipeDetail>(`/recipes/${id}`, { method: 'PUT', json: payload })
}

export function deleteRecipe(id: number): Promise<void> {
  return apiFetch<void>(`/recipes/${id}`, { method: 'DELETE' })
}

export function rateRecipe(id: number, rating: number): Promise<RatingResponse> {
  return apiFetch<RatingResponse>(`/recipes/${id}/rating`, { method: 'PUT', json: { rating } })
}

export function uploadRecipePhoto(id: number, file: File): Promise<RecipeDetail> {
  const form = new FormData()
  form.append('file', file)
  return apiFetch<RecipeDetail>(`/recipes/${id}/photo`, { method: 'POST', form })
}

export function deleteRecipePhoto(id: number): Promise<RecipeDetail> {
  return apiFetch<RecipeDetail>(`/recipes/${id}/photo`, { method: 'DELETE' })
}

export function fetchTags(): Promise<TagList> {
  return apiFetch<TagList>('/tags')
}

export function createTag(name: string): Promise<Tag> {
  return apiFetch<Tag>('/tags', { method: 'POST', json: { name } })
}
