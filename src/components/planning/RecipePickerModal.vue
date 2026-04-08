<script setup>
const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  searchValue: {
    type: String,
    default: '',
  },
  recipes: {
    type: Array,
    default: () => [],
  },
  title: {
    type: String,
    required: true,
  },
  closeLabel: {
    type: String,
    required: true,
  },
  searchPlaceholder: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['close', 'select-recipe', 'update:searchValue'])

function closeModal() {
  emit('close')
}

function updateSearch(value) {
  emit('update:searchValue', value)
}

function selectRecipe(recipeId) {
  emit('select-recipe', recipeId)
}
</script>

<template>
  <div v-if="props.visible" class="modal" @click.self="closeModal">
    <div class="modal-content">
      <div class="modal-header">
        <h4 class="title is-6">{{ props.title }}</h4>
        <button class="button is-small" type="button" @click="closeModal">
          {{ props.closeLabel }}
        </button>
      </div>

      <input
        :value="props.searchValue"
        class="input"
        :placeholder="props.searchPlaceholder"
        type="text"
        @input="updateSearch($event.target.value)"
      />

      <ul class="picker-list">
        <li v-for="recipe in props.recipes" :key="recipe.id">
          <button class="link" type="button" @click="selectRecipe(recipe.id)">
            {{ recipe.name }}
          </button>
        </li>
      </ul>
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

.link {
  border: none;
  padding: 0;
  background: transparent;
  color: var(--app-link);
  cursor: pointer;
}
</style>
