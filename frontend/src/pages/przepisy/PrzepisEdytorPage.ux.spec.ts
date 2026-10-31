import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CurrentUser } from '@/api/auth'
import { ApiError } from '@/api/client'
import type { RecipeDetail } from '@/api/recipes'
import ProductPicker from '@/components/domain/ProductPicker.vue'
import { queryKeys } from '@/api/queryKeys'
import { advanceSessionGeneration, captureSessionGeneration } from '@/lib/sessionGeneration'
import { useAuthStore } from '@/stores/auth'
import PrzepisEdytorPage from './PrzepisEdytorPage.vue'

const api = vi.hoisted(() => ({
  createRecipe: vi.fn(),
  updateRecipe: vi.fn(),
  copyRecipe: vi.fn(),
  createTag: vi.fn(),
  fetchRecipe: vi.fn(),
  fetchTags: vi.fn(),
  uploadRecipePhoto: vi.fn(),
  deleteRecipePhoto: vi.fn(),
}))
vi.mock('@/api/recipes', () => api)
vi.mock('@/api/catalog', () => ({
  fetchProducts: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchCategories: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  createProduct: vi.fn(),
  fetchProduct: vi.fn(),
  fetchUnitWeights: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}))

function detail(id = 19): RecipeDetail {
  return {
    id,
    name: 'Zupa rodzinna',
    instructions: 'Ugotuj powoli.',
    scope: 'household',
    owner_user_id: 1,
    base_servings: 2,
    prep_time_min: 30,
    difficulty: 3,
    is_archived: false,
    photo_url: null,
    photo_thumb_url: null,
    tags: [{ id: 4, name: 'Obiad', is_system: false }],
    avg_rating: null,
    ratings_count: 0,
    my_rating: null,
    servings: '1',
    ingredients: [
      {
        id: 8,
        product_id: 1,
        product_name: 'Pełnoziarnisty makaron z dodatkiem warzyw i nasion',
        measure_kind: 'mass',
        display_qty: '200',
        display_unit: 'g',
        amount: '200',
        amount_unit: 'g',
        scaled_amount: '100',
        note: 'Al dente',
        position: 0,
      },
    ],
    nutrition: {
      kcal: '0',
      protein_g: '0',
      fat_g: '0',
      carbs_g: '0',
      fiber_g: '0',
      sugars_g: '0',
      glycemic_load: '0',
      complete: true,
      missing: [],
    },
    created_at: '2026-10-03T10:00:00Z',
    updated_at: '2026-10-03T10:00:00Z',
  }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
const wrappers: { unmount(): void }[] = []
async function setup(path = '/przepisy/nowy', role: CurrentUser['role'] = 'admin') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/przepisy/nowy', name: 'przepis-nowy', component: PrzepisEdytorPage },
      { path: '/przepisy/:id/edytuj', name: 'przepis-edycja', component: PrzepisEdytorPage },
      { path: '/przepisy', name: 'przepisy', component: { template: '<div>Katalog</div>' } },
      {
        path: '/przepisy/:id',
        name: 'przepis-szczegol',
        component: { template: '<div>Szczegóły</div>' },
      },
      { path: '/login', name: 'login', component: { template: '<div>Logowanie</div>' } },
    ],
  })
  const pinia = createPinia()
  const auth = useAuthStore(pinia)
  auth.setUser(
    {
      id: 1,
      email: 'test@example.com',
      display_name: 'Test',
      role,
      household: { id: 1, name: 'Dom' },
      ui_settings: {},
    } as CurrentUser,
    captureSessionGeneration(),
  )
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  await router.push(path)
  const wrapper = mount(
    defineComponent({ components: { RouterView }, template: '<RouterView />' }),
    {
      attachTo: document.body,
      global: { plugins: [pinia, router, [VueQueryPlugin, { queryClient }]] },
    },
  )
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router, auth, queryClient }
}
async function submit(wrapper: Awaited<ReturnType<typeof setup>>['wrapper']) {
  await wrapper.get('[data-testid="recipe-form"]').trigger('submit')
  await flushPromises()
}

