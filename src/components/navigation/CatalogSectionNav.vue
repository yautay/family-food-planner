<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from '../../composables/useI18n'
import { catalogNavigationItems } from '../../config/navigation'

const { t } = useI18n()

const items = computed(() =>
  catalogNavigationItems.map((item) => ({
    ...item,
    label: t(item.labelKey),
  })),
)
</script>

<template>
  <nav class="catalog-section-nav" :aria-label="t('nav.catalog')">
    <RouterLink v-for="item in items" :key="item.key" :to="item.to" class="catalog-nav-link">
      {{ item.label }}
    </RouterLink>
  </nav>
</template>

<style scoped>
.catalog-section-nav {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0.45rem;
  margin-bottom: 1rem;
}

.catalog-nav-link {
  border: 1px solid var(--app-border);
  border-radius: 0.65rem;
  background: var(--app-surface-alt);
  color: var(--app-text);
  font-size: 0.9rem;
  font-weight: 600;
  text-align: center;
  padding: 0.45rem 0.6rem;
}

.catalog-nav-link.router-link-active {
  border-color: var(--app-accent);
  color: var(--app-accent);
  background: var(--app-surface);
}
</style>
