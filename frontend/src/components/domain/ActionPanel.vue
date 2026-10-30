<script setup lang="ts">
import { LoaderCircle, X } from '@lucide/vue'
import {
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from 'reka-ui'
import { nextTick, ref, useId, watch } from 'vue'
import { Button } from '@/components/ui/button'

const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    description?: string
    submitLabel: string
    submitDisabled?: boolean
    pending?: boolean
    error?: string | null
    validationMessage?: string | null
    warnings?: string[]
    testid?: string
  }>(),
  {
    description: undefined,
    submitDisabled: false,
    pending: false,
    error: null,
    validationMessage: null,
    warnings: () => [],
    testid: 'action-panel',
  },
)

const emit = defineEmits<{ submit: []; close: [] }>()
const id = useId()
const formId = `${id}-form`
const form = ref<HTMLFormElement>()
const errorBox = ref<HTMLElement>()
const dispatching = ref(false)
let opener: HTMLElement | null = null

// Panel nie posiada danych formularza ani serwera. Reka obsługuje modalność i trap.
watch(
  () => props.open,
  (open) => {
    if (open) {
      opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
      dispatching.value = false
    }
  },
  { immediate: true, flush: 'sync' },
)

watch(
  () => props.error,
  async (error) => {
    if (error && props.open) {
      await nextTick()
      errorBox.value?.focus()
    }
  },
)

function close(): void {
  // Trwającego zapisu nie wolno ukryć jako anulowanego.
  if (!props.pending && !dispatching.value) emit('close')
}

function restoreFocus(event: Event): void {
  event.preventDefault()
  if (opener?.isConnected) opener.focus()
}

async function submit(): Promise<void> {
  if (props.pending || dispatching.value || props.submitDisabled || props.validationMessage) return
  if (!form.value?.reportValidity()) {
    // Pola powiązane przez form= mogą leżeć poza elementem formularza.
    const invalid = Array.from(form.value?.elements ?? []).find(
      (element) =>
        element instanceof HTMLElement &&
        element.matches('input:invalid, select:invalid, textarea:invalid'),
    )
    if (invalid instanceof HTMLElement) invalid.focus()
    return
  }
  // Chroni także dwa zdarzenia w tej samej klatce, zanim rodzic ustawi pending.
  dispatching.value = true
  emit('submit')
  await nextTick()
  dispatching.value = false
}
</script>

<template>
  <DialogRoot
    :open="open"
    @update:open="
      (value) => {
        if (!value) close()
      }
    "
  >
    <DialogPortal>
      <DialogOverlay class="bg-overlay fixed inset-0 z-50 print:hidden" />
      <DialogContent
        class="bg-card text-card-foreground fixed inset-x-2 top-2 bottom-2 z-50 flex min-w-0 flex-col rounded-xl border shadow-xl sm:inset-y-4 sm:right-4 sm:left-auto sm:w-[min(36rem,calc(100vw-2rem))] print:hidden"
        :data-testid="testid"
        @escape-key-down="
          (event) => {
            if (pending || dispatching) event.preventDefault()
          }
        "
        @interact-outside="(event) => event.preventDefault()"
        @close-auto-focus="restoreFocus"
      >
        <header class="flex items-start gap-3 border-b p-4 sm:p-6">
          <div class="grid min-w-0 flex-1 gap-2">
            <DialogTitle class="text-xl font-semibold break-words">{{ title }}</DialogTitle>
            <DialogDescription
              class="text-muted-foreground text-sm leading-relaxed"
              :class="!description && 'sr-only'"
            >
              {{
                description ||
                'Uzupełnij dane i potwierdź działanie. Anuluj, aby wrócić bez zapisywania.'
              }}
            </DialogDescription>
            <slot name="context" />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Zamknij panel"
            :disabled="pending || dispatching"
            :data-testid="`${testid}-close`"
            @click="close"
          >
            <X aria-hidden="true" class="size-5" />
          </Button>
        </header>
        <div
          class="flex min-h-0 flex-1 flex-col"
          :aria-busy="pending"
          :aria-describedby="
            error ? `${id}-error` : validationMessage ? `${id}-validation` : undefined
          "
        >
          <!-- Osobny formularz z natywnym powiązaniem pól unika zagnieżdżania
               formularzy create-in-context dostarczanych przez pickery. -->
          <form :id="formId" ref="form" :aria-label="title" novalidate @submit.prevent="submit" />
          <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6">
            <fieldset
              class="grid min-w-0 gap-4 [&_select]:border-input [&_textarea]:border-input"
              :disabled="pending || dispatching"
            >
              <legend class="sr-only">{{ title }}</legend>
              <slot :form-id="formId" />
            </fieldset>
            <p
              v-if="validationMessage"
              :id="`${id}-validation`"
              class="text-destructive mt-4 text-sm"
              role="alert"
              :data-testid="`${testid}-validation`"
            >
              {{ validationMessage }}
            </p>
            <p
              v-if="error"
              :id="`${id}-error`"
              ref="errorBox"
              class="text-destructive mt-4 rounded-md text-sm"
              role="alert"
              tabindex="-1"
              :data-testid="`${testid}-error`"
            >
              {{ error }}
            </p>
            <ul
              v-if="warnings.length"
              class="text-warning mt-4 grid gap-2 text-sm"
              :data-testid="`${testid}-warnings`"
            >
              <li v-for="warning in warnings" :key="warning">{{ warning }}</li>
            </ul>
          </div>
          <footer class="flex shrink-0 flex-wrap gap-2 border-t p-4 sm:p-6">
            <Button
              type="submit"
              :form="formId"
              :disabled="submitDisabled || !!validationMessage || pending || dispatching"
              :data-testid="`${testid}-submit`"
            >
              <LoaderCircle
                v-if="pending"
                aria-hidden="true"
                class="size-4 animate-spin motion-reduce:animate-none"
              />
              {{ pending ? 'Zapisywanie…' : submitLabel }}
            </Button>
            <Button
              type="button"
              variant="ghost"
              :disabled="pending || dispatching"
              :data-testid="`${testid}-cancel`"
              @click="close"
              >Anuluj</Button
            >
            <slot name="footer-extra" :form-id="formId" />
          </footer>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
