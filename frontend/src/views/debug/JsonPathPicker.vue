<template>
  <a-popover
    v-model:open="popoverVisible"
    trigger="click"
    placement="bottomLeft"
    :overlayStyle="{ maxWidth: '500px', width: '460px' }"
  >
    <template #content>
      <div class="json-tree-container" v-if="treeData.length">
        <a-tree
          :treeData="treeData"
          :defaultExpandAll="false"
          :showLine="true"
          :showIcon="false"
          :selectable="true"
          @select="onSelect"
        />
      </div>
      <div v-else class="tree-empty">
        <a-empty :image="simpleImage" :description="emptyDescription" />
      </div>
    </template>
    <a-input
      :value="modelValue"
      @update:value="$emit('update:modelValue', $event)"
      :placeholder="parseError ? '仅 $.status_code / $.headers 可选' : '点击选择 JSONPath'"
      :class="{ 'jsonpath-input': true, 'jsonpath-input-warning': parseError && pathReferencesBody(modelValue) }"
      @change="$emit('change')"
    >
      <template #suffix>
        <ApartmentOutlined style="color: rgba(0,0,0,0.25)" />
      </template>
    </a-input>
  </a-popover>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Empty } from 'ant-design-vue'
import { ApartmentOutlined } from '@ant-design/icons-vue'

const simpleImage = Empty.PRESENTED_IMAGE_SIMPLE

