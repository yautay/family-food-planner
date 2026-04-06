<template>
  <section class="auth-page section p-0">
    <div class="auth-card">
      <h1 class="title is-4">{{ t('auth.registerTitle') }}</h1>

      <form @submit.prevent="onSubmit" class="form-grid">
        <label>
          {{ t('auth.username') }}
          <input v-model="username" class="input" required autocomplete="username" />
        </label>

        <label>
          {{ t('auth.email') }}
          <input v-model="email" class="input" type="email" required autocomplete="email" />
        </label>

        <label>
          {{ t('auth.password') }}
          <input
            v-model="password"
            class="input"
            type="password"
            required
            autocomplete="new-password"
          />
        </label>

        <TurnstileWidget v-if="captchaSiteKey" v-model="captchaToken" :site-key="captchaSiteKey" />

        <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

        <button type="submit" class="button is-primary">{{ t('auth.submitRegister') }}</button>
      </form>

      <div class="auth-links">
        <RouterLink to="/login">{{ t('auth.submitLogin') }}</RouterLink>
      </div>
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/authStore'
import { useI18n } from '../composables/useI18n'
import TurnstileWidget from '../components/TurnstileWidget.vue'

const router = useRouter()
const authStore = useAuthStore()
const { t } = useI18n()

const username = ref('')
const email = ref('')
const password = ref('')
const captchaToken = ref('')
const captchaSiteKey = ref('')
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
  errorMessage.value = ''

  if (!captchaToken.value) {
    errorMessage.value = t('auth.captchaRequired')
    return
  }

  try {
    await authStore.register({
      username: username.value,
      email: email.value,
      password: password.value,
      captcha_token: captchaToken.value,
    })
    await router.push('/catalog')
  } catch (error) {
    errorMessage.value = error?.response?.data?.error ?? t('auth.registrationFailed')
  }
}
</script>
