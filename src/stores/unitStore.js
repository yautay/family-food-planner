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
    units: []
  }),
  actions: {
    async fetchUnits() {
      try {
        const response = await apiClient.get('/units')
        this.units = response.data
      } catch (error) {
        console.error('Error fetching units:', error)
      }
    },
    async addUnit(unit) {
      try {
        await apiClient.post('/units', unit)
        await this.fetchUnits()
      } catch (error) {
        console.error('Error adding unit:', error)
      }
    },
    async updateUnit(unit) {
      try {
        await apiClient.put(`/units/${unit.id}`, unit )
        await this.fetchUnits()
      } catch (error) {
        console.error('Error updating unit:', error)
      }
    },
    async deleteUnit(unit) {
      try {
        await apiClient.delete(`/units/${unit.id}`)
        await this.fetchUnits()
      } catch (error) {
        console.error('Error deleting unit:', error)
      }
    },
  },
})
