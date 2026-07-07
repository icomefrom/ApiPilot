<template>
  <div class="chain-node chain-node-terminal" :class="nodeStatusClass">
    <div class="node-header node-header-end">
      <CheckCircleOutlined class="node-icon" />
      <span class="node-label">{{ translateText(data.label || '结束') }}</span>
    </div>
    <Handle type="target" :position="Position.Left" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { CheckCircleOutlined } from '@ant-design/icons-vue'
import { translateText } from '../../../i18n'

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
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
}
.node-header-end { background: #595959; }
.node-icon { font-size: 13px; }
.node-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.node-success { border-color: #52c41a; }
.node-failed { border-color: #ff4d4f; }
.node-skipped { border-color: #d9d9d9; opacity: 0.5; }
</style>
