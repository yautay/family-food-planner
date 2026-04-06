<template>
  <section class="surface-card">
    <h1 class="title is-4">Konto</h1>

    <p v-if="authStore.user">
      Zalogowany: <strong>{{ authStore.user.username }}</strong> ({{ authStore.user.email }})
    </p>

    <div class="badge-list">
      <span v-for="role in authStore.roles" :key="role" class="badge">{{ role }}</span>
    </div>

    <form @submit.prevent="onSubmit" class="form-grid compact">
      <h2 class="title is-5">Zmiana hasla</h2>

      <label>
        Aktualne haslo
        <input v-model="currentPassword" class="input" type="password" required autocomplete="current-password" />
      </label>

      <label>
        Nowe haslo
        <input v-model="newPassword" class="input" type="password" required autocomplete="new-password" />
      </label>

      <p v-if="message" class="success-message">{{ message }}</p>
      <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

      <button class="button is-primary" type="submit">Zmien haslo</button>
    </form>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '../stores/authStore'

const authStore = useAuthStore()

const currentPassword = ref('')
const newPassword = ref('')
const message = ref('')
const errorMessage = ref('')

async function onSubmit() {
  message.value = ''
  errorMessage.value = ''

  try {
    await authStore.changePassword(currentPassword.value, newPassword.value)
    message.value = 'Haslo zostalo zmienione. Zaloguj sie ponownie.'
    await authStore.logout()
  } catch (error) {
    errorMessage.value = error?.response?.data?.error ?? 'Nie udalo sie zmienic hasla'
  }
}
</script>
