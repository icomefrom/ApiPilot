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
      <a-divider style="margin: 8px 0" />
      <div class="custom-key-row">
        <a-input
          v-model:value="customKey"
          placeholder="输入自定义 key"
          size="small"
          style="flex: 1"
          @pressEnter="onCustomKeySubmit"
        />
        <a-button type="primary" size="small" @click="onCustomKeySubmit" :disabled="!customKey.trim()">确定</a-button>
      </div>
    </template>
    <slot :openPopover="() => popoverVisible = true">
      <a-button type="dashed" block size="small" style="margin-top: 4px">
        <PlusOutlined /> {{ addLabel }}
      </a-button>
    </slot>
  </a-popover>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Empty } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'

const simpleImage = Empty.PRESENTED_IMAGE_SIMPLE

const props = defineProps({
  /** 接口详情对象（selectedInterface），包含 headers/query_params/body/body_type */
  interfaceData: { type: Object, default: null },
  /** 要浏览的字段：'headers' | 'query_params' | 'body_fields' | 'all' */
  sourceField: { type: String, default: 'all' },
  /** 已存在的 key 列表（这些 key 在树中标记为已选/不可再选） */
  existingKeys: { type: Array, default: () => [] },
  /** 添加按钮文字 */
  addLabel: { type: String, default: '添加参数' },
})

const emit = defineEmits(['select'])
const popoverVisible = ref(false)
const customKey = ref('')

const MAX_ARRAY_CHILDREN = 100

function isSafeKey(key) {
  return /^[A-Za-z_$][A-Za-z0-9$]*$/.test(key)
}

/**
 * 从 JSONPath 中提取最后一段 key 名
 * $.headers.Authorization → Authorization
 * $.body.data[0].name → name
 * $['some-key'] → some-key
 */
function extractLeafKey(jsonpath) {
  if (!jsonpath) return jsonpath
  // 处理 bracket notation: ['xxx'] 或 ["xxx"]
  const bracketMatch = jsonpath.match(/\[['"]([^'"]+)['"]\]\s*$/)
  if (bracketMatch) return bracketMatch[1]
  // 处理 dot notation: .xxx
  const dotMatch = jsonpath.match(/\.(\w+)$/)
  if (dotMatch) return dotMatch[1]
  // 处理 array index: [N]
  const idxMatch = jsonpath.match(/\[(\d+)\]$/)
  if (idxMatch) return `[${idxMatch[1]}]`
  return jsonpath
}

/**
 * 递归构建树数据，与 JsonPathPicker 逻辑一致
 * @param {boolean} skipRoot - 是否跳过根节点层级（用于 headers/query_params 直接展开子节点）
 */
