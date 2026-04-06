<script setup>
import { computed, onMounted, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/authStore'
import { useUiStore } from './stores/uiStore'
import { useI18n } from './composables/useI18n'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const uiStore = useUiStore()
const { t } = useI18n()

const isLoggedIn = computed(() => authStore.isAuthenticated)
const canManagePermissions = computed(() => authStore.can('permissions.manage'))

function applyTheme() {
  document.documentElement.setAttribute('data-theme', uiStore.resolvedTheme)
}

watch(
  () => uiStore.theme,
  () => applyTheme(),
  { immediate: true },
)

watch(
  () => route.fullPath,
  () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  },
)

onMounted(async () => {
  await authStore.initialize()
})

async function logout() {
  await authStore.logout()
  await router.push('/login')
}
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <h1>Family Food Planner</h1>
        <p>Meal plans and shared shopping</p>
      </div>

      <nav class="nav-links">
        <RouterLink to="/">{{ t('nav.home') }}</RouterLink>
        <RouterLink to="/catalog">{{ t('nav.catalog') }}</RouterLink>
        <RouterLink to="/meals">{{ t('nav.meals') }}</RouterLink>
        <RouterLink to="/ingredients">{{ t('nav.ingredients') }}</RouterLink>
        <RouterLink to="/settings">{{ t('nav.settings') }}</RouterLink>
      </nav>

      <div class="toolbar">
        <label>
          {{ t('common.language') }}
          <select :value="uiStore.locale" @change="uiStore.setLocale($event.target.value)">
            <option value="pl">PL</option>
            <option value="en">EN</option>
          </select>
        </label>

        <label>
          {{ t('common.theme') }}
          <select :value="uiStore.theme" @change="uiStore.setTheme($event.target.value)">
            <option value="light">{{ t('common.light') }}</option>
            <option value="dark">{{ t('common.dark') }}</option>
            <option value="system">{{ t('common.system') }}</option>
          </select>
        </label>

        <template v-if="isLoggedIn">
          <RouterLink to="/account">{{ t('nav.account') }}</RouterLink>
          <RouterLink v-if="canManagePermissions" to="/access-control">ACL</RouterLink>
          <button type="button" @click="logout">{{ t('nav.logout') }}</button>
        </template>

        <template v-else>
          <RouterLink to="/login">{{ t('nav.login') }}</RouterLink>
          <RouterLink to="/register">{{ t('nav.register') }}</RouterLink>
        </template>
      </div>
    </header>

    <main class="page-wrap">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  background:
    radial-gradient(circle at 5% -10%, rgba(255, 180, 110, 0.2), transparent 25%),
    radial-gradient(circle at 95% 10%, rgba(59, 135, 255, 0.2), transparent 35%),
    var(--app-bg);
  color: var(--app-text);
}

.topbar {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
  padding: 1.1rem 1.2rem;
  border-bottom: 1px solid var(--app-border);
  backdrop-filter: blur(8px);
  position: sticky;
  top: 0;
  z-index: 40;
  background: color-mix(in srgb, var(--app-bg) 86%, transparent);
}

.brand h1 {
  font-size: 1.2rem;
  font-weight: 700;
}

.brand p {
  color: var(--app-muted);
  font-size: 0.88rem;
}

.nav-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.8rem;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.7rem;
}

.toolbar label {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.85rem;
}

.toolbar select,
.toolbar button,
.toolbar a {
  font-size: 0.9rem;
}

.page-wrap {
  width: min(1200px, 100% - 2rem);
  margin: 1.2rem auto 0;
  padding-bottom: 2rem;
}

a {
  color: var(--app-link);
  text-decoration: none;
}

a.router-link-active {
  text-decoration: underline;
}

button {
  border: 1px solid var(--app-border);
  border-radius: 0.5rem;
  padding: 0.42rem 0.7rem;
  background: var(--app-surface);
  color: var(--app-text);
}

select {
  border: 1px solid var(--app-border);
  border-radius: 0.45rem;
  padding: 0.35rem 0.5rem;
  background: var(--app-surface);
  color: var(--app-text);
}

@media (min-width: 1024px) {
  .topbar {
    grid-template-columns: 1.2fr 1fr 1.2fr;
    align-items: center;
  }

  .toolbar {
    justify-content: flex-end;
  }
}
</style>
