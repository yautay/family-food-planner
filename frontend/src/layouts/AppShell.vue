<script setup lang="ts">
/**
 * Szkielet aplikacji — BATCH_01 dostarcza wyłącznie ramę i tokens.
 *
 * Docelowo (06_UIUX §5): sidebar na desktopie, bottom-nav na mobile
 * (Plan / Przepisy / Zakupy / Więcej). Nawigację, nagłówek z użytkownikiem
 * i guard sesji dokłada BATCH_02 — tu nie ma jeszcze czego linkować.
 */
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
</script>

<template>
  <div class="bg-background text-foreground min-h-dvh">
    <header class="border-border bg-card border-b">
      <div class="mx-auto flex max-w-5xl items-center gap-3 px-4 py-4">
        <span class="bg-primary size-8 rounded-lg" aria-hidden="true" />
        <div>
          <p class="text-base font-semibold">Family Food Planner</p>
          <p class="text-muted-foreground text-sm">Planer żywienia rodziny</p>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-5xl px-4 py-8">
      <Card class="rounded-xl">
        <CardHeader>
          <CardTitle>Szkielet aplikacji</CardTitle>
          <CardDescription>
            Fundament projektu jest gotowy. Widoki planu dnia, przepisów i zakupów pojawią się w
            kolejnych etapach.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p class="text-muted-foreground text-sm">
            Backend odpowiada pod <code class="text-foreground">/api/v1/health</code>.
          </p>
        </CardContent>
      </Card>
    </main>
  </div>
</template>
