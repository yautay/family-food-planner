<script setup>
import { RouterLink } from 'vue-router'

const props = defineProps({
  navItems: {
    type: Array,
    default: () => [],
  },
  catalogItems: {
    type: Array,
    default: () => [],
  },
  catalogLabel: {
    type: String,
    required: true,
  },
  navigationMenuLabel: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['close'])

function closeMenus() {
  emit('close')
}
</script>

<template>
  <div class="menu-panel navigation-panel">
    <div class="app-panel-content">
      <nav class="menu-list-block" :aria-label="props.navigationMenuLabel">
        <RouterLink
          v-for="item in props.navItems"
          :key="item.key"
          class="menu-link"
          :to="item.to"
          @click="closeMenus"
        >
          {{ item.label }}
        </RouterLink>

        <div class="catalog-group" tabindex="0">
          <div class="menu-link menu-expand">
            <span>{{ props.catalogLabel }}</span>
            <span class="expand-indicator" aria-hidden="true">v</span>
          </div>

          <div class="submenu-block">
            <RouterLink
              v-for="item in props.catalogItems"
              :key="item.key"
              class="submenu-link"
              :to="item.to"
              @click="closeMenus"
            >
              {{ item.label }}
            </RouterLink>
          </div>
        </div>
      </nav>
    </div>
  </div>
</template>

<style scoped>
.menu-panel {
  position: sticky;
  top: 3.65rem;
  z-index: 45;
  background: var(--app-surface);
  border-bottom: 1px solid var(--app-border);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
}

.navigation-panel {
  width: min(25vw, 420px);
  margin-right: auto;
  border-right: 1px solid var(--app-border);
}

.app-panel-content {
  padding: 0.75rem;
}

.menu-list-block {
  display: grid;
  gap: 0.35rem;
}

.menu-link,
.submenu-link {
  border: 1px solid var(--app-border);
  border-radius: 0.7rem;
  color: var(--app-text);
  background: var(--app-surface);
  min-height: 2.45rem;
  padding: 0.55rem 0.75rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.menu-expand {
  cursor: default;
}

.catalog-group {
  display: grid;
  gap: 0.35rem;
}

.submenu-block {
  padding-left: 0.65rem;
  display: grid;
  gap: 0.35rem;
  max-height: 0;
  opacity: 0;
  overflow: hidden;
  visibility: hidden;
  transition:
    max-height 0.22s ease,
    opacity 0.2s ease;
}

.catalog-group:hover .submenu-block,
.catalog-group:focus-within .submenu-block {
  max-height: 18rem;
  opacity: 1;
  visibility: visible;
}

.submenu-link {
  background: var(--app-surface-alt);
}

.expand-indicator {
  font-weight: 700;
  transition: transform 0.2s ease;
}

.catalog-group:hover .expand-indicator,
.catalog-group:focus-within .expand-indicator {
  transform: rotate(180deg);
}
</style>
