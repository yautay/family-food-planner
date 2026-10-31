<script setup lang="ts">
/**
 * Ekran logowania (ADR-003: sesja w cookie HttpOnly, bez tokenów w JS).
 *
 * Walidacja formularza to wyłącznie UX — prawdą jest odpowiedź serwera:
 * 401 „nieprawidłowe dane" (neutralne, bez zdradzania czy konto istnieje)
 * i 429 „zbyt wiele prób" pokazujemy pod formularzem.
 */
import { toTypedSchema } from '@vee-validate/zod'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { useForm } from 'vee-validate'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as z from 'zod'

import type { LoginPayload } from '@/api/auth'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { APP_NAME, APP_TAGLINE, auth as texts, common } from '@/lib/texts'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()
const queryClient = useQueryClient()

const schema = toTypedSchema(
  z.object({
    email: z
      .string({ required_error: texts.emailRequired })
      .min(1, texts.emailRequired)
      .email(texts.emailInvalid),
    password: z.string({ required_error: texts.passwordRequired }).min(1, texts.passwordRequired),
  }),
)

const { handleSubmit, errors, defineField } = useForm({ validationSchema: schema })
const [email, emailAttrs] = defineField('email')
const [password, passwordAttrs] = defineField('password')

/** Adres powrotu z guardu — tylko ścieżka względna (żadnych przekierowań na obce hosty). */
function safeNext(): string | null {
  const next = route.query.next
  if (typeof next !== 'string' || !next.startsWith('/') || next.startsWith('//')) {
    return null
  }
  return next
}

const login = useMutation({
  mutationFn: (payload: LoginPayload) => authStore.login(payload),
  onSuccess: async () => {
    // Nowa tożsamość = wszystkie dane w cache są nieaktualne.
    await queryClient.invalidateQueries()
    await router.push(safeNext() ?? { name: 'plan-dnia' })
  },
})

const serverError = computed(() => {
  const error = login.error.value
  if (!error) {
    return null
  }
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return texts.invalidCredentials
    }
    if (error.status === 429) {
      return texts.tooManyAttempts
    }
    return error.message
  }
  return common.unexpectedError
})

const onSubmit = handleSubmit((values) => {
  login.mutate({ email: values.email, password: values.password })
})
</script>

<template>
  <div class="bg-background flex min-h-dvh items-center justify-center px-4 py-10">
    <Card class="w-full max-w-sm rounded-2xl" data-testid="login-card">
      <CardHeader>
        <p class="text-primary font-serif text-3xl">{{ APP_NAME }}</p>
        <h1 class="pt-3 text-xl font-semibold">{{ texts.loginTitle }}</h1>
        <CardDescription>{{ APP_TAGLINE }}</CardDescription>
      </CardHeader>

      <CardContent>
        <form class="grid gap-4" novalidate @submit="onSubmit">
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="login-email">{{ texts.emailLabel }}</label>
            <Input
              id="login-email"
              v-model="email"
              v-bind="emailAttrs"
              type="email"
              autocomplete="username"
              class="min-h-11"
              :aria-invalid="Boolean(errors.email)"
              :aria-describedby="errors.email ? 'login-email-error' : undefined"
              data-testid="login-email"
            />
            <p
              v-if="errors.email"
              id="login-email-error"
              class="text-destructive text-sm"
              data-testid="login-email-error"
            >
              {{ errors.email }}
            </p>
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="login-password">{{
              texts.passwordLabel
            }}</label>
            <Input
              id="login-password"
              v-model="password"
              v-bind="passwordAttrs"
              type="password"
              autocomplete="current-password"
              class="min-h-11"
              :aria-invalid="Boolean(errors.password)"
              :aria-describedby="errors.password ? 'login-password-error' : undefined"
              data-testid="login-password"
            />
            <p
              v-if="errors.password"
              id="login-password-error"
              class="text-destructive text-sm"
              data-testid="login-password-error"
            >
              {{ errors.password }}
            </p>
          </div>

          <p
            v-if="serverError"
            class="text-destructive text-sm"
            role="alert"
            data-testid="login-error"
          >
            {{ serverError }}
          </p>

          <Button
            type="submit"
            class="min-h-11 w-full"
            :disabled="login.isPending.value"
            data-testid="login-submit"
          >
            {{ login.isPending.value ? texts.submitPending : texts.submit }}
          </Button>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
