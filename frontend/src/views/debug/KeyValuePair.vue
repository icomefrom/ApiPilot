<template>
  <div class="kv-pair-editor">
    <div v-for="(item, index) in rows" :key="index" class="kv-row">
      <a-input v-model:value="item.key" placeholder="Key" size="small" style="flex: 1" @change="syncOutput" />
      <a-input v-model:value="item.value" placeholder="Value" size="small" style="flex: 1" @change="syncOutput" />
      <a-button type="text" danger size="small" @click="removeRow(index)">
        <DeleteOutlined />
      </a-button>
    </div>
    <a-button type="dashed" size="small" @click="addRow" block>
      <PlusOutlined /> 添加一行
    </a-button>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  data: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:data'])

const rows = ref([])

// 将对象转为行数组
function objToRows(obj) {
  return Object.entries(obj || {}).map(([key, value]) => ({
    key,
    value: Array.isArray(value) ? value.join(', ') : String(value),
  }))
}

// 将行数组转为对象
function rowsToObj(list) {
  const result = {}
  for (const row of list) {
    if (row.key.trim()) {
      result[row.key.trim()] = row.value
    }
  }
  return result
}

function addRow() {
  rows.value.push({ key: '', value: '' })
}

function removeRow(index) {
  rows.value.splice(index, 1)
  syncOutput()
}

function syncOutput() {
  emit('update:data', rowsToObj(rows.value))
}

// 初始化 + 外部变化时同步
watch(() => props.data, (newVal) => {
  const current = rowsToObj(rows.value)
  // 只在外部数据变化时同步（避免输入时覆盖）
  if (JSON.stringify(current) !== JSON.stringify(newVal || {})) {
    rows.value = objToRows(newVal)
  }
}, { immediate: true, deep: true })
</script>

<style scoped>
.kv-pair-editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kv-row {
  display: flex;
  gap: 6px;
  align-items: center;
}
</style>