<script setup>
import { onMounted, watch } from 'vue'
import AppLayout from './components/layout/AppLayout.vue'
import { useAuthStore } from './stores/authStore'
import { useUiStore } from './stores/uiStore'

const authStore = useAuthStore()
const uiStore = useUiStore()

function applyTheme() {
  document.documentElement.setAttribute('data-theme', uiStore.resolvedTheme)
}

watch(
  () => uiStore.theme,
  () => applyTheme(),
  { immediate: true },
)

onMounted(async () => {
  await authStore.initialize()
})
</script>

<template>
  <AppLayout />
</template>
