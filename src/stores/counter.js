import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { getCount, setCount } from '@/db'

export const useCounterStore = defineStore('counter', () => {
  const count = ref(getCount())
  const doubleCount = computed(() => count.value * 2)
  function increment() {
    count.value++
    setCount(count.value)
  }

  return { count, doubleCount, increment }
})
