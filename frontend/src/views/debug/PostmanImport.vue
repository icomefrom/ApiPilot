<template>
  <a-modal
    v-model:open="visible"
    title="导入 Postman Collection"
    width="640px"
    @ok="handleImport"
    @cancel="handleClose"
    :confirmLoading="importing"
    okText="导入"
  >
    <div class="import-hint">
      <a-alert type="info" show-icon>
        <template #message>
          支持 Postman Collection v2.1 格式。在 Postman 中：Collection → 右键 → Export → Collection v2.1 (推荐)。
          Postman 变量 <code v-pre>{{variable}}</code> 会自动转换为 <code v-pre>{{env.variable}}</code> 格式。
        </template>
      </a-alert>
    </div>

    <div class="import-tabs">
      <a-radio-group v-model:value="importMode" style="margin-bottom: 12px">
        <a-radio-button value="file">上传文件</a-radio-button>
        <a-radio-button value="paste">粘贴 JSON</a-radio-button>
      </a-radio-group>

      <!-- 文件上传模式 -->
      <div v-if="importMode === 'file'" class="upload-area">
        <a-upload-dragger
          :beforeUpload="handleFileSelect"
          :showUploadList="false"
          accept=".json,.postman_collection.json"
        >
          <p class="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p class="ant-upload-text">点击或拖拽 Postman Collection JSON 文件到此处</p>
          <p class="ant-upload-hint">支持 .json 格式</p>
        </a-upload-dragger>
        <div v-if="fileName" class="file-info">
          <CheckCircleOutlined style="color: #52c41a" />
          <span>{{ fileName }}</span>
        </div>
      </div>

      <!-- 粘贴 JSON 模式 -->
      <div v-else class="paste-area">
        <a-textarea
          v-model:value="jsonText"
          placeholder='将 Postman Collection JSON 粘贴到此处...'
          :auto-size="{ minRows: 10, maxRows: 20 }"
          class="json-editor"
        />
      </div>
    </div>

    <!-- 导入结果 -->
    <div v-if="importResult" class="import-result">
      <a-alert type="success" show-icon>
        <template #message>导入成功</template>
        <template #description>
          <div>
            集合名称：<strong>{{ importResult.collection_name }}</strong>
          </div>
          <div>创建了 {{ importResult.groups_count }} 个分组，{{ importResult.interfaces_count }} 个接口</div>
          <div v-if="importResult.environments?.length" style="margin-top: 4px">
            检测到 {{ importResult.environments[0].variables.length }} 个 Postman 变量，可保存为环境变量
          </div>
        </template>
      </a-alert>
    </div>
  </a-modal>
</template>

<script setup>
import { ref } from 'vue'
import { InboxOutlined, CheckCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useDebugStore } from '../../stores/debug'
import { useEnvironmentStore } from '../../stores/environment'
import { debugApi } from '../../api/debug'
import { environmentApi } from '../../api/environment'

const emit = defineEmits(['imported'])

const visible = ref(false)
const importing = ref(false)
const importMode = ref('file')
const jsonText = ref('')
const fileName = ref('')
const collectionData = ref(null)
const importResult = ref(null)

function open() {
  visible.value = true
  jsonText.value = ''
  fileName.value = ''
  collectionData.value = null
  importResult.value = null
  importMode.value = 'file'
}

function handleClose() {
  visible.value = false
}

function handleFileSelect(file) {
  fileName.value = file.name
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      collectionData.value = JSON.parse(e.target.result)
    } catch {
      message.error('JSON 文件解析失败，请检查文件格式')
      fileName.value = ''
      collectionData.value = null
    }
  }
  reader.readAsText(file)
  return false // prevent auto upload
}

async function handleImport() {
  let data = collectionData.value

  if (!data && importMode.value === 'paste') {
    if (!jsonText.value.trim()) {
      message.warning('请粘贴 Postman Collection JSON')
      return
    }
    try {
      data = JSON.parse(jsonText.value)
    } catch {
      message.error('JSON 解析失败，请检查格式')
      return
    }
  }

  if (!data) {
    message.warning('请选择文件或粘贴 JSON')
    return
  }

  importing.value = true
  try {
    const result = await debugApi.importPostman(data)
    importResult.value = result
    message.success(`导入成功：${result.interfaces_count} 个接口`)

    // 如果有 Postman 变量，提示保存为环境变量
    if (result.environments?.length) {
      const envData = result.environments[0]
      try {
        await environmentApi.createEnvironment({
          name: envData.name,
          variables: envData.variables,
        })
        message.info(`已自动创建环境变量：${envData.name}`)
      } catch {
        // 创建环境变量失败不影响主流程
      }
    }

    emit('imported', result)
  } catch (e) {
    // error handled by interceptor
  } finally {
    importing.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.import-hint {
  margin-bottom: 16px;
}

.import-hint code {
  background: #f5f5f5;
  padding: 1px 4px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 12px;
}

.upload-area {
  min-height: 120px;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  color: #52c41a;
  font-size: 13px;
}

.json-editor {
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
}

.import-result {
  margin-top: 16px;
}
</style>