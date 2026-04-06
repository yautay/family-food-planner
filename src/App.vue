<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/authStore'
import { useUiStore } from './stores/uiStore'
import { useI18n } from './composables/useI18n'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const uiStore = useUiStore()
const { t } = useI18n()
const isMenuOpen = ref(false)

const isLoggedIn = computed(() => authStore.isAuthenticated)
const canManagePermissions = computed(() => authStore.can('permissions.manage'))
const navbarThemeClass = computed(() => (uiStore.resolvedTheme === 'dark' ? 'is-dark' : 'is-light'))

function applyTheme() {
  document.documentElement.setAttribute('data-theme', uiStore.resolvedTheme)
}

function closeMobileMenu() {
  isMenuOpen.value = false
}

function toggleMobileMenu() {
  isMenuOpen.value = !isMenuOpen.value
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
    closeMobileMenu()
  },
)

onMounted(async () => {
  await authStore.initialize()
})

async function logout() {
  await authStore.logout()
  await router.push('/login')
  closeMobileMenu()
}
</script>

<template>
  <div>
    <nav class="navbar app-navbar" :class="navbarThemeClass" role="navigation" aria-label="main navigation">
      <div class="container is-fluid">
        <div class="navbar-brand">
          <RouterLink class="navbar-item" to="/" @click="closeMobileMenu">
            <span class="has-text-weight-semibold">Family Food Planner</span>
          </RouterLink>

          <button
            type="button"
            class="navbar-burger"
            :class="{ 'is-active': isMenuOpen }"
            aria-label="menu"
            :aria-expanded="isMenuOpen ? 'true' : 'false'"
            @click="toggleMobileMenu"
          >
            <span aria-hidden="true"></span>
            <span aria-hidden="true"></span>
            <span aria-hidden="true"></span>
          </button>
        </div>

        <div class="navbar-menu" :class="{ 'is-active': isMenuOpen }">
          <div class="navbar-start">
            <RouterLink class="navbar-item" to="/" @click="closeMobileMenu">{{ t('nav.home') }}</RouterLink>
            <RouterLink class="navbar-item" to="/catalog" @click="closeMobileMenu">{{ t('nav.catalog') }}</RouterLink>
            <RouterLink class="navbar-item" to="/meals" @click="closeMobileMenu">{{ t('nav.meals') }}</RouterLink>
            <RouterLink class="navbar-item" to="/ingredients" @click="closeMobileMenu">{{ t('nav.ingredients') }}</RouterLink>
            <RouterLink class="navbar-item" to="/settings" @click="closeMobileMenu">{{ t('nav.settings') }}</RouterLink>
          </div>

          <div class="navbar-end">
            <div class="navbar-item">
              <div class="field is-grouped is-grouped-multiline app-toolbar-controls">
                <div class="control">
                  <div class="select is-small">
                    <select aria-label="Language" :value="uiStore.locale" @change="uiStore.setLocale($event.target.value)">
                      <option value="pl">PL</option>
                      <option value="en">EN</option>
                    </select>
                  </div>
                </div>

                <div class="control">
                  <div class="select is-small">
                    <select aria-label="Theme" :value="uiStore.theme" @change="uiStore.setTheme($event.target.value)">
                      <option value="light">{{ t('common.light') }}</option>
                      <option value="dark">{{ t('common.dark') }}</option>
                      <option value="system">{{ t('common.system') }}</option>
                    </select>
                  </div>
                </div>

                <template v-if="isLoggedIn">
                  <div class="control">
                    <RouterLink class="button is-small" to="/account" @click="closeMobileMenu">{{ t('nav.account') }}</RouterLink>
                  </div>
                  <div v-if="canManagePermissions" class="control">
                    <RouterLink class="button is-small" to="/access-control" @click="closeMobileMenu">ACL</RouterLink>
                  </div>
                  <div class="control">
                    <button type="button" class="button is-small is-danger is-light" @click="logout">
                      {{ t('nav.logout') }}
                    </button>
                  </div>
                </template>

                <template v-else>
                  <div class="control">
                    <RouterLink class="button is-small" to="/login" @click="closeMobileMenu">{{ t('nav.login') }}</RouterLink>
                  </div>
                  <div class="control">
                    <RouterLink class="button is-small is-primary" to="/register" @click="closeMobileMenu">
                      {{ t('nav.register') }}
                    </RouterLink>
                  </div>
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>
    </nav>

    <main class="section app-main-section">
      <div class="container app-main-container">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<style scoped>
.app-navbar {
  position: sticky;
  top: 0;
  z-index: 40;
}

.app-main-section {
  padding-top: 1.25rem;
}

.app-main-container {
  max-width: 1180px;
}

.app-toolbar-controls {
  align-items: center;
}
</style>
