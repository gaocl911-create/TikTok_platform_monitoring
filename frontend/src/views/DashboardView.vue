<script setup lang="ts">
import { ArrowRight, CirclePlus, Refresh } from '@element-plus/icons-vue'
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

import { useCreatorStore } from '../stores/creators'
import type { Creator } from '../types/creator'

const store = useCreatorStore()
const router = useRouter()

const activeCount = computed(
  () => store.items.filter((creator) => creator.monitoring_status === 'active').length,
)
const totalFollowers = computed(() =>
  store.items.reduce((total, creator) => total + creator.follower_count, 0),
)
const totalLikes = computed(() =>
  store.items.reduce((total, creator) => total + creator.total_like_count, 0),
)
const latestCollection = computed(() => {
  const times = store.items
    .map((creator) => creator.last_collected_at)
    .filter((value): value is string => Boolean(value))
    .sort()
  return times.at(-1)
})

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 }).format(
    value,
  )
}

function formatTime(value: string | null | undefined) {
  if (!value) return '暂无采集'
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function openCreator(row: Creator) {
  router.push(`/creators/${row.id}`)
}

onMounted(() => store.fetchCreators({ page_size: 100 }))
</script>

<template>
  <div class="page-stack">
    <section class="action-row">
      <div>
        <h2>账号运行概况</h2>
        <p>基于最近一次公开数据快照</p>
      </div>
      <el-button type="primary" :icon="CirclePlus" @click="router.push('/creators')">
        添加监控账号
      </el-button>
    </section>

    <section class="metric-grid" aria-label="监控数据汇总">
      <article class="metric-block">
        <span>监控账号</span>
        <strong>{{ store.total }}</strong>
        <small>{{ activeCount }} 个正在运行</small>
      </article>
      <article class="metric-block">
        <span>覆盖粉丝</span>
        <strong>{{ formatNumber(totalFollowers) }}</strong>
        <small>所有账号公开粉丝合计</small>
      </article>
      <article class="metric-block">
        <span>累计获赞</span>
        <strong>{{ formatNumber(totalLikes) }}</strong>
        <small>最近公开指标</small>
      </article>
      <article class="metric-block">
        <span>最近采集</span>
        <strong class="time-value">{{ formatTime(latestCollection) }}</strong>
        <small>MockCollector 数据链路</small>
      </article>
    </section>

    <section class="content-section">
      <div class="section-heading">
        <div>
          <h2>重点账号</h2>
          <p>最近添加的监控对象</p>
        </div>
        <el-button text :icon="ArrowRight" @click="router.push('/creators')">查看全部</el-button>
      </div>

      <el-table
        :data="store.items.slice(0, 6)"
        :loading="store.loading"
        empty-text="还没有监控账号"
        @row-click="openCreator"
      >
        <el-table-column label="账号" min-width="220">
          <template #default="{ row }">
            <div class="creator-cell">
              <span class="platform-dot" :class="row.platform"></span>
              <div>
                <strong>{{ row.nickname }}</strong>
                <small>{{ row.group_name || '未分组' }}</small>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="粉丝" width="140">
          <template #default="{ row }">{{ row.follower_count.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="累计获赞" width="160">
          <template #default="{ row }">{{ row.total_like_count.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="最近采集" width="170">
          <template #default="{ row }">{{ formatTime(row.last_collected_at) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <span class="status" :class="row.monitoring_status">
              {{ row.monitoring_status === 'active' ? '监控中' : '已暂停' }}
            </span>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!store.loading && store.items.length === 0" class="empty-action">
        <el-icon><Refresh /></el-icon>
        <span>添加账号后，系统会立即生成第一条公开数据快照。</span>
      </div>
    </section>
  </div>
</template>
