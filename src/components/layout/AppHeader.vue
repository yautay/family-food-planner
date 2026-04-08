<script setup>
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/authStore'
import { useUiStore } from '../../stores/uiStore'
import { useI18n } from '../../composables/useI18n'
import { catalogNavigationItems, primaryNavigationItems } from '../../config/navigation'
import AppHeaderNavigationPanel from './header/AppHeaderNavigationPanel.vue'
import AppHeaderUserPanel from './header/AppHeaderUserPanel.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const uiStore = useUiStore()
const { t } = useI18n()

const isNavigationMenuOpen = ref(false)
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

const userMenuLabels = computed(() => ({
  loggedAs: t('header.loggedAs'),
  language: t('common.language'),
  theme: t('common.theme'),
  light: t('common.light'),
  dark: t('common.dark'),
  system: t('common.system'),
  account: t('nav.account'),
  accessControl: t('nav.accessControl'),
  logout: t('nav.logout'),
  login: t('nav.login'),
  register: t('nav.register'),
}))

watch(
  () => route.fullPath,
  () => {
    closeAllMenus()
  },
)

function closeAllMenus() {
  isNavigationMenuOpen.value = false
  isUserMenuOpen.value = false
}

function toggleNavigationMenu() {
  isNavigationMenuOpen.value = !isNavigationMenuOpen.value
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
    <AppHeaderNavigationPanel
      v-if="isNavigationMenuOpen"
      :nav-items="navItems"
      :catalog-items="catalogItems"
      :catalog-label="t('nav.catalog')"
      :navigation-menu-label="t('header.navigationMenu')"
      @close="closeAllMenus"
    />
  </transition>

  <transition name="slide-down">
    <AppHeaderUserPanel
      v-if="isUserMenuOpen"
      :user-name="userName"
      :is-logged-in="isLoggedIn"
      :can-manage-permissions="canManagePermissions"
      :locale="uiStore.locale"
      :theme="uiStore.theme"
      :labels="userMenuLabels"
      @close="closeAllMenus"
      @set-locale="uiStore.setLocale"
      @set-theme="uiStore.setTheme"
      @logout="logout"
    />
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
</style>
