<template>
  <div class="chain-node" :class="nodeStatusClass">
    <div class="node-header node-header-interface">
      <ApiOutlined class="node-icon" />
      <span class="node-label">{{ data.label || '接口节点' }}</span>
    </div>
    <div class="node-body" v-if="data.interface_id">
      <span class="node-meta">{{ data.interface_name || `ID: ${data.interface_id}` }}</span>
      <span v-if="data.retry_count > 0" class="node-retry-badge">重试x{{ data.retry_count }}</span>
    </div>
    <Handle type="target" :position="Position.Left" />
    <Handle type="source" :position="Position.Right" id="out" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { ApiOutlined } from '@ant-design/icons-vue'

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
  min-width: 160px;
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
.node-header-interface { background: #1677ff; }
.node-icon { font-size: 13px; }
.node-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.node-body {
  padding: 4px 10px 6px;
  font-size: 11px;
  color: #8c8c8c;
}
.node-meta { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }
.node-retry-badge {
  display: inline-block;
  font-size: 10px;
  line-height: 16px;
  padding: 0 4px;
  margin-top: 2px;
  border-radius: 3px;
  background: #fff7e6;
  color: #d46b08;
  border: 1px solid #ffd591;
}
.node-success { border-color: #52c41a; }
.node-failed { border-color: #ff4d4f; }
.node-skipped { border-color: #d9d9d9; opacity: 0.5; }
</style>