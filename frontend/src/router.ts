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
      // Data jest opcjonalna: `/plan-dnia` otwiera dzisiejszy dzień, a
      // `/plan-dnia/2026-08-17` konkretny — jeden wpis nawigacji, jedna trasa.
      {
        path: 'plan-dnia/:date?',
        name: 'plan-dnia',
        component: () => import('@/pages/plan-dnia/PlanDniaPage.vue'),
        meta: { title: 'Plan dnia' },
      },
      {
        path: 'tydzien/:weekStart?',
        name: 'tydzien',
        component: () => import('@/pages/tydzien/PlanTygodniaPage.vue'),
        meta: { title: 'Tydzień' },
      },
      {
        path: 'przepisy',
        name: 'przepisy',
        component: () => import('@/pages/przepisy/PrzepisyPage.vue'),
        meta: { title: 'Przepisy' },
      },
      // Trasy podrzędne sekcji „Przepisy" — bez nowych pozycji w nawigacji.
      // Statyczne `nowy` musi stać przed parametrem `:id` (kolejność dopasowania).
      {
        path: 'przepisy/nowy',
        name: 'przepis-nowy',
        component: () => import('@/pages/przepisy/PrzepisEdytorPage.vue'),
        meta: { title: 'Nowy przepis' },
      },
      {
        path: 'przepisy/:id',
        name: 'przepis-szczegol',
        component: () => import('@/pages/przepisy/PrzepisSzczegolPage.vue'),
        meta: { title: 'Przepis' },
      },
      {
        path: 'przepisy/:id/edytuj',
        name: 'przepis-edycja',
        component: () => import('@/pages/przepisy/PrzepisEdytorPage.vue'),
        meta: { title: 'Edycja przepisu' },
      },
      {
        path: 'produkty',
        name: 'produkty',
        component: () => import('@/pages/produkty/ProduktyPage.vue'),
        meta: { title: 'Produkty' },
      },
      // Trasy formularza są dziećmi sekcji „Produkty" w sensie nawigacyjnym,
      // ale pozycji w menu nie dokładają (jeden wpis = jedna sekcja).
      {
        path: 'produkty/nowy',
        name: 'produkt-nowy',
        component: () => import('@/pages/produkty/ProduktFormPage.vue'),
        meta: { title: 'Nowy produkt' },
      },
      {
        path: 'produkty/:id/edytuj',
        name: 'produkt-edycja',
        component: () => import('@/pages/produkty/ProduktFormPage.vue'),
        meta: { title: 'Edycja produktu' },
      },
      {
        path: 'spizarnia',
        name: 'spizarnia',
        component: () => import('@/pages/spizarnia/SpizarniaPage.vue'),
        meta: { title: 'Spiżarnia' },
      },
      {
        path: 'zakupy',
        name: 'zakupy',
        component: () => import('@/pages/zakupy/ZakupyPage.vue'),
        meta: { title: 'Zakupy' },
      },
      // Trasa-zaślepka strony listy zakupowej: finalizacja linkuje tutaj, a pełny
      // widok (checkboxy, sortowanie per sklep, druk, udostępnianie) dostarcza
      // BATCH_11 — podmieni WYŁĄCZNIE `component`, bez nowego wpisu nawigacji.
      {
        path: 'zakupy/listy/:id',
        name: 'zakupy-lista',
        component: PlaceholderPage,
        meta: { title: 'Lista zakupowa' },
      },
      {
        path: 'statystyki',
        name: 'statystyki',
        component: PlaceholderPage,
        meta: { title: 'Statystyki' },
      },
      {
        path: 'ustawienia',
        name: 'ustawienia',
        component: () => import('@/pages/UstawieniaPage.vue'),
        meta: { title: 'Ustawienia' },
      },
      {
        path: 'admin/uzytkownicy',
        name: 'admin-users',
        component: () => import('@/pages/admin/AdminUsersPage.vue'),
        meta: { title: 'Użytkownicy', admin: true },
      },
      {
        path: 'admin/rodziny',
        name: 'admin-households',
        component: () => import('@/pages/admin/AdminHouseholdsPage.vue'),
        meta: { title: 'Rodziny', admin: true },
      },
      {
        path: 'admin/weryfikacja',
        name: 'admin-verification',
        component: () => import('@/pages/admin/AdminWeryfikacjaPage.vue'),
        meta: { title: 'Weryfikacja', admin: true },
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
