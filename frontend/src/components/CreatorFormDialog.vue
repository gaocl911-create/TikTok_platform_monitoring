<script setup lang="ts">
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import { creatorApi } from '../api/creators'
import type { Creator, CreatorPayload, CreatorProfileResolveResult } from '../types/creator'
import { isValidProfileUrl, normalizeProfileUrl } from '../utils/profileUrl'

const props = defineProps<{
  modelValue: boolean
  creator?: Creator | null
  submitting?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: CreatorPayload]
}>()

const formRef = ref<FormInstance>()
const resolving = ref(false)
const resolvedProfile = ref<CreatorProfileResolveResult | null>(null)
const form = reactive<CreatorPayload>({
  platform: 'douyin',
  platform_account_id: '',
  platform_display_id: '',
  nickname: '',
  profile_url: '',
  avatar_url: null,
  bio: null,
  verified_info: null,
  location: null,
  group_name: '',
  tags: [],
  priority: 'normal',
  monitor_interval_minutes: 30,
  collector_type: 'tikomni_douyin',
  follower_count: 0,
  following_count: 0,
  total_like_count: 0,
  content_count: 0,
  profile_resolved: false,
})

const isEditing = computed(() => Boolean(props.creator))
const isDouyin = computed(() => form.platform === 'douyin')
const resolveInputValue = computed(
  () => form.profile_url.trim() || form.platform_display_id?.trim() || form.platform_account_id.trim(),
)
const canResolve = computed(() => isDouyin.value && !isEditing.value && Boolean(resolveInputValue.value))

const platformOptions = computed(() => [
  { label: '抖音', value: 'douyin' },
  { label: '小红书', value: 'xiaohongshu' },
])

const rules: FormRules<CreatorPayload> = {
  platform: [{ required: true, message: '请选择数据来源', trigger: 'change' }],
  platform_account_id: [{ required: true, message: '请先识别账号，生成采集ID', trigger: 'blur' }],
  nickname: [{ required: true, message: '请先识别或输入作者昵称', trigger: 'blur' }],
  profile_url: [
    { required: true, message: '请粘贴账号主页链接或平台分享文案', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (isValidProfileUrl(value)) callback()
        else callback(new Error('请输入有效且不含空格的 HTTP(S) 主页链接'))
      },
      trigger: 'blur',
    },
  ],
  monitor_interval_minutes: [
    { required: true, message: '请设置采集间隔', trigger: 'change' },
  ],
}

watch(
  () => [props.modelValue, props.creator] as const,
  ([visible, creator]) => {
    if (!visible) return
    Object.assign(form, {
      platform: creator?.platform || 'douyin',
      platform_account_id: creator?.platform_account_id || '',
      platform_display_id: creator?.platform_display_id || '',
      nickname: creator?.nickname || '',
      profile_url: creator?.profile_url || '',
      avatar_url: creator?.avatar_url || null,
      bio: creator?.bio || null,
      verified_info: creator?.verified_info || null,
      location: creator?.location || null,
      group_name: creator?.group_name || '',
      tags: creator?.tags || [],
      priority: creator?.priority || 'normal',
      monitor_interval_minutes: creator?.monitor_interval_minutes || 30,
      collector_type: creator?.collector_type || 'tikomni_douyin',
      follower_count: creator?.follower_count || 0,
      following_count: creator?.following_count || 0,
      total_like_count: creator?.total_like_count || 0,
      content_count: creator?.content_count || 0,
      profile_resolved: false,
    })
    if (!creator && form.platform === 'douyin') {
      form.collector_type = 'tikomni_douyin'
    }
    resolvedProfile.value = null
    formRef.value?.clearValidate()
  },
  { immediate: true },
)

watch(
  () => form.platform,
  (platform) => {
    form.collector_type = platform === 'douyin' ? 'tikomni_douyin' : 'mock'
    resolvedProfile.value = null
    formRef.value?.clearValidate()
  },
)

function formatNumber(value: number) {
  return value.toLocaleString('zh-CN')
}

function applyResolvedProfile(profile: CreatorProfileResolveResult) {
  form.platform_account_id = profile.platform_account_id
  form.platform_display_id = profile.platform_display_id
  form.nickname = profile.nickname
  form.profile_url = profile.profile_url
  form.avatar_url = profile.avatar_url
  form.bio = profile.bio
  form.verified_info = profile.verified_info
  form.location = profile.location
  form.follower_count = profile.follower_count
  form.following_count = profile.following_count
  form.total_like_count = profile.total_like_count
  form.content_count = profile.content_count
  form.collector_type = 'tikomni_douyin'
  form.profile_resolved = true
  resolvedProfile.value = profile
}

async function handleResolveProfile() {
  if (!isDouyin.value) {
    ElMessage.warning('小红书数据源已预留，当前阶段先接入抖音')
    return
  }
  if (!resolveInputValue.value) {
    ElMessage.warning('请先输入抖音号、主页链接或分享文案')
    return
  }

  resolving.value = true
  try {
    const profile = await creatorApi.resolveProfile({
      platform: form.platform,
      input_value: resolveInputValue.value,
    })
    applyResolvedProfile(profile)
    formRef.value?.clearValidate(['platform_account_id', 'nickname', 'profile_url'])
    if (profile.warnings.length > 0) {
      ElMessage.warning(profile.warnings[0])
    } else {
      ElMessage.success('账号主页信息已识别')
    }
  } finally {
    resolving.value = false
  }
}