const props = defineProps({
  modelValue: { type: String, default: '' },
  responseData: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue', 'change'])

const popoverVisible = ref(false)

const MAX_ARRAY_CHILDREN = 100

// 判断键名是否安全（可用点号访问）
function isSafeKey(key) {
  return /^[A-Za-z_$][A-Za-z0-9$]*$/.test(key)
}

// 递归构建树数据
function buildTreeData(value, segment, pathSoFar, displayKey) {
  const fullPath = pathSoFar + segment
  const node = {
    key: fullPath,
    jsonpath: fullPath,
    displayKey,
    isLeaf: false,
    children: [],
    valueType: 'object',
    title: '',
  }

  if (value === null) {
    node.valueType = 'null'
    node.title = `${displayKey} : null`
    node.isLeaf = true
    return node
  }

  if (Array.isArray(value)) {
    node.valueType = 'array'
    const len = value.length
    node.title = `${displayKey} [${len}]`
    if (len === 0) {
      node.isLeaf = true
      return node
    }
    const limit = Math.min(len, MAX_ARRAY_CHILDREN)
    for (let i = 0; i < limit; i++) {
      const arrSegment = `[${i}]`
      node.children.push(buildTreeData(value[i], arrSegment, fullPath, `[${i}]`))
    }
    if (len > MAX_ARRAY_CHILDREN) {
      node.children.push({
        key: `${fullPath}.__truncated__`,
        jsonpath: '',
        displayKey: '...',
        title: `... 还有 ${len - MAX_ARRAY_CHILDREN} 项 (可手动输入 [N] 索引)`,
        isLeaf: true,
        children: [],
        valueType: 'string',
        selectable: false,
      })
    }
    return node
  }

  if (typeof value === 'object') {
    const keys = Object.keys(value)
    node.title = `${displayKey} {${keys.length}}`
    if (keys.length === 0) {
      node.isLeaf = true
      return node
    }
    keys.forEach(k => {
      const childSegment = isSafeKey(k) ? `.${k}` : `['${k.replace(/'/g, "\\'")}']`
      node.children.push(buildTreeData(value[k], childSegment, fullPath, k))
    })
    return node
  }

  // 基本类型
  if (typeof value === 'string') {
    node.valueType = 'string'
    const preview = value.length > 40 ? value.substring(0, 40) + '...' : value
    node.title = `${displayKey} : "${preview}"`
  } else if (typeof value === 'number') {
    node.valueType = 'number'
    node.title = `${displayKey} : ${value}`
  } else if (typeof value === 'boolean') {
    node.valueType = 'boolean'
    node.title = `${displayKey} : ${value}`
  }
  node.isLeaf = true
  return node
}

// 解析响应数据，构建包装对象
const wrapper = computed(() => {
  if (!props.responseData) return null
  let parsedBody = null
  if (props.responseData.response_body) {
    try {
      parsedBody = JSON.parse(props.responseData.response_body)
    } catch {
      parsedBody = null
    }
  } else if (props.responseData.body && typeof props.responseData.body === 'object') {
    // 链路结果格式：body 已经是解析后的 JSON 对象
    parsedBody = props.responseData.body
  } else if (typeof props.responseData.body === 'string') {
    try {
      parsedBody = JSON.parse(props.responseData.body)
    } catch {
      parsedBody = null
    }
  }
  return {
    status_code: props.responseData.status_code,
    elapsed_ms: props.responseData.elapsed_ms,
    headers: props.responseData.response_headers || props.responseData.headers || {},
    body: parsedBody,
  }
})

// 是否解析失败
const parseError = computed(() => {
  const bodyStr = props.responseData?.response_body || (typeof props.responseData?.body === 'string' ? props.responseData.body : null)
  if (!bodyStr) return false
  try {
    JSON.parse(bodyStr)
    return false
  } catch {
    return true
  }
})

const emptyDescription = computed(() => {
  if (!props.responseData) return '暂无响应数据'
  if (parseError.value) return '响应体非 JSON 格式，仅 status_code/headers 可选'
  return '暂无数据'
})

// 判断 JSONPath 是否引用 $.body 路径
function pathReferencesBody(p) {
  if (!p || !p.trim().startsWith('$')) return false
  const afterRoot = p.trim().slice(1)
  return /^\.body/.test(afterRoot) || /^\['body'\]/.test(afterRoot) || /^\["body"\]/.test(afterRoot)
}

// 构建树数据（顶层直接展开 4 个节点）
const treeData = computed(() => {
  if (!wrapper.value) return []
  const w = wrapper.value
  const children = []

  // status_code
  children.push(buildTreeData(w.status_code, '.status_code', '$', 'status_code'))
  // elapsed_ms
  children.push(buildTreeData(w.elapsed_ms, '.elapsed_ms', '$', 'elapsed_ms'))
  // headers
  children.push(buildTreeData(w.headers, '.headers', '$', 'headers'))

  // body
  if (w.body !== null) {
    children.push(buildTreeData(w.body, '.body', '$', 'body'))
  } else if ((props.responseData?.response_body || typeof props.responseData?.body === 'string') && parseError.value) {
    // 非 JSON 响应体，加不可选的标记节点
    children.push({
      key: '$.body.__non_json__',
      jsonpath: '',
      displayKey: 'body',
      title: 'body : (非 JSON, 不可导航)',
      valueType: 'string',
      isLeaf: true,
      children: [],
      selectable: false,
      class: 'tree-node-disabled',
    })
  }

  return children
})

// 选中节点
function onSelect(selectedKeys) {
  if (selectedKeys.length > 0) {
    const path = selectedKeys[0]
    // 跳过不可选的占位节点
    if (!path || path.endsWith('__truncated__') || path.endsWith('__non_json__')) return
    emit('update:modelValue', path)
    emit('change')
    popoverVisible.value = false
  }
}
</script>

<style scoped>
.jsonpath-input {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
  cursor: pointer;
}

.json-tree-container {
  max-height: 360px;
  overflow-y: auto;
}

.json-tree-container :deep(.ant-tree-node-content-wrapper) {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
}

.jsonpath-input-warning :deep(.ant-input) {
  border-color: #faad14;
  background: #fffbe6;
}

.json-tree-container :deep(.ant-tree-node-content-wrapper.tree-node-disabled) {
  color: #bfbfbf;
  cursor: not-allowed;
  pointer-events: none;
}

.tree-empty {
  padding: 20px 0;
  min-width: 200px;
}
</style>