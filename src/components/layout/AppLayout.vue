<script setup>
import { RouterView, useRoute } from 'vue-router'
import { watch } from 'vue'
import AppHeader from './AppHeader.vue'
import AppFooter from './AppFooter.vue'

const route = useRoute()

watch(
  () => route.fullPath,
  () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  },
)
</script>

<template>
  <div class="app-layout">
    <AppHeader />

    <main class="section app-main-section">
      <div class="container app-main-container">
        <RouterView />
      </div>
    </main>

    <AppFooter />
  </div>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-main-section {
  flex: 1;
  padding-top: 1.25rem;
  padding-bottom: 1.4rem;
}

.app-main-container {
  max-width: 1180px;
}

@media (max-width: 768px) {
  .app-main-section {
    padding-top: 1rem;
    padding-bottom: 1rem;
  }
}
</style>
