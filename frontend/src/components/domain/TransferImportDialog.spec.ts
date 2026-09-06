import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type * as ApiClient from '@/api/client'
import type * as TransferApi from '@/api/transfer'

import TransferImportDialog from './TransferImportDialog.vue'

/**
 * Dialog importu — trzy kroki z karty B14 §Frontend.
 *
 * Najważniejsza asercja: między wgraniem pliku a kliknięciem „Zaimportuj" NIE
 * leci żaden `apply`. Dry-run istnieje właśnie po to, żeby użytkownik zobaczył
 * skutki przed zapisem (Acceptance Criterion 3), a regresja w tym miejscu jest
 * niewidoczna gołym okiem — po prostu import robi się sam.
 */
const { uploadForDryRun, applyImport } = vi.hoisted(() => ({
  uploadForDryRun: vi.fn(),
  applyImport: vi.fn(),
}))

vi.mock('@/api/transfer', async () => {
  const actual = await vi.importActual<typeof TransferApi>('@/api/transfer')
  return { ...actual, uploadForDryRun, applyImport }
})

function report(overrides: Record<string, unknown> = {}) {
  return {
    import_id: 'a'.repeat(32),
    schema_version: 1,
    scope: 'user',
    exported_at: '2026-08-29T10:00:00+00:00',
    app_version: '0.1.0',
    to_create: { recipes: 3, canonical_products: 2 },
    collisions: [],
    warnings: [],
    photos: 1,
    ...overrides,
  }
}

function collision(overrides: Record<string, unknown> = {}) {
  return {
    entity: 'canonical_products',
    source_id: 7,
    name: 'Cebula',
    existing_id: 99,
    existing_name: 'Cebula',
    default: 'use_existing',
    ...overrides,
  }
}

async function mountDialog(props: Record<string, unknown> = {}) {
  const wrapper = mount(TransferImportDialog, {
    props: { open: true, ...props },
    global: { plugins: [VueQueryPlugin] },
  })
  await flushPromises()
  return wrapper
}

/** Podmienia plik w inpucie: jsdom nie pozwala pisać do `files` wprost. */
async function pickFile(wrapper: Awaited<ReturnType<typeof mountDialog>>): Promise<void> {
  const input = wrapper.get('[data-testid="transfer-file"]').element as HTMLInputElement
  const file = new File([new Uint8Array([0x50, 0x4b, 3, 4])], 'export.zip', {
    type: 'application/zip',
  })
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  await wrapper.get('[data-testid="transfer-file"]').trigger('change')
}

describe('TransferImportDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    uploadForDryRun.mockResolvedValue(report())
    applyImport.mockResolvedValue({
      created: { recipes: 3 },
      reused: { canonical_products: 2 },
      photos_imported: 1,
      warnings: [],
    })
  })

  it('krok 1: bez wybranego pliku przycisk analizy jest nieaktywny', async () => {
    const wrapper = await mountDialog()

    expect(wrapper.find('[data-testid="transfer-step-file"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="transfer-analyze"]').attributes('disabled')).toBeDefined()
  })

  it('krok 2: raport pokazuje liczby per encja po polsku i NIC nie zapisuje', async () => {
    const wrapper = await mountDialog()

    await pickFile(wrapper)
    await wrapper.get('[data-testid="transfer-analyze"]').trigger('click')
    await flushPromises()

    expect(uploadForDryRun).toHaveBeenCalledTimes(1)
    // Sedno dry-runu: dopóki użytkownik nie potwierdzi, `apply` nie leci.
    expect(applyImport).not.toHaveBeenCalled()
    const table = wrapper.get('[data-testid="transfer-report-table"]').text()
    expect(table).toContain('Przepisy')
    expect(table).toContain('Produkty')
    expect(wrapper.get('[data-testid="transfer-row-recipes"]').text()).toContain('3')
  })

  it('kolizja: domyślna decyzja to „użyj istniejącego" i taka leci przy potwierdzeniu', async () => {
    uploadForDryRun.mockResolvedValue(report({ collisions: [collision()] }))
    const wrapper = await mountDialog()

    await pickFile(wrapper)
    await wrapper.get('[data-testid="transfer-analyze"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="transfer-confirm"]').trigger('click')
    await flushPromises()

    expect(applyImport).toHaveBeenCalledWith('a'.repeat(32), [
      { entity: 'canonical_products', source_id: 7, action: 'use_existing' },
    ])
  })

  it('kolizja: wybór „utwórz kopię" nadpisuje domyślną decyzję', async () => {
    uploadForDryRun.mockResolvedValue(report({ collisions: [collision()] }))
    const wrapper = await mountDialog()

    await pickFile(wrapper)
    await wrapper.get('[data-testid="transfer-analyze"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="transfer-create-copy-canonical_products-7"]').trigger('click')
    await wrapper.get('[data-testid="transfer-confirm"]').trigger('click')
    await flushPromises()

    expect(applyImport).toHaveBeenCalledWith('a'.repeat(32), [
      { entity: 'canonical_products', source_id: 7, action: 'create_copy' },
    ])
  })

  it('krok 3: podsumowanie pokazuje liczby utworzonych i reużytych wpisów', async () => {
    const wrapper = await mountDialog()

    await pickFile(wrapper)
    await wrapper.get('[data-testid="transfer-analyze"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="transfer-confirm"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="transfer-step-report"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="transfer-summary-created"]').text()).toContain('Przepisy: 3')
    expect(wrapper.get('[data-testid="transfer-summary-reused"]').text()).toContain('Produkty: 2')
  })

  it('błąd wersji pliku pokazuje komunikat z backendu, bez stacktrace', async () => {
    const { ApiError } = await vi.importActual<typeof ApiClient>('@/api/client')
    uploadForDryRun.mockRejectedValue(
      new ApiError(422, {
        code: 'validation_error',
        message: 'Plik pochodzi z nowszej lub innej wersji aplikacji (999).',
        details: {},
      }),
    )
    const wrapper = await mountDialog()

    await pickFile(wrapper)
    await wrapper.get('[data-testid="transfer-analyze"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="transfer-import-error"]').text()).toContain(
      'nowszej lub innej wersji aplikacji',
    )
    expect(wrapper.find('[data-testid="transfer-step-report"]').exists()).toBe(false)
  })

  it('ostrzeżenie o scaleniu dni planu ląduje w „Uwagach" (D24)', async () => {
    // Scalanie dnia planu jest MILCZĄCE w zapisie (D22/D24: posiłki zostają
    // nietknięte), więc jedynym miejscem, gdzie użytkownik może się o nim
    // dowiedzieć PRZED kliknięciem, jest raport. Bez tej asercji ostrzeżenie
    // z backendu mogłoby nigdzie się nie renderować i nikt by nie zauważył.
    uploadForDryRun.mockResolvedValue(
      report({
        to_create: { recipes: 1 },
        warnings: [
          '3 dni planu zostaną scalone z tym, co już masz — ' +
            'posiłki, które już tam są, zostaną nietknięte.',
        ],
      }),
    )
    const wrapper = await mountDialog()

    await pickFile(wrapper)
    await wrapper.get('[data-testid="transfer-analyze"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Uwagi')
    expect(wrapper.get('[data-testid="transfer-warnings"]').text()).toContain(
      '3 dni planu zostaną scalone',
    )
  })
})
