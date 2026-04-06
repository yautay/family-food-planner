<script setup>
import { RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/authStore'
import { useI18n } from '../composables/useI18n'

const authStore = useAuthStore()
const { t } = useI18n()
</script>

<template>
  <section class="settings-layout">
    <article class="surface-card section-stack">
      <h1 class="title is-4">{{ t('settings.title') }}</h1>
      <p class="muted">{{ t('settings.description') }}</p>
    </article>

    <article class="surface-card section-stack">
      <h2 class="title is-5">{{ t('settings.planningSection') }}</h2>
      <div class="settings-actions">
        <RouterLink class="button" to="/meals">{{ t('settings.plannerLink') }}</RouterLink>
      </div>
    </article>

    <article class="surface-card section-stack">
      <h2 class="title is-5">{{ t('settings.catalogSection') }}</h2>
      <div class="settings-actions">
        <RouterLink class="button" to="/catalog">{{ t('settings.catalogLink') }}</RouterLink>
        <RouterLink class="button" to="/ingredients">{{
          t('settings.ingredientsLink')
        }}</RouterLink>
        <RouterLink class="button" to="/units">{{ t('settings.unitsLink') }}</RouterLink>
        <RouterLink class="button" to="/packages">{{ t('settings.packagesLink') }}</RouterLink>
        <RouterLink class="button" to="/tags">{{ t('settings.tagsLink') }}</RouterLink>
        <RouterLink class="button" to="/recipes">{{ t('settings.recipesLink') }}</RouterLink>
      </div>
    </article>

    <article class="surface-card section-stack">
      <h2 class="title is-5">{{ t('settings.userSection') }}</h2>
      <div class="settings-actions">
        <RouterLink class="button" to="/account">{{ t('settings.accountLink') }}</RouterLink>
        <RouterLink v-if="authStore.can('permissions.manage')" class="button" to="/access-control">
          {{ t('settings.aclLink') }}
        </RouterLink>
      </div>
    </article>
  </section>
</template>

<style scoped>
.settings-layout {
  display: grid;
  gap: 1rem;
}

.section-stack {
  display: grid;
  gap: 0.55rem;
}

.settings-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}
</style>
