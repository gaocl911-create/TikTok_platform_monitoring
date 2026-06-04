export type Platform = 'douyin' | 'xiaohongshu'
export type Priority = 'high' | 'normal' | 'low'
export type MonitoringStatus = 'active' | 'paused'
export type CollectorType = 'mock' | 'douyin_public_web'
export type DataQualityStatus = 'pending' | 'mock' | 'verified' | 'partial' | 'failed'
export type ContentCollectionStatus = 'pending' | 'success' | 'unavailable' | 'failed'

export interface Creator {
  id: number
  platform: Platform
  platform_account_id: string
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
  monitoring_status: MonitoringStatus
  collector_type: CollectorType
  collector_version: string | null
  data_quality_status: DataQualityStatus
  last_content_status: ContentCollectionStatus
  last_collection_error: string | null
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
  nickname: string
  profile_url: string
  avatar_url?: string | null
  bio?: string | null
  group_name?: string | null
  tags: string[]
  priority: Priority
  monitor_interval_minutes: number
  collector_type: CollectorType
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
  started_at: string
  finished_at: string | null
  error_message: string | null
  result_summary: Record<string, number | string | string[]> | null
}

export interface CollectionResult {
  creator: Creator
  snapshot: CreatorSnapshot
  run: CollectionRun
}
