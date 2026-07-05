<template>
  <div class="chain-sidebar">
    <!-- 节点面板 -->
    <div class="sidebar-section">
      <div class="section-header">
        <span class="section-title">节点面板</span>
      </div>
      <div class="node-palette">
        <div
          v-for="item in NODE_PALETTE"
          :key="item.type"
          class="palette-item"
          :class="{ active: selectedNodeType === item.type }"
          :draggable="true"
          @dragstart="onDragStart($event, item.type)"
          @click="onPaletteClick(item.type)"
        >
          <component :is="item.icon" class="palette-icon" :style="{ color: item.color }" />
          <span>{{ item.label }}</span>
          <span v-if="selectedNodeType === item.type" class="palette-item-badge">点击画布放置</span>
        </div>
      </div>
    </div>

    <a-divider style="margin: 8px 0" />

    <!-- 链路列表 -->
    <div class="sidebar-section chain-list-section">
      <div class="section-header">
        <span class="section-title">链路列表</span>
        <a-button type="link" size="small" @click="handleNew">
          <PlusOutlined /> 新建
        </a-button>
      </div>
      <div class="chain-list">
        <div
          v-for="chain in store.chains"
          :key="chain.id"
          class="chain-item"
          :class="{ active: chain.id === store.currentChain.id }"
          @click="store.setCurrentChain(chain)"
        >
          <span class="chain-name">{{ chain.name }}</span>
          <span class="chain-status" :class="'status-' + chain.status">
            {{ chain.status === 'ready' ? '就绪' : '草稿' }}
          </span>
          <a-button
            type="text"
            danger
            size="small"
            class="chain-delete-btn"
            @click.stop="handleDelete(chain)"
          >
            <DeleteOutlined />
          </a-button>
        </div>
        <a-empty v-if="!store.chains.length" :image="simpleImage" description="暂无链路" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { Empty, Modal, message } from 'ant-design-vue'
import {
  PlusOutlined,
  DeleteOutlined,
  ApiOutlined,
  CodeOutlined,
  ClockCircleOutlined,
  BranchesOutlined,
} from '@ant-design/icons-vue'
import { useChainStore } from '../../stores/chain'

const simpleImage = Empty.PRESENTED_IMAGE_SIMPLE
const store = useChainStore()

const NODE_PALETTE = [
  { type: 'interface', label: '接口节点', icon: ApiOutlined, color: '#1677ff' },
  { type: 'script', label: '脚本节点', icon: CodeOutlined, color: '#722ed1' },
  { type: 'timer', label: '定时器', icon: ClockCircleOutlined, color: '#fa8c16' },
  { type: 'condition', label: '条件分支', icon: BranchesOutlined, color: '#13c2c2' },
]

// 当前选中的待放置节点类型（null 表示未选中）
const selectedNodeType = ref(null)

// 全局事件：Escape 取消选中
function onKeydown(e) {
  if (e.key === 'Escape' && selectedNodeType.value) {
    selectedNodeType.value = null
  }
}
onMounted(() => {
  store.fetchChains()
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})

function onPaletteClick(type) {
  // 切换选中：再次点击同一类型取消，否则选中新类型
  selectedNodeType.value = selectedNodeType.value === type ? null : type
}

function onDragStart(event, nodeType) {
  event.dataTransfer.setData('application/vueflow', nodeType)
  event.dataTransfer.effectAllowed = 'move'
  // 拖拽时自动取消点击选中模式
  selectedNodeType.value = null
}

async function handleNew() {
  await store.resetCurrent()
  const result = await store.saveChain({
    name: '新建链路',
    nodes: [],
    edges: [],
    globals: [],
    status: 'draft',
  })
  if (result) {
    await store.setCurrentChain(result)
    await store.fetchChains()
    message.success('链路已创建')
  }
}

function handleDelete(chain) {
  Modal.confirm({
    title: '删除链路',
    content: `确定要删除「${chain.name}」吗？删除后不可恢复。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      if (store.currentChain.id === chain.id) {
        store.resetCurrent()
      }
      await store.deleteChain(chain.id)
      message.success('链路已删除')
    },
  })
}

// 暴露 selectedNodeType 给父组件（ChainTest）使用
defineExpose({ selectedNodeType })
</script>

<style scoped>
.chain-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 8px;
}

.sidebar-section { flex-shrink: 0; }

.chain-list-section {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #262626;
}

.chain-list {
  flex: 1;
  overflow-y: auto;
}

.chain-item {
  display: flex;
  align-items: center;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.2s;
}

.chain-item:hover { background: #f0f5ff; }
.chain-item.active { background: #e6f4ff; font-weight: 500; }

.chain-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.chain-status {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  flex-shrink: 0;
  margin-left: 6px;
}

.chain-delete-btn {
  flex-shrink: 0;
  margin-left: 2px;
  opacity: 0;
  transition: opacity 0.2s;
}

.chain-item:hover .chain-delete-btn { opacity: 1; }

.status-draft { background: #f5f5f5; color: #8c8c8c; }
.status-ready { background: #f6ffed; color: #52c41a; }

.node-palette {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.palette-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  cursor: grab;
  font-size: 13px;
  transition: all 0.2s;
  position: relative;
}

.palette-item:hover {
  border-color: #91caff;
  background: #f0f5ff;
}

.palette-item:active { cursor: grabbing; }

.palette-item.active {
  border-color: #1677ff;
  background: #e6f4ff;
  cursor: crosshair;
}

.palette-icon { font-size: 16px; }

.palette-item-badge {
  margin-left: auto;
  font-size: 11px;
  color: #1677ff;
  background: #f0f5ff;
  padding: 1px 6px;
  border-radius: 3px;
  white-space: nowrap;
}
</style>