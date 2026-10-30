import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RecipeImage from './RecipeImage.vue'

describe('RecipeImage', () => {
  it('pokazuje rzeczywiste zdjęcie z opisem oraz ilustrację po błędzie ładowania', async () => {
    const wrapper = mount(RecipeImage, {
      props: { src: '/uploads/zurek.jpg', alt: 'Zdjęcie: Żurek' },
    })
    expect(wrapper.get('img').attributes('alt')).toBe('Zdjęcie: Żurek')
    await wrapper.get('img').trigger('error')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.get('[role="img"]').attributes('aria-label')).toContain('brak zdjęcia')
    expect(wrapper.get('[aria-hidden="true"]').classes()).toContain('pointer-events-none')
    await wrapper.setProps({ src: '/uploads/nowy-zurek.jpg' })
    expect(wrapper.get('img').attributes('src')).toBe('/uploads/nowy-zurek.jpg')
  })

  it('brak zdjęcia nie zamienia się w wielką pierwszą literę nazwy', () => {
    const wrapper = mount(RecipeImage, { props: { alt: 'Żurek' } })
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toBe('')
    expect(wrapper.get('[data-testid="recipe-image-fallback"]').attributes('role')).toBe('img')
  })
})
