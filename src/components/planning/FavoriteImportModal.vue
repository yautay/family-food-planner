<script setup>
const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  title: {
    type: String,
    required: true,
  },
  closeLabel: {
    type: String,
    required: true,
  },
  cancelLabel: {
    type: String,
    required: true,
  },
  confirmLabel: {
    type: String,
    required: true,
  },
  hint: {
    type: String,
    default: '',
  },
  meals: {
    type: Array,
    default: () => [],
  },
  selectedIndexes: {
    type: Array,
    default: () => [],
  },
  limit: {
    type: Number,
    default: 0,
  },
  resolveRecipeName: {
    type: Function,
    required: true,
  },
})

const emit = defineEmits(['close', 'toggle', 'confirm'])
</script>

<template>
  <div v-if="props.visible" class="modal" @click.self="$emit('close')">
    <div class="modal-content">
      <div class="modal-header">
        <h4 class="title is-6">{{ props.title }}</h4>
        <button class="button is-small" type="button" @click="$emit('close')">
          {{ props.closeLabel }}
        </button>
      </div>

      <p class="muted">{{ props.hint }}</p>

      <ul class="picker-list">
        <li v-for="(meal, index) in props.meals" :key="`overflow-meal-${index}`">
          <label class="overflow-option">
            <input
              type="checkbox"
              :checked="props.selectedIndexes.includes(index)"
              :disabled="
                !props.selectedIndexes.includes(index) &&
                props.selectedIndexes.length >= props.limit
              "
              @change="$emit('toggle', index)"
            />
            <span>{{ props.resolveRecipeName(meal.recipe_id) }}</span>
          </label>
        </li>
      </ul>

      <div class="actions-row">
        <button class="button is-primary" type="button" @click="$emit('confirm')">
          {{ props.confirmLabel }}
        </button>
        <button class="button" type="button" @click="$emit('close')">
          {{ props.cancelLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal {
  display: flex;
  justify-content: center;
  align-items: center;
  position: fixed;
  inset: 0;
  z-index: 70;
  background-color: rgba(0, 0, 0, 0.42);
}

.modal-content {
  width: min(720px, calc(100% - 1.25rem));
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 0.75rem;
  padding: 0.75rem;
  display: grid;
  gap: 0.55rem;
  max-height: calc(100vh - 3rem);
  overflow: auto;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.55rem;
}

.picker-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.35rem;
}

.overflow-option {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}

.actions-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}
</style>
