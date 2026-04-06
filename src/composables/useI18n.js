import { computed } from 'vue'
import { useUiStore } from '../stores/uiStore'
import { messages } from '../i18n/messages'

function getByPath(object, path) {
  return path.split('.').reduce((accumulator, key) => accumulator?.[key], object)
}

function interpolate(message, params = {}) {
  if (typeof message !== 'string') {
    return message
  }

  return message.replace(/\{\{\s*(\w+)\s*\}\}/g, (_match, key) => {
    const value = params[key]
    return value === undefined || value === null ? '' : String(value)
  })
}

export function useI18n() {
  const uiStore = useUiStore()

  const locale = computed(() => uiStore.locale)

  const t = (key, params) => {
    const localizedValue = getByPath(messages[locale.value], key)
    if (localizedValue !== undefined) {
      return interpolate(localizedValue, params)
    }

    const fallbackValue = getByPath(messages.en, key)
    return interpolate(fallbackValue ?? key, params)
  }

  return {
    locale,
    t,
  }
}
