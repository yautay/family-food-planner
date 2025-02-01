import { defineStore } from 'pinia'
import axios from 'axios'

const apiClient = axios.create({
  baseURL: 'http://localhost:3000/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

export const useIngredientStore = defineStore('ingredient', {
  state: () => ({
    ingredient: {
      name: '',
      comment: '',
      unit_id: null,
      quantity_per_package: null,
      calories: null,
      carbohydrates: null,
      sugars: null,
      fat: null,
      protein: null,
      fiber: null,
      g: null,
    },
  }),
  actions: {
    async addIngredient() {
      try {
        await apiClient.post('/food-items', this.ingredient)
        this.resetIngredient()
      } catch (error) {
        console.error('Error adding ingredient:', error)
      }
    },
    resetIngredient() {
      this.ingredient = {
        name: '',
        comment: '',
        unit_id: null,
        quantity_per_package: null,
        calories: null,
        carbohydrates: null,
        sugars: null,
        fat: null,
        protein: null,
        fiber: null,
        g: null,
      }
    },
  },
})
