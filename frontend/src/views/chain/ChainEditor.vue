<template>
  <div class="chain-editor" ref="editorRef">
    <VueFlow
      v-model:nodes="flowNodes"
      v-model:edges="flowEdges"
      :node-types="nodeTypes"
      :default-viewport="{ zoom: 1, x: 50, y: 50 }"
      :snap-to-grid="true"
      :snap-grid="[20, 20]"
      :min-zoom="0.3"
      :max-zoom="2"
      fit-view-on-init
      @node-click="onNodeClick"
      @connect="onConnect"
      @dragover="onDragOver"
      @drop="onDrop"
      @pane-click="onPaneClick"
    >
      <Background :gap="20" />
      <Controls />
      <MiniMap />
    </VueFlow>

    <!-- 放置模式提示 -->
    <div v-if="placementType" class="placement-hint">
      点击节点连线创建 · 点击空白放置 · Esc 取消
    </div>
  </div>
</template>

<script setup>
import { ref, watch, markRaw } from 'vue'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import InterfaceNode from './nodes/InterfaceNode.vue'
import ScriptNode from './nodes/ScriptNode.vue'
import TimerNode from './nodes/TimerNode.vue'
import ConditionNode from './nodes/ConditionNode.vue'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  result: { type: Object, default: null },
  placementType: { type: String, default: null },
})

const emit = defineEmits(['update:nodes', 'update:edges', 'node-click', 'placement-done'])

const nodeTypes = {
  interface: markRaw(InterfaceNode),
  script: markRaw(ScriptNode),
  timer: markRaw(TimerNode),
  condition: markRaw(ConditionNode),
}

const editorRef = ref(null)
let nodeIdCounter = Date.now()

const flowNodes = ref([])
const flowEdges = ref([])

const DEFAULT_DATA = {
  interface: {
    label: '接口节点',
    interface_id: null,
    overrides: {
      url: '',
      headers: {},
      query_params: {},
      body: '',
      body_fields: {},
      ws_message: '',
      rpc_method: '',
    },
    extractions: [],
    assertions: [],
    retry_count: 0,
    retry_interval: 1,
  },
  script: { label: '脚本节点', script: '', timeout: 10 },
  timer: { label: '等待', delay: 1 },
  condition: { label: '条件分支', condition_type: 'variable', source_var: '', operator: 'equals', expected: '', jsonpath: '', script: '', timeout: 10 },
}

let syncingFromProps = false

// props → flowNodes/flowEdges 同步
watch(() => props.nodes, (newNodes) => {
  if (syncingFromProps) return
  flowNodes.value = (newNodes || []).map(n => ({
    id: n.id,
    type: n.type,
    position: n.position || { x: 0, y: 0 },
    data: { ...n.data, _status: _getNodeStatus(n.id) },
  }))
}, { immediate: true, deep: true })

watch(() => props.edges, (newEdges) => {
  if (syncingFromProps) return
  flowEdges.value = (newEdges || []).map(e => ({
    id: e.id,
    source: e.source,
    target: e.target,
    sourceHandle: e.sourceHandle || undefined,
    animated: true,
  }))
}, { immediate: true, deep: true })

// 执行结果 → 节点颜色
watch(() => props.result, (result) => {
  if (!result?.step_results) return
  flowNodes.value = flowNodes.value.map(node => {
    const step = result.step_results.find(s => s.node_id === node.id)
    const status = step ? step.status : 'skipped'
    return { ...node, data: { ...node.data, _status: status } }
  })
}, { deep: true })

// flowNodes/flowEdges 变化 → 通知 store（防循环）
let syncTimer = null
function syncToStore() {
  if (syncTimer) clearTimeout(syncTimer)
  syncTimer = setTimeout(() => {
    syncingFromProps = true
    emit('update:nodes', flowNodes.value.map(n => ({
      id: n.id,
      type: n.type,
      position: n.position,
      data: { ...n.data, _status: undefined },
    })))
    emit('update:edges', flowEdges.value.map(e => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle || undefined,
    })))
    setTimeout(() => { syncingFromProps = false }, 50)
  }, 100)
}

