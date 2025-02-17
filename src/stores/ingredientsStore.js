import { defineStore } from 'pinia'
import axios from 'axios'

const apiClient = axios.create({
  baseURL: 'http://localhost:3000/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

export const useIngredientStore = defineStore('ingredients', {
  state: () => ({
    ingredients: [],
  }),
  actions: {
    async fetchIngredients() {
      try {
        const response = await apiClient.get('/ingredients')
        this.ingredients = response.data.map(ingredient => {
          if (typeof ingredient.tag_id === 'string') {
            ingredient.tag_id = ingredient.tag_id.split(',').map(Number)
          }
          return ingredient
        })
      } catch (error) {
        console.error('Error fetching ingredients:', error)
      }
    },
    async addIngredient(ingredient) {
      try {
        await apiClient.post('/ingredients', ingredient.value)
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
