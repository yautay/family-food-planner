import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import AppShell from '@/layouts/AppShell.vue'
import LoginPage from '@/pages/LoginPage.vue'
import PlaceholderPage from '@/pages/PlaceholderPage.vue'
import { useAuthStore } from '@/stores/auth'

/**
 * Mapa tras wg 05_FRONTEND §3. Sekcje domenowe pokazują na razie
 * `PlaceholderPage` — kolejne batche podmieniają wyłącznie `component`.
 *
 * `meta.public` = trasa dostępna bez sesji, `meta.admin` = wymaga roli ADMIN.
 */
export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: LoginPage,
    meta: { public: true },
  },
  {
    path: '/',
    component: AppShell,
    children: [
      { path: '', redirect: { name: 'plan-dnia' } },
      {
        path: 'plan-dnia',
        name: 'plan-dnia',
        component: PlaceholderPage,
        meta: { title: 'Plan dnia' },
      },
      { path: 'tydzien', name: 'tydzien', component: PlaceholderPage, meta: { title: 'Tydzień' } },
      {
        path: 'przepisy',
        name: 'przepisy',
        component: PlaceholderPage,
        meta: { title: 'Przepisy' },
      },
      {
        path: 'produkty',
        name: 'produkty',
        component: PlaceholderPage,
        meta: { title: 'Produkty' },
      },
      {
        path: 'spizarnia',
        name: 'spizarnia',
        component: PlaceholderPage,
        meta: { title: 'Spiżarnia' },
      },
      { path: 'zakupy', name: 'zakupy', component: PlaceholderPage, meta: { title: 'Zakupy' } },
      {
        path: 'statystyki',
        name: 'statystyki',
        component: PlaceholderPage,
        meta: { title: 'Statystyki' },
      },
      {
        path: 'ustawienia',
        name: 'ustawienia',
        component: PlaceholderPage,
        meta: { title: 'Ustawienia' },
      },
      {
        path: 'admin/uzytkownicy',
        name: 'admin-users',
        component: () => import('@/pages/admin/AdminUsersPage.vue'),
        meta: { title: 'Użytkownicy', admin: true },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: { name: 'plan-dnia' },
  },
]

/**
 * Guard sesji (05_FRONTEND §3): brak sesji → `/login`, zalogowany na `/login`
 * → `/plan-dnia`, trasa administracyjna dla nie-admina → `/plan-dnia`
 * (nie pokazujemy, że coś takiego istnieje).
 */
export async function authGuard(
  to: { name?: unknown; fullPath: string; meta: Record<string, unknown> },
  auth: ReturnType<typeof useAuthStore>,
): Promise<true | { name: string; query?: Record<string, string> }> {
  await auth.ensureLoaded()

  if (to.meta.public === true) {
    return auth.isAuthenticated ? { name: 'plan-dnia' } : true
  }
  if (!auth.isAuthenticated) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  if (to.meta.admin === true && !auth.isAdmin) {
    return { name: 'plan-dnia' }
  }
  return true
}

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => authGuard(to, useAuthStore()))
