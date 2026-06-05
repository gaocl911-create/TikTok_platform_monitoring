<script setup lang="ts">
import { Refresh, Search } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'

import { monitoringApi } from '../api/monitoring'
import type { CollectionRun } from '../types/creator'
import { formatApiDateTime } from '../utils/datetime'

const loading = ref(false)
const items = ref<CollectionRun[]>([])
const total = ref(0)
const query = reactive({
  status: '' as '' | 'success' | 'partial' | 'failed' | 'skipped',
  collector_type: '' as '' | 'mock' | 'douyin_public_web',
  page: 1,
  page_size: 20,
})

const successCount = computed(() => items.value.filter((item) => item.status === 'success').length)
const failedCount = computed(() => items.value.filter((item) => item.status === 'failed').length)
const skippedCount = computed(() => items.value.filter((item) => item.status === 'skipped').length)

function statusLabel(status: string) {
  return {
    success: '成功',
    partial: '部分成功',
    failed: '失败',
    skipped: '已跳过',
    running: '运行中',
  }[status] || status
}

function triggerLabel(source: string) {
  return { initial: '首次采集', manual: '手动', scheduled: '定时任务' }[source] || source
}

function sourceLabel(source: string | null) {
  return source === 'douyin_public_web' ? '抖音公开主页' : source === 'mock' ? '模拟采集器' : '未知'
}

function formatDuration(value: number | null) {
  if (value === null) return '--'
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(1)} s`
}

function summary(run: CollectionRun) {
  const value = run.result_summary
  if (!value) return run.error_message || '暂无摘要'
  if (run.status === 'skipped') return String(value.reason || run.error_message || '任务已跳过')
  const parts = [
    `内容状态：${String(value.content_status || '--')}`,
    `新增作品：${String(value.new_content_count ?? '--')}`,
    `预警：${String(value.alert_count ?? '--')}`,
  ]
  return parts.join(' · ')
}

async function load() {
  loading.value = true
  try {
    const response = await monitoringApi.listCollectionRuns(query)
    items.value = response.items
    total.value = response.total
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page-stack">
    <section class="action-row">
      <div>
        <h2>采集运行记录</h2>
        <p>查看每次真实或模拟采集的状态、耗时、重试次数与失败原因</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新记录</el-button>
    </section>

    <section class="metric-grid">
      <article class="metric-block">
        <span>记录总数</span><strong>{{ total }}</strong><small>符合当前筛选条件</small>
      </article>
      <article class="metric-block">
        <span>当前页成功</span><strong>{{ successCount }}</strong><small>完整采集完成</small>
      </article>
      <article class="metric-block">
        <span>当前页失败</span><strong>{{ failedCount }}</strong><small>可查看错误分类</small>
      </article>
      <article class="metric-block">
        <span>当前页跳过</span><strong>{{ skippedCount }}</strong><small>通常由同账号任务去重产生</small>
      </article>
    </section>

    <section class="filter-bar run-filter">
      <el-select v-model="query.status" placeholder="全部状态" clearable @change="load">
        <el-option label="成功" value="success" />
        <el-option label="部分成功" value="partial" />
        <el-option label="失败" value="failed" />
        <el-option label="已跳过" value="skipped" />
      </el-select>
      <el-select v-model="query.collector_type" placeholder="全部数据来源" clearable @change="load">
        <el-option label="抖音公开主页" value="douyin_public_web" />
        <el-option label="模拟采集器" value="mock" />
      </el-select>
      <el-button :icon="Search" @click="load">查询</el-button>
    </section>

    <section v-loading="loading" class="content-section run-table-wrap">
      <el-table :data="items" empty-text="暂无采集运行记录">
        <el-table-column label="账号" min-width="150">
          <template #default="{ row }">
            <div class="creator-cell">
              <span class="platform-dot" :class="row.creator.platform"></span>
              <div><strong>{{ row.creator.nickname }}</strong><small>#{{ row.creator_id }}</small></div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span class="run-status" :class="row.status">{{ statusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" min-width="130">
          <template #default="{ row }">{{ sourceLabel(row.collector_type) }}</template>
        </el-table-column>
        <el-table-column label="触发 / 尝试" min-width="120">
          <template #default="{ row }">{{ triggerLabel(row.trigger_source) }} · 第 {{ row.attempt }} 次</template>
        </el-table-column>
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
        </el-table-column>
        <el-table-column label="开始时间" min-width="170">
          <template #default="{ row }">{{ formatApiDateTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column label="结果摘要" min-width="320">
          <template #default="{ row }">
            <div class="run-summary">
              <span>{{ summary(row) }}</span>
              <small v-if="row.error_type">{{ row.error_type }}：{{ row.error_message }}</small>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <div class="pagination-row">
      <span>共 {{ total }} 条运行记录</span>
      <el-pagination
        v-model:current-page="query.page"
        layout="prev, pager, next"
        :page-size="query.page_size"
        :total="total"
        @current-change="load"
      />
    </div>
  </div>
</template>
