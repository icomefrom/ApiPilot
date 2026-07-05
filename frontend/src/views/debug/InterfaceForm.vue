<template>
  <div class="interface-form">
    <!-- 顶部：协议选择 + 方法 + URL + 发送 -->
    <div class="request-bar">
      <a-radio-group v-model:value="store.currentInterface.protocol" size="small" @change="onProtocolChange" class="protocol-radio">
        <a-radio-button value="http">HTTP</a-radio-button>
        <a-radio-button value="websocket">WebSocket</a-radio-button>
        <a-radio-button value="rpc">RPC</a-radio-button>
      </a-radio-group>

      <a-select
        v-if="store.currentInterface.protocol === 'http'"
        v-model:value="store.currentInterface.method"
        style="width: 100px"
        size="large"
      >
        <a-select-option v-for="m in ['GET','POST','PUT','DELETE','PATCH','HEAD','OPTIONS']" :key="m" :value="m">
          <span :style="{ color: methodColor(m), fontWeight: 600 }">{{ m }}</span>
        </a-select-option>
      </a-select>

      <a-input
        v-model:value="store.currentInterface.url"
        :placeholder="urlPlaceholder"
        size="large"
        class="url-input"
        @pressEnter="handleSend"
      />

      <a-button v-if="store.currentInterface.protocol === 'http'" size="large" @click="$emit('importCurl')" class="import-btn">
        <ImportOutlined /> 导入cURL
      </a-button>

      <a-button type="primary" size="large" :loading="store.executing" @click="handleSend" class="send-btn">
        发送
      </a-button>
    </div>

    <!-- Tab 面板 -->
    <a-tabs v-model:activeKey="activeTab" size="small" class="request-tabs">
      <!-- 参数 Tab -->
      <a-tab-pane key="params" tab="Params">
        <KeyValuePair v-model:data="store.currentInterface.query_params" />
      </a-tab-pane>

      <!-- 请求头 Tab -->
      <a-tab-pane key="headers" tab="Headers">
        <KeyValuePair v-model:data="store.currentInterface.headers" />
      </a-tab-pane>

      <!-- Body Tab (仅 HTTP) -->
      <a-tab-pane v-if="store.currentInterface.protocol === 'http'" key="body" tab="Body">
        <div class="body-type-select">
          <a-radio-group v-model:value="store.currentInterface.body_type" size="small">
            <a-radio-button value="none">none</a-radio-button>
            <a-radio-button value="json">JSON</a-radio-button>
            <a-radio-button value="form">Form</a-radio-button>
            <a-radio-button value="raw">Raw</a-radio-button>
            <a-radio-button value="xml">XML</a-radio-button>
          </a-radio-group>
        </div>
        <div v-if="store.currentInterface.body_type === 'form'">
          <KeyValuePair v-model:data="formData" />
        </div>
        <a-textarea
          v-else-if="store.currentInterface.body_type !== 'none'"
          v-model:value="store.currentInterface.body"
          :placeholder="bodyPlaceholder"
          :auto-size="{ minRows: 6, maxRows: 16 }"
          class="body-editor"
        />
      </a-tab-pane>

      <!-- WebSocket 消息 Tab -->
      <a-tab-pane v-if="store.currentInterface.protocol === 'websocket'" key="ws" tab="消息">
        <a-textarea
          v-model:value="store.currentInterface.ws_message"
          placeholder="输入要发送的消息内容"
          :auto-size="{ minRows: 6, maxRows: 16 }"
          class="body-editor"
        />
      </a-tab-pane>

      <!-- RPC Tab -->
      <a-tab-pane v-if="store.currentInterface.protocol === 'rpc'" key="rpc" tab="RPC">
        <a-form layout="vertical">
          <a-form-item label="服务名">
            <a-input v-model:value="store.currentInterface.rpc_service" placeholder="RPC 服务名 (可选)" />
          </a-form-item>
          <a-form-item label="方法名">
            <a-input v-model:value="store.currentInterface.rpc_method" placeholder="RPC 方法名" />
          </a-form-item>
          <a-form-item label="参数 (JSON)">
            <a-textarea
              v-model:value="store.currentInterface.body"
              placeholder='例如: [1, 2, 3] 或 {"key": "value"}'
              :auto-size="{ minRows: 4, maxRows: 12 }"
              class="body-editor"
            />
          </a-form-item>
        </a-form>
      </a-tab-pane>
    </a-tabs>

    <!-- 保存按钮 -->
    <div class="save-bar">
      <a-input
        v-model:value="store.currentInterface.name"
        placeholder="接口名称（保存时使用）"
        style="width: 260px; margin-right: 8px;"
        size="small"
      />
      <a-select
        v-model:value="selectedGroupValue"
        placeholder="选择分组"
        style="width: 140px; margin-right: 8px;"
        size="small"
      >
        <a-select-option :value="DEFAULT_GROUP_VALUE">
          默认分组
        </a-select-option>
        <a-select-option v-for="g in store.groups" :key="g.id" :value="g.id">
          {{ g.name }}
        </a-select-option>
      </a-select>
      <a-button size="small" @click="handleSave" :loading="saving">
        {{ store.currentInterface.id ? '更新' : '保存' }}
      </a-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { ImportOutlined } from '@ant-design/icons-vue'
