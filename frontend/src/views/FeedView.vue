<script setup lang="ts">
import { Link, Plus, Refresh, Search, TrendCharts } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import { monitoringApi } from '../api/monitoring'
import ContentDetailDrawer from '../components/ContentDetailDrawer.vue'
import type { Platform } from '../types/creator'
import type { ContentLinkResolveResponse, ContentPost, ContentSnapshot } from '../types/monitoring'
import { formatApiDateTime } from '../utils/datetime'

const loading = ref(false)
const items = ref<ContentPost[]>([])
const total = ref(0)
const detailVisible = ref(false)
const detailLoading = ref(false)
const selectedPost = ref<ContentPost | null>(null)
const snapshots = ref<ContentSnapshot[]>([])
const linkDialogVisible = ref(false)
const linkResolving = ref(false)
const linkSubmitting = ref(false)
const linkPreview = ref<ContentLinkResolveResponse | null>(null)
const query = reactive<{ search: string; platform: Platform | ''; page: number; page_size: number }>({
  search: '',
  platform: '',
  page: 1,
  page_size: 20,
})
const linkForm = reactive<{
  platform: Platform
  input_value: string
  group_name: string
  tags: string[]
  monitor_interval_minutes: number
}>({
  platform: 'douyin',
  input_value: '',
  group_name: '',
  tags: [],
  monitor_interval_minutes: 30,
})
const linkPlatformOptions = [
  { label: '抖音', value: 'douyin' },
  { label: '小红书', value: 'xiaohongshu' },
]

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

function displayTime(post: ContentPost) {
  return post.published_at || post.first_discovered_at
}

function timeLabel(post: ContentPost) {
  return post.published_at ? '发布于' : '发现于'
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
  return post.metrics_status === 'unavailable' ? '--' : formatNumber(value)
}

function formatPreviewMetric(value: number, status: ContentLinkResolveResponse['content']['metrics_status']) {
  return status === 'unavailable' ? '--' : formatNumber(value)
}

function sourceBadgeClass(post: ContentPost) {
  if (post.data_source === 'mock') return 'mock'
  if (post.data_source === 'tikomni_douyin') return 'tikomni'
  return 'verified'
}

