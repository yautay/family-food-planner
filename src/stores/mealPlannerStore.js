import { defineStore } from 'pinia'
import { mealPlannerApi } from '../services/mealPlannerApi'

export const useMealPlannerStore = defineStore('mealPlanner', {
  state: () => ({
    mealPlans: [],
    activeMealPlan: null,
    dayPlans: [],
    activeDayPlan: null,
    shoppingLists: [],
    activeShoppingList: null,
  }),
  actions: {
    async fetchMealPlans() {
      const response = await mealPlannerApi.fetchMealPlans()
      this.mealPlans = response.data
      return response.data
    },

    async fetchMealPlan(mealPlanId) {
      const response = await mealPlannerApi.fetchMealPlan(mealPlanId)
      this.activeMealPlan = response.data
      return response.data
    },

    async createMealPlan(payload) {
      const response = await mealPlannerApi.createMealPlan(payload)
      await this.fetchMealPlans()
      this.activeMealPlan = response.data
      return response.data
    },

    async updateMealPlan(mealPlanId, payload) {
      const response = await mealPlannerApi.updateMealPlan(mealPlanId, payload)
      await this.fetchMealPlans()
      this.activeMealPlan = response.data
      return response.data
    },

    async deleteMealPlan(mealPlanId) {
      await mealPlannerApi.deleteMealPlan(mealPlanId)
      await this.fetchMealPlans()

      if (this.activeMealPlan?.id === mealPlanId) {
        this.activeMealPlan = null
      }
    },

    async replaceMealPlanMealSlots(mealPlanId, slots) {
      const response = await mealPlannerApi.replaceMealPlanMealSlots(mealPlanId, slots)
      this.activeMealPlan = response.data
      await this.fetchMealPlans()
      return response.data
    },

    async updateMealPlanDaySlot(mealPlanId, plannedDate, payload) {
      const response = await mealPlannerApi.updateMealPlanDaySlot(mealPlanId, plannedDate, payload)
      this.activeMealPlan = response.data
      await this.fetchMealPlans()
      return response.data
    },

    async replaceMealPlanDaySlotMeals(mealPlanId, plannedDate, meals) {
      const response = await mealPlannerApi.replaceMealPlanDaySlotMeals(
        mealPlanId,
        plannedDate,
        meals,
      )
      this.activeMealPlan = response.data
      await this.fetchMealPlans()
      return response.data
    },

    async replaceMealPlanEntries(mealPlanId, entries) {
      const response = await mealPlannerApi.replaceMealPlanEntries(mealPlanId, entries)
      this.activeMealPlan = response.data
      await this.fetchMealPlans()
      return response.data
    },

    async fetchDayPlans() {
      const response = await mealPlannerApi.fetchDayPlans()
      this.dayPlans = response.data
      return response.data
    },

    async fetchDayPlan(dayPlanId) {
      const response = await mealPlannerApi.fetchDayPlan(dayPlanId)
      this.activeDayPlan = response.data
      return response.data
    },

    async createDayPlan(payload) {
      const response = await mealPlannerApi.createDayPlan(payload)
      await this.fetchDayPlans()
      this.activeDayPlan = response.data
      return response.data
    },

    async updateDayPlan(dayPlanId, payload) {
      const response = await mealPlannerApi.updateDayPlan(dayPlanId, payload)
      await this.fetchDayPlans()
      this.activeDayPlan = response.data
      return response.data
    },

    async deleteDayPlan(dayPlanId) {
      await mealPlannerApi.deleteDayPlan(dayPlanId)
      await this.fetchDayPlans()

      if (this.activeDayPlan?.id === dayPlanId) {
        this.activeDayPlan = null
      }
    },

    async replaceDayPlanMeals(dayPlanId, meals) {
      const response = await mealPlannerApi.replaceDayPlanMeals(dayPlanId, meals)
      this.activeDayPlan = response.data
      await this.fetchDayPlans()
      return response.data
    },

    async fetchShoppingLists() {
      const response = await mealPlannerApi.fetchShoppingLists()
      this.shoppingLists = response.data
      return response.data
    },

    async fetchShoppingList(shoppingListId) {
      const response = await mealPlannerApi.fetchShoppingList(shoppingListId)
      this.activeShoppingList = response.data
      return response.data
    },

    async createShoppingList(payload) {
      const response = await mealPlannerApi.createShoppingList(payload)
      await this.fetchShoppingLists()
      this.activeShoppingList = response.data
      return response.data
    },

    async updateShoppingList(shoppingListId, payload) {
      const response = await mealPlannerApi.updateShoppingList(shoppingListId, payload)
      await this.fetchShoppingLists()
      this.activeShoppingList = response.data
      return response.data
    },

    async deleteShoppingList(shoppingListId) {
      await mealPlannerApi.deleteShoppingList(shoppingListId)
      await this.fetchShoppingLists()

      if (this.activeShoppingList?.id === shoppingListId) {
        this.activeShoppingList = null
      }
    },

    async addShoppingListItem(shoppingListId, payload) {
      const response = await mealPlannerApi.addShoppingListItem(shoppingListId, payload)
      this.activeShoppingList = response.data
      await this.fetchShoppingLists()
      return response.data
    },

    async updateShoppingListItem(shoppingListId, itemId, payload) {
      const response = await mealPlannerApi.updateShoppingListItem(shoppingListId, itemId, payload)
      this.activeShoppingList = response.data
      await this.fetchShoppingLists()
      return response.data
    },

    async deleteShoppingListItem(shoppingListId, itemId) {
      await mealPlannerApi.deleteShoppingListItem(shoppingListId, itemId)
      if (this.activeShoppingList?.id === shoppingListId) {
        await this.fetchShoppingList(shoppingListId)
      }
      await this.fetchShoppingLists()
    },

    async generateShoppingListFromMealPlan(mealPlanId, payload = {}) {
      const response = await mealPlannerApi.generateShoppingListFromMealPlan(mealPlanId, payload)
      await this.fetchShoppingLists()
      this.activeShoppingList = response.data
      return response.data
    },
  },
})
