<script setup lang="ts">
import { nextTick, ref } from 'vue'

export type SettingsSection = 'family' | 'goals' | 'shopping' | 'data'

defineProps<{ modelValue: SettingsSection }>()
const emit = defineEmits<{ 'update:modelValue': [section: SettingsSection] }>()
const tabs = [
  { id: 'family', label: 'Rodzina' },
  { id: 'goals', label: 'Moje cele' },
  { id: 'shopping', label: 'Zakupy' },
  { id: 'data', label: 'Dane' },
] as const
const list = ref<HTMLElement | null>(null)

async function navigate(event: KeyboardEvent, index: number): Promise<void> {
  let next: number
  if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
  else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = tabs.length - 1
  else return
  event.preventDefault()
  emit('update:modelValue', tabs[next]!.id)
  await nextTick()
  list.value?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus()
}
</script>

<template>
  <div
    ref="list"
    class="border-border grid grid-cols-2 gap-1 border-b pb-2 sm:flex sm:flex-wrap"
    role="tablist"
    aria-label="Sekcje ustawień"
  >
    <button
      v-for="(tab, index) in tabs"
      :id="`settings-tab-${tab.id}`"
      :key="tab.id"
      type="button"
      role="tab"
      class="min-h-11 rounded-lg px-4 py-2 text-sm font-medium"
      :class="
        modelValue === tab.id
          ? 'bg-primary text-primary-foreground'
          : 'text-muted-foreground hover:bg-muted'
      "
      :aria-selected="modelValue === tab.id"
      :aria-controls="`settings-panel-${tab.id}`"
      :tabindex="modelValue === tab.id ? 0 : -1"
      :data-testid="`settings-tab-${tab.id}`"
      @click="emit('update:modelValue', tab.id)"
      @keydown="navigate($event, index)"
    >
      {{ tab.label }}
    </button>
  </div>
</template>
