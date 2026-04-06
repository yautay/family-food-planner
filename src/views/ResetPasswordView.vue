<template>
  <section class="auth-page section p-0">
    <div class="auth-card">
      <h1 class="title is-4">{{ t('auth.resetTitle') }}</h1>

      <form @submit.prevent="onSubmit" class="form-grid">
        <label>
          {{ t('auth.newPassword') }}
          <input
            v-model="newPassword"
            class="input"
            type="password"
            required
            autocomplete="new-password"
          />
        </label>

        <p v-if="message" class="success-message">{{ message }}</p>
        <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

        <button type="submit" class="button is-primary">{{ t('auth.resetSubmit') }}</button>
      </form>

      <div class="auth-links">
        <RouterLink to="/login">{{ t('auth.backToLogin') }}</RouterLink>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/authStore'
import { useI18n } from '../composables/useI18n'

const route = useRoute()
const authStore = useAuthStore()
const { t } = useI18n()
const newPassword = ref('')
const message = ref('')
const errorMessage = ref('')

const token = computed(() => {
  const queryToken = route.query.token
  return typeof queryToken === 'string' ? queryToken : ''
})

async function onSubmit() {
  message.value = ''
  errorMessage.value = ''

  if (!token.value) {
    errorMessage.value = t('auth.resetMissingToken')
    return
  }

  try {
    await authStore.resetPassword(token.value, newPassword.value)
    message.value = t('auth.resetSuccess')
  } catch (error) {
    errorMessage.value = error?.response?.data?.error ?? t('auth.resetFailed')
  }
}
</script>
