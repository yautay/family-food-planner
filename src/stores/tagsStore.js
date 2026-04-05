import { defineStore } from 'pinia'
import apiClient from '../services/apiClient'

export const useTagStore = defineStore('tag', {
  state: () => ({
    tags: [],
  }),
  actions: {
    async fetchTags() {
      try {
        const response = await apiClient.get('/tags')
        this.tags = response.data
      } catch (error) {
        console.error('Error fetching tags:', error)
      }
    },
    async addTag(tag) {
      try {
        await apiClient.post('/tags', tag)
        await this.fetchTags()
      } catch (error) {
        console.error('Error adding tag:', error)
      }
    },
    async updateTag(tag) {
      try {
        await apiClient.put(`/tags/${tag.id}`, tag)
        await this.fetchTags()
      } catch (error) {
        console.error('Error updating tag:', error)
      }
    },
    async deleteTag(tag) {
      try {
        await apiClient.delete(`/tags/${tag.id}`)
        await this.fetchTags()
      } catch (error) {
        console.error('Error deleting tag:', error)
      }
    },
  },
})
