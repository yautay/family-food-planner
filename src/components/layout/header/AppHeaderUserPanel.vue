<script setup>
import { RouterLink } from 'vue-router'

const props = defineProps({
  userName: {
    type: String,
    required: true,
  },
  isLoggedIn: {
    type: Boolean,
    default: false,
  },
  canManagePermissions: {
    type: Boolean,
    default: false,
  },
  locale: {
    type: String,
    required: true,
  },
  theme: {
    type: String,
    required: true,
  },
  labels: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['close', 'set-locale', 'set-theme', 'logout'])

function closeMenus() {
  emit('close')
}

function onLocaleChange(value) {
  emit('set-locale', value)
}

function onThemeChange(value) {
  emit('set-theme', value)
}

function onLogout() {
  emit('logout')
}
</script>

<template>
  <div class="menu-panel user-panel">
    <div class="container app-panel-content user-panel-content">
      <div class="user-summary">{{ props.labels.loggedAs }}: {{ props.userName }}</div>

      <div class="field-grid">
        <label>
          {{ props.labels.language }}
          <div class="select is-small">
            <select
              :aria-label="props.labels.language"
              :value="props.locale"
              @change="onLocaleChange($event.target.value)"
            >
              <option value="pl">PL</option>
              <option value="en">EN</option>
            </select>
          </div>
        </label>

        <label>
          {{ props.labels.theme }}
          <div class="select is-small">
            <select
              :aria-label="props.labels.theme"
              :value="props.theme"
              @change="onThemeChange($event.target.value)"
            >
              <option value="light">{{ props.labels.light }}</option>
              <option value="dark">{{ props.labels.dark }}</option>
              <option value="system">{{ props.labels.system }}</option>
            </select>
          </div>
        </label>
      </div>

      <div class="actions-row">
        <template v-if="props.isLoggedIn">
          <RouterLink class="button is-small" to="/account" @click="closeMenus">{{
            props.labels.account
          }}</RouterLink>
          <RouterLink
            v-if="props.canManagePermissions"
            class="button is-small"
            to="/access-control"
            @click="closeMenus"
          >
            {{ props.labels.accessControl }}
          </RouterLink>
          <button type="button" class="button is-small is-danger is-light" @click="onLogout">
            {{ props.labels.logout }}
          </button>
        </template>

        <template v-else>
          <RouterLink class="button is-small" to="/login" @click="closeMenus">{{
            props.labels.login
          }}</RouterLink>
          <RouterLink class="button is-small is-primary" to="/register" @click="closeMenus">
            {{ props.labels.register }}
          </RouterLink>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.menu-panel {
  position: sticky;
  z-index: 45;
  background: var(--app-surface);
  border-bottom: 1px solid var(--app-border);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
}

.user-panel {
  top: calc(3.65rem + 0.1rem);
}

.app-panel-content {
  padding-top: 0.75rem;
  padding-bottom: 0.75rem;
}

.user-panel-content {
  display: grid;
  gap: 0.75rem;
}

.user-summary {
  font-weight: 600;
}

.field-grid {
  display: grid;
  gap: 0.7rem;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
}

.field-grid label {
  display: grid;
  gap: 0.35rem;
  font-size: 0.9rem;
  font-weight: 500;
}

.actions-row {
  display: flex;
  gap: 0.55rem;
  flex-wrap: wrap;
}

@media (min-width: 900px) {
  .app-panel-content {
    max-width: 1180px;
  }

  .user-panel-content {
    margin-left: auto;
    width: min(460px, 100%);
  }
}
</style>
