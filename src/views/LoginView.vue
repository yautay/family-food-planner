<template>
  <section class="auth-page section p-0">
    <div class="auth-card">
      <h1 class="title is-4">{{ t('auth.loginTitle') }}</h1>

      <form @submit.prevent="onSubmit" class="form-grid">
        <label>
          {{ t('auth.emailOrUsername') }}
          <input v-model="identity" class="input" required autocomplete="username" />
        </label>

        <label>
          {{ t('auth.password') }}
          <input v-model="password" class="input" type="password" required autocomplete="current-password" />
        </label>

        <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

        <button type="submit" class="button is-primary">{{ t('auth.submitLogin') }}</button>
      </form>

      <div class="auth-links">
        <RouterLink to="/register">{{ t('auth.submitRegister') }}</RouterLink>
        <RouterLink to="/forgot-password">{{ t('auth.forgotPassword') }}</RouterLink>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute, RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/authStore'
import { useI18n } from '../composables/useI18n'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const { t } = useI18n()

const identity = ref('')
const password = ref('')
const errorMessage = ref('')

async function onSubmit() {
  errorMessage.value = ''

  try {
    await authStore.login(identity.value, password.value)
    const redirectPath = typeof route.query.redirect === 'string' ? route.query.redirect : '/catalog'
    await router.push(redirectPath)
  } catch (error) {
    errorMessage.value = error?.response?.data?.error ?? 'Login failed'
  }
}
</script>
