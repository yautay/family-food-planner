<script setup lang="ts">
/** Kompatybilny adapter paneli tygodnia; stan formularza pozostaje u konsumenta. */
import ActionPanel from '@/components/domain/ActionPanel.vue'

defineProps<{
  open: boolean
  title: string
  subtitle?: string
  submitLabel: string
  submitDisabled?: boolean
  pending?: boolean
  error?: string | null
  validationMessage?: string | null
  warnings?: string[]
  testid: string
}>()
const emit = defineEmits<{ submit: []; close: [] }>()
</script>

<template>
  <ActionPanel
    :open="open"
    :title="title"
    :description="subtitle"
    :submit-label="submitLabel"
    :submit-disabled="submitDisabled"
    :pending="pending"
    :error="error"
    :validation-message="validationMessage"
    :warnings="warnings"
    :testid="testid"
    @submit="emit('submit')"
    @close="emit('close')"
  >
    <template #default="{ formId }"><slot :form-id="formId" /></template>
    <template #footer-extra="{ formId }"><slot name="footer-extra" :form-id="formId" /></template>
  </ActionPanel>
</template>
