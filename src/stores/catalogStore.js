import { defineStore } from 'pinia'
import apiClient from '../services/apiClient'

export const useCatalogStore = defineStore('catalog', {
  state: () => ({
    products: [],
    recipes: [],
    activeRecipe: null,
    activeRecipeIngredients: [],
  }),
  actions: {
    async fetchProducts(search = '') {
      try {
        const response = await apiClient.get('/products', {
          params: search ? { search } : undefined,
        })
        this.products = response.data
      } catch (error) {
        console.error('Error fetching products:', error)
      }
    },

    async fetchRecipes(search = '') {
      try {
        const response = await apiClient.get('/recipes', {
          params: search ? { search } : undefined,
        })
        this.recipes = response.data
      } catch (error) {
        console.error('Error fetching recipes:', error)
      }
    },

    async fetchRecipeDetails(recipeId) {
      try {
        const [recipeResponse, ingredientsResponse] = await Promise.all([
          apiClient.get(`/recipes/${recipeId}`),
          apiClient.get(`/recipes/${recipeId}/ingredients`),
        ])

        this.activeRecipe = recipeResponse.data
        this.activeRecipeIngredients = ingredientsResponse.data
      } catch (error) {
        console.error('Error fetching recipe details:', error)
      }
    },

    async createRecipe(payload) {
      const response = await apiClient.post('/recipes', payload)
      await this.fetchRecipes()
      return response.data
    },

    async updateRecipe(recipeId, payload) {
      const response = await apiClient.put(`/recipes/${recipeId}`, payload)
      await this.fetchRecipes()
      return response.data
    },

    async deleteRecipe(recipeId) {
      await apiClient.delete(`/recipes/${recipeId}`)
      await this.fetchRecipes()
      if (this.activeRecipe?.id === recipeId) {
        this.activeRecipe = null
        this.activeRecipeIngredients = []
      }
    },
  },
})