import { useDebugStore } from '../../stores/debug'
import { useEnvironmentStore } from '../../stores/environment'
import KeyValuePair from './KeyValuePair.vue'

const emit = defineEmits(['saved', 'importCurl'])
const store = useDebugStore()
const envStore = useEnvironmentStore()

const activeTab = ref('params')
const formData = ref({})
const saving = ref(false)
const DEFAULT_GROUP_VALUE = '__default__'

const selectedGroupValue = computed({
  get() {
    return store.currentInterface.group ?? DEFAULT_GROUP_VALUE
  },
  set(value) {
    store.currentInterface.group = value === DEFAULT_GROUP_VALUE ? null : value
  },
})

const urlPlaceholder = computed(() => {
  if (store.currentInterface.protocol === 'websocket') return 'ws:// 或 wss:// 地址'
  if (store.currentInterface.protocol === 'rpc') return 'RPC 服务地址 (HTTP)'
  return 'https://api.example.com/path'
})

const bodyPlaceholder = computed(() => {
  const t = store.currentInterface.body_type
  if (t === 'json') return '{\n  "key": "value"\n}'
  if (t === 'xml') return '<root>\n  <item>value</item>\n</root>'
  return '请求体内容'
})

function methodColor(m) {
  const colors = { GET: '#52c41a', POST: '#1890ff', PUT: '#faad14', DELETE: '#ff4d4f', PATCH: '#722ed1', HEAD: '#8c8c8c', OPTIONS: '#8c8c8c' }
  return colors[m] || '#1890ff'
}

function onProtocolChange() {
  if (store.currentInterface.protocol === 'http') {
    activeTab.value = 'params'
  } else if (store.currentInterface.protocol === 'websocket') {
    activeTab.value = 'ws'
  } else {
    activeTab.value = 'rpc'
  }
}

async function handleSend() {
  if (!store.currentInterface.url) {
    message.warning('请输入请求地址')
    return
  }
  // 传完整接口对象，已保存的接口走 executeSaved，结果的 interface_id 不为空
  const itf = { ...store.currentInterface }
  if (itf.body_type === 'form') {
    itf.body = JSON.stringify(formData.value)
  }
  await store.executeInterface(itf, envStore.activeEnvironmentId)
}

async function handleSave() {
  if (!store.currentInterface.url) {
    message.warning('请输入请求地址')
    return
  }
  if (!store.currentInterface.name) {
    store.currentInterface.name = `${store.currentInterface.method} ${store.currentInterface.url}`.substring(0, 200)
  }
  saving.value = true
  try {
    const payload = {
      ...store.currentInterface,
      body: store.currentInterface.body_type === 'form' ? JSON.stringify(formData.value) : store.currentInterface.body,
    }
    await store.saveInterface(payload)
    message.success(store.currentInterface.id ? '更新成功' : '保存成功')
    emit('saved')
  } catch {
    // 错误已在拦截器处理
  } finally {
    saving.value = false
  }
}

function handleNew() {
  store.resetCurrent()
  formData.value = {}
  activeTab.value = 'params'
}

// 同步 form data
watch(() => store.currentInterface.body_type, (val) => {
  if (val === 'form') {
    try {
      formData.value = JSON.parse(store.currentInterface.body || '{}')
    } catch {
      formData.value = {}
    }
  }
})

watch(() => store.currentInterface.id, () => {
  if (store.currentInterface.body_type === 'form') {
    try {
      formData.value = JSON.parse(store.currentInterface.body || '{}')
    } catch {
      formData.value = {}
    }
  }
})
</script>

<style scoped>
.interface-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.request-bar {
  display: flex;
  gap: 8px;
  align-items: center;
}

.protocol-radio {
  flex-shrink: 0;
}

.url-input {
  flex: 1;
  font-family: monospace;
}

.send-btn {
  flex-shrink: 0;
}

.import-btn {
  flex-shrink: 0;
}

.request-tabs {
  min-height: 200px;
}

.body-type-select {
  margin-bottom: 12px;
}

.body-editor {
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
}

.save-bar {
  display: flex;
  align-items: center;
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
}
</style>
