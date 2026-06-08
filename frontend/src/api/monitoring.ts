import apiClient from './client'
import type { Platform } from '../types/creator'
import type { CollectionRunListResponse, CollectorType } from '../types/creator'
import type {
  AlertListResponse,
  AlertRecord,
  AlertRule,
  AlertStatus,
  AlertType,
  ContentPost,
  ContentLinkCreateRequest,
  ContentLinkCreateResponse,
  ContentLinkResolveRequest,
  ContentLinkResolveResponse,
  ContentPostListResponse,
  ContentSnapshot,
} from '../types/monitoring'

export interface PostQuery {
  page?: number
  page_size?: number
  creator_id?: number
  platform?: Platform | ''
  search?: string
}

export interface AlertQuery {
  page?: number
  page_size?: number
  status?: AlertStatus | ''
  alert_type?: AlertType | ''
}

export interface CollectionRunQuery {
  page?: number
  page_size?: number
  creator_id?: number
  status?: '' | 'success' | 'partial' | 'failed' | 'skipped'
  collector_type?: '' | CollectorType
}

export const monitoringApi = {
  async listPosts(params: PostQuery = {}) {
    const { data } = await apiClient.get<ContentPostListResponse>('/posts', { params })
    return data
  },

  async getPost(id: number) {
    const { data } = await apiClient.get<ContentPost>(`/posts/${id}`)
    return data
  },

  async getPostSnapshots(id: number) {
    const { data } = await apiClient.get<ContentSnapshot[]>(`/posts/${id}/snapshots`)
    return data
  },

  async resolvePostLink(payload: ContentLinkResolveRequest) {
    const { data } = await apiClient.post<ContentLinkResolveResponse>('/posts/resolve-link', payload)
    return data
  },

  async addPostFromLink(payload: ContentLinkCreateRequest) {
    const { data } = await apiClient.post<ContentLinkCreateResponse>('/posts/from-link', payload)
    return data
  },

  async listAlerts(params: AlertQuery = {}) {
    const { data } = await apiClient.get<AlertListResponse>('/alerts', { params })
    return data
  },

  async markAlertRead(id: number) {
    const { data } = await apiClient.patch<AlertRecord>(`/alerts/${id}/read`)
    return data
  },

  async markAllAlertsRead() {
    const { data } = await apiClient.patch<{ updated: number }>('/alerts/read-all')
    return data
  },

  async listAlertRules() {
    const { data } = await apiClient.get<AlertRule[]>('/alert-rules')
    return data
  },

  async updateAlertRule(id: number, payload: Partial<Pick<AlertRule, 'conditions_json' | 'is_enabled'>>) {
    const { data } = await apiClient.patch<AlertRule>(`/alert-rules/${id}`, payload)
    return data
  },

  async listCollectionRuns(params: CollectionRunQuery = {}) {
    const { data } = await apiClient.get<CollectionRunListResponse>('/collection-runs', { params })
    return data
  },
}
