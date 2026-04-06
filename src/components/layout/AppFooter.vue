<script setup>
import { computed } from 'vue'
import { useI18n } from '../../composables/useI18n'
import { appMeta } from '../../config/appMeta'

const { t } = useI18n()

const currentYear = computed(() => new Date().getFullYear())
const repositoryLabel = computed(() => appMeta.repositoryUrl.replace(/^https?:\/\//, ''))
</script>

<template>
  <footer class="app-footer" role="contentinfo">
    <div class="container app-footer-content">
      <p>{{ t('footer.copyright', { year: String(currentYear) }) }}</p>
      <p>{{ t('footer.author') }}: {{ appMeta.author }}</p>
      <p>
        {{ t('footer.repository') }}:
        <a :href="appMeta.repositoryUrl" target="_blank" rel="noopener noreferrer">{{
          repositoryLabel
        }}</a>
      </p>
      <p>
        {{ t('footer.version') }}: {{ appMeta.version }} | {{ t('footer.codename') }}:
        {{ appMeta.codename }}
      </p>
    </div>
  </footer>
</template>

<style scoped>
.app-footer {
  border-top: 1px solid var(--app-border);
  background: var(--app-surface-alt);
}

.app-footer-content {
  min-height: 4.5rem;
  padding: 0.95rem 0.75rem;
  display: grid;
  gap: 0.2rem;
  font-size: 0.88rem;
  color: var(--app-muted);
}

.app-footer-content a {
  color: var(--app-link);
}

@media (min-width: 820px) {
  .app-footer-content {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.35rem 0.75rem;
  }
}
</style>
