import { computed } from 'vue'
import { useUiStore } from '../stores/uiStore'
import { messages } from '../i18n/messages'

function getByPath(object, path) {
  return path.split('.').reduce((accumulator, key) => accumulator?.[key], object)
}

export function useI18n() {
  const uiStore = useUiStore()

  const locale = computed(() => uiStore.locale)

  const t = (key) => {
    const localizedValue = getByPath(messages[locale.value], key)
    if (localizedValue !== undefined) {
      return localizedValue
    }

    const fallbackValue = getByPath(messages.en, key)
    return fallbackValue ?? key
  }

  return {
    locale,
    t,
  }
}
