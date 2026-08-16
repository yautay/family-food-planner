/**
 * Nawigacja aplikacji — jedno źródło dla sidebara (desktop) i bottom-nav
 * (mobile), 06_UIUX §5. Kolejność jest wiążąca: tak samo w obu wariantach.
 *
 * `primary: true` = pozycja widoczna wprost w bottom-nav (Plan / Przepisy /
 * Zakupy); reszta chowa się pod „Więcej". `adminOnly` = tylko rola ADMIN.
 */

import {
  CalendarDays,
  CalendarRange,
  ChartColumn,
  ChefHat,
  Carrot,
  Refrigerator,
  Settings,
  Shield,
  ShoppingCart,
} from '@lucide/vue'
import type { FunctionalComponent } from 'vue'

export interface NavItem {
  /** Nazwa trasy z `router.ts`. */
  name: string
  label: string
  icon: FunctionalComponent
  primary?: boolean
  adminOnly?: boolean
}

export const NAV_ITEMS: readonly NavItem[] = [
  { name: 'plan-dnia', label: 'Plan dnia', icon: CalendarDays, primary: true },
  { name: 'tydzien', label: 'Tydzień', icon: CalendarRange },
  { name: 'przepisy', label: 'Przepisy', icon: ChefHat, primary: true },
  { name: 'produkty', label: 'Produkty', icon: Carrot },
  { name: 'spizarnia', label: 'Spiżarnia', icon: Refrigerator },
  { name: 'zakupy', label: 'Zakupy', icon: ShoppingCart, primary: true },
  { name: 'statystyki', label: 'Statystyki', icon: ChartColumn },
  { name: 'ustawienia', label: 'Ustawienia', icon: Settings },
  { name: 'admin-users', label: 'Admin', icon: Shield, adminOnly: true },
] as const

/** Pozycje widoczne dla danej roli. */
export function visibleNavItems(isAdmin: boolean): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin)
}
