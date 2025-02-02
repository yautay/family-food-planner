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
    ingredients: [],
    ingredient: {
      name: '',
      comment: '',
      unit_id: null,
      quantity_per_package: null,
      calories_per_100g: null,
      carbohydrates_per_100g: null,
      sugars_per_100g: null,
      fat_per_100g: null,
      protein_per_100g: null,
      fiber_per_100g: null,
      tags: [],
    },
  }),
  actions: {
    async fetchIngredients() {
      try {
        const response = await apiClient.get('/ingredients')
        this.ingredients = response.data
      } catch (error) {
        console.error('Error fetching ingredients:', error)
      }
    },
    async addIngredient(ingredient) {
      try {
        await apiClient.post('/ingredients', ingredient)
        await this.fetchIngredients()
      } catch (error) {
        console.error('Error adding ingredient:', error)
      }
    },
    async updateIngredient(ingredient) {
      try {
        await apiClient.put(`/ingredients/${ingredient.id}`, ingredient)
        await this.fetchIngredients()
      } catch (error) {
        console.error('Error updating ingredient:', error)
      }
    },
    async deleteIngredient(ingredient) {
      try {
        await apiClient.delete(`/ingredients/${ingredient.id}`)
        await this.fetchIngredients()
      } catch (error) {
        console.error('Error deleting ingredient:', error)
      }
    },
  },
})
