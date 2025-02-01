import { defineStore } from 'pinia'
import axios from 'axios'

const apiClient = axios.create({
  baseURL: 'http://localhost:3000/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

export const useUnitStore = defineStore('unit', {
  state: () => ({
    units: {
      name: String,
    },
    addUnit: {
      name: String,
    },
    editUnit: {
      id: null,
      name: String,
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
    async addUnit(name) {
      try {
        await apiClient.post('/units', this.newUnit)
        this.newUnit.name = name
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
      console.error('Set Edit unit:', unit.id)
      this.editUnit.id = unit.id
      this.editUnit.name = unit.name
    },
  },
})
