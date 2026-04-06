import { defineStore } from 'pinia'
import apiClient from '../services/apiClient'

export const useMealPlannerStore = defineStore('mealPlanner', {
  state: () => ({
    mealPlans: [],
    activeMealPlan: null,
    shoppingLists: [],
    activeShoppingList: null,
  }),
  actions: {
    async fetchMealPlans() {
      const response = await apiClient.get('/meal-plans')
      this.mealPlans = response.data
      return response.data
    },

    async fetchMealPlan(mealPlanId) {
      const response = await apiClient.get(`/meal-plans/${mealPlanId}`)
      this.activeMealPlan = response.data
      return response.data
    },

    async createMealPlan(payload) {
      const response = await apiClient.post('/meal-plans', payload)
      await this.fetchMealPlans()
      this.activeMealPlan = response.data
      return response.data
    },

    async updateMealPlan(mealPlanId, payload) {
      const response = await apiClient.put(`/meal-plans/${mealPlanId}`, payload)
      await this.fetchMealPlans()
      this.activeMealPlan = response.data
      return response.data
    },

    async deleteMealPlan(mealPlanId) {
      await apiClient.delete(`/meal-plans/${mealPlanId}`)
      await this.fetchMealPlans()

      if (this.activeMealPlan?.id === mealPlanId) {
        this.activeMealPlan = null
      }
    },

    async replaceMealPlanEntries(mealPlanId, entries) {
      const response = await apiClient.put(`/meal-plans/${mealPlanId}/entries`, {
        entries,
      })
      this.activeMealPlan = response.data
      await this.fetchMealPlans()
      return response.data
    },

    async fetchShoppingLists() {
      const response = await apiClient.get('/shopping-lists')
      this.shoppingLists = response.data
      return response.data
    },

    async fetchShoppingList(shoppingListId) {
      const response = await apiClient.get(`/shopping-lists/${shoppingListId}`)
      this.activeShoppingList = response.data
      return response.data
    },

    async createShoppingList(payload) {
      const response = await apiClient.post('/shopping-lists', payload)
      await this.fetchShoppingLists()
      this.activeShoppingList = response.data
      return response.data
    },

    async updateShoppingList(shoppingListId, payload) {
      const response = await apiClient.put(`/shopping-lists/${shoppingListId}`, payload)
      await this.fetchShoppingLists()
      this.activeShoppingList = response.data
      return response.data
    },

    async deleteShoppingList(shoppingListId) {
      await apiClient.delete(`/shopping-lists/${shoppingListId}`)
      await this.fetchShoppingLists()

      if (this.activeShoppingList?.id === shoppingListId) {
        this.activeShoppingList = null
      }
    },

    async addShoppingListItem(shoppingListId, payload) {
      const response = await apiClient.post(`/shopping-lists/${shoppingListId}/items`, payload)
      this.activeShoppingList = response.data
      await this.fetchShoppingLists()
      return response.data
    },

    async updateShoppingListItem(shoppingListId, itemId, payload) {
      const response = await apiClient.put(`/shopping-lists/${shoppingListId}/items/${itemId}`, payload)
      this.activeShoppingList = response.data
      await this.fetchShoppingLists()
      return response.data
    },

    async deleteShoppingListItem(shoppingListId, itemId) {
      await apiClient.delete(`/shopping-lists/${shoppingListId}/items/${itemId}`)
      if (this.activeShoppingList?.id === shoppingListId) {
        await this.fetchShoppingList(shoppingListId)
      }
      await this.fetchShoppingLists()
    },

    async generateShoppingListFromMealPlan(mealPlanId, payload = {}) {
      const response = await apiClient.post(`/shopping-lists/from-meal-plan/${mealPlanId}`, payload)
      await this.fetchShoppingLists()
      this.activeShoppingList = response.data
      return response.data
    },
  },
})
