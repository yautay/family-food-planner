<template>
  <section class="surface-card">
    <h1 class="title is-4">{{ t('account.title') }}</h1>

    <p v-if="authStore.user">
      {{ t('account.loggedInAs') }}: <strong>{{ authStore.user.username }}</strong> ({{
        authStore.user.email
      }})
    </p>

    <div class="badge-list">
      <span v-for="role in authStore.roles" :key="role" class="badge">{{ role }}</span>
    </div>

    <form @submit.prevent="onSubmit" class="form-grid compact">
      <h2 class="title is-5">{{ t('account.changePasswordTitle') }}</h2>

      <label>
        {{ t('auth.currentPassword') }}
        <input
          v-model="currentPassword"
          class="input"
          type="password"
          required
          autocomplete="current-password"
        />
      </label>

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

      <button class="button is-primary" type="submit">
        {{ t('account.changePasswordSubmit') }}
      </button>
    </form>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '../stores/authStore'
import { useI18n } from '../composables/useI18n'

const authStore = useAuthStore()
const { t } = useI18n()

const currentPassword = ref('')
const newPassword = ref('')
const message = ref('')
const errorMessage = ref('')

async function onSubmit() {
  message.value = ''
  errorMessage.value = ''

  try {
    await authStore.changePassword(currentPassword.value, newPassword.value)
    message.value = t('account.changePasswordSuccess')
    await authStore.logout()
  } catch (error) {
    errorMessage.value = error?.response?.data?.error ?? t('account.changePasswordError')
  }
}
</script>
