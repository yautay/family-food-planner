import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { createMemoryHistory, createRouter, RouterLink } from 'vue-router'

import { routes } from '@/router'

import { Button } from '.'

/**
 * Regres z BATCH_04/05 wykryty w E2E (ustalenie zaparkowane dla R2).
 *
 * `<Button as="router-link">` NIE renderuje linku: reka-ui `Primitive` wywołuje
 * `h(props.as, …)`, a `h()` z ciągiem znaków tworzy ELEMENT o tej nazwie, nie
 * komponent. W przeglądarce powstawał nieznany tag `<router-link>` — bez `href`,
 * bez nawigacji i bez roli `link` dla czytnika ekranu (snapshot ARIA
 * Playwrighta pokazywał w tym miejscu goły tekst). Dziewięć przycisków
 * „Dodaj produkt"/„Edytuj"/„Wróć do listy" było martwe.
 *
 * Poprawny wzorzec to `as-child` z zagnieżdżonym `<RouterLink>`: `Primitive`
 * renderuje wtedy `Slot`, który scala atrybuty (w tym klasy `buttonVariants`)
 * z prawdziwym linkiem.
 */
async function mountLinkButton() {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/produkty')
  await router.isReady()

  return mount(
    {
      render: () =>
        h(Button, { asChild: true, variant: 'outline', class: 'min-h-11' }, () => [
          h(
            RouterLink,
            { to: { name: 'produkt-nowy' }, 'data-testid': 'products-add' },
            () => 'Dodaj produkt',
          ),
        ]),
    },
    { global: { plugins: [router] } },
  )
}

describe('Button', () => {
  it('domyślnie renderuje element <button>', () => {
    const wrapper = mount(Button, { slots: { default: 'Zapisz' } })

    expect(wrapper.element.tagName).toBe('BUTTON')
  })

  it('z `as-child` i RouterLinkiem renderuje <a> z href-em', async () => {
    const wrapper = await mountLinkButton()

    const link = wrapper.get('[data-testid="products-add"]')
    expect(link.element.tagName).toBe('A')
    expect(link.attributes('href')).toBe('/produkty/nowy')
    expect(link.text()).toBe('Dodaj produkt')
  })

  it('z `as-child` zachowuje klasy wariantu na linku', async () => {
    const wrapper = await mountLinkButton()

    const link = wrapper.get('[data-testid="products-add"]')
    // Klasy z `buttonVariants` scala `Slot` przez `mergeProps` — bez tego link
    // wyglądałby jak zwykły tekst, a przycisk zniknąłby z interfejsu.
    expect(link.classes()).toContain('min-h-11')
    expect(link.classes()).toContain('inline-flex')
    expect(link.attributes('data-slot')).toBe('button')
  })
})

/**
 * Strażnik na cały katalog źródeł: testy komponentu pokrywają wzorzec POPRAWNY,
 * ale nie powiedzą nic o dziewiątym miejscu, w którym ktoś znów napisze
 * `as="router-link"`. Ten test pilnuje właśnie tego — jest tani i łapie
 * dokładnie ten regres, który przeszedł przez cztery batche niezauważony.
 */
describe('nawigacja w komponentach', () => {
  // `import.meta.glob` zamiast `node:fs`: tsconfig aplikacji nie ma typów Node'a,
  // a Vite i tak potrafi wczytać źródła jako tekst (`?raw`) w czasie testu.
  const sources = import.meta.glob('/src/**/*.vue', {
    query: '?raw',
    eager: true,
    import: 'default',
  }) as Record<string, string>

  it('nie używa nazwy komponentu jako ciągu znaków w propsie `as`', () => {
    const offenders = Object.entries(sources)
      .filter(([, source]) => /\bas="(router-link|RouterLink)"/.test(source))
      .map(([file]) => file)

    expect(
      offenders,
      'Użyj `as-child` z zagnieżdżonym <RouterLink> — `as="router-link"` renderuje nieznany tag, nie link',
    ).toEqual([])
  })
})
