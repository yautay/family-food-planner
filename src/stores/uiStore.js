import { defineStore } from 'pinia'

const THEME_STORAGE_KEY = 'ffp_theme'
const LOCALE_STORAGE_KEY = 'ffp_locale'

function getInitialTheme() {
  return localStorage.getItem(THEME_STORAGE_KEY) ?? 'system'
}

function getInitialLocale() {
  return localStorage.getItem(LOCALE_STORAGE_KEY) ?? 'pl'
}

export const useUiStore = defineStore('ui', {
  state: () => ({
    theme: getInitialTheme(),
    locale: getInitialLocale(),
  }),
  getters: {
    resolvedTheme: (state) => {
      if (state.theme !== 'system') {
        return state.theme
      }

      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    },
  },
  actions: {
    setTheme(theme) {
      this.theme = theme
      localStorage.setItem(THEME_STORAGE_KEY, theme)
    },
    setLocale(locale) {
      this.locale = locale
      localStorage.setItem(LOCALE_STORAGE_KEY, locale)
    },
  },
})
