<template>
  <div class="mock-panel">
    <!-- 未保存接口时提示 -->
    <div v-if="!interfaceId" class="mock-placeholder">
      <a-empty :description="t('请先保存接口，再配置 Mock 规则')" :image-style="{ height: '60px' }" />
    </div>

    <!-- 已保存接口：Mock 配置面板 -->
    <div v-else class="mock-content">
      <!-- 顶部开关栏 -->
      <div class="mock-header">
        <div class="mock-header-left">
          <a-switch
            :checked="mockEnabled"
            :loading="saving"
            @change="handleToggle"
            size="small"
          />
          <span class="mock-status" :class="{ active: mockEnabled }">
            {{ mockEnabled ? t('Mock 已启用') : t('Mock 已禁用') }}
          </span>
        </div>
        <a-button
          v-if="hasRule"
          type="link"
          danger
          size="small"
          @click="handleDelete"
          :loading="saving"
        >
          {{ t('删除规则') }}
        </a-button>
      </div>

      <!-- 配置表单 -->
      <a-form layout="vertical" size="small" class="mock-form">
        <!-- 响应状态码 -->
        <a-form-item :label="t('响应状态码')">
          <a-input-number
            v-model:value="formData.status_code"
            :min="100"
            :max="599"
            style="width: 140px"
            :disabled="!mockEnabled"
          />
        </a-form-item>

        <!-- Content-Type -->
        <a-form-item :label="'Content-Type'">
          <a-select v-model:value="formData.content_type" style="width: 240px" :disabled="!mockEnabled">
            <a-select-option value="application/json">application/json</a-select-option>
            <a-select-option value="text/plain">text/plain</a-select-option>
            <a-select-option value="text/html">text/html</a-select-option>
            <a-select-option value="application/xml">application/xml</a-select-option>
            <a-select-option value="application/x-www-form-urlencoded">x-www-form-urlencoded</a-select-option>
          </a-select>
        </a-form-item>

        <!-- 响应模式 -->
        <a-form-item :label="t('响应模式')">
          <a-radio-group v-model:value="formData.response_mode" :disabled="!mockEnabled">
            <a-radio-button value="static">{{ t('静态响应') }}</a-radio-button>
            <a-radio-button value="echo">{{ t('回显请求') }}</a-radio-button>
            <a-radio-button value="template">{{ t('模板响应') }}</a-radio-button>
          </a-radio-group>
        </a-form-item>

        <!-- 响应体 -->
        <a-form-item :label="t('响应体')">
          <a-textarea
            v-model:value="formData.response_body"
            :placeholder="responseBodyPlaceholder"
            :auto-size="{ minRows: 8, maxRows: 20 }"
            class="response-body-editor"
            :disabled="!mockEnabled"
          />
        </a-form-item>

        <!-- 模拟延迟 -->
        <a-form-item :label="t('模拟延迟')">
          <a-slider
            v-model:value="formData.delay_ms"
            :min="0"
            :max="5000"
            :step="100"
            :disabled="!mockEnabled"
          />
          <span class="delay-value">{{ formData.delay_ms }}ms</span>
        </a-form-item>

        <!-- 场景标签 -->
        <a-form-item :label="t('场景标签')">
          <a-input
            v-model:value="formData.scenario"
            :placeholder="t('如: default, error, timeout')"
            style="width: 240px"
            :disabled="!mockEnabled"
          />
        </a-form-item>
      </a-form>

      <!-- 自动保存提示 -->
      <div class="mock-actions">
        <span v-if="dirty" class="saving-hint">
          <a-spin size="small" /> {{ t('保存中...') }}
        </span>
        <span v-else-if="hasRule" class="saved-hint">
          {{ t('已自动保存') }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import { useMockStore } from '../../stores/mock'
import { t } from '../../i18n'

const props = defineProps({
  interfaceId: { type: [Number, String], default: null },
})

const mockStore = useMockStore()
const saving = ref(false)
const dirty = ref(false)
let saveTimer = null

const formData = reactive({
  status_code: 200,
  content_type: 'application/json',
  response_mode: 'static',
  response_body: '{}',
  delay_ms: 0,
  scenario: 'default',
})

const hasRule = computed(() => !!mockStore.getMockRule(props.interfaceId))
const mockEnabled = computed(() => {
  const rule = mockStore.getMockRule(props.interfaceId)
  return rule?.enabled ?? false
})

const responseBodyPlaceholder = computed(() => {
  if (formData.response_mode === 'echo') {
    return t('回显模式：响应体将替换为请求体内容\n若请求无 body，则使用此处内容作为兜底')
  }
  if (formData.response_mode === 'template') {
    return t('模板模式：支持 {{vars.key}} 变量替换\n例如: { "order_id": "{{vars.order_id}}" }')
  }
  return '{\n  "code": 0,\n  "message": "ok",\n  "data": {}\n}'
})

// 加载 Mock 规则
async function loadRule() {
  if (!props.interfaceId) return
  const rule = await mockStore.loadMockRule(props.interfaceId)
  if (rule) {
    formData.status_code = rule.status_code
    formData.content_type = rule.content_type || 'application/json'
    formData.response_mode = rule.response_mode || 'static'
    formData.response_body = rule.response_body || '{}'
    formData.delay_ms = rule.delay_ms || 0
    formData.scenario = rule.scenario || 'default'
  } else {
    // 重置为默认值
    formData.status_code = 200
    formData.content_type = 'application/json'
    formData.response_mode = 'static'
    formData.response_body = '{}'
    formData.delay_ms = 0
    formData.scenario = 'default'
  }
}

// 切换启用/禁用
async function handleToggle() {
  if (!hasRule.value) {
    // 尚未创建规则，先创建再启用
    saving.value = true
    try {
      await mockStore.saveMockRule({
        interface: props.interfaceId,
        enabled: true,
        ...formData,
      })
      message.success(t('Mock 规则已创建并启用'))
    } catch {
      // error handled in request interceptor
    } finally {
      saving.value = false
    }
  } else {
    saving.value = true
    try {
      await mockStore.toggleMock(props.interfaceId)
    } finally {
      saving.value = false
    }
  }
}

// 自动保存（防抖 600ms）
function scheduleAutoSave() {
  if (!props.interfaceId || !hasRule.value) return
  dirty.value = true
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => doAutoSave(), 600)
}

