import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import AppShell from '@/layouts/AppShell.vue'
import LoginPage from '@/pages/LoginPage.vue'

/**
 * Trasy BATCH_01 — wyłącznie szkielet. Docelową mapę (plan-dnia, tydzien,
 * przepisy, produkty, spizarnia, zakupy, statystyki, ustawienia, /l/:token)
 * opisuje 05_FRONTEND §3; strony dostarczają kolejne batche.
 *
 * Guard „brak sesji → /login" dostarcza BATCH_02 (nie ma jeszcze authStore).
 */
export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: AppShell,
  },
  {
    path: '/login',
    name: 'login',
    component: LoginPage,
  },
  {
    // Nieznana ścieżka wraca do shella — dedykowany widok 404 dostarczy B02.
    path: '/:pathMatch(.*)*',
    redirect: { name: 'home' },
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
