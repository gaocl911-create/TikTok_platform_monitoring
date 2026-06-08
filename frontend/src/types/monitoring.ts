import type { Platform } from './creator'

export interface ContentCreator {
  id: number
  platform: Platform
  nickname: string
}

export interface ContentPost {
  id: number
  creator_id: number
  platform_content_id: string
  title: string
  summary: string | null
  content_type: string
  content_url: string
  cover_url: string | null
  published_at: string | null
  first_discovered_at: string
  latest_like_count: number
  latest_comment_count: number
  latest_collect_count: number
  latest_share_count: number
  status: string
  data_source: 'mock' | 'douyin_public_web' | 'tikomni_douyin'
  metrics_status: 'success' | 'partial' | 'unavailable'
  creator: ContentCreator
}

export interface ContentPostListResponse {
  items: ContentPost[]
  total: number
  page: number
  page_size: number
}

export interface ContentSnapshot {
  id: number
  content_id: number
  like_count: number
  comment_count: number
  collect_count: number
  share_count: number
  captured_at: string
}

export type AlertType = 'new_content' | 'content_like_growth' | 'collection_failure'
export type AlertStatus = 'unread' | 'read'

export interface AlertRecord {
  id: number
  creator_id: number
  content_id: number | null
  rule_id: number | null
  alert_type: AlertType
  severity: 'info' | 'warning' | 'critical'
  title: string
  message: string
  status: AlertStatus
  notification_status: 'pending' | 'sent' | 'failed' | 'skipped'
  notification_error: string | null
  triggered_at: string
  read_at: string | null
}

export interface AlertListResponse {
  items: AlertRecord[]
  total: number
  unread_count: number
  page: number
  page_size: number
}

export interface AlertRule {
  id: number
  name: string
  alert_type: AlertType
  conditions_json: Record<string, number | string | boolean>
  notification_channels_json: string[]
  is_enabled: boolean
  created_at: string
  updated_at: string
}
