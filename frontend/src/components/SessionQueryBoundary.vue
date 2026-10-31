<script setup lang="ts">
import { QueryClient, VUE_QUERY_CLIENT, useQueryClient } from '@tanstack/vue-query'
import { onScopeDispose, provide } from 'vue'

const parent = useQueryClient()
// Callbacki mutacji mogą działać po unmount. Każda generacja otrzymuje osobny
// klient, więc onError starego widoku nie może przywrócić A w cache konta B.
const client = new QueryClient({ defaultOptions: parent.getDefaultOptions() })
client.mount()
provide(VUE_QUERY_CLIENT, client)
onScopeDispose(() => {
  client.clear()
  client.unmount()
})
</script>

<template><slot /></template>
