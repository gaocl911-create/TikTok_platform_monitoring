import apiClient from './client'
import type {
  CollectionResult,
  CollectionRetryQueued,
  Creator,
  CreatorListResponse,
  CreatorPayload,
  CreatorProfileResolvePayload,
  CreatorProfileResolveResult,
  CreatorSnapshot,
  CollectorType,
  MonitoringStatus,
  Platform,
  Priority,
} from '../types/creator'

export interface CreatorQuery {
  page?: number
  page_size?: number
  platform?: Platform | ''
  monitoring_status?: MonitoringStatus | ''
  search?: string
}

export interface CreatorUpdatePayload {
  nickname?: string
  platform_display_id?: string | null
  profile_url?: string
  avatar_url?: string | null
  bio?: string | null
  group_name?: string | null
  tags?: string[]
  priority?: Priority
  monitor_interval_minutes?: number
  monitoring_status?: MonitoringStatus
  collector_type?: CollectorType
}

export const creatorApi = {
  async list(params: CreatorQuery = {}) {
    const { data } = await apiClient.get<CreatorListResponse>('/creators', { params })
    return data
  },

  async get(id: number) {
    const { data } = await apiClient.get<Creator>(`/creators/${id}`)
    return data
  },

  async create(payload: CreatorPayload) {
    const { data } = await apiClient.post<Creator>('/creators', payload)
    return data
  },

  async resolveProfile(payload: CreatorProfileResolvePayload) {
    const { data } = await apiClient.post<CreatorProfileResolveResult>(
      '/creators/resolve-profile',
      payload,
      { timeout: 90_000 },
    )
    return data
  },

  async update(id: number, payload: CreatorUpdatePayload) {
    const { data } = await apiClient.patch<Creator>(`/creators/${id}`, payload)
    return data
  },

  async remove(id: number) {
    await apiClient.delete(`/creators/${id}`)
  },

  async collect(id: number) {
    const { data } = await apiClient.post<CollectionResult | CollectionRetryQueued>(
      `/creators/${id}/collect`,
      undefined,
      { timeout: 90_000 },
    )
    return data
  },

  async snapshots(id: number) {
    const { data } = await apiClient.get<CreatorSnapshot[]>(`/creators/${id}/snapshots`)
    return data
  },
}
