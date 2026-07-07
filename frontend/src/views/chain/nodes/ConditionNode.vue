<template>
  <div class="chain-node" :class="nodeStatusClass">
    <div class="node-header node-header-condition">
      <BranchesOutlined class="node-icon" />
      <span class="node-label">{{ data.label || '条件分支' }}</span>
    </div>
    <div class="node-body" v-if="conditionSummary">
      <span class="node-meta">{{ conditionSummary }}</span>
    </div>
    <Handle type="target" :position="Position.Left" />
    <Handle type="source" :position="Position.Right" id="true" :style="{ top: '40%' }" />
    <Handle type="source" :position="Position.Right" id="false" :style="{ top: '70%' }" />
    <div class="handle-labels">
      <span class="handle-label-true">T</span>
      <span class="handle-label-false">F</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { BranchesOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  id: String,
  data: { type: Object, default: () => ({}) },
})

const OPERATOR_LABELS = {
  equals: '==', not_equals: '!=', contains: '∋',
  not_contains: '∌', greater_than: '>', less_than: '<',
  exists: '∃', not_exists: '∄',
}

const CONDITION_TYPE_LABELS = {
  variable: '变量',
  jsonpath: 'JSONPath',
  script: '脚本',
}

const operatorLabel = computed(() => OPERATOR_LABELS[props.data.operator] || '==')

const conditionSummary = computed(() => {
  const ctype = props.data.condition_type || 'variable'
  const typeLabel = CONDITION_TYPE_LABELS[ctype] || '变量'

  if (ctype === 'variable') {
    if (!props.data.source_var) return typeLabel
    return `${props.data.source_var} ${operatorLabel.value} ${props.data.expected || ''}`
  } else if (ctype === 'jsonpath') {
    if (!props.data.jsonpath) return 'JSONPath'
    const shortPath = props.data.jsonpath.length > 20
      ? props.data.jsonpath.substring(0, 20) + '...'
      : props.data.jsonpath
    return `JSONPath: ${shortPath}`
  } else if (ctype === 'script') {
    return '脚本'
  }
  return typeLabel
})

const nodeStatusClass = computed(() => {
  const s = props.data._status
  if (s === 'success') return 'node-success'
  if (s === 'failed') return 'node-failed'
  if (s === 'skipped') return 'node-skipped'
  return ''
})
</script>

<style scoped>
.chain-node {
  background: #fff;
  border: 2px solid #d9d9d9;
  border-radius: 8px;
  min-width: 150px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.08);
  transition: border-color 0.3s;
  position: relative;
}
.node-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 6px 6px 0 0;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
}
.node-header-condition { background: #13c2c2; }
.node-icon { font-size: 13px; }
.node-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.node-body { padding: 4px 10px 6px; font-size: 11px; color: #8c8c8c; }
.node-meta { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }
.handle-labels {
  position: absolute;
  right: 4px;
  top: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
  pointer-events: none;
}
.handle-label-true, .handle-label-false {
  font-size: 10px;
  font-weight: 700;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.handle-label-true { color: #52c41a; background: #f6ffed; }
.handle-label-false { color: #ff4d4f; background: #fff2f0; }
.node-success { border-color: #52c41a; }
.node-failed { border-color: #ff4d4f; }
.node-skipped { border-color: #d9d9d9; opacity: 0.5; }
</style>