function buildTreeData(value, segment, pathSoFar, displayKey, depth) {
  const fullPath = pathSoFar + segment
  const node = {
    key: fullPath,
    displayKey,
    isLeaf: false,
    children: [],
    valueType: 'object',
    title: '',
    jsonpath: fullPath,
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
      node.children.push(buildTreeData(value[i], arrSegment, fullPath, `[${i}]`, depth + 1))
    }
    if (len > MAX_ARRAY_CHILDREN) {
      node.children.push({
        key: `${fullPath}.__truncated__`,
        displayKey: '...',
        title: `... 还有 ${len - MAX_ARRAY_CHILDREN} 项`,
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
      node.children.push(buildTreeData(value[k], childSegment, fullPath, k, depth + 1))
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

/**
 * 构建接口参数的树形数据
 * 将 headers / query_params / body 组织为顶层节点
 */
const treeData = computed(() => {
  if (!props.interfaceData) return []
  const iface = props.interfaceData
  const existing = new Set(props.existingKeys)
  const children = []

  const sources = []

  if (props.sourceField === 'all' || props.sourceField === 'headers') {
    const headers = iface.headers
    if (headers && typeof headers === 'object' && Object.keys(headers).length > 0) {
      sources.push({ label: 'headers', data: headers })
    }
  }

  if (props.sourceField === 'all' || props.sourceField === 'query_params') {
    const qp = iface.query_params
    if (qp && typeof qp === 'object' && Object.keys(qp).length > 0) {
      sources.push({ label: 'query_params', data: qp })
    }
  }

  if (props.sourceField === 'all' || props.sourceField === 'body_fields') {
    // 解析 body JSON
    if (iface.body_type === 'json' && iface.body) {
      try {
        const parsed = JSON.parse(iface.body)
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          sources.push({ label: 'body', data: parsed })
        }
      } catch { /* non-JSON, skip */ }
    }
  }

  // 单一 source 且是 headers/query_params 时，直接展开子节点（跳过根层级）
  if (sources.length === 1 && (sources[0].label === 'headers' || sources[0].label === 'query_params')) {
    const src = sources[0]
    for (const k of Object.keys(src.data)) {
      const childSegment = isSafeKey(k) ? `.${k}` : `['${k.replace(/'/g, "\\'")}']`
      const fullPath = `$.${src.label}${childSegment}`
      const isExisting = existing.has(k)
      const value = src.data[k]
      let title = `${k}`
      if (typeof value === 'string') {
        const preview = value.length > 30 ? value.substring(0, 30) + '...' : value
        title = `${k} : "${preview}"`
      } else if (value !== null && value !== undefined) {
        title = `${k} : ${typeof value === 'object' ? '{...}' : value}`
      }
      children.push({
        key: fullPath,
        displayKey: k,
        title: isExisting ? `${title} (已添加)` : title,
        isLeaf: true,
        children: [],
        valueType: typeof value,
        selectable: !isExisting,
        class: isExisting ? 'tree-node-existing' : '',
        jsonpath: fullPath,
      })
    }
  } else if (sources.length === 1 && sources[0].label === 'body') {
    // body_fields 专用：展开 body 的顶层 key，同时支持导航到嵌套字段
    const src = sources[0]
    for (const k of Object.keys(src.data)) {
      const childSegment = isSafeKey(k) ? `.${k}` : `['${k.replace(/'/g, "\\'")}']`
      const fullPath = `$.body${childSegment}`
      const isExisting = existing.has(k)
      const value = src.data[k]
      if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
        // 嵌套对象 → 可展开子节点
        const subTree = buildTreeData(value, childSegment, '$.body', k, 1)
        // 标记嵌套对象顶部节点
        if (isExisting) {
          subTree.title = `${subTree.title} (已添加)`
          subTree.selectable = false
          subTree.class = 'tree-node-existing'
        }
        children.push(subTree)
      } else {
        // 基本类型 → 叶节点
        let title = `${k}`
        if (typeof value === 'string') {
          const preview = value.length > 30 ? value.substring(0, 30) + '...' : value
          title = `${k} : "${preview}"`
        } else if (value !== null && value !== undefined) {
          title = `${k} : ${value}`
        }
        children.push({
          key: fullPath,
          displayKey: k,
          title: isExisting ? `${title} (已添加)` : title,
          isLeaf: true,
          children: [],
          valueType: typeof value,
          selectable: !isExisting,
          class: isExisting ? 'tree-node-existing' : '',
          jsonpath: fullPath,
        })
      }
    }
  } else {
    // 多 source — 每个作为顶层节点
    for (const src of sources) {
      children.push(buildTreeData(src.data, `.${src.label}`, '$', src.label, 0))
    }
  }

  return children
})

function onSelect(selectedKeys) {
  if (selectedKeys.length > 0) {
    const path = selectedKeys[0]
    if (!path || path.endsWith('__truncated__') || path.endsWith('__non_json__')) return
    // 根据 sourceField 提取合适的 key：
    // headers/query_params: 提取最后一段 leaf key
    // body_fields: 去掉 $.body. 前缀，保留路径（支持嵌套字段如 user.name）
    let key
    if (props.sourceField === 'body_fields') {
      // 去掉 $.body. 前缀
      key = path.replace(/^\$\.body\.?/, '').replace(/^\$\['body'\]\.?/, '')
      if (!key) key = extractLeafKey(path)
    } else {
      key = extractLeafKey(path)
    }
    emit('select', { key, jsonpath: path })
    popoverVisible.value = false
  }
}

function onCustomKeySubmit() {
  const k = customKey.value.trim()
  if (!k) return
  if (props.existingKeys.includes(k)) return  // 已存在则跳过
  emit('select', { key: k, jsonpath: null })
  customKey.value = ''
  popoverVisible.value = false
}
</script>

<style scoped>
.json-tree-container {
  max-height: 360px;
  overflow-y: auto;
}

.json-tree-container :deep(.ant-tree-node-content-wrapper) {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
}

.json-tree-container :deep(.ant-tree-node-content-wrapper.tree-node-existing) {
  color: #bfbfbf;
  cursor: not-allowed;
}

.tree-empty {
  padding: 20px 0;
  min-width: 200px;
}

.custom-key-row {
  display: flex;
  gap: 6px;
  align-items: center;
}
</style>