<script setup lang="ts">
import { Delete, Edit, Plus, Refresh, Search, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import CreatorFormDialog from '../components/CreatorFormDialog.vue'
import { useCreatorStore } from '../stores/creators'
import type { Creator, CreatorPayload, MonitoringStatus, Platform } from '../types/creator'

const store = useCreatorStore()
const router = useRouter()
const dialogVisible = ref(false)
const submitting = ref(false)
const collectingId = ref<number | null>(null)
const editingCreator = ref<Creator | null>(null)
const query = reactive<{
  search: string
  platform: Platform | ''
  monitoring_status: MonitoringStatus | ''
  page: number
  page_size: number
}>({
  search: '',
  platform: '',
  monitoring_status: '',
  page: 1,
  page_size: 20,
})

function formatNumber(value: number) {
  return value.toLocaleString('zh-CN')
}

function formatTime(value: string | null) {
  if (!value) return '尚未采集'
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function load() {
  await store.fetchCreators(query)
}

function openCreateDialog() {
  editingCreator.value = null
  dialogVisible.value = true
}

function openEditDialog(creator: Creator) {
  editingCreator.value = creator
  dialogVisible.value = true
}

async function handleSubmit(payload: CreatorPayload) {
  submitting.value = true
  try {
    if (editingCreator.value) {
      await store.updateCreator(editingCreator.value.id, {
        nickname: payload.nickname,
        profile_url: payload.profile_url,
        group_name: payload.group_name,
        tags: payload.tags,
        priority: payload.priority,
        monitor_interval_minutes: payload.monitor_interval_minutes,
      })
      ElMessage.success('账号配置已更新')
    } else {
      await store.createCreator(payload)
      ElMessage.success('账号已添加，并完成首次采集')
    }
    dialogVisible.value = false
    await load()
  } finally {
    submitting.value = false
  }
}

async function handleCollect(creator: Creator) {
  collectingId.value = creator.id
  try {
    const result = await store.collectCreator(creator.id)
    const delta = result.run.result_summary?.follower_delta || 0
    ElMessage.success(`采集完成，粉丝变化 +${delta}`)
    await load()
  } finally {
    collectingId.value = null
  }
}

async function toggleStatus(creator: Creator) {
  const monitoring_status = creator.monitoring_status === 'active' ? 'paused' : 'active'
  await store.updateCreator(creator.id, { monitoring_status })
  ElMessage.success(monitoring_status === 'active' ? '已恢复监控' : '已暂停监控')
  await load()
}

async function handleDelete(creator: Creator) {
  await ElMessageBox.confirm(
    `删除“${creator.nickname}”后，其历史快照也会一并删除。`,
    '确认删除监控账号',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  )
  await store.deleteCreator(creator.id)
  ElMessage.success('监控账号已删除')
  await load()
}

onMounted(load)
</script>

<template>
  <div class="page-stack">
    <section class="action-row">
      <div>
        <h2>账号监控列表</h2>
        <p>统一管理指定账号、采集频率与运行状态</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreateDialog">添加账号</el-button>
    </section>

    <section class="filter-bar">
      <el-input
        v-model="query.search"
        :prefix-icon="Search"
        clearable
        placeholder="搜索昵称、账号 ID 或分组"
        @keyup.enter="load"
        @clear="load"
      />
      <el-select v-model="query.platform" placeholder="全部平台" clearable @change="load">
        <el-option label="抖音" value="douyin" />
        <el-option label="小红书" value="xiaohongshu" />
      </el-select>
      <el-select
        v-model="query.monitoring_status"
        placeholder="全部状态"
        clearable
        @change="load"
      >
        <el-option label="监控中" value="active" />
        <el-option label="已暂停" value="paused" />
      </el-select>
      <el-button :icon="Search" @click="load">查询</el-button>
    </section>

    <section class="content-section table-section desktop-table">
      <el-table :data="store.items" :loading="store.loading" empty-text="还没有监控账号">
        <el-table-column label="账号" min-width="230" fixed>
          <template #default="{ row }">
            <button class="creator-link" type="button" @click="router.push(`/creators/${row.id}`)">
              <span class="platform-dot" :class="row.platform"></span>
              <span>
                <strong>{{ row.nickname }}</strong>
                <small>{{ row.platform_account_id }}</small>
              </span>
            </button>
          </template>
        </el-table-column>
        <el-table-column label="分组 / 标签" min-width="180">
          <template #default="{ row }">
            <div class="tag-cell">
              <span>{{ row.group_name || '未分组' }}</span>
              <el-tag v-for="tag in row.tags.slice(0, 2)" :key="tag" size="small" effect="plain">
                {{ tag }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="粉丝" width="130" align="right">
          <template #default="{ row }">{{ formatNumber(row.follower_count) }}</template>
        </el-table-column>
        <el-table-column label="累计获赞" width="150" align="right">
          <template #default="{ row }">{{ formatNumber(row.total_like_count) }}</template>
        </el-table-column>
        <el-table-column label="作品" width="90" align="right" prop="content_count" />
        <el-table-column label="采集设置" width="160">
          <template #default="{ row }">
            <div class="collection-setting">
              <span class="status" :class="row.monitoring_status">
                {{ row.monitoring_status === 'active' ? '监控中' : '已暂停' }}
              </span>
              <small>每 {{ row.monitor_interval_minutes }} 分钟</small>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="最近采集" width="160">
          <template #default="{ row }">{{ formatTime(row.last_collected_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-tooltip content="查看详情">
                <el-button
                  circle
                  :icon="View"
                  aria-label="查看账号详情"
                  @click="router.push(`/creators/${row.id}`)"
                />
              </el-tooltip>
              <el-tooltip content="立即采集">
                <el-button
                  circle
                  :icon="Refresh"
                  :loading="collectingId === row.id"
                  aria-label="立即采集账号数据"
                  @click="handleCollect(row)"
                />
              </el-tooltip>
              <el-tooltip content="编辑">
                <el-button circle :icon="Edit" aria-label="编辑账号" @click="openEditDialog(row)" />
              </el-tooltip>
              <el-tooltip :content="row.monitoring_status === 'active' ? '暂停监控' : '恢复监控'">
                <el-switch
                  :model-value="row.monitoring_status === 'active'"
                  aria-label="切换监控状态"
                  @change="toggleStatus(row)"
                />
              </el-tooltip>
              <el-tooltip content="删除">
                <el-button
                  circle
                  type="danger"
                  plain
                  :icon="Delete"
                  aria-label="删除账号"
                  @click="handleDelete(row)"
                />
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-row">
        <span>共 {{ store.total }} 个账号</span>
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          layout="prev, pager, next"
          :total="store.total"
          @current-change="load"
        />
      </div>
    </section>

    <section class="mobile-account-list" aria-label="移动端账号列表">
      <article v-for="creator in store.items" :key="creator.id" class="mobile-account">
        <div class="mobile-account-heading">
          <div class="creator-cell">
            <span class="platform-dot" :class="creator.platform"></span>
            <div>
              <strong>{{ creator.nickname }}</strong>
              <small>{{ creator.group_name || creator.platform_account_id }}</small>
            </div>
          </div>
          <span class="status" :class="creator.monitoring_status">
            {{ creator.monitoring_status === 'active' ? '监控中' : '已暂停' }}
          </span>
        </div>
        <dl>
          <div>
            <dt>粉丝</dt>
            <dd>{{ formatNumber(creator.follower_count) }}</dd>
          </div>
          <div>
            <dt>累计获赞</dt>
            <dd>{{ formatNumber(creator.total_like_count) }}</dd>
          </div>
          <div>
            <dt>采集间隔</dt>
            <dd>{{ creator.monitor_interval_minutes }} 分钟</dd>
          </div>
        </dl>
        <div class="mobile-account-actions">
          <el-button :icon="View" @click="router.push(`/creators/${creator.id}`)">详情</el-button>
          <el-button
            :icon="Refresh"
            :loading="collectingId === creator.id"
            @click="handleCollect(creator)"
          >
            采集
          </el-button>
          <el-button :icon="Edit" aria-label="编辑账号" @click="openEditDialog(creator)" />
          <el-switch
            :model-value="creator.monitoring_status === 'active'"
            aria-label="切换监控状态"
            @change="toggleStatus(creator)"
          />
          <el-button
            type="danger"
            plain
            :icon="Delete"
            aria-label="删除账号"
            @click="handleDelete(creator)"
          />
        </div>
      </article>
    </section>

    <CreatorFormDialog
      v-model="dialogVisible"
      :creator="editingCreator"
      :submitting="submitting"
      @submit="handleSubmit"
    />
  </div>
</template>
