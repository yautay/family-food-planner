<template>
  <section class="surface-card">
    <div class="content mb-4">
      <h1>{{ t('home.title') }}</h1>
      <p>{{ t('home.description') }}</p>
    </div>

    <div class="columns is-multiline">
      <div class="column is-4-desktop is-6-tablet">
        <RouterLink to="/catalog" class="box is-block">
          <h2 class="title is-5 mb-2">{{ t('home.catalogTitle') }}</h2>
          <p class="is-size-6 has-text-grey">{{ t('home.catalogDescription') }}</p>
        </RouterLink>
      </div>

      <div class="column is-4-desktop is-6-tablet">
        <RouterLink to="/ingredients" class="box is-block">
          <h2 class="title is-5 mb-2">{{ t('home.ingredientsTitle') }}</h2>
          <p class="is-size-6 has-text-grey">{{ t('home.ingredientsDescription') }}</p>
        </RouterLink>
      </div>

      <div class="column is-4-desktop is-6-tablet">
        <RouterLink to="/settings" class="box is-block">
          <h2 class="title is-5 mb-2">{{ t('home.settingsTitle') }}</h2>
          <p class="is-size-6 has-text-grey">{{ t('home.settingsDescription') }}</p>
        </RouterLink>
      </div>
    </div>
  </section>
</template>

<script setup>
import { RouterLink } from 'vue-router'
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()
</script>
