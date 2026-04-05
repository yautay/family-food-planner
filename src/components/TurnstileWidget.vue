<template>
  <div class="turnstile-container">
    <div ref="widgetElement"></div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  siteKey: {
    type: String,
    required: true,
  },
  modelValue: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:modelValue'])
const widgetElement = ref(null)
let widgetId = null

function loadTurnstileScript() {
  if (window.turnstile) {
    return Promise.resolve()
  }

  if (window.__turnstileLoaderPromise) {
    return window.__turnstileLoaderPromise
  }

  window.__turnstileLoaderPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load Turnstile script'))
    document.head.appendChild(script)
  })

  return window.__turnstileLoaderPromise
}

async function renderWidget() {
  if (!props.siteKey || !widgetElement.value) {
    return
  }

  await loadTurnstileScript()

  widgetId = window.turnstile.render(widgetElement.value, {
    sitekey: props.siteKey,
    callback: (token) => emit('update:modelValue', token),
    'expired-callback': () => emit('update:modelValue', ''),
    'error-callback': () => emit('update:modelValue', ''),
  })
}

onMounted(() => {
  renderWidget().catch(() => emit('update:modelValue', ''))
})

watch(
  () => props.siteKey,
  () => {
    if (!window.turnstile || !widgetId) {
      return
    }
    window.turnstile.remove(widgetId)
    widgetId = null
    emit('update:modelValue', '')
    renderWidget().catch(() => emit('update:modelValue', ''))
  },
)

onBeforeUnmount(() => {
  if (window.turnstile && widgetId) {
    window.turnstile.remove(widgetId)
  }
})
</script>

<style scoped>
.turnstile-container {
  display: flex;
  justify-content: flex-start;
}
</style>
