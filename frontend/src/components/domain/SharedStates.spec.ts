import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import EmptyState from './EmptyState.vue'
import ErrorState from './ErrorState.vue'
import PageHeader from './PageHeader.vue'
import SummaryPanel from './SummaryPanel.vue'
import LoadingState from './LoadingState.vue'
import FeedbackMessage from './FeedbackMessage.vue'

describe('Wspólne stany i nagłówki', () => {
  it('ogłasza ładowanie i potwierdzony wynik słowami, a skeleton jest dekoracją', () => {
    const loading = mount(LoadingState, { props: { label: 'Wczytywanie przepisów…' } })
    expect(loading.get('[role="status"]').attributes('aria-busy')).toBe('true')
    expect(loading.get('[aria-hidden="true"]').classes()).toContain('pointer-events-none')
    const feedback = mount(FeedbackMessage, {
      props: { tone: 'success', message: 'Przepis został zapisany.' },
    })
    expect(feedback.get('[role="status"]').text()).toBe('Przepis został zapisany.')
  })
  it('zachowuje hierarchię nagłówka, treść i akcje oraz ukrywa ozdoby przed czytnikiem', () => {
    const wrapper = mount(PageHeader, {
      props: {
        title: 'Plan dnia — Łucja i Żaneta',
        description: 'Późny obiad po spacerze',
        decoration: 'herbs',
        titleTestid: 'plan-date',
      },
      slots: { actions: '<button>Zaplanuj</button>' },
    })
    expect(wrapper.get('h1').text()).toContain('Łucja i Żaneta')
    expect(wrapper.get('[data-testid="plan-date"]').element.tagName).toBe('H1')
    expect(wrapper.get('[data-testid="header-decoration"]').attributes('aria-hidden')).toBe('true')
    expect(wrapper.get('button').text()).toBe('Zaplanuj')
  })

  it('pusty stan uczy i pozwala wykonać akcję', async () => {
    const wrapper = mount(EmptyState, {
      props: {
        title: 'Jeszcze nie ma przepisów',
        description: 'Dodaj pierwszy przepis do domowej książki.',
        actionLabel: 'Dodaj przepis',
      },
    })
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('action')).toHaveLength(1)
  })

  it('błąd odświeżenia nie usuwa danych rodzica, ponowienie ma stan oczekiwania', async () => {
    const wrapper = mount(ErrorState, {
      props: {
        title: 'Nie udało się odświeżyć',
        message: 'Widać ostatnio pobrane dane.',
        compact: true,
      },
      slots: { default: '<p>Żurek · 3 porcje</p>' },
    })
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
    await wrapper.setProps({ pending: true })
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Żurek · 3 porcje')
    expect(wrapper.get('[role="alert"]').text()).toContain('ostatnio pobrane dane')
  })

  it('podsumowanie nie wylicza i nie dorabia danych domenowych', () => {
    const wrapper = mount(SummaryPanel, {
      props: { title: 'Podsumowanie dnia' },
      slots: { default: '<p>Niepełne dane — brakuje wartości produktu.</p>' },
    })
    expect(wrapper.get('h2').text()).toBe('Podsumowanie dnia')
    expect(wrapper.text()).toContain('Niepełne dane')
  })
})
