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
          placeholder="链路名称"
          style="width: 200px"
          size="small"
        />
        <div class="toolbar-actions">
          <span class="active-env">环境：{{ envStore.activeEnvName }}</span>
          <a-button size="small" @click="showGlobalsModal = true">
            <SettingOutlined /> 全局参数
          </a-button>
          <a-button
            type="primary"
            size="small"
            :loading="store.executing"
            :disabled="!store.currentChain.id"
            @click="handleRun"
          >
            <PlayCircleOutlined /> 运行
          </a-button>
          <a-button size="small" :disabled="!store.currentChain.id" @click="handleSave">
            <SaveOutlined /> 保存
          </a-button>
        </div>
      </div>

      <div class="canvas-body">
        <ChainEditor
          :nodes="store.currentChain.nodes"
          :edges="store.currentChain.edges"
          :result="store.currentResult"
          :placement-type="placementType"
          @update:nodes="handleNodesUpdate"
          @update:edges="val => store.currentChain.edges = val"
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
      title="全局参数"
      @ok="showGlobalsModal = false"
      @cancel="showGlobalsModal = false"
      :width="600"
    >
      <div class="globals-editor">
        <div v-for="(g, idx) in store.currentChain.globals" :key="idx" class="global-item">
          <a-input v-model:value="g.key" placeholder="参数名" style="width: 30%" />
          <a-input v-model:value="g.value" placeholder="参数值" style="flex: 1" />
          <a-input v-model:value="g.description" placeholder="说明" style="width: 25%" />
          <a-button type="text" danger size="small" @click="removeGlobal(idx)"><DeleteOutlined /></a-button>
        </div>
        <a-button type="dashed" block size="small" @click="addGlobal">
          <PlusOutlined /> 添加参数
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

const store = useChainStore()
const envStore = useEnvironmentStore()
const debugStore = useDebugStore()
const route = useRoute()

const sidebarRef = ref(null)
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
}

async function handleSave() {
  if (!store.currentChain.id) {
    message.warning('请先创建链路')
    return
  }
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
    message.success('链路已保存')
    await store.fetchChains()
  } catch (e) {
    message.error('保存失败')
  }
}

async function handleRun() {
  if (!store.currentChain.id) {
    message.warning('请先保存链路再运行')
    return
  }
  // 先保存再执行
  if (dirty.value) {
    await handleSave()
  }
  try {
    const result = await store.executeChain(envStore.activeEnvironmentId)
    if (result) {
      const failCount = result.step_results?.filter(s => s.status === 'failed').length || 0
      if (result.status === 'completed' && !failCount) {
        message.success(`链路执行完成，全部通过`)
      } else if (failCount) {
        message.warning(`链路执行完成，${failCount} 个节点失败`)
      } else {
        message.error(`链路执行失败: ${result.error_message || '未知错误'}`)
      }
    }
  } catch (e) {
    message.error('链路执行失败')
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