<script setup lang="ts">
import { Bell, Check, Link, Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import { monitoringApi } from '../api/monitoring'
import type { AlertRecord, AlertRule, AlertStatus, AlertType } from '../types/monitoring'
import { formatApiDateTime } from '../utils/datetime'

const loading = ref(false)
const items = ref<AlertRecord[]>([])
const rules = ref<AlertRule[]>([])
const total = ref(0)
const unreadCount = ref(0)
const query = reactive<{
  status: AlertStatus | ''
  alert_type: AlertType | ''
  page: number
  page_size: number
}>({ status: '', alert_type: '', page: 1, page_size: 20 })

const sentCount = computed(() => items.value.filter((item) => item.notification_status === 'sent').length)

function formatTime(value: string) {
  return formatApiDateTime(value)
}

function alertTypeLabel(type: AlertType) {
  return type === 'new_content' ? '新内容' : '增长预警'
}

function notificationLabel(status: AlertRecord['notification_status']) {
  return {
    pending: '等待发送',
    sent: '已发送',
    failed: '发送失败',
    skipped: '未配置',
  }[status]
}

async function load() {
  loading.value = true
  try {
    const [alertResponse, ruleResponse] = await Promise.all([
      monitoringApi.listAlerts(query),
      monitoringApi.listAlertRules(),
    ])
    items.value = alertResponse.items
    total.value = alertResponse.total
    unreadCount.value = alertResponse.unread_count
    rules.value = ruleResponse
  } finally {
    loading.value = false
  }
}

async function markRead(alert: AlertRecord) {
  await monitoringApi.markAlertRead(alert.id)
  await load()
}

async function markAllRead() {
  const result = await monitoringApi.markAllAlertsRead()
  ElMessage.success(`已处理 ${result.updated} 条未读预警`)
  await load()
}

async function toggleRule(rule: AlertRule) {
  await monitoringApi.updateAlertRule(rule.id, { is_enabled: rule.is_enabled })
  ElMessage.success(rule.is_enabled ? '预警规则已启用' : '预警规则已暂停')
}

async function saveThreshold(rule: AlertRule) {
  await monitoringApi.updateAlertRule(rule.id, { conditions_json: rule.conditions_json })
  ElMessage.success('增长阈值已更新')
}

onMounted(load)
</script>

<template>
  <div class="page-stack">
    <section class="action-row">
      <div>
        <h2>预警中心</h2>
        <p>集中处理新内容与互动增长提醒</p>
      </div>
      <el-button type="primary" :icon="Check" :disabled="unreadCount === 0" @click="markAllRead">
        全部标为已读
      </el-button>
    </section>

    <section class="metric-grid alert-metrics">
      <article class="metric-block">
        <span>未读预警</span>
        <strong>{{ unreadCount }}</strong>
        <small>等待运营人员处理</small>
      </article>
      <article class="metric-block">
        <span>当前列表</span>
        <strong>{{ total }}</strong>
        <small>符合当前筛选条件</small>
      </article>
      <article class="metric-block">
        <span>通知已发送</span>
        <strong>{{ sentCount }}</strong>
        <small>当前页 Webhook 发送成功</small>
      </article>
      <article class="metric-block">
        <span>启用规则</span>
        <strong>{{ rules.filter((rule) => rule.is_enabled).length }}</strong>
        <small>新内容与增长规则</small>
      </article>
    </section>

    <section class="alert-workspace">
      <div class="alert-main">
        <section class="filter-bar alert-filter">
          <el-select v-model="query.status" placeholder="全部状态" clearable @change="load">
            <el-option label="未读" value="unread" />
            <el-option label="已读" value="read" />
          </el-select>
          <el-select v-model="query.alert_type" placeholder="全部类型" clearable @change="load">
            <el-option label="新内容" value="new_content" />
            <el-option label="增长预警" value="content_like_growth" />
          </el-select>
        </section>

        <section v-loading="loading" class="alert-list">
          <article
            v-for="alert in items"
            :key="alert.id"
            class="alert-item"
            :class="[alert.status, alert.severity]"
          >
            <div class="alert-icon"><el-icon><Bell /></el-icon></div>
            <div class="alert-copy">
              <div class="alert-meta">
                <span>{{ alertTypeLabel(alert.alert_type) }}</span>
                <span>{{ formatTime(alert.triggered_at) }}</span>
                <span>通知：{{ notificationLabel(alert.notification_status) }}</span>
              </div>
              <h3>{{ alert.title }}</h3>
              <p>{{ alert.message }}</p>
            </div>
            <div class="alert-actions">
              <el-button
                v-if="alert.content_id"
                :icon="Link"
                @click="$router.push('/feed')"
              >
                查看动态
              </el-button>
              <el-button v-if="alert.status === 'unread'" :icon="Check" @click="markRead(alert)">
                标为已读
              </el-button>
            </div>
          </article>
          <el-empty v-if="!loading && items.length === 0" description="当前没有预警" />
        </section>
      </div>

      <aside class="rule-panel">
        <div class="section-heading">
          <div>
            <h2>预警规则</h2>
            <p>采集完成后自动执行</p>
          </div>
          <el-icon><Setting /></el-icon>
        </div>
        <article v-for="rule in rules" :key="rule.id" class="rule-item">
          <div class="rule-heading">
            <div>
              <strong>{{ rule.name }}</strong>
              <small>{{ alertTypeLabel(rule.alert_type) }}</small>
            </div>
            <el-switch v-model="rule.is_enabled" @change="toggleRule(rule)" />
          </div>
          <div v-if="rule.alert_type === 'content_like_growth'" class="rule-threshold">
            <span>单次新增点赞达到</span>
            <el-input-number
              v-model="rule.conditions_json.threshold"
              :min="1"
              :max="1000000"
              controls-position="right"
              @change="saveThreshold(rule)"
            />
          </div>
          <p>通知渠道：{{ rule.notification_channels_json.join('、') || '仅站内' }}</p>
        </article>
      </aside>
    </section>
  </div>
</template>
