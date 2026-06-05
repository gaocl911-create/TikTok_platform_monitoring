<script setup lang="ts">
import { Link } from '@element-plus/icons-vue'
import { computed } from 'vue'

import type { ContentPost, ContentSnapshot } from '../types/monitoring'
import { formatApiDateTime } from '../utils/datetime'

const visible = defineModel<boolean>({ required: true })
const props = defineProps<{
  post: ContentPost | null
  snapshots: ContentSnapshot[]
  loading: boolean
}>()

const likeDelta = computed(() => {
  if (props.snapshots.length < 2) return 0
  return props.snapshots.at(-1)!.like_count - props.snapshots.at(-2)!.like_count
})

function formatNumber(value: number) {
  if (props.post?.metrics_status !== 'success') return '--'
  return value.toLocaleString('zh-CN')
}

function formatDelta() {
  if (props.post?.metrics_status !== 'success') return '--'
  return `+${likeDelta.value.toLocaleString('zh-CN')}`
}

function formatTime(value: string) {
  return formatApiDateTime(value)
}
</script>

<template>
  <el-drawer v-model="visible" size="min(560px, 94vw)" title="内容监测详情">
    <div v-loading="loading" class="drawer-stack">
      <template v-if="post">
        <section class="drawer-post-summary">
          <div class="content-kind" :class="post.creator.platform">
            {{ post.content_type === 'video' ? '视频' : '图文' }}
          </div>
          <div>
            <span class="platform-label">
              {{ post.creator.platform === 'douyin' ? '抖音' : '小红书' }} ·
              {{ post.creator.nickname }} ·
              {{ post.data_source === 'mock' ? '模拟内容' : '真实公开内容' }}
            </span>
            <h2>{{ post.title }}</h2>
            <p>{{ post.summary }}</p>
          </div>
        </section>

        <section class="compact-metrics">
          <div><span>点赞</span><strong>{{ formatNumber(post.latest_like_count) }}</strong></div>
          <div><span>评论</span><strong>{{ formatNumber(post.latest_comment_count) }}</strong></div>
          <div><span>收藏</span><strong>{{ formatNumber(post.latest_collect_count) }}</strong></div>
          <div><span>最近增赞</span><strong>{{ formatDelta() }}</strong></div>
        </section>

        <el-button :icon="Link" tag="a" :href="post.content_url" target="_blank">
          打开平台内容
        </el-button>

        <section class="drawer-history">
          <div class="section-heading">
            <div>
              <h2>指标快照</h2>
              <p>每次账号采集时同步记录</p>
            </div>
          </div>
          <el-table :data="[...snapshots].reverse()" empty-text="暂无内容快照">
            <el-table-column label="采集时间" min-width="170">
              <template #default="{ row }">{{ formatTime(row.captured_at) }}</template>
            </el-table-column>
            <el-table-column label="点赞" min-width="100" align="right">
              <template #default="{ row }">{{ formatNumber(row.like_count) }}</template>
            </el-table-column>
            <el-table-column label="评论" min-width="90" align="right">
              <template #default="{ row }">{{ formatNumber(row.comment_count) }}</template>
            </el-table-column>
            <el-table-column label="收藏" min-width="90" align="right">
              <template #default="{ row }">{{ formatNumber(row.collect_count) }}</template>
            </el-table-column>
          </el-table>
        </section>
      </template>
    </div>
  </el-drawer>
</template>
