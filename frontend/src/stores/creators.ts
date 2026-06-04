import { defineStore } from 'pinia'
import { ref } from 'vue'

import { creatorApi, type CreatorQuery, type CreatorUpdatePayload } from '../api/creators'
import type { Creator, CreatorPayload, CreatorSnapshot } from '../types/creator'

export const useCreatorStore = defineStore('creators', () => {
  const items = ref<Creator[]>([])
  const total = ref(0)
  const loading = ref(false)

  async function fetchCreators(query: CreatorQuery = {}) {
    loading.value = true
    try {
      const response = await creatorApi.list(query)
      items.value = response.items
      total.value = response.total
      return response
    } finally {
      loading.value = false
    }
  }

  async function createCreator(payload: CreatorPayload) {
    return creatorApi.create(payload)
  }

  async function updateCreator(id: number, payload: CreatorUpdatePayload) {
    return creatorApi.update(id, payload)
  }

  async function deleteCreator(id: number) {
    await creatorApi.remove(id)
  }

  async function collectCreator(id: number) {
    return creatorApi.collect(id)
  }

  async function getCreator(id: number): Promise<Creator> {
    return creatorApi.get(id)
  }

  async function getSnapshots(id: number): Promise<CreatorSnapshot[]> {
    return creatorApi.snapshots(id)
  }

  return {
    items,
    total,
    loading,
    fetchCreators,
    createCreator,
    updateCreator,
    deleteCreator,
    collectCreator,
    getCreator,
    getSnapshots,
  }
})
