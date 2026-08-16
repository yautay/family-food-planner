/**
 * Nawigacja aplikacji — jedno źródło dla sidebara (desktop) i bottom-nav
 * (mobile), 06_UIUX §5. Kolejność jest wiążąca: tak samo w obu wariantach.
 *
 * `primary: true` = pozycja widoczna wprost w bottom-nav (Plan / Przepisy /
 * Zakupy); reszta chowa się pod „Więcej". `adminOnly` = tylko rola ADMIN.
 * `group` = nagłówek sekcji w sidebarze; każdy wpis pozostaje realną trasą,
 * więc kolejne batche dokładają podsekcje administracji jedną linijką.
 */

import {
  BadgeCheck,
  CalendarDays,
  CalendarRange,
  ChartColumn,
  ChefHat,
  Carrot,
  Refrigerator,
  Settings,
  Shield,
  ShoppingCart,
  Users,
} from '@lucide/vue'
import type { FunctionalComponent } from 'vue'

/** Nagłówek sekcji administracyjnej (Użytkownicy / Rodziny / kolejne w B04+). */
export const ADMIN_GROUP = 'Administracja'

export interface NavItem {
  /** Nazwa trasy z `router.ts`. */
  name: string
  label: string
  icon: FunctionalComponent
  primary?: boolean
  adminOnly?: boolean
  group?: string
}

export interface NavGroup {
  /** `undefined` = pozycje bez nagłówka (główna część menu). */
  label?: string
  items: NavItem[]
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
  {
    name: 'admin-users',
    label: 'Użytkownicy',
    icon: Shield,
    adminOnly: true,
    group: ADMIN_GROUP,
  },
  {
    name: 'admin-households',
    label: 'Rodziny',
    icon: Users,
    adminOnly: true,
    group: ADMIN_GROUP,
  },
  {
    name: 'admin-verification',
    label: 'Weryfikacja',
    icon: BadgeCheck,
    adminOnly: true,
    group: ADMIN_GROUP,
  },
] as const

/** Pozycje widoczne dla danej roli. */
export function visibleNavItems(isAdmin: boolean): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin)
}

/** Te same pozycje pogrupowane pod nagłówkami — kolejność bez zmian. */
export function navGroups(isAdmin: boolean): NavGroup[] {
  const groups: NavGroup[] = []
  for (const item of visibleNavItems(isAdmin)) {
    const last = groups.at(-1)
    if (last && last.label === item.group) {
      last.items.push(item)
    } else {
      groups.push({ label: item.group, items: [item] })
    }
  }
  return groups
}
