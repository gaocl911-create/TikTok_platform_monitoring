import type { CollectorType, Creator, DataQualityStatus } from '../types/creator'

const collectorLabels: Record<CollectorType, string> = {
  mock: '小红书待接入',
  douyin_public_web: '抖音公开主页',
  tikomni_douyin: '抖音真实数据',
}

const qualityLabels: Record<DataQualityStatus, string> = {
  pending: '等待采集',
  mock: '模拟数据',
  verified: '真实完整',
  partial: '部分可用',
  failed: '采集失败',
}

export function collectorLabel(type: CollectorType) {
  return collectorLabels[type]
}

export function qualityLabel(status: DataQualityStatus) {
  return qualityLabels[status]
}

export function creatorQualityLabel(creator: Creator) {
  if (creator.last_collection_error) return '采集异常'
  if (creator.last_content_status === 'budget_limited') return '预算限制'
  if (creator.last_content_status === 'baseline_created') return '等待新作品'
  if (creator.last_content_status === 'metrics_refreshed') return '作品监控中'
  if (creator.last_content_status === 'success') return '作品监控中'
  if (creator.last_content_status === 'partial') return '指标部分缺失'
  if (creator.last_content_status === 'no_new_content') return '未发现新作品'
  if (creator.last_content_status === 'pending' && creator.data_quality_status === 'partial') {
    return '主页已采集'
  }
  return qualityLabel(creator.data_quality_status)
}

export function qualityDescription(creator: Creator) {
  if (creator.last_collection_error) return creator.last_collection_error
  if (creator.last_content_status === 'baseline_created') {
    return '已建立作品基线，历史作品不会进入内容动态；后续发现新作品会自动加入监测。'
  }
  if (creator.last_content_status === 'no_new_content') {
    return '本次已检查作品列表，未发现新作品。'
  }
  if (creator.last_content_status === 'metrics_refreshed') {
    return '本次未发现新作品，已刷新已跟踪作品的点赞、评论、收藏、分享指标。'
  }
  if (creator.last_content_status === 'budget_limited') {
    return 'TikOmni 每日预算已达上限，本次已停止继续调用真实 API。'
  }
  if (creator.last_content_status === 'pending' && creator.data_quality_status === 'partial') {
    return '作者主页信息已真实采集，作品监控还未完成第一次内容采集。'
  }
  if (creator.data_quality_status === 'pending') return '已选择真实数据，等待首次采集。'
  if (creator.data_quality_status === 'mock') return '当前指标和内容均为模拟数据。'
  if (creator.data_quality_status === 'verified') return '作品监控链路已可用，系统会按采集间隔刷新。'
  if (creator.data_quality_status === 'partial') {
    return '账号或作品部分字段已真实采集，但仍有指标字段暂不可用。'
  }
  return '最近一次真实采集失败，请稍后重试或检查主页链接。'
}