watch(flowNodes, syncToStore, { deep: true })
watch(flowEdges, syncToStore, { deep: true })

function _getNodeStatus(nodeId) {
  if (!props.result?.step_results) return undefined
  const step = props.result.step_results.find(s => s.node_id === nodeId)
  return step?.status
}

function createNode(type, position, sourceNodeId = null, sourceHandle = null) {
  const nodeId = `node_${++nodeIdCounter}`
  const newNode = {
    id: nodeId,
    type,
    position,
    data: { ...(DEFAULT_DATA[type] || { label: '节点' }) },
  }
  flowNodes.value = [...flowNodes.value, newNode]

  if (sourceNodeId) {
    const newEdge = {
      id: `e-${sourceNodeId}-${nodeId}-${++nodeIdCounter}`,
      source: sourceNodeId,
      target: nodeId,
      sourceHandle: sourceHandle || undefined,
      animated: true,
    }
    flowEdges.value = [...flowEdges.value, newEdge]
  }

  return newNode
}

function onNodeClick(event) {
  if (props.placementType && event?.node) {
    const clickedNode = event.node
    const nodeType = props.placementType
    const offsetX = nodeType === 'condition' ? 240 : 220
    const position = {
      x: clickedNode.position.x + offsetX,
      y: clickedNode.position.y,
    }

    let sourceHandle = 'out'
    if (clickedNode.type === 'condition') {
      sourceHandle = 'true'
    }

    createNode(nodeType, position, clickedNode.id, sourceHandle)
    emit('placement-done')
    return
  }

  if (event?.node) {
    emit('node-click', event.node)
  }
}

function onPaneClick(event) {
  if (!props.placementType) return

  const x = event.x ?? 0
  const y = event.y ?? 0
  createNode(props.placementType, { x: Math.max(0, x), y: Math.max(0, y) })
  emit('placement-done')
}

function onConnect(params) {
  const newEdge = {
    ...params,
    animated: true,
    id: `e-${params.source}-${params.target}-${++nodeIdCounter}`,
  }
  flowEdges.value = [...flowEdges.value, newEdge]
}

function onDragOver(event) {
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'move'
  }
}

function onDrop(event) {
  const type = event.dataTransfer?.getData('application/vueflow')
  if (!type) return

  const editorEl = editorRef.value
  if (!editorEl) return

  const rect = editorEl.getBoundingClientRect()
  const x = event.clientX - rect.left - 50
  const y = event.clientY - rect.top - 50

  createNode(type, { x: Math.max(0, x), y: Math.max(0, y) })
}

defineExpose({ flowNodes, flowEdges })
</script>

<style>
/* Handle 连接点样式 — 全局覆盖，确保画布连线可交互 */
.chain-editor .vue-flow__handle {
  width: 10px;
  height: 10px;
  background: #fff;
  border: 2px solid #91caff;
  pointer-events: all;
  transition: all 0.15s;
}
.chain-editor .vue-flow__handle:hover {
  background: #1677ff;
  border-color: #1677ff;
  transform: scale(1.4);
  box-shadow: 0 0 6px rgba(22, 119, 255, 0.4);
}
/* 拖拽连线时源 Handle 高亮 */
.chain-editor .vue-flow__handle.connecting {
  background: #1677ff;
  border-color: #1677ff;
}
/* 连接线 */
.chain-editor .vue-flow__edge-path {
  stroke: #91caff;
  stroke-width: 2;
}
.chain-editor .vue-flow__edge.animated .vue-flow__edge-path {
  stroke-dasharray: 5;
  animation: dash 0.5s linear infinite;
}
@keyframes dash {
  to { stroke-dashoffset: -5; }
}
</style>

<style scoped>
.chain-editor {
  width: 100%;
  height: 100%;
  background: #f8f9fa;
  position: relative;
}

.placement-hint {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(22, 119, 255, 0.9);
  color: #fff;
  padding: 6px 16px;
  border-radius: 6px;
  font-size: 12px;
  pointer-events: none;
  z-index: 10;
  white-space: nowrap;
}
</style>