import apiClient from './apiClient'

function mealPlanPath(mealPlanId = '') {
  return `/meal-plans${mealPlanId ? `/${mealPlanId}` : ''}`
}

function dayPlanPath(dayPlanId = '') {
  return `/day-plans${dayPlanId ? `/${dayPlanId}` : ''}`
}

function shoppingListPath(shoppingListId = '') {
  return `/shopping-lists${shoppingListId ? `/${shoppingListId}` : ''}`
}

export const mealPlannerApi = {
  fetchMealPlans: () => apiClient.get(mealPlanPath()),
  fetchMealPlan: (mealPlanId) => apiClient.get(mealPlanPath(mealPlanId)),
  createMealPlan: (payload) => apiClient.post(mealPlanPath(), payload),
  updateMealPlan: (mealPlanId, payload) => apiClient.put(mealPlanPath(mealPlanId), payload),
  deleteMealPlan: (mealPlanId) => apiClient.delete(mealPlanPath(mealPlanId)),
  replaceMealPlanMealSlots: (mealPlanId, slots) =>
    apiClient.put(`${mealPlanPath(mealPlanId)}/meal-slots`, { slots }),
  updateMealPlanDaySlot: (mealPlanId, plannedDate, payload) =>
    apiClient.put(`${mealPlanPath(mealPlanId)}/day-slots/${plannedDate}`, payload),
  replaceMealPlanDaySlotMeals: (mealPlanId, plannedDate, meals) =>
    apiClient.put(`${mealPlanPath(mealPlanId)}/day-slots/${plannedDate}/meals`, { meals }),
  replaceMealPlanEntries: (mealPlanId, entries) =>
    apiClient.put(`${mealPlanPath(mealPlanId)}/entries`, { entries }),

  fetchDayPlans: () => apiClient.get(dayPlanPath()),
  fetchDayPlan: (dayPlanId) => apiClient.get(dayPlanPath(dayPlanId)),
  createDayPlan: (payload) => apiClient.post(dayPlanPath(), payload),
  updateDayPlan: (dayPlanId, payload) => apiClient.put(dayPlanPath(dayPlanId), payload),
  deleteDayPlan: (dayPlanId) => apiClient.delete(dayPlanPath(dayPlanId)),
  replaceDayPlanMeals: (dayPlanId, meals) =>
    apiClient.put(`${dayPlanPath(dayPlanId)}/meals`, { meals }),

  fetchShoppingLists: () => apiClient.get(shoppingListPath()),
  fetchShoppingList: (shoppingListId) => apiClient.get(shoppingListPath(shoppingListId)),
  createShoppingList: (payload) => apiClient.post(shoppingListPath(), payload),
  updateShoppingList: (shoppingListId, payload) =>
    apiClient.put(shoppingListPath(shoppingListId), payload),
  deleteShoppingList: (shoppingListId) => apiClient.delete(shoppingListPath(shoppingListId)),
  addShoppingListItem: (shoppingListId, payload) =>
    apiClient.post(`${shoppingListPath(shoppingListId)}/items`, payload),
  updateShoppingListItem: (shoppingListId, itemId, payload) =>
    apiClient.put(`${shoppingListPath(shoppingListId)}/items/${itemId}`, payload),
  deleteShoppingListItem: (shoppingListId, itemId) =>
    apiClient.delete(`${shoppingListPath(shoppingListId)}/items/${itemId}`),
  generateShoppingListFromMealPlan: (mealPlanId, payload = {}) =>
    apiClient.post(`/shopping-lists/from-meal-plan/${mealPlanId}`, payload),
}
