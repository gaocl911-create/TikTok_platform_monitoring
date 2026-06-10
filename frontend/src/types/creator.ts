export type Platform = 'douyin' | 'xiaohongshu'
export type Priority = 'high' | 'normal' | 'low'
export type MonitoringStatus = 'active' | 'paused'
export type CollectorType = 'mock' | 'douyin_public_web' | 'tikhub_douyin'
export type MonitorScope = 'creator_collection' | 'single_content'
export type DataQualityStatus = 'pending' | 'mock' | 'verified' | 'partial' | 'failed'
export type ContentCollectionStatus =
  | 'pending'
  | 'success'
  | 'partial'
  | 'unavailable'
  | 'baseline_created'
  | 'no_new_content'
  | 'metrics_refreshed'
  | 'budget_limited'
  | 'failed'

export interface Creator {
  id: number
  platform: Platform
  platform_account_id: string
  platform_display_id: string | null
  nickname: string
  profile_url: string
  avatar_url: string | null
  bio: string | null
  verified_info: string | null
  location: string | null
  group_name: string | null
  tags: string[]
  priority: Priority
  monitor_interval_minutes: number
  monitor_scope: MonitorScope
  monitoring_status: MonitoringStatus
  collector_type: CollectorType
  collector_version: string | null
  data_quality_status: DataQualityStatus
  last_content_status: ContentCollectionStatus
  last_collection_error: string | null
  content_baseline_established_at: string | null
  follower_count: number
  following_count: number
  total_like_count: number
  content_count: number
  last_collected_at: string | null
  next_collect_at: string | null
  consecutive_failures: number
  created_at: string
  updated_at: string
}

export interface CreatorPayload {
  platform: Platform
  platform_account_id: string
  platform_display_id?: string | null
  nickname: string
  profile_url: string
  avatar_url?: string | null
  bio?: string | null
  verified_info?: string | null
  location?: string | null
  group_name?: string | null
  tags: string[]
  priority: Priority
  monitor_interval_minutes: number
  monitor_scope?: MonitorScope
  collector_type: CollectorType
  follower_count?: number
  following_count?: number
  total_like_count?: number
  content_count?: number
  profile_resolved?: boolean
}

export interface CreatorProfileResolvePayload {
  platform: Platform
  input_value: string
}

export interface CreatorProfileResolveResult {
  platform: Platform
  platform_account_id: string
  platform_display_id: string | null
  nickname: string
  profile_url: string
  avatar_url: string | null
  bio: string | null
  verified_info: string | null
  location: string | null
  follower_count: number
  following_count: number
  total_like_count: number
  content_count: number
  collector_type: CollectorType
  sec_user_id: string | null
  warnings: string[]
}

export interface CreatorListResponse {
  items: Creator[]
  total: number
  page: number
  page_size: number
}

export interface CreatorSnapshot {
  id: number
  creator_id: number
  follower_count: number
  following_count: number
  total_like_count: number
  content_count: number
  collector_type: CollectorType
  data_quality_status: DataQualityStatus
  captured_at: string
}

export interface CollectionRun {
  id: number
  creator_id: number
  task_type: string
  status: string
  trigger_source: 'initial' | 'manual' | 'scheduled'
  attempt: number
  collector_type: CollectorType | null
  error_type: string | null
  duration_ms: number | null
  started_at: string
  finished_at: string | null
  error_message: string | null
  result_summary: Record<string, unknown> | null
  creator: {
    id: number
    nickname: string
    platform: Platform
  }
}

export interface CollectionResult {
  creator: Creator
  snapshot: CreatorSnapshot
  run: CollectionRun
}

export interface CollectionRetryQueued {
  creator_id: number
  task_id: string
  status: 'queued'
  retry_after_seconds: number
  message: string
}

export interface CollectionRunListResponse {
  items: CollectionRun[]
  total: number
  page: number
  page_size: number
}
