<template>
  <div class="chain-test-page">
    <!-- 左侧面板 -->
    <div class="chain-sidebar-wrap">
      <ChainSidebar ref="sidebarRef" />
    </div>

    <!-- 中间画布 -->
    <div class="chain-canvas-wrap">
      <div class="canvas-toolbar">
        <a-input
          v-model:value="store.currentChain.name"
          :placeholder="t('链路名称')"
          style="width: 200px"
          size="small"
        />
        <div class="toolbar-actions">
          <span class="active-env">{{ t('环境：') }} {{ translateText(envStore.activeEnvName) }}</span>
          <a-button size="small" @click="showGlobalsModal = true">
            <SettingOutlined /> {{ t('全局参数') }}
          </a-button>
          <a-button
            type="primary"
            size="small"
            :loading="store.executing"
            :disabled="!store.currentChain.id"
            @click="handleRun"
          >
            <PlayCircleOutlined /> {{ t('运行') }}
          </a-button>
          <a-button size="small" :disabled="!store.currentChain.id" @click="handleSave">
            <SaveOutlined /> {{ t('保存') }}
          </a-button>
        </div>
      </div>

      <div class="canvas-body">
        <ChainEditor
          ref="editorRef"
          :nodes="store.currentChain.nodes"
          :edges="store.currentChain.edges"
          :result="store.currentResult"
          :placement-type="placementType"
          @update:nodes="handleNodesUpdate"
          @update:edges="handleEdgesUpdate"
          @node-click="handleNodeClick"
          @placement-done="handlePlacementDone"
        />
      </div>
    </div>

    <!-- 右侧节点属性抽屉 -->
    <NodePanel
      :visible="nodePanelVisible"
      :node="selectedNode"
      :chain-result="store.currentResult"
      :globals="store.currentChain.globals"
      :nodes="store.currentChain.nodes"
      @update:visible="nodePanelVisible = $event"
      @change="dirty = true"
    />

    <!-- 全局参数 Modal -->
    <a-modal
      v-model:open="showGlobalsModal"
      :title="t('全局参数')"
      @ok="showGlobalsModal = false"
      @cancel="showGlobalsModal = false"
      :width="600"
    >
      <div class="globals-editor">
        <div v-for="(g, idx) in store.currentChain.globals" :key="idx" class="global-item">
          <a-input v-model:value="g.key" :placeholder="t('参数名')" style="width: 30%" />
          <a-input v-model:value="g.value" :placeholder="t('参数值')" style="flex: 1" />
          <a-input v-model:value="g.description" :placeholder="t('说明')" style="width: 25%" />
          <a-button type="text" danger size="small" @click="removeGlobal(idx)"><DeleteOutlined /></a-button>
        </div>
        <a-button type="dashed" block size="small" @click="addGlobal">
          <PlusOutlined /> {{ t('添加参数') }}
        </a-button>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  PlayCircleOutlined,
  SaveOutlined,
  SettingOutlined,
  PlusOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue'
import { useChainStore } from '../../stores/chain'
import { useEnvironmentStore } from '../../stores/environment'
import { useDebugStore } from '../../stores/debug'
import ChainSidebar from './ChainSidebar.vue'
import ChainEditor from './ChainEditor.vue'
import NodePanel from './NodePanel.vue'
import { t, translateText } from '../../i18n'

const store = useChainStore()
const envStore = useEnvironmentStore()
const debugStore = useDebugStore()
const route = useRoute()

const sidebarRef = ref(null)
const editorRef = ref(null)
const nodePanelVisible = ref(false)
const selectedNode = ref(null)
const showGlobalsModal = ref(false)
const dirty = ref(false)

// 放置模式：从侧边栏选中的节点类型
const placementType = computed(() => sidebarRef.value?.selectedNodeType?.value || null)

// 放置完成 → 清除选中状态
function handlePlacementDone() {
  if (sidebarRef.value?.selectedNodeType) {
    sidebarRef.value.selectedNodeType.value = null
  }
}

function handleNodeClick(node) {
  if (!node) {
    selectedNode.value = null
    nodePanelVisible.value = false
    return
  }
  // 使用 store 中的 node 而非 VueFlow GraphNode / ChainEditor flowNode，
  // store.currentChain 是 reactive()，对 node.data 的修改直接即时生效，
  // 不依赖 flowNodes 的 deep watcher → syncToStore 链路
  const storeNode = store.currentChain.nodes.find(n => n.id === node.id)
  selectedNode.value = storeNode || node
  nodePanelVisible.value = true
}

// ChainEditor syncToStore 回传的节点变化，以合并方式同步到 store，
// 而非整体替换数组，以保留 selectedNode / NodePanel 所持有的响应式引用。
// 仅同步 position、type（画布拖拽产生的变化）；data 由 store 侧（NodePanel）为唯一数据源。
function handleNodesUpdate(newNodes) {
  const current = store.currentChain.nodes
  for (const newNode of newNodes) {
    const existing = current.find(n => n.id === newNode.id)
    if (existing) {
      existing.position = newNode.position
      existing.type = newNode.type
    } else {
      current.push(newNode)
    }
  }
  for (let i = current.length - 1; i >= 0; i--) {
    if (!newNodes.some(n => n.id === current[i].id)) {
      current.splice(i, 1)
    }
  }
  dirty.value = true
}

