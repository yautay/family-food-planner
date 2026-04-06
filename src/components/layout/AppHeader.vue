<script setup>
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/authStore'
import { useUiStore } from '../../stores/uiStore'
import { useI18n } from '../../composables/useI18n'
import { catalogNavigationItems, primaryNavigationItems } from '../../config/navigation'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const uiStore = useUiStore()
const { t } = useI18n()

const isNavigationMenuOpen = ref(false)
const isCatalogExpanded = ref(false)
const isUserMenuOpen = ref(false)

const isLoggedIn = computed(() => authStore.isAuthenticated)
const canManagePermissions = computed(() => authStore.can('permissions.manage'))
const navbarThemeClass = computed(() => (uiStore.resolvedTheme === 'dark' ? 'is-dark' : 'is-light'))
const userName = computed(() => authStore.user?.username ?? t('header.guest'))

const navItems = computed(() =>
  primaryNavigationItems.map((item) => ({
    ...item,
    label: t(item.labelKey),
  })),
)

const catalogItems = computed(() =>
  catalogNavigationItems.map((item) => ({
    ...item,
    label: t(item.labelKey),
  })),
)

watch(
  () => route.fullPath,
  () => {
    closeAllMenus()
  },
)

function closeAllMenus() {
  isNavigationMenuOpen.value = false
  isCatalogExpanded.value = false
  isUserMenuOpen.value = false
}

function toggleNavigationMenu() {
  isNavigationMenuOpen.value = !isNavigationMenuOpen.value
  if (!isNavigationMenuOpen.value) {
    isCatalogExpanded.value = false
  }
}

function toggleCatalog() {
  isCatalogExpanded.value = !isCatalogExpanded.value
}

function toggleUserMenu() {
  isUserMenuOpen.value = !isUserMenuOpen.value
}

async function logout() {
  await authStore.logout()
  closeAllMenus()
  await router.push('/login')
}
</script>

<template>
  <header class="navbar app-navbar" :class="navbarThemeClass" role="banner">
    <div class="container is-fluid app-navbar-content">
      <div class="header-left-side">
        <button
          type="button"
          class="app-icon-button burger-button"
          :aria-label="t('header.navigationToggle')"
          :aria-expanded="isNavigationMenuOpen ? 'true' : 'false'"
          @click="toggleNavigationMenu"
        >
          <span aria-hidden="true"></span>
          <span aria-hidden="true"></span>
          <span aria-hidden="true"></span>
        </button>

        <RouterLink class="brand-link" to="/" @click="closeAllMenus"
          >Family Food Planner</RouterLink
        >
      </div>

      <div class="header-right-side">
        <button
          type="button"
          class="app-icon-button"
          :aria-label="t('header.userMenuToggle')"
          :aria-expanded="isUserMenuOpen ? 'true' : 'false'"
          @click="toggleUserMenu"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="8" r="4"></circle>
            <path d="M4 20a8 8 0 0 1 16 0"></path>
          </svg>
        </button>
      </div>
    </div>
  </header>

  <transition name="slide-down">
    <div v-if="isNavigationMenuOpen" class="menu-panel">
      <div class="container app-panel-content">
        <nav class="menu-list-block" :aria-label="t('header.navigationMenu')">
          <RouterLink
            v-for="item in navItems"
            :key="item.key"
            class="menu-link"
            :to="item.to"
            @click="closeAllMenus"
          >
            {{ item.label }}
          </RouterLink>

          <button
            type="button"
            class="menu-link menu-expand"
            :aria-expanded="isCatalogExpanded ? 'true' : 'false'"
            @click="toggleCatalog"
          >
            <span>{{ t('nav.catalog') }}</span>
            <span class="expand-indicator">{{ isCatalogExpanded ? '-' : '+' }}</span>
          </button>

          <div v-if="isCatalogExpanded" class="submenu-block">
            <RouterLink
              v-for="item in catalogItems"
              :key="item.key"
              class="submenu-link"
              :to="item.to"
              @click="closeAllMenus"
            >
              {{ item.label }}
            </RouterLink>
          </div>
        </nav>
      </div>
    </div>
  </transition>

  <transition name="slide-down">
    <div v-if="isUserMenuOpen" class="menu-panel user-panel">
      <div class="container app-panel-content user-panel-content">
        <div class="user-summary">{{ t('header.loggedAs') }}: {{ userName }}</div>

        <div class="field-grid">
          <label>
            {{ t('common.language') }}
            <div class="select is-small">
              <select
                :aria-label="t('common.language')"
                :value="uiStore.locale"
                @change="uiStore.setLocale($event.target.value)"
              >
                <option value="pl">PL</option>
                <option value="en">EN</option>
              </select>
            </div>
          </label>

          <label>
            {{ t('common.theme') }}
            <div class="select is-small">
              <select
                :aria-label="t('common.theme')"
                :value="uiStore.theme"
                @change="uiStore.setTheme($event.target.value)"
              >
                <option value="light">{{ t('common.light') }}</option>
                <option value="dark">{{ t('common.dark') }}</option>
                <option value="system">{{ t('common.system') }}</option>
              </select>
            </div>
          </label>
        </div>

        <div class="actions-row">
          <template v-if="isLoggedIn">
            <RouterLink class="button is-small" to="/account" @click="closeAllMenus">{{
              t('nav.account')
            }}</RouterLink>
            <RouterLink
              v-if="canManagePermissions"
              class="button is-small"
              to="/access-control"
              @click="closeAllMenus"
            >
              {{ t('nav.accessControl') }}
            </RouterLink>
            <button type="button" class="button is-small is-danger is-light" @click="logout">
              {{ t('nav.logout') }}
            </button>
          </template>

          <template v-else>
            <RouterLink class="button is-small" to="/login" @click="closeAllMenus">{{
              t('nav.login')
            }}</RouterLink>
            <RouterLink class="button is-small is-primary" to="/register" @click="closeAllMenus">{{
              t('nav.register')
            }}</RouterLink>
          </template>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.app-navbar {
  position: sticky;
  top: 0;
  z-index: 50;
  border-bottom: 1px solid var(--app-border);
}

.app-navbar-content {
  min-height: 3.65rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-left-side,
.header-right-side {
  display: flex;
  align-items: center;
  gap: 0.65rem;
}

.brand-link {
  font-weight: 700;
  color: var(--app-text);
}

.app-icon-button {
  width: 2.2rem;
  height: 2.2rem;
  border: 1px solid var(--app-border);
  border-radius: 0.6rem;
  background: var(--app-surface);
  color: var(--app-text);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.app-icon-button svg {
  width: 1.25rem;
  height: 1.25rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.75;
}

.burger-button {
  flex-direction: column;
  gap: 0.2rem;
}

.burger-button span {
  width: 1rem;
  height: 2px;
  background: currentColor;
  display: block;
}

.menu-panel {
  position: sticky;
  top: 3.65rem;
  z-index: 45;
  background: var(--app-surface);
  border-bottom: 1px solid var(--app-border);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
}

.app-panel-content {
  padding-top: 0.75rem;
  padding-bottom: 0.75rem;
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
  cursor: pointer;
}

.submenu-block {
  padding-left: 0.65rem;
  display: grid;
  gap: 0.35rem;
}

.submenu-link {
  background: var(--app-surface-alt);
}

.expand-indicator {
  font-weight: 700;
}

.user-panel {
  top: calc(3.65rem + 0.1rem);
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

.slide-down-enter-active,
.slide-down-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}

.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-6px);
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
