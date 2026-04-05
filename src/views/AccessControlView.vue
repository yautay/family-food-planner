<template>
  <section class="surface-card">
    <h1>Uprawnienia uzytkownikow</h1>

    <p class="muted">Tylko uzytkownik z uprawnieniem <code>permissions.manage</code> moze edytowac ten widok.</p>
    <p v-if="loadError" class="error-message">{{ loadError }}</p>

    <div v-for="user in users" :key="user.id" class="user-card">
      <h2>{{ user.username }}</h2>
      <p class="muted">{{ user.email }}</p>

      <div class="grid-two">
        <div>
          <h3>Role</h3>
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
          <h3>Uprawnienia bezposrednie</h3>
          <label v-for="permission in accessCatalog.permissions" :key="permission.name" class="checkbox-line">
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

const authStore = useAuthStore()
const loadError = computed(() => authStore.can('permissions.manage') ? '' : 'Brak uprawnien do zarzadzania ACL.')

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