async function doAutoSave() {
  if (!props.interfaceId) return
  saving.value = true
  try {
    const rule = mockStore.getMockRule(props.interfaceId)
    await mockStore.saveMockRule({
      id: rule?.id,
      interface: props.interfaceId,
      ...formData,
      enabled: rule?.enabled ?? true,
    })
    dirty.value = false
  } catch {
    // error handled in request interceptor
  } finally {
    saving.value = false
  }
}

// 监听表单字段变化，自动保存
watch(
  () => ({
    status_code: formData.status_code,
    content_type: formData.content_type,
    response_mode: formData.response_mode,
    response_body: formData.response_body,
    delay_ms: formData.delay_ms,
    scenario: formData.scenario,
  }),
  () => {
    // 规则存在且已启用时才自动保存
    if (hasRule.value && mockEnabled.value) {
      scheduleAutoSave()
    }
  },
  { deep: true },
)

// 接口切换时重新加载
watch(() => props.interfaceId, (newId) => {
  if (newId) {
    clearTimeout(saveTimer)
    dirty.value = false
    loadRule()
  }
}, { immediate: true })
// 删除规则
async function handleDelete() {
  saving.value = true
  try {
    await mockStore.deleteMockRule(props.interfaceId)
    // 重置表单
    formData.status_code = 200
    formData.content_type = 'application/json'
    formData.response_mode = 'static'
    formData.response_body = '{}'
    formData.delay_ms = 0
    formData.scenario = 'default'
    message.success(t('Mock 规则已删除'))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.mock-panel {
  padding: 4px 0;
}

.mock-placeholder {
  padding: 32px 0;
}

.mock-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.mock-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mock-status {
  font-size: 13px;
  color: #8c8c8c;
}

.mock-status.active {
  color: #52c41a;
  font-weight: 500;
}

.mock-form {
  max-width: 560px;
}

.response-body-editor {
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
}

.delay-value {
  display: inline-block;
  margin-left: 8px;
  font-size: 12px;
  color: #8c8c8c;
}

.mock-actions {
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
  min-height: 32px;
  display: flex;
  align-items: center;
}

.saving-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #faad14;
}

.saved-hint {
  font-size: 12px;
  color: #52c41a;
}
</style>
