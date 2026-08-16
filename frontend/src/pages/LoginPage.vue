<script setup lang="ts">
/**
 * Ekran logowania — PLACEHODER BEZ LOGIKI (BATCH_01).
 *
 * Formularz nic nie wysyła: sesje, CSRF i walidacja (vee-validate + zod)
 * powstają w BATCH_02 (ADR-003). Strona istnieje po to, by potwierdzić
 * działanie tokens 06_UIUX i komponentów shadcn-vue.
 */
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
</script>

<template>
  <div class="bg-background flex min-h-dvh items-center justify-center px-4 py-10">
    <Card class="w-full max-w-sm rounded-xl" data-testid="login-card">
      <CardHeader>
        <CardTitle>Zaloguj się</CardTitle>
        <CardDescription>Planer żywienia rodziny</CardDescription>
      </CardHeader>

      <CardContent>
        <form class="grid gap-4" @submit.prevent>
          <div class="grid gap-2">
            <label class="text-sm font-medium" for="login-email">Adres e-mail</label>
            <Input id="login-email" type="email" autocomplete="username" disabled />
          </div>

          <div class="grid gap-2">
            <label class="text-sm font-medium" for="login-password">Hasło</label>
            <Input id="login-password" type="password" autocomplete="current-password" disabled />
          </div>

          <Button type="submit" class="min-h-11 w-full" disabled data-testid="login-submit">
            Zaloguj
          </Button>

          <p class="text-muted-foreground text-sm">
            Logowanie zostanie uruchomione w kolejnym etapie prac.
          </p>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
