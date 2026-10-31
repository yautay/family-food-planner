/** Jeden rejestr sekcji dla komputera, telefonu i menu konta. URL-e są stabilne. */
import {
  BadgeCheck,
  BookOpen,
  CalendarDays,
  CalendarRange,
  Carrot,
  ChartColumn,
  DatabaseBackup,
  Refrigerator,
  Settings,
  Shield,
  ShoppingBasket,
  Users,
} from '@lucide/vue'
import type { FunctionalComponent } from 'vue'
import type { RouteLocationNormalizedLoaded, RouteLocationRaw } from 'vue-router'

import { MAX_STATS_RANGE_DAYS } from '@/api/stats'
import { addDays, daysBetween, isoDate, startOfWeek } from '@/lib/dates'
import { isValidIsoDate } from '@/lib/schemas/template'

export const ADMIN_GROUP = 'Administracja'
export interface NavItem {
  name: string
  label: string
  icon: FunctionalComponent
  primary?: boolean
  adminOnly?: boolean
  group?: string
  /** Szczegóły i edytory należą do sekcji, chociaż są osobnymi trasami. */
  routes: readonly string[]
}
export interface NavGroup {
  label?: string
  items: NavItem[]
}
export const NAV_ITEMS: readonly NavItem[] = [
  {
    name: 'plan-dnia',
    label: 'Plan',
    icon: CalendarDays,
    primary: true,
    routes: ['plan-dnia', 'tydzien', 'statystyki'],
  },
  {
    name: 'przepisy',
    label: 'Przepisy',
    icon: BookOpen,
    primary: true,
    routes: ['przepisy', 'przepis-nowy', 'przepis-szczegol', 'przepis-edycja'],
  },
  {
    name: 'zakupy',
    label: 'Zakupy',
    icon: ShoppingBasket,
    primary: true,
    routes: ['zakupy', 'zakupy-lista'],
  },
  {
    name: 'spizarnia',
    label: 'Spiżarnia',
    icon: Refrigerator,
    primary: true,
    routes: ['spizarnia'],
  },
  {
    name: 'produkty',
    label: 'Biblioteka produktów',
    icon: Carrot,
    routes: ['produkty', 'produkt-nowy', 'produkt-edycja'],
  },
  { name: 'ustawienia', label: 'Dom i ustawienia', icon: Settings, routes: ['ustawienia'] },
  {
    name: 'admin-users',
    label: 'Użytkownicy',
    icon: Shield,
    adminOnly: true,
    group: ADMIN_GROUP,
    routes: ['admin-users'],
  },
  {
    name: 'admin-households',
    label: 'Rodziny',
    icon: Users,
    adminOnly: true,
    group: ADMIN_GROUP,
    routes: ['admin-households'],
  },
  {
    name: 'admin-verification',
    label: 'Weryfikacja',
    icon: BadgeCheck,
    adminOnly: true,
    group: ADMIN_GROUP,
    routes: ['admin-verification'],
  },
  {
    name: 'admin-transfer',
    label: 'Dane',
    icon: DatabaseBackup,
    adminOnly: true,
    group: ADMIN_GROUP,
    routes: ['admin-transfer'],
  },
]
export const PLAN_VIEWS = [
  { name: 'plan-dnia', label: 'Dzień', icon: CalendarDays },
  { name: 'tydzien', label: 'Tydzień', icon: CalendarRange },
  { name: 'statystyki', label: 'Podsumowanie', icon: ChartColumn },
] as const
export function visibleNavItems(isAdmin: boolean): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin)
}
export function navGroups(isAdmin: boolean): NavGroup[] {
  const groups: NavGroup[] = []
  for (const item of visibleNavItems(isAdmin)) {
    const last = groups.at(-1)
    if (last && last.label === item.group) last.items.push(item)
    else groups.push({ label: item.group, items: [item] })
  }
  return groups
}
export function isNavItemActive(item: NavItem, routeName: unknown): boolean {
  return typeof routeName === 'string' && item.routes.includes(routeName)
}
export function isPlanView(routeName: unknown): boolean {
  return PLAN_VIEWS.some((view) => view.name === routeName)
}

/** UI kalendarza, nigdy kopia danych serwera. Daty ISO, zakres włącznie. */
export interface PlanNavigationContext {
  selectedDate: string
  from: string
  to: string
}
type NavigationRoute = Pick<RouteLocationNormalizedLoaded, 'name' | 'params' | 'query'>
/** Powtarzany query/param jest niejednoznaczny i nie jest akceptowany. */
export function validNavigationDate(value: unknown): string | null {
  return typeof value === 'string' && isValidIsoDate(value) ? value : null
}
export function navigationRange(
  query: NavigationRoute['query'],
): { from: string; to: string } | null {
  const from = validNavigationDate(query.from)
  const to = validNavigationDate(query.to)
  return from && to && from <= to && daysBetween(from, to) < MAX_STATS_RANGE_DAYS
    ? { from, to }
    : null
}
export function planNavigationContext(
  route: NavigationRoute,
  today = isoDate(new Date()),
): PlanNavigationContext {
  const requestedRange = navigationRange(route.query)
  const requestedDate = validNavigationDate(route.query.selectedDate)
  let selectedDate = requestedDate ?? today
  if (route.name === 'plan-dnia') selectedDate = validNavigationDate(route.params.date) ?? today
  if (route.name === 'tydzien') {
    const weekStart = startOfWeek(validNavigationDate(route.params.weekStart) ?? today)
    const weekEnd = addDays(weekStart, 6)
    selectedDate =
      requestedDate && requestedDate >= weekStart && requestedDate <= weekEnd
        ? requestedDate
        : today >= weekStart && today <= weekEnd
          ? today
          : weekStart
    return { selectedDate, from: weekStart, to: weekEnd }
  }
  if (
    route.name === 'statystyki' &&
    requestedRange &&
    (selectedDate < requestedRange.from || selectedDate > requestedRange.to)
  ) {
    selectedDate = requestedRange.from
  }
  const from = startOfWeek(selectedDate)
  return { selectedDate, ...(requestedRange ?? { from, to: addDays(from, 6) }) }
}
/** Kontrakt UX03/05/07/10: from/to włącznie, selectedDate = lokalny dzień ISO. */
export function planNavigationTarget(
  name: string,
  context: PlanNavigationContext,
): RouteLocationRaw {
  const { selectedDate, from, to } = context
  const query = { selectedDate, from, to }
  if (name === 'plan-dnia') return { name, params: { date: selectedDate }, query }
  if (name === 'tydzien') return { name, params: { weekStart: startOfWeek(selectedDate) }, query }
  if (name === 'statystyki' || name === 'zakupy' || name === 'przepisy') return { name, query }
  return { name }
}
