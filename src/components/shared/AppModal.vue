<script setup>
const props = defineProps({
  title: {
    type: String,
    default: '',
  },
  width: {
    type: String,
    default: '560px',
  },
  closeLabel: {
    type: String,
    default: 'Close',
  },
})

const emit = defineEmits(['close'])

function closeModal() {
  emit('close')
}
</script>

<template>
  <div class="modal" @click.self="closeModal">
    <div class="modal-content" :style="{ '--modal-width': props.width }">
      <div class="modal-header">
        <h2 v-if="props.title" class="title is-5">{{ props.title }}</h2>
        <button class="button is-small" type="button" @click="closeModal">{{ closeLabel }}</button>
      </div>

      <slot />
    </div>
  </div>
</template>

<style scoped>
.modal {
  display: flex;
  justify-content: center;
  align-items: center;
  position: fixed;
  z-index: 60;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  overflow: auto;
  background-color: rgba(0, 0, 0, 0.4);
}

.modal-content {
  background-color: var(--app-surface);
  color: var(--app-text);
  padding: 1rem;
  border: 1px solid var(--app-border);
  border-radius: 0.75rem;
  width: min(var(--modal-width), calc(100% - 1.5rem));
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
</style>
