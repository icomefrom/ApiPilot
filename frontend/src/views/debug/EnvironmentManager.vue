<template>
  <a-modal
    v-model:open="visible"
    title="环境管理"
    width="800px"
    :footer="null"
    @cancel="handleClose"
  >
    <div class="env-manager">
      <div class="env-sidebar">
        <div class="env-sidebar-header">
          <span>环境列表</span>
          <a-button type="link" size="small" @click="handleAdd">
            <PlusOutlined /> 新建
          </a-button>
        </div>
        <div class="env-list">
          <div
            v-for="env in environmentStore.environments"
            :key="env.id"
            class="env-item"
            :class="{ active: editingEnv?.id === env.id }"
            @click="handleSelectEnv(env)"
          >
            <span class="env-name">{{ env.name }}</span>
            <a-popconfirm
              title="确定删除此环境？"
              @confirm="handleDelete(env.id)"
            >
              <DeleteOutlined class="env-delete" />
            </a-popconfirm>
          </div>
          <a-empty v-if="!environmentStore.environments.length" description="暂无环境" />
        </div>
      </div>
      <div class="env-editor">
        <template v-if="editingEnv">
          <div class="env-editor-header">
            <a-input
              v-model:value="editingEnv.name"
              placeholder="环境名称（如：开发环境、测试环境、生产环境）"
              style="flex: 1"
            />
          </div>
          <div class="env-section">
            <div class="env-section-title">基础地址</div>
            <a-form layout="vertical" class="env-form">
              <a-form-item label="HTTP Base URL">
                <a-input v-model:value="editingEnv.base_url" placeholder="例如：https://api.test.com；接口可填写 /users" />
              </a-form-item>
              <a-form-item label="WebSocket Base URL">
                <a-input v-model:value="editingEnv.ws_base_url" placeholder="例如：wss://ws.test.com；可不填" />
              </a-form-item>
              <a-form-item label="RPC Base URL">
                <a-input v-model:value="editingEnv.rpc_base_url" placeholder="例如：https://rpc.test.com；不填时回退 HTTP Base URL" />
              </a-form-item>
            </a-form>
          </div>

          <div class="env-section">
            <div class="env-section-title">认证</div>
            <a-form layout="vertical" class="env-form">
              <a-form-item label="认证类型">
                <a-select v-model:value="editingEnv.auth_type">
                  <a-select-option value="none">无认证</a-select-option>
                  <a-select-option value="bearer">Bearer Token</a-select-option>
                  <a-select-option value="api_key">API Key</a-select-option>
                  <a-select-option value="basic">Basic Auth</a-select-option>
                  <a-select-option value="custom">自定义 Header</a-select-option>
                </a-select>
              </a-form-item>
              <template v-if="editingEnv.auth_type !== 'none'">
                <a-form-item label="Header 名">
                  <a-input v-model:value="editingEnv.auth_header" placeholder="例如：Authorization / authentication / X-API-Key" />
                </a-form-item>
                <template v-if="editingEnv.auth_type === 'basic'">
                  <a-form-item label="用户名">
                    <a-input v-model:value="editingEnv.auth_username" placeholder="Basic 用户名" />
                  </a-form-item>
                  <a-form-item label="密码">
                    <a-input-password v-model:value="editingEnv.auth_password" placeholder="留空或保持 ****** 表示不修改" />
                  </a-form-item>
                </template>
                <a-form-item v-else label="Token / 值">
                  <a-input-password v-model:value="editingEnv.auth_token" placeholder="留空或保持 ****** 表示不修改" />
                </a-form-item>
              </template>
            </a-form>
          </div>

          <div class="env-section env-vars">
            <div class="env-vars-header">
              <span>自定义变量</span>
              <a-button type="link" size="small" @click="addVariable">
                <PlusOutlined /> 添加
              </a-button>
            </div>
            <a-table
              :dataSource="editingEnv.variables"
              :columns="varColumns"
              :pagination="false"
              size="small"
              rowKey="_idx"
            >
              <template #bodyCell="{ column, record, index }">
                <template v-if="column.key === 'key'">
                  <a-input
                    v-model:value="record.key"
                    placeholder="变量名"
                    size="small"
                  />
                </template>
                <template v-if="column.key === 'value'">
                  <a-input
                    v-model:value="record.value"
                    placeholder="变量值"
                    size="small"
                  />
                </template>
                <template v-if="column.key === 'action'">
                  <a-button
                    type="link"
                    danger
                    size="small"
                    @click="removeVariable(index)"
                  >
                    <DeleteOutlined />
                  </a-button>
                </template>
              </template>
            </a-table>
          </div>
          <div class="env-editor-footer">
            <a-button @click="handleClose">取消</a-button>
            <a-button type="primary" :loading="saving" @click="handleSave">保存</a-button>
          </div>
        </template>
        <a-empty v-else description="选择或新建一个环境" />
      </div>
    </div>
  </a-modal>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useEnvironmentStore } from '../../stores/environment'

