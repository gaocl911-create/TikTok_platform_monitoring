<script setup lang="ts">
import { ArrowLeft, Link, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import TrendChart from '../components/TrendChart.vue'
import { useCreatorStore } from '../stores/creators'
import type { Creator, CreatorSnapshot } from '../types/creator'
import { collectorLabel, qualityDescription, qualityLabel } from '../utils/collector'
import { formatApiDateTime } from '../utils/datetime'

const route = useRoute()
const router = useRouter()
const store = useCreatorStore()
const creator = ref<Creator | null>(null)
const snapshots = ref<CreatorSnapshot[]>([])
const loading = ref(true)
const collecting = ref(false)
const metric = ref<'follower_count' | 'total_like_count'>('follower_count')
const creatorId = computed(() => Number(route.params.id))
const sourceSnapshots = computed(() =>
  snapshots.value.filter((snapshot) => snapshot.collector_type === creator.value?.collector_type),
)

const followerDelta = computed(() => {
  if (sourceSnapshots.value.length < 2) return 0
  const latest = sourceSnapshots.value.at(-1)!
  const previous = sourceSnapshots.value.at(-2)!
  return latest.follower_count - previous.follower_count
})

function formatNumber(value: number | undefined) {
  return Number(value || 0).toLocaleString('zh-CN')
}

function formatTime(value: string | null | undefined) {
  if (!value) return '尚未采集'
  return formatApiDateTime(value)
}

async function load() {
  loading.value = true
  try {
    ;[creator.value, snapshots.value] = await Promise.all([
      store.getCreator(creatorId.value),
      store.getSnapshots(creatorId.value),
    ])
  } finally {
    loading.value = false
  }
}

async function collect() {
  collecting.value = true
  try {
    const result = await store.collectCreator(creatorId.value)
    if (!('run' in result)) {
      ElMessage.warning('首次采集失败，已加入自动重试队列，可在“采集运行”查看进度')
    } else if (result.run.status === 'partial') {
      ElMessage.warning('真实账号指标已更新，作品明细暂不可用')
    } else {
      ElMessage.success('公开数据快照已更新')
    }
    await load()
  } finally {
    collecting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="page-stack">
    <section class="detail-toolbar">
      <el-button :icon="ArrowLeft" @click="router.push('/creators')">返回账号列表</el-button>
      <div>
        <el-button
          v-if="creator"
          :icon="Link"
          tag="a"
          :href="creator.profile_url"
          target="_blank"
        >
          打开主页
        </el-button>
        <el-button type="primary" :icon="Refresh" :loading="collecting" @click="collect">
          立即采集
        </el-button>
      </div>
    </section>

    <template v-if="creator">
      <section class="profile-band">
        <div class="profile-main">
          <span class="profile-avatar" :class="creator.platform">
            {{ creator.nickname.slice(0, 1) }}
          </span>
          <div>
            <div class="profile-title">
              <h2>{{ creator.nickname }}</h2>
              <span class="status" :class="creator.monitoring_status">
                {{ creator.monitoring_status === 'active' ? '监控中' : '已暂停' }}
              </span>
            </div>
            <p>{{ creator.bio || '暂无公开简介' }}</p>
            <div class="profile-meta">
              <span>{{ creator.platform === 'douyin' ? '抖音' : '小红书' }}</span>
              <span>ID {{ creator.platform_account_id }}</span>
              <span>{{ creator.group_name || '未分组' }}</span>
              <span>{{ creator.location || '地区未知' }}</span>
            </div>
          </div>
        </div>
        <div class="profile-collection">
          <span>最近采集</span>
          <strong>{{ formatTime(creator.last_collected_at) }}</strong>
          <small>下次：{{ formatTime(creator.next_collect_at) }}</small>
        </div>
      </section>

      <section class="collection-health" :class="creator.data_quality_status">
        <div>
          <span>数据来源</span>
          <strong>{{ collectorLabel(creator.collector_type) }}</strong>
        </div>
        <div>
          <span>数据质量</span>
          <strong>{{ qualityLabel(creator.data_quality_status) }}</strong>
        </div>
        <p>{{ qualityDescription(creator) }}</p>
      </section>

      <section class="metric-grid">
        <article class="metric-block">
          <span>粉丝</span>
          <strong>{{ formatNumber(creator.follower_count) }}</strong>
          <small>最近变化 +{{ followerDelta }}</small>
        </article>
        <article class="metric-block">
          <span>关注</span>
          <strong>{{ formatNumber(creator.following_count) }}</strong>
          <small>公开主页指标</small>
        </article>
        <article class="metric-block">
          <span>累计获赞</span>
          <strong>{{ formatNumber(creator.total_like_count) }}</strong>
          <small>最近公开指标</small>
        </article>
        <article class="metric-block">
          <span>公开作品</span>
          <strong>{{ formatNumber(creator.content_count) }}</strong>
          <small>
            {{
              creator.last_content_status === 'success'
                ? creator.collector_type === 'mock'
                  ? '模拟作品数据'
                  : '真实作品明细可用'
                : '真实作品明细暂不可用'
            }}
          </small>
        </article>
      </section>

      <section class="content-section">
        <div class="section-heading">
          <div>
            <h2>历史趋势</h2>
            <p>每次采集生成一条账号公开数据快照</p>
          </div>
          <el-segmented
            v-model="metric"
            :options="[
              { label: '粉丝趋势', value: 'follower_count' },
              { label: '获赞趋势', value: 'total_like_count' },
            ]"
          />
        </div>
        <TrendChart v-if="sourceSnapshots.length" :snapshots="sourceSnapshots" :metric="metric" />
        <el-empty v-else description="暂无历史快照" />
      </section>

      <section class="content-section snapshot-section">
        <div class="section-heading">
          <div>
            <h2>采集记录</h2>
            <p>当前数据来源最近 {{ sourceSnapshots.length }} 条可用账号快照</p>
          </div>
        </div>
        <el-table :data="[...sourceSnapshots].reverse()" empty-text="暂无当前来源快照">
          <el-table-column label="采集时间" min-width="190">
            <template #default="{ row }">{{ formatTime(row.captured_at) }}</template>
          </el-table-column>
          <el-table-column label="粉丝" min-width="130" align="right">
            <template #default="{ row }">{{ formatNumber(row.follower_count) }}</template>
          </el-table-column>
          <el-table-column label="关注" min-width="130" align="right">
            <template #default="{ row }">{{ formatNumber(row.following_count) }}</template>
          </el-table-column>
          <el-table-column label="累计获赞" min-width="150" align="right">
            <template #default="{ row }">{{ formatNumber(row.total_like_count) }}</template>
          </el-table-column>
          <el-table-column label="公开作品" min-width="130" align="right" prop="content_count" />
        </el-table>
      </section>
    </template>
  </div>
</template>
