<template>
  <div class="api-debug-page">
    <!-- 左侧面板 -->
    <div class="left-panel">
      <div class="panel-header">
        <span class="panel-title">{{ t('接口列表') }}</span>
        <div class="panel-actions">
          <a-dropdown>
            <template #overlay>
              <a-menu>
                <a-menu-item key="postman" @click="openPostmanImport">
                  导入 Postman Collection
                </a-menu-item>
                <a-menu-item key="openapi" @click="openOpenApiImport">
                  导入 OpenAPI / Swagger
                </a-menu-item>
              </a-menu>
            </template>
            <a-button size="small">
              <ImportOutlined /> {{ t('导入') }}
              <DownOutlined />
            </a-button>
          </a-dropdown>
          <a-button size="small" @click="handleNewGroup">
            <PlusOutlined /> {{ t('新建分组') }}
          </a-button>
        </div>
      </div>
      <InterfaceList />
    </div>

    <!-- 右侧面板 -->
    <div class="right-panel">
      <InterfaceForm ref="interfaceFormRef" @saved="onSaved" @importCurl="openCurlImport" />
      <a-divider style="margin: 8px 0" />
      <div class="response-header">
        <span class="response-title">{{ t('响应结果') }}</span>
        <div class="response-header-actions">
          <a-button size="small" type="link" @click="assertionDrawerVisible = true">
            <SafetyCertificateOutlined /> {{ t('断言校验') }}
            <span v-if="assertionBadge" :class="['assertion-badge', assertionBadge.class]">{{ assertionBadge.text }}</span>
          </a-button>
          <a-button v-if="store.currentResult" size="small" type="link" @click="store.currentResult = null">
            {{ t('清除') }}
          </a-button>
        </div>
      </div>
      <ResponseViewer :result="store.currentResult" />
    </div>

    <!-- cURL 导入弹窗 -->
    <CurlImport ref="curlImportRef" @parsed="onCurlParsed" />

    <!-- Postman 导入弹窗 -->
    <PostmanImport ref="postmanImportRef" @imported="onPostmanImported" />

    <!-- OpenAPI 导入弹窗 -->
    <OpenApiImport ref="openApiImportRef" @imported="onOpenApiImported" />

    <!-- 断言校验抽屉 -->
    <a-drawer
      v-model:open="assertionDrawerVisible"
      :title="t('断言校验')"
      placement="right"
      :width="520"
      :destroyOnClose="false"
    >
      <AssertionPanel :result="store.currentResult" @summary-change="onSummaryChange" />
    </a-drawer>
  </div>
</template>

<script setup>
import { ref, computed, h, onMounted, onBeforeUnmount } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { PlusOutlined, ImportOutlined, SafetyCertificateOutlined, DownOutlined } from '@ant-design/icons-vue'
import { useDebugStore } from '../../stores/debug'
import InterfaceList from './InterfaceList.vue'
import InterfaceForm from './InterfaceForm.vue'
import CurlImport from './CurlImport.vue'
import PostmanImport from './PostmanImport.vue'
import OpenApiImport from './OpenApiImport.vue'
import ResponseViewer from './ResponseViewer.vue'
import AssertionPanel from './AssertionPanel.vue'
import { t } from '../../i18n'

const store = useDebugStore()
const curlImportRef = ref(null)
const postmanImportRef = ref(null)
const openApiImportRef = ref(null)
const interfaceFormRef = ref(null)
const assertionDrawerVisible = ref(false)
const assertionSummary = ref({ total: 0, pass: 0, fail: 0 })
const newGroupName = ref('')

// 断言摘要角标
const assertionBadge = computed(() => {
  if (assertionSummary.value.total === 0) return null
  if (assertionSummary.value.fail > 0) return { text: `${assertionSummary.value.fail} ${t('失败')}`, class: 'badge-fail' }
  return { text: `${assertionSummary.value.pass} ${t('通过')}`, class: 'badge-pass' }
})

function onSummaryChange(stats) {
  assertionSummary.value = stats
}

function openCurlImport() {
  curlImportRef.value?.open()
}

function onCurlParsed() {
  // cURL 解析后，form 已自动填充
}

function openPostmanImport() {
  postmanImportRef.value?.open()
}

function openOpenApiImport() {
  openApiImportRef.value?.open()
}

function onPostmanImported() {
  store.fetchInterfaces()
  store.fetchGroups()
}

function onOpenApiImported() {
  store.fetchInterfaces()
  store.fetchGroups()
}

function handleNewGroup() {
  newGroupName.value = ''
  Modal.confirm({
    title: t('新建分组'),
    content: () => h('input', {
      value: newGroupName.value,
      class: 'ant-input',
      style: 'margin-top:8px',
      placeholder: t('输入分组名称'),
      onInput: (e) => { newGroupName.value = e.target.value },
    }),
    async onOk() {
      const name = newGroupName.value.trim()
      if (!name) {
        message.warning(t('分组名称不能为空'))
        return
      }
      try {
        const result = await store.saveGroup({ name })
        await store.fetchGroups()
        store.fetchInterfaces()
        message.success(t('分组创建成功'))
        // 通知 InterfaceList 展开新分组
        window.dispatchEvent(new CustomEvent('group-created', { detail: result.id }))
      } catch {
        // 全局拦截器已弹错误提示
      }
    },
  })
}

function handleProjectChanged() {
  store.resetCurrent()
  store.currentResult = null
  store.fetchGroups()
  store.fetchInterfaces()
}

onMounted(() => {
  window.addEventListener('project-changed', handleProjectChanged)
})

onBeforeUnmount(() => {
  window.removeEventListener('project-changed', handleProjectChanged)
})

function onSaved() {
  store.fetchInterfaces()
}
</script>

<style scoped>
.api-debug-page {
  display: flex;
  gap: 16px;
  height: calc(100vh - 152px);
  min-height: 400px;
}

.left-panel {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  background: #fafafa;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.panel-title {
  font-weight: 600;
  font-size: 14px;
  color: #262626;
}

.panel-actions {
  display: flex;
  gap: 4px;
}

.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 16px;
  background: #fff;
  overflow-y: auto;
}

.response-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.response-header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.response-title {
  font-weight: 600;
  font-size: 14px;
  color: #262626;
}

.assertion-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 500;
  padding: 0 6px;
  border-radius: 8px;
  margin-left: 4px;
  line-height: 18px;
}

.assertion-badge.badge-pass {
  background: #f6ffed;
  color: #52c41a;
}

.assertion-badge.badge-fail {
  background: #fff2f0;
  color: #ff4d4f;
}
</style>