function sourceBadgeLabel(post: ContentPost) {
  if (post.data_source === 'mock') return '小红书待接入'
  if (post.data_source === 'tikomni_douyin') return '抖音真实内容'
  return '真实公开内容'
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

function resetLinkForm() {
  linkForm.platform = 'douyin'
  linkForm.input_value = ''
  linkForm.group_name = ''
  linkForm.tags = []
  linkForm.monitor_interval_minutes = 30
  linkPreview.value = null
}

function openLinkDialog() {
  resetLinkForm()
  linkDialogVisible.value = true
}

function clearLinkPreview() {
  linkPreview.value = null
}

async function resolveLink() {
  if (linkForm.platform === 'xiaohongshu') {
    ElMessage.warning('小红书单作品监控已预留，当前阶段先接入抖音')
    return
  }
  if (!linkForm.input_value.trim()) {
    ElMessage.warning('请先粘贴抖音作品链接或分享文案')
    return
  }

  linkResolving.value = true
  try {
    const response = await monitoringApi.resolvePostLink({
      platform: linkForm.platform,
      input_value: linkForm.input_value.trim(),
    })
    linkPreview.value = response
    if (response.warnings.length > 0) {
      ElMessage.warning(response.warnings[0])
    } else {
      ElMessage.success('作品信息已识别')
    }
  } finally {
    linkResolving.value = false
  }
}

async function submitLink() {
  if (!linkPreview.value) {
    await resolveLink()
  }
  if (!linkPreview.value) return

  linkSubmitting.value = true
  try {
    const response = await monitoringApi.addPostFromLink({
      platform: linkForm.platform,
      input_value: linkForm.input_value.trim(),
      resolve_token: linkPreview.value.resolve_token,
      group_name: linkForm.group_name.trim() || null,
      tags: [...linkForm.tags],
      monitor_interval_minutes: linkForm.monitor_interval_minutes,
    })
    linkDialogVisible.value = false
    query.page = 1
    await load()
    if (response.warnings.length > 0) {
      ElMessage.warning(response.warnings[0])
    } else {
      ElMessage.success(response.post_created ? '作品已添加到监控' : '作品已存在，指标已更新')
    }
  } finally {
    linkSubmitting.value = false
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
      <div class="action-buttons">
        <el-button type="primary" :icon="Plus" @click="openLinkDialog">添加作品链接</el-button>
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新动态</el-button>
      </div>
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
            <span>{{ timeLabel(post) }} {{ formatTime(displayTime(post)) }}</span>
            <span class="quality-badge" :class="sourceBadgeClass(post)">
              {{ sourceBadgeLabel(post) }}
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

    <el-dialog
      v-model="linkDialogVisible"
      title="根据链接添加作品"
      width="680px"
      destroy-on-close
      @closed="resetLinkForm"
    >
      <el-form label-position="top">
        <div class="link-form-grid">
          <el-form-item label="数据来源">
            <el-segmented
              v-model="linkForm.platform"
              :options="linkPlatformOptions"
              @change="clearLinkPreview"
            />
          </el-form-item>
          <el-form-item label="监控间隔">
            <el-select v-model="linkForm.monitor_interval_minutes">
              <el-option label="每 15 分钟" :value="15" />
              <el-option label="每 30 分钟" :value="30" />
              <el-option label="每 1 小时" :value="60" />
              <el-option label="每 3 小时" :value="180" />
            </el-select>
          </el-form-item>
        </div>

        <el-form-item label="作品链接 / 分享文案">
          <el-input
            v-model="linkForm.input_value"
            type="textarea"
            :rows="3"
            placeholder="粘贴抖音作品链接、短链或分享文案"
            @input="clearLinkPreview"
          />
        </el-form-item>

        <div class="link-form-grid">
          <el-form-item label="作者备注">
            <el-input v-model="linkForm.group_name" placeholder="例如：兼职投放、员工账号" />
          </el-form-item>
          <el-form-item label="标签">
            <el-select
              v-model="linkForm.tags"
              multiple
              filterable
              allow-create
              default-first-option
              placeholder="输入标签后回车"
            />
          </el-form-item>
        </div>

        <el-alert
          v-if="linkForm.platform === 'xiaohongshu'"
          class="link-source-alert"
          type="info"
          title="小红书待接入"
          description="当前阶段先实现抖音单作品识别和真实指标监控。"
          show-icon
          :closable="false"
        />

        <section v-if="linkPreview" class="work-preview">
          <div class="work-preview-heading">
            <el-avatar :size="42" :src="linkPreview.creator.avatar_url || undefined">
              {{ linkPreview.creator.nickname.slice(0, 1) }}
            </el-avatar>
            <div>
              <strong>{{ linkPreview.creator.nickname }}</strong>
              <small>{{ linkPreview.creator.platform_display_id || linkPreview.creator.platform_account_id }}</small>
            </div>
            <el-tag :type="linkPreview.existing_creator_id ? 'success' : 'warning'" effect="plain">
              {{ linkPreview.existing_creator_id ? '已有作者' : '新作者' }}
            </el-tag>
          </div>

          <h3>{{ linkPreview.content.title }}</h3>
          <p>{{ linkPreview.content.summary || '暂无公开摘要' }}</p>

          <dl class="work-preview-metrics">
            <div>
              <dt>点赞</dt>
              <dd>{{ formatPreviewMetric(linkPreview.content.like_count, linkPreview.content.metrics_status) }}</dd>
            </div>
            <div>
              <dt>评论</dt>
              <dd>{{ formatPreviewMetric(linkPreview.content.comment_count, linkPreview.content.metrics_status) }}</dd>
            </div>
            <div>
              <dt>收藏</dt>
              <dd>{{ formatPreviewMetric(linkPreview.content.collect_count, linkPreview.content.metrics_status) }}</dd>
            </div>
            <div>
              <dt>分享</dt>
              <dd>{{ formatPreviewMetric(linkPreview.content.share_count, linkPreview.content.metrics_status) }}</dd>
            </div>
          </dl>
        </section>
      </el-form>

      <template #footer>
        <el-button @click="linkDialogVisible = false">取消</el-button>
        <el-button
          :loading="linkResolving"
          :disabled="linkSubmitting || linkForm.platform !== 'douyin'"
          @click="resolveLink"
        >
          识别作品
        </el-button>
        <el-button
          type="primary"
          :loading="linkSubmitting"
          :disabled="linkResolving || linkForm.platform !== 'douyin'"
          @click="submitLink"
        >
          添加监控
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.action-buttons {
  display: flex;
  align-items: center;
  gap: 8px;
}

.link-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.link-form-grid :deep(.el-segmented),
.link-form-grid :deep(.el-select) {
  width: 100%;
}

.link-source-alert {
  margin-bottom: 16px;
}

.work-preview {
  padding: 14px;
  border: 1px solid #dbe3ea;
  border-radius: 8px;
  background: #f8fafb;
}

.work-preview-heading {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.work-preview-heading > div {
  min-width: 0;
  flex: 1;
}

.work-preview-heading strong,
.work-preview-heading small {
  display: block;
}

.work-preview-heading small {
  margin-top: 3px;
  color: #718096;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.work-preview h3,
.work-preview p {
  margin: 0;
}

.work-preview h3 {
  margin-top: 12px;
  color: #102033;
  font-size: 15px;
  line-height: 1.5;
}

.work-preview p {
  margin-top: 6px;
  color: #718096;
  font-size: 12px;
  line-height: 1.6;
}

.work-preview-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  margin: 14px 0 0;
  background: #dbe3ea;
}

.work-preview-metrics div {
  min-width: 0;
  padding: 8px 10px;
  background: #ffffff;
}

.work-preview-metrics dt,
.work-preview-metrics dd {
  display: block;
  margin: 0;
}

.work-preview-metrics dt {
  color: #718096;
  font-size: 10px;
}

.work-preview-metrics dd {
  margin-top: 4px;
  color: #102033;
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 760px) {
  .action-buttons,
  .link-form-grid {
    width: 100%;
    grid-template-columns: 1fr;
  }

  .action-buttons {
    display: grid;
  }

  .action-buttons .el-button {
    width: 100%;
    margin-left: 0;
  }

  .work-preview-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
