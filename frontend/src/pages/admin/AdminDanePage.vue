<script setup lang="ts">
/**
 * Dane instancji (`/admin/dane`) — eksport i import CAŁEJ instancji (BATCH_14).
 *
 * Wariant administracyjny różni się od sekcji „Kopia danych rodziny" w Ustawieniach
 * wyłącznie ZAKRESEM (`scope=instance`): plik niesie także konta i rodziny.
 * Dialog importu jest ten sam — endpoint rozpoznaje zakres z nagłówka pliku,
 * więc drugi komponent tylko rozjechałby się z pierwszym.
 *
 * Konta z importu powstają BEZ hasła (hash nigdy nie opuszcza bazy, 07_SECURITY
 * §7) — strona mówi to wprost, żeby administrator nie zdziwił się, że nikt się
 * nie loguje. Hasła nadaje się potem w `/admin/uzytkownicy`.
 */
import { Info } from '@lucide/vue'
import { useMutation } from '@tanstack/vue-query'
import { ref } from 'vue'

import { ApiError, assertSessionRequestCurrent, captureSessionRequest } from '@/api/client'
import { downloadExport } from '@/api/transfer'
import TransferImportDialog from '@/components/domain/TransferImportDialog.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { saveBlob } from '@/lib/download'
import { common, transfer as texts } from '@/lib/texts'

const importOpen = ref(false)
const helpOpen = ref(false)
const errorMessage = ref<string | null>(null)
const exportedFilename = ref<string | null>(null)

const exportInstance = useMutation({
  onMutate: () => ({ sessionTicket: captureSessionRequest() }),
  mutationFn: () => downloadExport('instance'),
  onSuccess: (file, _variables, context) => {
    if (!context) return
    assertSessionRequestCurrent(context.sessionTicket)
    errorMessage.value = null
    exportedFilename.value = file.filename
    saveBlob(file.blob, file.filename)
  },
  onError: (error: unknown) => {
    errorMessage.value = error instanceof ApiError ? error.message : common.unexpectedError
  },
})
</script>

<template>
  <section class="grid gap-6" data-testid="admin-dane-page">
    <header class="grid gap-1">
      <h1 class="text-2xl font-semibold">{{ texts.instanceTitle }}</h1>
      <p class="text-muted-foreground text-sm">{{ texts.instanceSubtitle }}</p>
      <div class="grid gap-2">
        <Button
          type="button"
          variant="ghost"
          class="min-h-11 w-fit justify-start px-2"
          :aria-expanded="helpOpen"
          aria-controls="admin-dane-help"
          data-testid="admin-dane-help-toggle"
          @click="helpOpen = !helpOpen"
        >
          <Info aria-hidden="true" />
          {{ texts.instanceHelpToggle }}
        </Button>
        <div
          v-if="helpOpen"
          id="admin-dane-help"
          class="border-border bg-muted text-foreground grid gap-2 rounded-xl border p-3 text-sm"
          role="note"
          data-testid="admin-dane-help"
        >
          <p v-for="line in texts.instanceHelpLines" :key="line">{{ line }}</p>
        </div>
      </div>
    </header>

    <Card class="rounded-xl">
      <CardHeader>
        <CardTitle>{{ texts.instanceTitle }}</CardTitle>
        <CardDescription>{{ texts.exportHint }}</CardDescription>
      </CardHeader>

      <CardContent class="grid gap-3">
        <p
          v-if="errorMessage"
          class="text-destructive text-sm"
          role="alert"
          data-testid="admin-transfer-error"
        >
          {{ errorMessage }}
        </p>

        <div class="flex flex-wrap gap-2">
          <Button
            type="button"
            class="min-h-11"
            :disabled="exportInstance.isPending.value"
            data-testid="admin-transfer-export"
            @click="exportInstance.mutate()"
          >
            {{ exportInstance.isPending.value ? texts.exportPending : texts.exportInstanceButton }}
          </Button>
          <Button
            type="button"
            variant="outline"
            class="min-h-11"
            data-testid="admin-transfer-import-open"
            @click="importOpen = !importOpen"
          >
            {{ texts.importInstanceButton }}
          </Button>
        </div>

        <p v-if="exportedFilename" class="text-sm" data-testid="admin-transfer-export-done">
          {{ texts.exportDone(exportedFilename) }}
        </p>

        <TransferImportDialog :open="importOpen" instance @close="importOpen = false" />
      </CardContent>
    </Card>
  </section>
</template>
