<template>
  <section class="surface-card">
    <h1 class="title is-4">{{ t('accessControl.title') }}</h1>

    <p class="muted">{{ t('accessControl.description') }}</p>
    <p v-if="loadError" class="error-message">{{ loadError }}</p>

    <div v-for="user in users" :key="user.id" class="user-card">
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
import { computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/authStore'
import { useI18n } from '../composables/useI18n'

const authStore = useAuthStore()
const { t } = useI18n()
const loadError = computed(() =>
  authStore.can('permissions.manage') ? '' : t('accessControl.noPermission'),
)

const users = computed(() => authStore.users)
const accessCatalog = computed(() => authStore.accessCatalog)

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
