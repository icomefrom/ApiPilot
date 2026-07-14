<template>
  <a-modal
    v-model:open="visible"
    title="导入 OpenAPI / Swagger"
    width="680px"
    @ok="handleImport"
    @cancel="handleClose"
    :confirmLoading="importing"
    okText="导入"
  >
    <div class="import-hint">
      <a-alert type="info" show-icon>
        <template #message>
          支持 OpenAPI 3.0/3.1 和 Swagger 2.0 规范。tags 会自动映射为接口分组，securitySchemes 会映射为环境认证配置。
        </template>
      </a-alert>
    </div>

    <div class="import-tabs">
      <a-radio-group v-model:value="importMode" style="margin-bottom: 12px">
        <a-radio-button value="file">上传文件</a-radio-button>
        <a-radio-button value="paste">粘贴内容</a-radio-button>
      </a-radio-group>

      <!-- 文件上传模式 -->
      <div v-if="importMode === 'file'" class="upload-area">
        <a-upload-dragger
          :beforeUpload="handleFileSelect"
          :showUploadList="false"
          accept=".json,.yaml,.yml"
        >
          <p class="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p class="ant-upload-text">点击或拖拽 OpenAPI/Swagger 文件到此处</p>
          <p class="ant-upload-hint">支持 .json / .yaml / .yml 格式</p>
        </a-upload-dragger>
        <div v-if="fileName" class="file-info">
          <CheckCircleOutlined style="color: #52c41a" />
          <span>{{ fileName }}</span>
        </div>
      </div>

      <!-- 粘贴内容模式 -->
      <div v-else class="paste-area">
        <a-textarea
          v-model:value="specText"
          placeholder="将 OpenAPI / Swagger JSON 或 YAML 粘贴到此处..."
          :auto-size="{ minRows: 10, maxRows: 20 }"
          class="spec-editor"
        />
      </div>
    </div>

    <!-- 导入结果 -->
    <div v-if="importResult" class="import-result">
      <a-alert type="success" show-icon>
        <template #message>导入成功</template>
        <template #description>
          <div>
            规范名称：<strong>{{ importResult.spec_title }}</strong>
            <a-tag v-if="importResult.version === 'swagger2'" color="orange">Swagger 2.0</a-tag>
            <a-tag v-else color="blue">OpenAPI 3.x</a-tag>
          </div>
          <div>创建了 {{ importResult.groups_count }} 个分组，{{ importResult.interfaces_count }} 个接口</div>
          <div v-if="importResult.environments?.length" style="margin-top: 4px">
            检测到 base_url：<code>{{ importResult.environments[0].base_url }}</code>
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
import { debugApi } from '../../api/debug'
import { environmentApi } from '../../api/environment'

const emit = defineEmits(['imported'])

const visible = ref(false)
const importing = ref(false)
const importMode = ref('file')
const specText = ref('')
const fileName = ref('')
const specData = ref(null)
const importResult = ref(null)

function open() {
  visible.value = true
  specText.value = ''
  fileName.value = ''
  specData.value = null
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
    const content = e.target.result
    const isYaml = file.name.endsWith('.yaml') || file.name.endsWith('.yml')
    if (isYaml) {
      // YAML 直接传字符串，后端解析
      specData.value = content
    } else {
      try {
        specData.value = JSON.parse(content)
      } catch {
        message.error('JSON 文件解析失败，请检查文件格式')
        fileName.value = ''
        specData.value = null
      }
    }
  }
  reader.readAsText(file)
  return false // prevent auto upload
}

async function handleImport() {
  let data = specData.value

  if (!data && importMode.value === 'paste') {
    if (!specText.value.trim()) {
      message.warning('请粘贴 OpenAPI / Swagger 规范内容')
      return
    }
    data = specText.value
  }

  if (!data) {
    message.warning('请选择文件或粘贴内容')
    return
  }

  importing.value = true
  try {
    const result = await debugApi.importOpenApi(data)
    importResult.value = result
    message.success(`导入成功：${result.interfaces_count} 个接口`)

    // 自动创建环境变量
    if (result.environments?.length) {
      const envData = result.environments[0]
      try {
        await environmentApi.createEnvironment({
          name: envData.name,
          base_url: envData.base_url,
          auth_type: envData.auth_type,
          auth_header: envData.auth_header,
          auth_token: envData.auth_token,
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

.spec-editor {
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
}

.import-result {
  margin-top: 16px;
}
</style>
