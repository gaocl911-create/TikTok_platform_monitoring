import type { CollectorType, Creator, DataQualityStatus } from '../types/creator'

const collectorLabels: Record<CollectorType, string> = {
  mock: '模拟数据',
  douyin_public_web: '抖音公开主页',
}

const qualityLabels: Record<DataQualityStatus, string> = {
  pending: '等待真实采集',
  mock: '模拟',
  verified: '真实完整',
  partial: '真实部分可用',
  failed: '采集失败',
}

export function collectorLabel(type: CollectorType) {
  return collectorLabels[type]
}

export function qualityLabel(status: DataQualityStatus) {
  return qualityLabels[status]
}

export function qualityDescription(creator: Creator) {
  if (creator.last_collection_error) return creator.last_collection_error
  if (creator.data_quality_status === 'pending') return '已选择真实数据，等待首次采集。'
  if (creator.data_quality_status === 'mock') return '当前指标和内容均为模拟数据。'
  if (creator.data_quality_status === 'verified') return '最近一次真实公开数据采集完整成功。'
  if (creator.data_quality_status === 'partial') return '账号指标已真实采集，部分数据暂不可用。'
  return '最近一次真实采集失败，请稍后重试或检查主页链接。'
}