const emit = defineEmits(['close'])

const environmentStore = useEnvironmentStore()
const visible = ref(false)
const editingEnv = ref(null)
const saving = ref(false)

const varColumns = [
  { title: '变量名', key: 'key', width: '35%' },
  { title: '变量值', key: 'value', width: '55%' },
  { title: '操作', key: 'action', width: '10%', align: 'center' },
]

function open() {
  visible.value = true
  editingEnv.value = null
  environmentStore.fetchEnvironments()
}

function handleClose() {
  visible.value = false
  editingEnv.value = null
  emit('close')
}

function createEditableEnv(env = {}) {
  return reactive({
    id: env.id || null,
    name: env.name || '',
    base_url: env.base_url || '',
    ws_base_url: env.ws_base_url || '',
    rpc_base_url: env.rpc_base_url || '',
    auth_type: env.auth_type || 'none',
    auth_header: env.auth_header || 'Authorization',
    auth_token: env.auth_token_masked || '',
    auth_username: env.auth_username || '',
    auth_password: env.auth_password_masked || '',
    variables: (env.variables || []).map((v, i) => ({ ...v, _idx: i })),
  })
}

function handleAdd() {
  editingEnv.value = createEditableEnv({
    variables: [{ key: 'tenant_id', value: '', _idx: 0 }],
  })
}

function handleSelectEnv(env) {
  editingEnv.value = createEditableEnv(env)
}

function addVariable() {
  if (!editingEnv.value) return
  const vars = editingEnv.value.variables
  vars.push({ key: '', value: '', _idx: vars.length })
}

function removeVariable(index) {
  if (!editingEnv.value) return
  editingEnv.value.variables.splice(index, 1)
}

async function handleSave() {
  if (!editingEnv.value) return
  if (!editingEnv.value.name.trim()) {
    message.warning('请输入环境名称')
    return
  }

  saving.value = true
  try {
    // 清理 _idx 字段
    const data = {
      id: editingEnv.value.id,
      name: editingEnv.value.name.trim(),
      base_url: editingEnv.value.base_url || '',
      ws_base_url: editingEnv.value.ws_base_url || '',
      rpc_base_url: editingEnv.value.rpc_base_url || '',
      auth_type: editingEnv.value.auth_type || 'none',
      auth_header: editingEnv.value.auth_header || 'Authorization',
      auth_token: editingEnv.value.auth_token || '',
      auth_username: editingEnv.value.auth_username || '',
      auth_password: editingEnv.value.auth_password || '',
      variables: editingEnv.value.variables
        .filter(v => v.key.trim())
        .map(v => ({ key: v.key.trim(), value: v.value || '' })),
    }
    await environmentStore.saveEnvironment(data)
    await environmentStore.fetchEnvironments()
    message.success('保存成功')
    handleClose()
  } catch (e) {
    // error handled by interceptor
  } finally {
    saving.value = false
  }
}

async function handleDelete(id) {
  try {
    await environmentStore.deleteEnvironment(id)
    if (editingEnv.value?.id === id) {
      editingEnv.value = null
    }
    message.success('删除成功')
  } catch (e) {
    // error handled by interceptor
  }
}

defineExpose({ open })
</script>

<style scoped>
.env-manager {
  display: flex;
  min-height: 400px;
  border: 1px solid #f0f0f0;
  border-radius: 4px;
}

.env-sidebar {
  width: 200px;
  border-right: 1px solid #f0f0f0;
  display: flex;
  flex-direction: column;
}

.env-sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-bottom: 1px solid #f0f0f0;
  font-weight: 500;
}

.env-list {
  flex: 1;
  overflow-y: auto;
}

.env-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.2s;
}

.env-item:hover {
  background: #f5f5f5;
}

.env-item.active {
  background: #e6f7ff;
  border-right: 2px solid #1890ff;
}

.env-name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.env-delete {
  color: #999;
  font-size: 12px;
  display: none;
}

.env-item:hover .env-delete {
  display: inline-block;
}

.env-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px;
}

.env-editor-header {
  margin-bottom: 16px;
}

.env-section {
  margin-top: 12px;
}

.env-section-title {
  margin-bottom: 8px;
  font-weight: 500;
  color: #262626;
}

.env-form :deep(.ant-form-item) {
  margin-bottom: 8px;
}

.env-vars {
  flex: 1;
  overflow-y: auto;
}

.env-vars-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 500;
}

.env-editor-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}
</style>