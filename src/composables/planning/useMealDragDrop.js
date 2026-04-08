import { ref } from 'vue'

export function useMealDragDrop({ isReadOnly, getMeals, emitMeals }) {
  const draggingIndex = ref(null)
  const dropTargetIndex = ref(null)

  function startMealDrag(index, event) {
    if (isReadOnly()) {
      return
    }

    draggingIndex.value = index
    if (event?.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move'
      event.dataTransfer.setData('text/plain', String(index))
    }
  }

  function allowMealDrop(index, event) {
    if (isReadOnly()) {
      return
    }

    event.preventDefault()
    dropTargetIndex.value = index
    if (event?.dataTransfer) {
      event.dataTransfer.dropEffect = 'move'
    }
  }

  function dropMeal(index, event) {
    if (isReadOnly()) {
      return
    }

    event.preventDefault()
    const fromIndex = draggingIndex.value
    if (!Number.isInteger(fromIndex) || fromIndex === index) {
      draggingIndex.value = null
      dropTargetIndex.value = null
      return
    }

    const nextMeals = getMeals()
    const [movedMeal] = nextMeals.splice(fromIndex, 1)
    if (!movedMeal) {
      draggingIndex.value = null
      dropTargetIndex.value = null
      return
    }

    nextMeals.splice(index, 0, movedMeal)
    emitMeals(nextMeals)
    draggingIndex.value = null
    dropTargetIndex.value = null
  }

  function endMealDrag() {
    draggingIndex.value = null
    dropTargetIndex.value = null
  }

  return {
    draggingIndex,
    dropTargetIndex,
    startMealDrag,
    allowMealDrop,
    dropMeal,
    endMealDrag,
  }
}
