import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import AppShell from '@/layouts/AppShell.vue'
import LoginPage from '@/pages/LoginPage.vue'
import { useAuthStore } from '@/stores/auth'

/**
 * Mapa tras wg 05_FRONTEND §3. Batch domenowy podmieniał `component`
 * istniejącego wpisu (nigdy nie dokładał pozycji nawigacji); od BATCH_13
 * każda trasa ma już własną stronę, więc `PlaceholderPage` nie jest tu używany.
 *
 * `meta.public` = trasa LOGOWANIA (dostępna bez sesji, ale zalogowany jest z niej
 * odsyłany), `meta.anonymous` = trasa dostępna dla KAŻDEGO — zalogowanego też,
 * bez przekierowania (publiczny link listy, ADR-010), `meta.admin` = wymaga
 * roli ADMIN.
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
      // Strona listy zakupowej — trasa istnieje od B10 (finalizacja tu linkuje),
      // BATCH_11 podmienił WYŁĄCZNIE `component`, bez nowego wpisu nawigacji.
      {
        path: 'zakupy/listy/:id',
        name: 'zakupy-lista',
        component: () => import('@/pages/zakupy/ListaZakupowPage.vue'),
        meta: { title: 'Lista zakupowa' },
      },
      {
        path: 'statystyki',
        name: 'statystyki',
        component: () => import('@/pages/StatystykiPage.vue'),
        meta: { title: 'Statystyki' },
      },
      // Import jadłospisów PDF (BATCH_15). Wyjątek od reguły „batch podmienia
      // component istniejącej trasy": mapa 05_FRONTEND §3 nie przewidywała
      // osobnego ekranu importu, bo powstawała przed audytem PDF-ów. Trasa
      // i pozycja nawigacji wchodzą razem — karta B15 §Frontend.
      {
        path: 'import',
        name: 'import',
        component: () => import('@/pages/ImportPage.vue'),
        meta: { title: 'Import PDF' },
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
      // Dane instancji (BATCH_14) — podsekcja administracji zapowiedziana
      // w 05_FRONTEND §3 („/admin/* → AdminPage: … import/eksport").
      {
        path: 'admin/dane',
        name: 'admin-transfer',
        component: () => import('@/pages/admin/AdminDanePage.vue'),
        meta: { title: 'Dane', admin: true },
      },
    ],
  },
  // Publiczny link listy (ADR-010): POZA `AppShell` i poza guardem sesji.
  // Osobny chunk (import leniwy), bo strona ma być lekka i nie ciągnąć shella —
  // B12 zrobi ją offline-capable (karta B11, Implementation Notes pkt 2).
  {
    path: '/l/:token',
    name: 'publiczna-lista',
    component: () => import('@/pages/public/PublicznaListaPage.vue'),
    meta: { anonymous: true, title: 'Lista zakupowa' },
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
  // Publiczny link jest dostępny dla WSZYSTKICH i nie wymaga wiedzy o sesji:
  // sprawdzamy to PRZED `ensureLoaded`, żeby otwarcie `/l/{token}` nie strzelało
  // do `/auth/me` i żeby zalogowany nie został odesłany na plan dnia (co robi
  // `meta.public`, przeznaczone dla ekranu logowania).
  if (to.meta.anonymous === true) {
    return true
  }

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