describe('UX08 — niezapisane zmiany i błędy edytora', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    api.fetchTags.mockResolvedValue({
      items: [{ id: 4, name: 'Obiad', is_system: false }],
      total: 1,
    })
    api.fetchRecipe.mockImplementation((id: number) => Promise.resolve(detail(id)))
    api.createRecipe.mockResolvedValue(detail(77))
    api.updateRecipe.mockResolvedValue(detail())
    api.copyRecipe.mockResolvedValue({ ...detail(99), scope: 'household' })
    vi.spyOn(window, 'confirm').mockReturnValue(false)
  })
  afterEach(() => {
    for (const wrapper of wrappers.splice(0)) wrapper.unmount()
    vi.restoreAllMocks()
  })

  it('brudny formularz zatrzymuje link i zmianę ID, przywrócenie wartości usuwa ostrzeżenie', async () => {
    const { wrapper, router } = await setup('/przepisy/19/edytuj')
    expect(wrapper.get('[data-testid="recipe-dirty-status"]').text()).toBe(
      'Brak niezapisanych zmian',
    )
    await wrapper.get('[data-testid="recipe-name"]').setValue('Zupa po zmianie')
    expect(wrapper.get('[data-testid="recipe-dirty-status"]').text()).toContain('Masz niezapisane')
    await wrapper.get('[data-testid="recipe-editor-back"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('przepis-edycja')
    await router.push('/przepisy/20/edytuj')
    expect(router.currentRoute.value.params.id).toBe('19')
    expect(window.confirm).toHaveBeenCalledTimes(2)
    expect(wrapper.get<HTMLInputElement>('[data-testid="recipe-name"]').element.value).toBe(
      'Zupa po zmianie',
    )
    await wrapper.get('[data-testid="recipe-name"]').setValue('Zupa rodzinna')
    await router.push('/przepisy')
    expect(router.currentRoute.value.name).toBe('przepisy')
    expect(window.confirm).toHaveBeenCalledTimes(2)
  })

  it('składniki, tagi, notatka i przygotowanie są częścią ochrony; anulowanie zachowuje dane', async () => {
    const { wrapper, router } = await setup('/przepisy/19/edytuj')
    await wrapper.get('[data-testid="recipe-instructions"]').setValue('Nie zgub tego kroku')
    await wrapper.get('[data-testid="ingredient-note-0"]').setValue('Długa notatka')
    await wrapper.get('[data-testid="recipe-tag-4"]').trigger('click')
    await wrapper.get('[data-testid="ingredient-add"]').trigger('click')
    await router.push('/przepisy')
    expect(wrapper.findAll('[data-testid^="ingredient-row-"]')).toHaveLength(2)
    expect(
      wrapper.get<HTMLTextAreaElement>('[data-testid="recipe-instructions"]').element.value,
    ).toBe('Nie zgub tego kroku')
    expect(wrapper.get<HTMLInputElement>('[data-testid="ingredient-note-0"]').element.value).toBe(
      'Długa notatka',
    )
    expect(wrapper.get('[data-testid="recipe-tag-4"]').attributes('aria-pressed')).toBe('false')
  })

  it('zgoda na opuszczenie pozwala przejść, a kolejne ID wypełnia świeży formularz', async () => {
    const { wrapper, router } = await setup('/przepisy/19/edytuj')
    await wrapper.get('[data-testid="recipe-name"]').setValue('Zmiana')
    vi.mocked(window.confirm).mockReturnValue(true)
    await router.push('/przepisy/20/edytuj')
    await flushPromises()
    expect(router.currentRoute.value.params.id).toBe('20')
    expect(api.fetchRecipe).toHaveBeenCalledWith(20)
    expect(wrapper.get<HTMLInputElement>('[data-testid="recipe-name"]').element.value).toBe(
      'Zupa rodzinna',
    )
    expect(wrapper.get('[data-testid="recipe-dirty-status"]').text()).toBe(
      'Brak niezapisanych zmian',
    )
  })

  it('beforeunload chroni tylko brudny formularz i usuwa listener po odmontowaniu', async () => {
    const { wrapper } = await setup()
    const clean = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(clean)
    expect(clean.defaultPrevented).toBe(false)
    await wrapper.get('[data-testid="recipe-name"]').setValue('Nowy')
    const dirty = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(dirty)
    expect(dirty.defaultPrevented).toBe(true)
    wrapper.unmount()
    const gone = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(gone)
    expect(gone.defaultPrevented).toBe(false)
  })

  it('prawidłowy zapis od razu otwiera zwrócone ID bez pytania o utratę zmian', async () => {
    const { wrapper, router } = await setup(
      '/przepisy/nowy?q=zupa&tag=4&selectedDate=2031-04-09&next=evil&offset=50',
    )
    await wrapper.get('[data-testid="recipe-name"]').setValue('Zupa nowa')
    await submit(wrapper)
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('przepis-szczegol'))
    expect(router.currentRoute.value.params.id).toBe('77')
    expect(router.currentRoute.value.query).toEqual({
      q: 'zupa',
      tag: ['4'],
      selectedDate: '2031-04-09',
    })
    expect(window.confirm).not.toHaveBeenCalled()
  })

  it('walidacja lokalna otwiera dodatkowe pola, ustawia fokus i zachowuje inne wartości', async () => {
    const { wrapper } = await setup()
    await wrapper.get('[data-testid="recipe-name"]').setValue('Nazwa zostaje')
    await wrapper.get('[data-testid="recipe-instructions"]').setValue('Kroki zostają')
    await wrapper.get('[data-testid="recipe-difficulty"]').setValue('11')
    await submit(wrapper)
    await vi.waitFor(() =>
      expect(document.activeElement).toBe(wrapper.get('[data-testid="recipe-difficulty"]').element),
    )
    expect(wrapper.get<HTMLDetailsElement>('[data-testid="recipe-extras"]').element.open).toBe(true)
    expect(wrapper.get<HTMLInputElement>('[data-testid="recipe-name"]').element.value).toBe(
      'Nazwa zostaje',
    )
    expect(
      wrapper.get<HTMLTextAreaElement>('[data-testid="recipe-instructions"]').element.value,
    ).toBe('Kroki zostają')
    expect(api.createRecipe).not.toHaveBeenCalled()
  })

  it('brak produktu ogniskuje właściwy drugi wiersz bez utraty pierwszego', async () => {
    const { wrapper } = await setup('/przepisy/19/edytuj')
    await wrapper.get('[data-testid="ingredient-add"]').trigger('click')
    await submit(wrapper)
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="ingredient-error-1"]').exists()).toBe(true),
    )
    await vi.waitFor(() =>
      expect(document.activeElement).toBe(
        wrapper.get('[data-testid="ingredient-row-1"] [data-testid="picker-input"]').element,
      ),
    )
    expect(wrapper.get('[data-testid="ingredient-error-1"]').text()).toContain('Wybierz produkt')
    expect(wrapper.get<HTMLInputElement>('[data-testid="ingredient-amount-0"]').element.value).toBe(
      '200',
    )
    expect(api.updateRecipe).not.toHaveBeenCalled()
  })

  it.each([403, 409])(
    'błąd %s zachowuje cały formularz i ustawia fokus w komunikacie',
    async (status) => {
      api.updateRecipe.mockRejectedValue(
        new ApiError(status, {
          code: 'denied',
          message: 'Nie można teraz zapisać przepisu.',
          details: {},
        }),
      )
      const { wrapper } = await setup('/przepisy/19/edytuj')
      await wrapper.get('[data-testid="recipe-name"]').setValue('Moja zmiana')
      await submit(wrapper)
      await vi.waitFor(() =>
        expect(document.activeElement).toBe(
          wrapper.get('[data-testid="recipe-editor-error"]').element,
        ),
      )
      expect(wrapper.get<HTMLInputElement>('[data-testid="recipe-name"]').element.value).toBe(
        'Moja zmiana',
      )
      expect(
        wrapper.get<HTMLInputElement>('[data-testid="ingredient-amount-0"]').element.value,
      ).toBe('200')
      expect(wrapper.get('[data-testid="recipe-dirty-status"]').text()).toContain(
        'Masz niezapisane',
      )
    },
  )

  it.each(['difficulty', 'ingredients.0.quantity', 'ingredients.0.unit'])(
    '422 mapuje %s na pole, fokus po odblokowaniu formularza i pozostawia dane',
    async (field) => {
      api.updateRecipe.mockRejectedValue(
        new ApiError(422, {
          code: 'validation_error',
          message: 'Popraw dane przepisu.',
          details: { fields: [{ field, message: 'English message' }] },
        }),
      )
      const { wrapper } = await setup('/przepisy/19/edytuj')
      await wrapper.get('[data-testid="recipe-name"]').setValue('Nie zgub')
      const testid =
        field === 'difficulty'
          ? 'recipe-difficulty'
          : field.endsWith('unit')
            ? 'ingredient-amount-0-unit'
            : 'ingredient-amount-0'
      const target = wrapper.get<HTMLElement>(`[data-testid="${testid}"]`).element
      const focus = vi.spyOn(target, 'focus')
      const scrollIntoView = vi.fn(() => {
        expect(target.matches(':disabled')).toBe(false)
        expect(document.activeElement).toBe(target)
        if (field === 'difficulty') expect(target.closest('details')!.open).toBe(true)
      })
      Object.defineProperty(target, 'scrollIntoView', { value: scrollIntoView, configurable: true })
      await submit(wrapper)
      await vi.waitFor(() =>
        expect(document.activeElement).toBe(wrapper.get(`[data-testid="${testid}"]`).element),
      )
      expect(focus).toHaveBeenCalledWith({ preventScroll: true })
      expect(scrollIntoView).toHaveBeenCalledExactlyOnceWith({
        block: 'center',
        inline: 'nearest',
        behavior: 'instant',
      })
      expect(wrapper.text()).not.toContain('English message')
      expect(wrapper.get<HTMLInputElement>('[data-testid="recipe-name"]').element.value).toBe(
        'Nie zgub',
      )
      expect(wrapper.get('[data-testid="recipe-submit"]').attributes('disabled')).toBeUndefined()
    },
  )

  it('błąd przelicznika produktu wskazuje jego jednostkę, nie pierwsze pole formularza', async () => {
    api.updateRecipe.mockRejectedValue(
      new ApiError(422, {
        code: 'unit_conversion',
        message: 'Brak przelicznika jednostki.',
        details: { product_id: 1, unit: 'łyżka' },
      }),
    )
    const { wrapper } = await setup('/przepisy/19/edytuj')
    await submit(wrapper)
    await vi.waitFor(() =>
      expect(document.activeElement).toBe(
        wrapper.get('[data-testid="ingredient-amount-0-unit"]').element,
      ),
    )
    expect(wrapper.get('[data-testid="ingredient-error-0"]').text()).toBe(
      'Brak przelicznika jednostki.',
    )
  })

  it('422 dla niedostępnego produktu wskazuje wybór produktu, a 409 pokazuje rzeczywiste użycia', async () => {
    api.updateRecipe
      .mockRejectedValueOnce(
        new ApiError(422, {
          code: 'validation_error',
          message: 'Produkt jest niedostępny.',
          details: { product_ids: [1] },
        }),
      )
      .mockRejectedValueOnce(
        new ApiError(409, {
          code: 'conflict',
          message: 'Przepis jest używany poza rodziną.',
          details: { used_in: [{ name: 'Obiad w planie 2031-04-09', type: 'plan_day', id: 4 }] },
        }),
      )
    const { wrapper } = await setup('/przepisy/19/edytuj')
    await submit(wrapper)
    await vi.waitFor(() =>
      expect(document.activeElement).toBe(wrapper.get('[data-testid="picker-change"]').element),
    )
    expect(wrapper.get('[data-testid="ingredient-error-0"]').text()).toContain(
      'Wybierz inny produkt',
    )
    await submit(wrapper)
    await vi.waitFor(() =>
      expect(wrapper.get('[data-testid="recipe-editor-used-in"]').text()).toContain(
        'Obiad w planie 2031-04-09',
      ),
    )
    expect(wrapper.get<HTMLInputElement>('[data-testid="ingredient-amount-0"]').element.value).toBe(
      '200',
    )
  })

  it('nieudany upload pozwala ponowić ten sam plik, a usunięcie zdjęcia ma rzeczywisty wynik', async () => {
    const uploaded = {
      ...detail(),
      photo_url: '/uploads/photo.jpg',
      photo_thumb_url: '/uploads/photo_thumb.jpg',
    }
    api.uploadRecipePhoto
      .mockRejectedValueOnce(
        new ApiError(413, {
          code: 'payload_too_large',
          message: 'Zdjęcie jest za duże.',
          details: {},
        }),
      )
      .mockResolvedValueOnce(uploaded)
    api.deleteRecipePhoto.mockResolvedValue(detail())
    const { wrapper } = await setup('/przepisy/19/edytuj')
    const input = wrapper.get<HTMLInputElement>('[data-testid="recipe-photo-input"]')
    Object.defineProperty(input.element, 'files', {
      value: [new File(['same photo'], 'photo.png', { type: 'image/png' })],
    })
    await input.trigger('change')
    await vi.waitFor(() =>
      expect(wrapper.get('[data-testid="recipe-photo-error"]').text()).toBe(
        'Zdjęcie jest za duże.',
      ),
    )
    expect(input.element.value).toBe('')
    api.fetchRecipe.mockResolvedValue(uploaded)
    await input.trigger('change')
    await vi.waitFor(() =>
      expect(wrapper.get('[data-testid="recipe-photo-preview"]').attributes('src')).toBe(
        '/uploads/photo_thumb.jpg',
      ),
    )
    expect(wrapper.find('[data-testid="recipe-photo-error"]').exists()).toBe(false)
    api.fetchRecipe.mockResolvedValue(detail())
    await wrapper.get('[data-testid="recipe-photo-remove"]').trigger('click')
    await vi.waitFor(() =>
      expect(wrapper.get('[data-testid="recipe-photo-success"]').text()).toBe('Zdjęcie usunięte.'),
    )
    expect(wrapper.find('[data-testid="recipe-photo-preview"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="recipe-photo-empty"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="recipe-dirty-status"]').text()).toBe(
      'Brak niezapisanych zmian',
    )
  })

  it('refetch i operacje zdjęcia nie nadpisują niezapisanych pól; upload blokuje duplikaty i daje status', async () => {
    const upload = deferred<RecipeDetail>()
    api.uploadRecipePhoto.mockReturnValue(upload.promise)
    const { wrapper, queryClient } = await setup('/przepisy/19/edytuj')
    await wrapper.get('[data-testid="recipe-name"]').setValue('Niezapisana nazwa')
    const input = wrapper.get<HTMLInputElement>('[data-testid="recipe-photo-input"]')
    Object.defineProperty(input.element, 'files', {
      value: [new File(['photo'], 'photo.png', { type: 'image/png' })],
    })
    await input.trigger('change')
    await flushPromises()
    expect(wrapper.get('[data-testid="recipe-photo-pending"]').text()).toContain('Przesyłanie')
    expect(input.attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="recipe-submit"]').attributes('disabled')).toBeDefined()
    const saved = {
      ...detail(),
      photo_url: '/uploads/new.jpg',
      photo_thumb_url: '/uploads/new_thumb.jpg',
    }
    api.fetchRecipe.mockResolvedValue(saved)
    upload.resolve(saved)
    await vi.waitFor(() =>
      expect(wrapper.get('[data-testid="recipe-photo-success"]').text()).toBe('Zdjęcie zapisane.'),
    )
    expect(wrapper.get('[data-testid="recipe-photo-preview"]').attributes('src')).toBe(
      '/uploads/new_thumb.jpg',
    )
    expect(wrapper.get<HTMLInputElement>('[data-testid="recipe-name"]').element.value).toBe(
      'Niezapisana nazwa',
    )
    await queryClient.invalidateQueries({ queryKey: queryKeys.recipes.all })
    expect(wrapper.get<HTMLInputElement>('[data-testid="recipe-name"]').element.value).toBe(
      'Niezapisana nazwa',
    )
  })

  it('błąd zdjęcia jest lokalny, zachowuje poprzedni obraz i nie czyści brudnego formularza', async () => {
    api.fetchRecipe.mockResolvedValue({
      ...detail(),
      photo_url: '/uploads/old.jpg',
      photo_thumb_url: '/uploads/old_thumb.jpg',
    })
    api.deleteRecipePhoto.mockRejectedValue(
      new ApiError(403, {
        code: 'forbidden',
        message: 'Nie masz uprawnień do zdjęcia.',
        details: {},
      }),
    )
    const { wrapper } = await setup('/przepisy/19/edytuj')
    await wrapper.get('[data-testid="recipe-name"]').setValue('Zachowaj')
    await wrapper.get('[data-testid="recipe-photo-remove"]').trigger('click')
    await vi.waitFor(() =>
      expect(document.activeElement).toBe(
        wrapper.get('[data-testid="recipe-photo-error"]').element,
      ),
    )
    expect(wrapper.get('[data-testid="recipe-photo-preview"]').attributes('src')).toBe(
      '/uploads/old_thumb.jpg',
    )
    expect(wrapper.get<HTMLInputElement>('[data-testid="recipe-name"]').element.value).toBe(
      'Zachowaj',
    )
    expect(wrapper.find('[data-testid="recipe-editor-error"]').exists()).toBe(false)
  })

  it('globalny USER ma wszystkie pola zablokowane, a kopia otwiera własny edytor', async () => {
    api.fetchRecipe.mockImplementation((id: number) =>
      Promise.resolve({ ...detail(id), scope: id === 19 ? 'global' : 'household' }),
    )
    const { wrapper, router } = await setup('/przepisy/19/edytuj?q=zupa', 'user')
    expect(wrapper.get('[data-testid="recipe-read-only"]').text()).toContain('tylko do odczytu')
    for (const id of [
      'recipe-name',
      'recipe-instructions',
      'ingredient-add',
      'ingredient-note-0',
      'recipe-photo-input',
    ]) {
      expect(wrapper.get(`[data-testid="${id}"]`).attributes('disabled')).toBeDefined()
    }
    await submit(wrapper)
    expect(api.updateRecipe).not.toHaveBeenCalled()
    await wrapper.get('[data-testid="recipe-editor-copy"]').trigger('click')
    await flushPromises()
    await vi.waitFor(() => expect(router.currentRoute.value.params.id).toBe('99'))
    expect(router.currentRoute.value.name).toBe('przepis-edycja')
    expect(router.currentRoute.value.query).toEqual({ q: 'zupa' })
    expect(api.copyRecipe).toHaveBeenCalledWith(19)
    expect(window.confirm).not.toHaveBeenCalled()
  })

  it('zmiana generacji sesji omija ostrzeżenie i odrzuca spóźniony zapis', async () => {
    const pending = deferred<RecipeDetail>()
    api.createRecipe.mockReturnValue(pending.promise)
    const { wrapper, router, queryClient } = await setup()
    await wrapper.get('[data-testid="recipe-name"]').setValue('Prywatny szkic')
    await submit(wrapper)
    advanceSessionGeneration()
    await flushPromises()
    expect(wrapper.find('[data-testid="recipe-name"]').exists()).toBe(false)
    await router.push('/login')
    pending.resolve(detail(77))
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('login')
    expect(window.confirm).not.toHaveBeenCalled()
    expect(queryClient.getQueryData(queryKeys.recipes.detail(77, '1'))).toBeUndefined()
  })

  it('spóźniona odpowiedź po świadomym opuszczeniu nie przejmuje nawigacji', async () => {
    const pending = deferred<RecipeDetail>()
    api.createRecipe.mockReturnValue(pending.promise)
    const { wrapper, router } = await setup()
    await wrapper.get('[data-testid="recipe-name"]').setValue('Szkic')
    await submit(wrapper)
    vi.mocked(window.confirm).mockReturnValue(true)
    await router.push('/przepisy')
    pending.resolve(detail(77))
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('przepisy')
  })

  it('pierwszy odczyt i błąd nie pokazują edytowalnego pustego przepisu', async () => {
    const pending = deferred<RecipeDetail>()
    api.fetchRecipe.mockReturnValue(pending.promise)
    const { wrapper } = await setup('/przepisy/19/edytuj')
    expect(wrapper.find('[data-testid="recipe-editor-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-form"]').exists()).toBe(false)
    pending.reject(
      new ApiError(404, { code: 'not_found', message: 'Nie znaleziono przepisu.', details: {} }),
    )
    await vi.waitFor(() =>
      expect(wrapper.get('[data-testid="recipe-editor-load-error"]').text()).toContain(
        'Nie znaleziono przepisu.',
      ),
    )
    expect(wrapper.find('[data-testid="recipe-form"]').exists()).toBe(false)
  })

  it('zmiana produktu zachowuje pozostałe składniki i notatki', async () => {
    const { wrapper } = await setup('/przepisy/19/edytuj')
    await wrapper.get('[data-testid="ingredient-add"]').trigger('click')
    wrapper
      .findAllComponents(ProductPicker)[1]!
      .vm.$emit('selected', { id: 2, name: 'Nowy produkt', measure_kind: 'volume' })
    await flushPromises()
    await wrapper.get('[data-testid="ingredient-amount-1"]').setValue('12,5')
    await submit(wrapper)
    await vi.waitFor(() => expect(api.updateRecipe).toHaveBeenCalled())
    expect(api.updateRecipe).toHaveBeenCalledWith(
      19,
      expect.objectContaining({
        ingredients: [
          { product_id: 1, quantity: '200', unit: 'g', note: 'Al dente' },
          { product_id: 2, quantity: '12.5', unit: 'ml', note: '' },
        ],
      }),
    )
  })
})
