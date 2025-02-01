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
  },
})
