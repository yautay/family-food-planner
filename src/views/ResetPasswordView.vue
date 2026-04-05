<template>
  <section class="auth-page">
    <div class="auth-card">
      <h1>Ustaw nowe haslo</h1>

      <form @submit.prevent="onSubmit" class="form-grid">
        <label>
          Nowe haslo
          <input v-model="newPassword" type="password" required autocomplete="new-password" />
        </label>

        <p v-if="message" class="success-message">{{ message }}</p>
        <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

        <button type="submit" class="btn-primary">Zmien haslo</button>
      </form>

      <div class="auth-links">
        <RouterLink to="/login">Powrot do logowania</RouterLink>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/authStore'

const route = useRoute()
const authStore = useAuthStore()
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
    errorMessage.value = 'Brak tokenu resetu hasla'
    return
  }

  try {
    await authStore.resetPassword(token.value, newPassword.value)
    message.value = 'Haslo zmienione. Mozesz sie zalogowac.'
  } catch (error) {
    errorMessage.value = error?.response?.data?.error ?? 'Reset failed'
  }
}
</script>
