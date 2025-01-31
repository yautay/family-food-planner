import { defineStore } from 'pinia'
import axios from 'axios'

const apiClient = axios.create({
  baseURL: 'http://localhost:3000/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

export const useFoodStore = defineStore('food', {
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
    units: [],
    newUnit: {
      name: '',
    },
    editUnit: {
      id: null,
      name: '',
    },
  }),
  actions: {
    async fetchUnits() {
      try {
        const response = await apiClient.get('/units')
        console.log('Fetched units:', response.data) // Log fetched units
        this.units = response.data
        console.log('Units in state:', this.units) // Log units in state
      } catch (error) {
        console.error('Error fetching units:', error)
      }
    },
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
    async addUnit() {
      try {
        await apiClient.post('/units', this.newUnit)
        this.newUnit.name = ''
        await this.fetchUnits()
      } catch (error) {
        console.error('Error adding unit:', error)
      }
    },
    async updateUnit() {
      try {
        await apiClient.put(`/units/${this.editUnit.id}`, this.editUnit)
        this.editUnit.id = null
        this.editUnit.name = ''
        await this.fetchUnits()
      } catch (error) {
        console.error('Error updating unit:', error)
      }
    },
    async deleteUnit(id) {
      try {
        await apiClient.delete(`/units/${id}`)
        await this.fetchUnits()
      } catch (error) {
        console.error('Error deleting unit:', error)
      }
    },
    setEditUnit(unit) {
      this.editUnit.id = unit.id
      this.editUnit.name = unit.name
    },
  },
})
