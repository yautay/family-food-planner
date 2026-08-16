<script setup lang="ts">
/**
 * Zaślepka sekcji, których jeszcze nie ma. Jeden komponent dla wszystkich tras
 * z BATCH_02 — tytuł bierze z `meta.title` bieżącej trasy, więc kolejne batche
 * podmieniają tylko wpis w routerze.
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { common } from '@/lib/texts'

const route = useRoute()
const title = computed(() => (route.meta.title as string | undefined) ?? 'Sekcja w budowie')
</script>

<template>
  <section class="grid gap-4" data-testid="placeholder-page">
    <h1 class="text-2xl font-semibold">{{ title }}</h1>

    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ title }}</CardTitle>
        <CardDescription>{{ common.placeholderSection }}</CardDescription>
      </CardHeader>
      <CardContent>
        <p class="text-muted-foreground text-sm">
          Fundament aplikacji (konta, sesje, nawigacja) jest gotowy. Funkcje tej sekcji dokładają
          kolejne etapy prac.
        </p>
      </CardContent>
    </Card>
  </section>
</template>
