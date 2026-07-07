<template>
  <div class="response-viewer" v-if="result">
    <!-- 错误提示 -->
    <a-alert
      v-if="result.error_message"
      :message="result.error_message"
      type="error"
      show-icon
      style="margin-bottom: 12px"
    />
    <!-- 状态栏 -->
    <div class="response-status-bar">
      <span :class="['status-badge', statusClass]">{{ statusText }}</span>
      <span class="meta-item" v-if="result.elapsed_ms != null">
        <ClockCircleOutlined /> {{ result.elapsed_ms }}ms
      </span>
      <span class="meta-item" v-if="bodySize">
        <FileTextOutlined /> {{ bodySize }}
      </span>
    </div>

    <!-- 响应内容 -->
    <a-tabs v-model:activeKey="activeTab" size="small">
      <a-tab-pane key="body" :tab="t('响应体')">
        <div class="response-body-toolbar">
          <a-radio-group v-model:value="bodyFormat" size="small">
            <a-radio-button value="pretty">{{ t('格式化') }}</a-radio-button>
            <a-radio-button value="raw">{{ t('原始') }}</a-radio-button>
          </a-radio-group>
          <a-button size="small" @click="copyBody">
            <CopyOutlined /> {{ t('复制') }}
          </a-button>
        </div>
        <pre class="response-body-content" :class="{ 'json-content': bodyFormat === 'pretty' && isJson }">{{ displayBody }}</pre>
      </a-tab-pane>
      <a-tab-pane key="headers" :tab="t('响应头')">
        <a-table
          :dataSource="headerRows"
          :columns="headerColumns"
          :pagination="false"
          size="small"
          rowKey="key"
        />
      </a-tab-pane>
    </a-tabs>
  </div>
  <div v-else class="response-empty">
    <a-empty :description="t('点击 发送 按钮查看响应结果')" />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ClockCircleOutlined, FileTextOutlined, CopyOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { t } from '../../i18n'

const props = defineProps({
  result: { type: Object, default: null },
})

const activeTab = ref('body')
const bodyFormat = ref('pretty')

const statusClass = computed(() => {
  if (!props.result) return ''
  const code = props.result.status_code
  if (!code) return 'status-error'
  if (code < 300) return 'status-success'
  if (code < 400) return 'status-redirect'
  return 'status-error'
})

const statusText = computed(() => {
  if (!props.result) return ''
  if (props.result.status === 'timeout') return 'TIMEOUT'
  if (props.result.status === 'failed') return 'ERROR'
  return props.result.status_code ? `${props.result.status_code}` : 'N/A'
})

const isJson = computed(() => {
  if (!props.result?.response_body) return false
  try {
    JSON.parse(props.result.response_body)
    return true
  } catch {
    return false
  }
})

const displayBody = computed(() => {
  if (!props.result?.response_body) return ''
  if (bodyFormat.value === 'pretty' && isJson.value) {
    try {
      return JSON.stringify(JSON.parse(props.result.response_body), null, 2)
    } catch {
      return props.result.response_body
    }
  }
  return props.result.response_body
})

const bodySize = computed(() => {
  if (!props.result?.response_body) return ''
  const bytes = new Blob([props.result.response_body]).size
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
})

const headerColumns = computed(() => [
  { title: t('键'), dataIndex: 'key', width: '40%' },
  { title: t('值'), dataIndex: 'value' },
])

const headerRows = computed(() => {
  if (!props.result?.response_headers) return []
  return Object.entries(props.result.response_headers).map(([key, value]) => ({
    key,
    value: Array.isArray(value) ? value.join(', ') : String(value),
  }))
})

function copyBody() {
  if (!props.result?.response_body) return
  navigator.clipboard.writeText(displayBody.value)
  message.success(t('已复制到剪贴板'))
}

// 切换结果时重置 tab
watch(() => props.result, () => {
  activeTab.value = 'body'
})
</script>

<style scoped>
.response-viewer {
  margin-top: 16px;
}

.response-status-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #f0f0f0;
}

.status-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 4px;
  font-weight: 600;
  font-size: 13px;
}

.status-success {
  background: #f6ffed;
  color: #52c41a;
  border: 1px solid #b7eb8f;
}

.status-redirect {
  background: #fffbe6;
  color: #faad14;
  border: 1px solid #ffe58f;
}

.status-error {
  background: #fff2f0;
  color: #ff4d4f;
  border: 1px solid #ffccc7;
}

.meta-item {
  color: #8c8c8c;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.response-body-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.response-body-content {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px 16px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
  max-height: 500px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.json-content {
  color: #9cdcfe;
}

.response-empty {
  padding: 60px 0;
}
</style>
