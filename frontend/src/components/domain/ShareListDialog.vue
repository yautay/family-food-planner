<script setup lang="ts">
/**
 * Udostępnianie listy zakupowej publicznym linkiem (ADR-010, karta B11 §Frontend).
 *
 * Cztery rzeczy, które ten panel musi robić dobrze:
 *
 * 1. **Kontrolka „Odwołaj link" jest WIDOCZNA, kiedy link jest aktywny** —
 *    wymóg ADR-010. Link raz wysłany żyje do wygaśnięcia, więc odebranie
 *    dostępu nie może być schowane w menu.
 * 2. **QR renderuje się KLIENCKO** (`qrcode` z npm, ADR-010) z PEŁNEGO adresu
 *    (origin z przeglądarki) — kod z relatywną ścieżką nie zaprowadziłby
 *    nigdzie po zeskanowaniu telefonem.
 * 3. **Web Share API z fallbackiem.** `navigator.share` istnieje głównie na
 *    telefonach; na desktopie zostaje „kopiuj link", a nie martwy przycisk.
 * 4. **Trzy stany, każdy widoczny**: brak linku / aktywny / odwołany. Panel
 *    nigdy nie udaje, że linku nie było — po odwołaniu proponuje nowy.
 *
 * Panel osadzony w stronie, nie modal — ten sam wzorzec co `PlanningDialog`
 * z B07 (na telefonie modal odcina kontekst listy).
 */
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'

import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { Share } from '@/api/shoppingLists'
import { absoluteShareUrl, revokeShoppingListShare, shareShoppingList } from '@/api/shoppingLists'
import { Button } from '@/components/ui/button'
import { formatDate } from '@/lib/dates'
import { common, shoppingList as texts } from '@/lib/texts'

/** Warianty ważności linku; 7 dni to domyślna z ADR-010. */
const VALIDITY_OPTIONS = [1, 7, 30] as const
const DEFAULT_VALIDITY = 7

const props = defineProps<{
  open: boolean
  listId: number
  /** Aktualny stan udostępnienia z odpowiedzi listy (`null` = nigdy nie udostępniona). */
  share: Share | null
}>()

const emit = defineEmits<{
  (event: 'close'): void
}>()

const queryClient = useQueryClient()

const validity = ref<number>(DEFAULT_VALIDITY)
const errorMessage = ref<string | null>(null)
const copied = ref(false)
const qrDataUrl = ref<string | null>(null)

const activeShare = computed(() => (props.share && !props.share.revoked ? props.share : null))
const revokedShare = computed(() => (props.share && props.share.revoked ? props.share : null))
const fullUrl = computed(() => (activeShare.value ? absoluteShareUrl(activeShare.value.url) : null))
const canSystemShare = computed(() => typeof navigator !== 'undefined' && 'share' in navigator)

/** Zamknięcie panelu czyści stan pomocniczy — QR i komunikaty nie mogą „przeciekać". */
watch(
  () => props.open,
  (open) => {
    if (!open) {
      qrDataUrl.value = null
      copied.value = false
      errorMessage.value = null
    }
  },
)

/** Odwołanie linku musi natychmiast zabrać QR — inaczej pokazywałby martwy adres. */
watch(activeShare, (share) => {
  if (!share) {
    qrDataUrl.value = null
  }
})

function reportError(error: unknown): void {
  errorMessage.value = error instanceof ApiError ? error.message : common.unexpectedError
}

async function invalidate(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: queryKeys.shopping.list(props.listId) })
  await queryClient.invalidateQueries({ queryKey: queryKeys.shopping.listsIndex })
}

const create = useMutation({
  mutationFn: () => shareShoppingList(props.listId, { expires_in_days: validity.value }),
  onSuccess: async () => {
    errorMessage.value = null
    copied.value = false
    qrDataUrl.value = null
    await invalidate()
  },
  onError: reportError,
})

const revoke = useMutation({
  mutationFn: () => revokeShoppingListShare(props.listId),
  onSuccess: async () => {
    errorMessage.value = null
    await invalidate()
  },
  onError: reportError,
})

async function copyLink(): Promise<void> {
  if (!fullUrl.value) {
    return
  }
  try {
    await navigator.clipboard.writeText(fullUrl.value)
    copied.value = true
  } catch {
    // Schowek bywa zablokowany (brak HTTPS, odmowa uprawnień) — link jest
    // widoczny w polu obok, więc użytkownik zawsze może go zaznaczyć ręcznie.
    errorMessage.value = common.unexpectedError
  }
}

async function systemShare(): Promise<void> {
  if (!fullUrl.value) {
    return
  }
  try {
    await navigator.share({ title: texts.shareTitle, url: fullUrl.value })
  } catch {
    // Anulowanie systemowego okna to normalna decyzja użytkownika, nie błąd.
  }
}

