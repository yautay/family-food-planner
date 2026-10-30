import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import type { RecipeDetail, RecipeSummary } from '@/api/recipes'
import ActionPanel from './ActionPanel.vue'
import AmountInput from './AmountInput.vue'
import RecipePicker from './RecipePicker.vue'

const { fetchRecipes, createRecipe } = vi.hoisted(() => ({
  fetchRecipes: vi.fn(),
  createRecipe: vi.fn(),
}))
vi.mock('@/api/recipes', () => ({ fetchRecipes, createRecipe }))

const recipe: RecipeDetail = {
  id: 9,
  name: 'Żurek Łucji',
  scope: 'private',
  owner_user_id: 1,
  base_servings: 1,
  prep_time_min: null,
  difficulty: null,
  is_archived: false,
  photo_url: null,
  photo_thumb_url: null,
  tags: [],
  avg_rating: null,
  ratings_count: 0,
  my_rating: null,
  nutrition: {
    kcal: '420',
    protein_g: '20',
    fat_g: '10',
    carbs_g: '55',
    fiber_g: '6',
    sugars_g: '8',
    glycemic_load: '25',
    complete: true,
    missing: [],
  },
  created_at: '2026-10-03T10:00:00Z',
  updated_at: '2026-10-03T10:00:00Z',
  instructions: '',
  servings: '1',
  ingredients: [],
}

describe('ActionPanel + istniejący RecipePicker create-in-context', () => {
  it('wewnętrzny zapis tworzy i wybiera przepis bez wysłania akcji panelu; zewnętrzny zapis waliduje wyłącznie własne pola', async () => {
    fetchRecipes.mockResolvedValue({ items: [], total: 0 })
    createRecipe.mockResolvedValue(recipe)
    const submit = vi.fn()
    const Host = defineComponent({
      setup() {
        const selected = ref<RecipeSummary | null>(null)
        return () =>
          h(
            ActionPanel,
            { open: true, title: 'Zaplanuj przepis', submitLabel: 'Zaplanuj', onSubmit: submit },
            {
              default: ({ formId }: { formId: string }) => [
                h('label', ['Posiłek', h('input', { name: 'meal', required: true, form: formId })]),
                h(AmountInput, { modelValue: '1', form: formId, units: ['g', 'ml'], unit: 'g' }),
                h(RecipePicker, {
                  modelValue: selected.value,
                  debounceMs: 0,
                  'onUpdate:modelValue': (value: RecipeSummary | null) => {
                    selected.value = value
                  },
                }),
              ],
            },
          )
      },
    })
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const wrapper = mount(Host, {
      attachTo: document.body,
      global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
    })
    try {
      await flushPromises()
      const picker = wrapper.findComponent(RecipePicker)
      const input = document.querySelector<HTMLInputElement>('[data-testid="recipe-picker-input"]')!
      input.focus()
      input.value = recipe.name
      input.dispatchEvent(new Event('input', { bubbles: true }))
      await vi.waitFor(() =>
        expect(document.querySelector('[data-testid="recipe-picker-create"]')).not.toBeNull(),
      )
      document.querySelector<HTMLElement>('[data-testid="recipe-picker-create"]')!.click()
      await flushPromises()
      const inner = document.querySelector<HTMLFormElement>('[data-testid="recipe-create-drawer"]')!
      expect(document.querySelectorAll('form form')).toHaveLength(0)
      expect(inner.closest('form')).toBe(inner)
      // Wymagane puste pole zewnętrzne nie blokuje minimalnego tworzenia przepisu.
      inner.requestSubmit()
      await flushPromises()
      await vi.waitFor(() => expect(picker.emitted('selected')).toHaveLength(1))
      expect(createRecipe).toHaveBeenCalledTimes(1)
      expect(submit).not.toHaveBeenCalled()
      expect(
        document.querySelector('[data-testid="recipe-picker-selected"]')?.textContent,
      ).toContain(recipe.name)
      const meal = document.querySelector<HTMLInputElement>('input[name="meal"]')!
      const mainForm = document.getElementById(meal.getAttribute('form')!) as HTMLFormElement
      expect(document.querySelector<HTMLInputElement>('[data-testid="amount"]')?.form).toBe(
        mainForm,
      )
      expect(document.querySelector<HTMLSelectElement>('[data-testid="amount-unit"]')?.form).toBe(
        mainForm,
      )
      mainForm.requestSubmit()
      await flushPromises()
      expect(submit).not.toHaveBeenCalled()
      expect(document.activeElement).toBe(meal)
      meal.value = 'Późny obiad'
      mainForm.requestSubmit()
      await flushPromises()
      expect(submit).toHaveBeenCalledTimes(1)
    } finally {
      wrapper.unmount()
      client.clear()
      document.body.innerHTML = ''
    }
  })
})
