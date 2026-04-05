<template>
  <section class="auth-page">
    <div class="auth-card">
      <h1>Reset hasla</h1>

      <form @submit.prevent="onSubmit" class="form-grid">
        <label>
          Email
          <input v-model="email" type="email" required autocomplete="email" />
        </label>

        <TurnstileWidget v-if="captchaSiteKey" v-model="captchaToken" :site-key="captchaSiteKey" />

        <p v-if="message" class="success-message">{{ message }}</p>
        <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

        <button type="submit" class="btn-primary">Wyslij link resetu</button>
      </form>

      <div class="auth-links">
        <RouterLink to="/login">Powrot do logowania</RouterLink>
      </div>
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/authStore'
import TurnstileWidget from '../components/TurnstileWidget.vue'

const authStore = useAuthStore()
const email = ref('')
const captchaToken = ref('')
const captchaSiteKey = ref('')
const message = ref('')
const errorMessage = ref('')

onMounted(async () => {
  try {
    const config = await authStore.getCaptchaConfig()
    captchaSiteKey.value = config.turnstile_site_key
  } catch (_error) {
    captchaSiteKey.value = ''
  }
})

async function onSubmit() {
  message.value = ''
  errorMessage.value = ''

  if (!captchaToken.value) {
    errorMessage.value = 'Captcha is required'
    return
  }

  try {
    await authStore.forgotPassword(email.value, captchaToken.value)
    message.value = 'Jesli email istnieje, wyslalismy link resetu.'
  } catch (error) {
    errorMessage.value = error?.response?.data?.error ?? 'Request failed'
  }
}
</script>