function handleEdgesUpdate(newEdges) {
  store.currentChain.edges = newEdges
  dirty.value = true
}

function validateBoundaryNodes() {
  const nodes = store.currentChain.nodes
  const edges = store.currentChain.edges
  const startNodes = nodes.filter(n => n.type === 'start')
  const endNodes = nodes.filter(n => n.type === 'end')
  if (startNodes.length !== 1 || endNodes.length !== 1) {
    message.warning(t('链路必须且只能包含一个开始节点和一个结束节点'))
    return false
  }
  // 检查开始节点是否有出边
  const startId = startNodes[0].id
  const hasOutgoing = edges.some(e => e.source === startId)
  if (!hasOutgoing) {
    message.warning(t('开始节点未连接后续节点，请连线后再保存'))
    return false
  }
  // 检查从开始节点能否到达结束节点（BFS）
  const adjacency = {}
  for (const n of nodes) adjacency[n.id] = []
  for (const e of edges) {
    if (adjacency[e.source]) adjacency[e.source].push(e.target)
  }
  const visited = new Set()
  const queue = [startId]
  visited.add(startId)
  while (queue.length) {
    const cur = queue.shift()
    for (const next of adjacency[cur] || []) {
      if (!visited.has(next)) {
        visited.add(next)
        queue.push(next)
      }
    }
  }
  if (!visited.has(endNodes[0].id)) {
    message.warning(t('开始节点无法到达结束节点，请检查连线'))
    return false
  }
  return true
}

function syncEditorSnapshot() {
  const editor = editorRef.value
  if (!editor) return
  if (typeof editor.syncToStoreNow === 'function') {
    editor.syncToStoreNow()
    return
  }
  if (typeof editor.getSerializedNodes === 'function') {
    handleNodesUpdate(editor.getSerializedNodes())
  }
  if (typeof editor.getSerializedEdges === 'function') {
    handleEdgesUpdate(editor.getSerializedEdges())
  }
}

async function handleSave() {
  if (!store.currentChain.id) {
    message.warning(t('请先创建链路'))
    return
  }
  syncEditorSnapshot()
  if (!validateBoundaryNodes()) return false
  try {
    await store.saveChain({
      id: store.currentChain.id,
      name: store.currentChain.name,
      description: store.currentChain.description,
      nodes: store.currentChain.nodes,
      edges: store.currentChain.edges,
      globals: store.currentChain.globals,
      status: 'ready',
    })
    store.currentChain.status = 'ready'
    dirty.value = false
    message.success(t('链路已保存'))
    await store.fetchChains()
    return true
  } catch (e) {
    message.error(t('保存失败'))
    return false
  }
}

async function handleRun() {
  if (!store.currentChain.id) {
    message.warning(t('请先保存链路再运行'))
    return
  }
  syncEditorSnapshot()
  // 先保存再执行
  if (dirty.value) {
    const saved = await handleSave()
    if (!saved) return
  } else if (!validateBoundaryNodes()) {
    return
  }
  try {
    const result = await store.executeChain(envStore.activeEnvironmentId)
    if (result) {
      const failCount = result.step_results?.filter(s => s.status === 'failed').length || 0
      if (result.status === 'completed' && !failCount) {
        message.success(t('链路执行完成，全部通过'))
      } else if (failCount) {
        message.warning(`${t('链路执行完成，')}${failCount}${t(' 个节点失败')}`)
      } else {
        message.error(`${t('链路执行失败')}: ${result.error_message || t('未知错误')}`)
      }
    }
  } catch (e) {
    message.error(t('链路执行失败'))
  }
}

function addGlobal() {
  store.currentChain.globals.push({ key: '', value: '', description: '' })
}

function handleProjectChanged() {
  store.resetCurrent()
  store.fetchChains()
  selectedNode.value = null
  nodePanelVisible.value = false
}

// 监听接口名称变更，同步到链路编辑器中的接口节点
function handleInterfaceUpdated(e) {
  const { id } = e.detail || {}
  if (id) {
    store.syncInterfaceNames(id)
  }
}

onMounted(() => {
  window.addEventListener('project-changed', handleProjectChanged)
  window.addEventListener('interface-updated', handleInterfaceUpdated)
  // 支持 URL 参数加载指定链路（从 Agent 页面跳转过来）
  const chainId = parseInt(route.query.id)
  if (chainId) {
    store.setCurrentChain({ id: chainId })
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('project-changed', handleProjectChanged)
  window.removeEventListener('interface-updated', handleInterfaceUpdated)
})

function removeGlobal(idx) {
  store.currentChain.globals.splice(idx, 1)
}
</script>

<style scoped>
.chain-test-page {
  display: flex;
  height: calc(100vh - 152px);
  background: #fff;
}

.chain-sidebar-wrap {
  width: 240px;
  flex-shrink: 0;
  background: #fafafa;
  border-right: 1px solid #f0f0f0;
  overflow-y: auto;
}

.chain-canvas-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.canvas-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.active-env {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #595959;
  font-size: 12px;
}

.canvas-body {
  flex: 1;
  overflow: hidden;
}

.globals-editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.global-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
