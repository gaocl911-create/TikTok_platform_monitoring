<script setup lang="ts">
import type { FormInstance, FormRules } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import type { Creator, CreatorPayload } from '../types/creator'

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
const form = reactive<CreatorPayload>({
  platform: 'douyin',
  platform_account_id: '',
  nickname: '',
  profile_url: '',
  group_name: '',
  tags: [],
  priority: 'normal',
  monitor_interval_minutes: 60,
  collector_type: 'douyin_public_web',
})

const isEditing = computed(() => Boolean(props.creator))
const collectorOptions = computed(() => [
  {
    label: '真实公开数据',
    value: 'douyin_public_web',
    disabled: form.platform !== 'douyin',
  },
  { label: '模拟数据', value: 'mock' },
])
const rules: FormRules<CreatorPayload> = {
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }],
  platform_account_id: [{ required: true, message: '请输入平台账号 ID', trigger: 'blur' }],
  nickname: [{ required: true, message: '请输入账号昵称', trigger: 'blur' }],
  profile_url: [{ required: true, message: '请输入账号主页链接', trigger: 'blur' }],
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
      nickname: creator?.nickname || '',
      profile_url: creator?.profile_url || '',
      group_name: creator?.group_name || '',
      tags: creator?.tags || [],
      priority: creator?.priority || 'normal',
      monitor_interval_minutes: creator?.monitor_interval_minutes || 60,
      collector_type: creator?.collector_type || 'douyin_public_web',
    })
    formRef.value?.clearValidate()
  },
  { immediate: true },
)

watch(
  () => form.platform,
  (platform) => {
    if (platform !== 'douyin' && form.collector_type === 'douyin_public_web') {
      form.collector_type = 'mock'
    }
  },
)

async function handleSubmit() {
  await formRef.value?.validate()
  emit('submit', { ...form, tags: [...form.tags] })
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="isEditing ? '编辑监控账号' : '添加监控账号'"
    width="560px"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <div class="form-grid">
        <el-form-item label="平台" prop="platform">
          <el-segmented
            v-model="form.platform"
            :options="[
              { label: '抖音', value: 'douyin' },
              { label: '小红书', value: 'xiaohongshu' },
            ]"
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

      <el-form-item label="数据来源" prop="collector_type">
        <el-segmented v-model="form.collector_type" :options="collectorOptions" />
        <p class="source-hint">
          {{
            form.collector_type === 'douyin_public_web'
              ? '通过标准浏览器读取公开主页；无法取得的内容会明确标记，不会使用模拟数据补全。'
              : '用于开发和演示，会生成模拟账号指标与作品。'
          }}
        </p>
      </el-form-item>

      <div class="form-grid">
        <el-form-item label="账号昵称" prop="nickname">
          <el-input v-model="form.nickname" placeholder="用于快速识别账号" />
        </el-form-item>
        <el-form-item label="平台账号 ID" prop="platform_account_id">
          <el-input
            v-model="form.platform_account_id"
            placeholder="平台内唯一 ID"
            :disabled="isEditing"
          />
        </el-form-item>
      </div>

      <el-form-item label="账号主页链接" prop="profile_url">
        <el-input v-model="form.profile_url" placeholder="https://..." />
      </el-form-item>

      <div class="form-grid">
        <el-form-item label="账号分组">
          <el-input v-model="form.group_name" placeholder="例如：竞品观察" />
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
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        {{ isEditing ? '保存修改' : '添加并采集' }}
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

.source-hint {
  margin: 7px 0 0;
  color: #77808c;
  font-size: 11px;
  line-height: 1.5;
}

@media (max-width: 620px) {
  .form-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