async function handleSubmit() {
  if (!isDouyin.value) {
    ElMessage.warning('小红书数据源已预留，当前阶段先接入抖音')
    return
  }
  if (!isEditing.value && !form.profile_resolved && resolveInputValue.value) {
    await handleResolveProfile()
  }
  form.collector_type = 'tikomni_douyin'
  form.profile_url = normalizeProfileUrl(form.profile_url)
  await formRef.value?.validate()
  emit('submit', { ...form, tags: [...form.tags] })
}

function normalizeUrlField() {
  form.profile_url = normalizeProfileUrl(form.profile_url)
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="isEditing ? '编辑监控账号' : '添加监控账号'"
    width="640px"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <div class="form-grid">
        <el-form-item label="数据来源" prop="platform">
          <el-segmented
            v-model="form.platform"
            :options="platformOptions"
            :disabled="isEditing"
          />
        </el-form-item>
        <el-form-item label="监控优先级" prop="priority">
          <el-select v-model="form.priority">
            <el-option label="重点" value="high" />
            <el-option label="普通" value="normal" />
            <el-option label="低频" value="low" />
          </el-select>
        </el-form-item>
      </div>

      <el-alert
        v-if="form.platform === 'xiaohongshu'"
        class="source-alert"
        type="info"
        title="小红书待接入"
        description="当前阶段先实现抖音主页识别和真实采集。"
        show-icon
        :closable="false"
      />

      <el-form-item label="账号主页 / 分享链接" prop="profile_url">
        <el-input
          v-model="form.profile_url"
          placeholder="粘贴抖音主页链接、短链或分享文案"
          :disabled="!isDouyin"
          @blur="normalizeUrlField"
        >
          <template #append>
            <el-button
              :loading="resolving"
              :disabled="!canResolve"
              @click="handleResolveProfile"
            >
              识别账号
            </el-button>
          </template>
        </el-input>
      </el-form-item>

      <div class="form-grid">
        <el-form-item label="作者昵称" prop="nickname">
          <el-input v-model="form.nickname" placeholder="识别后自动回填，可手动修正" />
        </el-form-item>
        <el-form-item label="抖音号">
          <el-input
            v-model="form.platform_display_id"
            placeholder="识别后显示，例如 34867887966"
          />
        </el-form-item>
      </div>

      <el-form-item label="采集ID（sec_user_id）" prop="platform_account_id">
        <el-input
          v-model="form.platform_account_id"
          placeholder="系统自动识别，用于真实采集"
          :disabled="isEditing"
          readonly
        />
      </el-form-item>

      <section v-if="resolvedProfile" class="profile-preview">
        <div class="preview-heading">
          <el-avatar :size="40" :src="resolvedProfile.avatar_url || undefined">
            {{ resolvedProfile.nickname.slice(0, 1) }}
          </el-avatar>
          <div>
            <strong>{{ resolvedProfile.nickname }}</strong>
            <small>{{ resolvedProfile.bio || '暂无简介' }}</small>
          </div>
        </div>
        <dl>
          <div>
            <dt>粉丝</dt>
            <dd>{{ formatNumber(resolvedProfile.follower_count) }}</dd>
          </div>
          <div>
            <dt>关注</dt>
            <dd>{{ formatNumber(resolvedProfile.following_count) }}</dd>
          </div>
          <div>
            <dt>获赞</dt>
            <dd>{{ formatNumber(resolvedProfile.total_like_count) }}</dd>
          </div>
          <div>
            <dt>作品</dt>
            <dd>{{ formatNumber(resolvedProfile.content_count) }}</dd>
          </div>
        </dl>
      </section>

      <div class="form-grid">
        <el-form-item label="作者备注">
          <el-input v-model="form.group_name" placeholder="例如：科技类竞品、重点观察" />
        </el-form-item>
        <el-form-item label="采集间隔" prop="monitor_interval_minutes">
          <el-select v-model="form.monitor_interval_minutes">
            <el-option label="每 15 分钟" :value="15" />
            <el-option label="每 30 分钟" :value="30" />
            <el-option label="每 1 小时" :value="60" />
            <el-option label="每 3 小时" :value="180" />
            <el-option label="每天" :value="1440" />
          </el-select>
        </el-form-item>
      </div>

      <el-form-item label="标签">
        <el-select
          v-model="form.tags"
          multiple
          filterable
          allow-create
          default-first-option
          placeholder="输入标签后回车"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting || resolving"
        :disabled="form.platform !== 'douyin'"
        @click="handleSubmit"
      >
        {{ isEditing ? '保存修改' : '添加并采集主页' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

:deep(.el-segmented),
:deep(.el-select) {
  width: 100%;
}

.source-alert {
  margin: 0 0 16px;
}

.profile-preview {
  margin: 0 0 18px;
  padding: 14px;
  border: 1px solid #dbe3ea;
  border-radius: 8px;
  background: #f8fafb;
}

.preview-heading {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.preview-heading strong,
.preview-heading small {
  display: block;
}

.preview-heading small {
  margin-top: 3px;
  color: #718096;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 480px;
}

.profile-preview dl {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0 0;
}

.profile-preview dt {
  color: #7b8794;
  font-size: 12px;
}

.profile-preview dd {
  margin: 4px 0 0;
  color: #102033;
  font-size: 18px;
  font-weight: 700;
}

@media (max-width: 620px) {
  .form-grid,
  .profile-preview dl {
    grid-template-columns: 1fr;
    gap: 0;
  }

  .preview-heading small {
    max-width: 240px;
  }
}
</style>