async function toggleQr(): Promise<void> {
  if (qrDataUrl.value !== null) {
    qrDataUrl.value = null
    return
  }
  if (!fullUrl.value) {
    return
  }
  // Import dynamiczny: biblioteka QR jest potrzebna dopiero po kliknięciu, więc
  // nie ma powodu ciągnąć jej w głównym bundlu (dotyczy też strony listy).
  const { toDataURL } = await import('qrcode')
  qrDataUrl.value = await toDataURL(fullUrl.value, { width: 240, margin: 1 })
}

function askRevoke(): void {
  if (window.confirm(texts.shareRevokeConfirm)) {
    revoke.mutate()
  }
}
</script>

<template>
  <section
    v-if="open"
    class="border-border bg-card grid gap-3 rounded-xl border p-3 shadow-sm print:hidden"
    role="group"
    :aria-label="texts.shareTitle"
    data-testid="share-dialog"
  >
    <header class="grid gap-1">
      <h3 class="text-sm font-medium">{{ texts.shareTitle }}</h3>
      <p class="text-muted-foreground text-xs">{{ texts.shareDescription }}</p>
    </header>

    <!-- Stan 1: linku nie ma (albo został odwołany) — wybór ważności + utworzenie. -->
    <div v-if="!activeShare" class="grid gap-2">
      <p v-if="revokedShare" class="text-muted-foreground text-xs" data-testid="share-revoked">
        {{ texts.shareRevoked }}
      </p>
      <p v-else class="text-muted-foreground text-xs" data-testid="share-none">
        {{ texts.shareNone }}
      </p>

      <fieldset class="grid gap-1">
        <legend class="text-xs font-medium">{{ texts.shareValidity }}</legend>
        <div class="flex flex-wrap gap-2">
          <label
            v-for="days in VALIDITY_OPTIONS"
            :key="days"
            class="border-border flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border px-3 text-sm"
            :class="validity === days ? 'border-primary text-primary' : ''"
          >
            <input
              v-model="validity"
              type="radio"
              class="size-4"
              :value="days"
              :data-testid="`share-validity-${days}`"
            />
            {{ texts.shareDays(days) }}
          </label>
        </div>
      </fieldset>

      <div>
        <Button
          type="button"
          class="min-h-11"
          :disabled="create.isPending.value"
          data-testid="share-create"
          @click="create.mutate()"
        >
          {{
            create.isPending.value
              ? common.loading
              : revokedShare
                ? texts.shareRecreate
                : texts.shareCreate
          }}
        </Button>
      </div>
    </div>

    <!-- Stan 2: link aktywny — adres, akcje wysyłki i ZAWSZE widoczne odwołanie. -->
    <div v-else class="grid gap-2">
      <p class="text-sm font-medium" data-testid="share-active">
        {{ texts.shareActiveUntil(formatDate(activeShare.expires_at.slice(0, 10))) }}
      </p>
      <p
        class="border-border text-muted-foreground overflow-x-auto rounded-lg border px-3 py-2 font-mono text-xs"
        data-testid="share-url"
      >
        {{ fullUrl }}
      </p>

      <div class="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          class="min-h-11"
          data-testid="share-copy"
          @click="copyLink()"
        >
          {{ texts.shareCopy }}
        </Button>
        <Button
          v-if="canSystemShare"
          type="button"
          variant="outline"
          class="min-h-11"
          data-testid="share-system"
          @click="systemShare()"
        >
          {{ texts.shareSystem }}
        </Button>
        <Button
          type="button"
          variant="outline"
          class="min-h-11"
          data-testid="share-qr"
          @click="toggleQr()"
        >
          {{ qrDataUrl ? texts.shareQrHide : texts.shareQr }}
        </Button>
        <Button
          type="button"
          variant="ghost"
          class="text-destructive min-h-11"
          :disabled="revoke.isPending.value"
          data-testid="share-revoke"
          @click="askRevoke()"
        >
          {{ texts.shareRevoke }}
        </Button>
      </div>

      <p v-if="copied" class="text-secondary text-xs" role="status" data-testid="share-copied">
        {{ texts.shareCopied }}
      </p>

      <img
        v-if="qrDataUrl"
        :src="qrDataUrl"
        :alt="texts.shareQrAlt"
        class="border-border h-60 w-60 self-center rounded-lg border bg-white p-2"
        data-testid="share-qr-image"
      />
    </div>

    <p v-if="errorMessage" class="text-destructive text-sm" role="alert" data-testid="share-error">
      {{ errorMessage }}
    </p>

    <footer>
      <Button
        type="button"
        variant="ghost"
        class="min-h-11"
        data-testid="share-close"
        @click="emit('close')"
      >
        {{ common.cancel }}
      </Button>
    </footer>
  </section>
</template>
