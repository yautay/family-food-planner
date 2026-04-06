<template>
  <section class="surface-card">
    <h1 class="title is-4">{{ t('accessControl.title') }}</h1>

    <p class="muted">{{ t('accessControl.description') }}</p>
    <p v-if="loadError" class="error-message">{{ loadError }}</p>

    <div class="toolbar-grid" v-if="users.length > 0">
      <label>
        {{ t('catalog.searchProduct') }}
        <input v-model="search" class="input" type="text" />
      </label>
      <label>
        {{ t('common.sortBy') }}
        <select v-model="sortBy" class="input">
          <option value="username">{{ t('auth.username') }}</option>
          <option value="email">{{ t('auth.email') }}</option>
        </select>
      </label>
      <label>
        {{ t('common.sortOrder') }}
        <select v-model="sortDirection" class="input">
          <option value="asc">{{ t('common.sortAsc') }}</option>
          <option value="desc">{{ t('common.sortDesc') }}</option>
        </select>
      </label>
    </div>

    <div v-for="user in filteredUsers" :key="user.id" class="user-card">
      <h2 class="title is-5">{{ user.username }}</h2>
      <p class="muted">{{ user.email }}</p>

      <div class="grid-two">
        <div>
          <h3>{{ t('accessControl.roles') }}</h3>
          <label v-for="role in accessCatalog.roles" :key="role.name" class="checkbox-line">
            <input
              type="checkbox"
              :checked="user.roles.includes(role.name)"
              @change="toggleRole(user, role.name, $event.target.checked)"
            />
            {{ role.name }}
          </label>
        </div>

        <div>
          <h3>{{ t('accessControl.directPermissions') }}</h3>
          <label
            v-for="permission in accessCatalog.permissions"
            :key="permission.name"
            class="checkbox-line"
          >
            <input
              type="checkbox"
              :checked="user.permissions.includes(permission.name)"
              @change="togglePermission(user, permission.name, $event.target.checked)"
            />
            {{ permission.name }}
          </label>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/authStore'
import { useI18n } from '../composables/useI18n'

const authStore = useAuthStore()
const { t } = useI18n()
const search = ref('')
const sortBy = ref('username')
const sortDirection = ref('asc')
const loadError = computed(() =>
  authStore.can('permissions.manage') ? '' : t('accessControl.noPermission'),
)

const users = computed(() => authStore.users)
const accessCatalog = computed(() => authStore.accessCatalog)

const filteredUsers = computed(() => {
  const needle = search.value.trim().toLowerCase()
  const direction = sortDirection.value === 'desc' ? -1 : 1

  const filtered = users.value.filter((user) => {
    if (!needle) {
      return true
    }

    return `${user.username} ${user.email}`.toLowerCase().includes(needle)
  })

  return [...filtered].sort(
    (left, right) =>
      String(left[sortBy.value] ?? '').localeCompare(String(right[sortBy.value] ?? ''), undefined, {
        sensitivity: 'base',
        numeric: true,
      }) * direction,
  )
})

onMounted(async () => {
  if (!authStore.can('permissions.manage')) {
    return
  }

  await Promise.all([authStore.fetchAccessCatalog(), authStore.fetchUsers()])
})

async function toggleRole(user, roleName, checked) {
  if (!authStore.can('permissions.manage')) {
    return
  }

  const roles = checked
    ? Array.from(new Set([...user.roles, roleName]))
    : user.roles.filter((item) => item !== roleName)

  await authStore.updateUserRoles(user.id, roles)
  await authStore.fetchUsers()
}

async function togglePermission(user, permissionName, checked) {
  if (!authStore.can('permissions.manage')) {
    return
  }

  const selectedPermissions = checked
    ? Array.from(new Set([...user.permissions, permissionName]))
    : user.permissions.filter((item) => item !== permissionName)

  const permissions = selectedPermissions.map((name) => ({ name, allow: true }))

  await authStore.updateUserPermissions(user.id, permissions)
  await authStore.fetchUsers()
}
</script>

<style scoped>
.toolbar-grid {
  display: grid;
  gap: 0.65rem;
  margin: 0.75rem 0;
}

@media (min-width: 900px) {
  .toolbar-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
