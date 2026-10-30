<script setup lang="ts">
import { ChevronDown, LogOut, UserRound } from '@lucide/vue'
import {
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuPortal,
  DropdownMenuRoot,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from 'reka-ui'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ADMIN_GROUP, isNavItemActive, visibleNavItems } from '@/lib/navigation'
import { auth as authTexts } from '@/lib/texts'

const props = defineProps<{
  displayName?: string
  householdName?: string
  isAdmin: boolean
  pending: boolean
  mobile?: boolean
}>()
defineEmits<{ logout: [] }>()
const route = useRoute()
const open = ref(false)
const openedPath = ref(route.path)
const items = computed(() => visibleNavItems(props.isAdmin).filter((item) => !item.primary))
const active = computed(() => items.value.some((item) => isNavItemActive(item, route.name)))
const suffix = computed(() => (props.mobile ? '-mobile' : ''))
watch(
  open,
  (value) => {
    if (value) openedPath.value = route.path
  },
  { flush: 'sync' },
)
function closeAutoFocus(event: Event): void {
  // Po rzeczywistej nawigacji fokus należy do treści AppShell. Escape nadal
  // przywraca wywołujący przycisk zgodnie z domyślnym zachowaniem Reka.
  if (route.path !== openedPath.value) event.preventDefault()
}
function selectDestination(event: Event, name: string): void {
  // Zamykamy dopiero po zaakceptowaniu nawigacji przez router. Dzięki temu
  // powrót fokusu menu nie wyprzedza lazy-loadu ani guarda niezapisanego formularza.
  if (route.name !== name) event.preventDefault()
}
watch(
  () => route.fullPath,
  () => {
    open.value = false
  },
)
</script>

<template>
  <DropdownMenuRoot v-model:open="open">
    <DropdownMenuTrigger
      class="hover:bg-accent flex min-h-11 max-w-full items-center gap-3 rounded-xl p-2 text-left"
      :class="[mobile ? '' : 'w-full', active ? 'bg-accent text-primary' : '']"
      :data-testid="`account-toggle${suffix}`"
      aria-label="Konto i ustawienia"
    >
      <span
        class="bg-accent text-primary flex size-9 shrink-0 items-center justify-center rounded-full"
        ><UserRound class="size-5" aria-hidden="true"
      /></span>
      <span v-if="!mobile" class="min-w-0 flex-1"
        ><span class="block truncate text-sm font-medium" data-testid="current-user">{{
          displayName
        }}</span
        ><span v-if="householdName" class="text-muted-foreground block truncate text-xs">{{
          householdName
        }}</span></span
      >
      <ChevronDown class="size-4 shrink-0" aria-hidden="true" />
    </DropdownMenuTrigger>
    <DropdownMenuPortal>
      <DropdownMenuContent
        align="end"
        :side-offset="8"
        class="border-border bg-popover text-popover-foreground z-50 max-h-[var(--reka-dropdown-menu-content-available-height)] w-64 max-w-[calc(100vw-2rem)] overflow-y-auto rounded-xl border p-2 shadow-lg print:hidden"
        :data-testid="`account-menu${suffix}`"
        @close-auto-focus="closeAutoFocus"
      >
        <DropdownMenuLabel class="text-muted-foreground px-3 py-2 text-xs">{{
          displayName
        }}</DropdownMenuLabel>
        <template v-for="(item, index) in items" :key="item.name">
          <template v-if="item.group && items[index - 1]?.group !== item.group"
            ><DropdownMenuSeparator class="bg-border my-2 h-px" /><DropdownMenuLabel
              class="text-muted-foreground px-3 py-2 text-xs font-medium"
              :data-testid="`nav-group-${ADMIN_GROUP}${suffix}`"
              >{{ item.group }}</DropdownMenuLabel
            ></template
          >
          <DropdownMenuItem as-child @select="selectDestination($event, item.name)">
            <RouterLink
              :to="{ name: item.name }"
              class="data-[highlighted]:bg-accent flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm outline-none"
              :class="isNavItemActive(item, route.name) ? 'bg-accent font-medium' : ''"
              :aria-current="isNavItemActive(item, route.name) ? 'page' : undefined"
              :data-testid="`account-item-${item.name}${suffix}`"
              ><component :is="item.icon" class="size-5 shrink-0" aria-hidden="true" />{{
                item.label
              }}</RouterLink
            >
          </DropdownMenuItem>
        </template>
        <DropdownMenuSeparator class="bg-border my-2 h-px" />
        <DropdownMenuItem as-child :disabled="pending" @select="$emit('logout')">
          <button
            type="button"
            :disabled="pending"
            class="data-[highlighted]:bg-accent flex min-h-11 w-full items-center gap-3 rounded-lg px-3 text-sm outline-none disabled:opacity-50"
            :data-testid="`logout-button${suffix}`"
          >
            <LogOut class="size-5" aria-hidden="true" />{{ authTexts.logout }}
          </button>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>
