<script setup lang="ts">
import { Link, Refresh, Search, TrendCharts } from '@element-plus/icons-vue'
import { onMounted, reactive, ref } from 'vue'

import { monitoringApi } from '../api/monitoring'
import ContentDetailDrawer from '../components/ContentDetailDrawer.vue'
import type { Platform } from '../types/creator'
import type { ContentPost, ContentSnapshot } from '../types/monitoring'
import { formatApiDateTime } from '../utils/datetime'

const loading = ref(false)
const items = ref<ContentPost[]>([])
const total = ref(0)
const detailVisible = ref(false)
const detailLoading = ref(false)
const selectedPost = ref<ContentPost | null>(null)
const snapshots = ref<ContentSnapshot[]>([])
const query = reactive<{ search: string; platform: Platform | ''; page: number; page_size: number }>({
  search: '',
  platform: '',
  page: 1,
  page_size: 20,
})

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

function formatTime(value: string | null) {
  if (!value) return '公开页面未提供'
  return formatApiDateTime(value, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatMetric(post: ContentPost, value: number) {
  return post.metrics_status === 'success' ? formatNumber(value) : '--'
}

async function load() {
  loading.value = true
  try {
    const response = await monitoringApi.listPosts(query)
    items.value = response.items
    total.value = response.total
  } finally {
    loading.value = false
  }
}

async function openDetail(post: ContentPost) {
  selectedPost.value = post
  snapshots.value = []
  detailVisible.value = true
  detailLoading.value = true
  try {
    snapshots.value = await monitoringApi.getPostSnapshots(post.id)
  } finally {
    detailLoading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page-stack">
    <section class="action-row">
      <div>
        <h2>内容动态流</h2>
        <p>识别监控账号发布的新内容，并持续追踪公开互动指标</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新动态</el-button>
    </section>

    <section class="filter-bar feed-filter">
      <el-input
        v-model="query.search"
        :prefix-icon="Search"
        clearable
        placeholder="搜索内容标题或创作者"
        @keyup.enter="load"
        @clear="load"
      />
      <el-select v-model="query.platform" placeholder="全部平台" clearable @change="load">
        <el-option label="抖音" value="douyin" />
        <el-option label="小红书" value="xiaohongshu" />
      </el-select>
      <el-button :icon="Search" @click="load">查询</el-button>
    </section>

    <section v-loading="loading" class="feed-list" aria-live="polite">
      <article v-for="post in items" :key="post.id" class="feed-item">
        <div class="content-kind" :class="post.creator.platform">
          {{ post.content_type === 'video' ? '视频' : '图文' }}
        </div>
        <div class="feed-content">
          <div class="feed-meta">
            <span class="platform-dot" :class="post.creator.platform"></span>
            <strong>{{ post.creator.nickname }}</strong>
            <span>{{ post.creator.platform === 'douyin' ? '抖音' : '小红书' }}</span>
            <span>发布于 {{ formatTime(post.published_at) }}</span>
            <span class="quality-badge" :class="post.data_source === 'mock' ? 'mock' : 'verified'">
              {{ post.data_source === 'mock' ? '模拟内容' : '真实公开内容' }}
            </span>
          </div>
          <h3>{{ post.title }}</h3>
          <p>{{ post.summary || '暂无公开摘要' }}</p>
          <dl class="engagement-row">
            <div><dt>点赞</dt><dd>{{ formatMetric(post, post.latest_like_count) }}</dd></div>
            <div><dt>评论</dt><dd>{{ formatMetric(post, post.latest_comment_count) }}</dd></div>
            <div><dt>收藏</dt><dd>{{ formatMetric(post, post.latest_collect_count) }}</dd></div>
            <div><dt>分享</dt><dd>{{ formatMetric(post, post.latest_share_count) }}</dd></div>
          </dl>
        </div>
        <div class="feed-actions">
          <el-button :icon="TrendCharts" @click="openDetail(post)">查看快照</el-button>
          <el-button :icon="Link" tag="a" :href="post.content_url" target="_blank">打开内容</el-button>
        </div>
      </article>
      <el-empty v-if="!loading && items.length === 0" description="还没有发现内容动态" />
    </section>

    <div class="pagination-row">
      <span>共发现 {{ total }} 条内容</span>
      <el-pagination
        v-model:current-page="query.page"
        layout="prev, pager, next"
        :page-size="query.page_size"
        :total="total"
        @current-change="load"
      />
    </div>

    <ContentDetailDrawer
      v-model="detailVisible"
      :post="selectedPost"
      :snapshots="snapshots"
      :loading="detailLoading"
    />
  </div>
</template>
