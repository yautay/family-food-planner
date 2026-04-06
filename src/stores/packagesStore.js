import { defineStore } from 'pinia'
import apiClient from '../services/apiClient'

export const usePackagesStore = defineStore('packages', {
  state: () => ({
    packages: [],
    packageTypes: [],
  }),
  actions: {
    async fetchPackageTypes() {
      try {
        const response = await apiClient.get('/packages/types')
        this.packageTypes = response.data
      } catch (error) {
        console.error('Error fetching package types:', error)
      }
    },
    async fetchPackages() {
      try {
        const response = await apiClient.get('/packages')
        this.packages = response.data
      } catch (error) {
        console.error('Error fetching packages:', error)
      }
    },
    async addPackage(payload) {
      try {
        await apiClient.post('/packages', payload)
        await this.fetchPackages()
      } catch (error) {
        console.error('Error adding package:', error)
        throw error
      }
    },
    async updatePackage(payload) {
      try {
        await apiClient.put(`/packages/${payload.id}`, payload)
        await this.fetchPackages()
      } catch (error) {
        console.error('Error updating package:', error)
        throw error
      }
    },
    async deletePackage(payload) {
      try {
        await apiClient.delete(`/packages/${payload.id}`)
        await this.fetchPackages()
      } catch (error) {
        console.error('Error deleting package:', error)
        throw error
      }
    },
  },
})
