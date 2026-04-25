<template>
  <section class="auth-page section p-0">
    <div class="auth-card">
      <h1 class="title is-4">{{ t('auth.forgotTitle') }}</h1>

      <form @submit.prevent="onSubmit" class="form-grid">
        <label>
          {{ t('auth.email') }}
          <input v-model="email" class="input" type="email" required autocomplete="email" />
        </label>

        <TurnstileWidget v-if="captchaSiteKey" v-model="captchaToken" :site-key="captchaSiteKey" />

        <p v-if="message" class="success-message">{{ message }}</p>
        <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

        <button type="submit" class="button is-primary">{{ t('auth.forgotSubmit') }}</button>
      </form>

      <div class="auth-links">
        <RouterLink to="/login">{{ t('auth.backToLogin') }}</RouterLink>
      </div>
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/authStore'
import { useI18n } from '../composables/useI18n'
import TurnstileWidget from '../components/TurnstileWidget.vue'

const authStore = useAuthStore()
const { t } = useI18n()
const email = ref('')
const captchaToken = ref('')
const captchaSiteKey = ref('')
const captchaEnabled = ref(false)
const message = ref('')
const errorMessage = ref('')

onMounted(async () => {
  try {
    const config = await authStore.getCaptchaConfig()
    captchaEnabled.value = Boolean(config.captcha_enabled)
    captchaSiteKey.value = config.turnstile_site_key ?? ''
  } catch (_error) {
    captchaEnabled.value = false
    captchaSiteKey.value = ''
  }
})

async function onSubmit() {
  message.value = ''
  errorMessage.value = ''

  if (captchaEnabled.value && !captchaToken.value) {
    errorMessage.value = t('auth.captchaRequired')
    return
  }

  try {
    await authStore.forgotPassword(
      email.value,
      captchaEnabled.value ? captchaToken.value : undefined,
    )
    message.value = t('auth.forgotSuccess')
  } catch (error) {
    errorMessage.value = error?.response?.data?.error ?? t('auth.requestFailed')
  }
}
</script>
