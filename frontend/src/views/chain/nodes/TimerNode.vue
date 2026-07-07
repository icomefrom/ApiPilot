<template>
  <div class="chain-node" :class="nodeStatusClass">
    <div class="node-header node-header-timer">
      <ClockCircleOutlined class="node-icon" />
      <span class="node-label">{{ data.label || '定时器' }}</span>
    </div>
    <div class="node-body" v-if="data.delay">
      <span class="node-meta">延迟 {{ data.delay }}s</span>
    </div>
    <Handle type="target" :position="Position.Left" />
    <Handle type="source" :position="Position.Right" id="out" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { ClockCircleOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  id: String,
  data: { type: Object, default: () => ({}) },
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
  min-width: 120px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.08);
  transition: border-color 0.3s;
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
.node-header-timer { background: #fa8c16; }
.node-icon { font-size: 13px; }
.node-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.node-body { padding: 4px 10px 6px; font-size: 11px; color: #8c8c8c; }
.node-meta { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }
.node-success { border-color: #52c41a; }
.node-failed { border-color: #ff4d4f; }
.node-skipped { border-color: #d9d9d9; opacity: 0.5; }
</style>