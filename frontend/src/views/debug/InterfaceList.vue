<template>
  <div class="interface-list">
    <div class="search-row">
      <a-input
        v-model:value="searchText"
        placeholder="搜索接口..."
        size="small"
        allowClear
        @change="onSearch"
      >
        <template #prefix><SearchOutlined /></template>
      </a-input>
    </div>

    <!-- 分组 + 接口列表 -->
    <div class="list-content">
      <!-- 默认分组 -->
      <div class="group-section">
        <div class="group-header">
          <div class="group-toggle" @click="toggleGroup('__default__')">
            <RightOutlined :class="{ rotated: expandedGroups.has('__default__') }" />
            <span>默认分组</span>
            <span class="group-count">{{ ungrouped.length }}</span>
          </div>
          <a-dropdown :trigger="['click']">
            <span class="group-more" @click.stop>…</span>
            <template #overlay>
              <a-menu @click="({ key }) => onDefaultGroupMenuClick(key)">
                <a-menu-item key="newInterface"><PlusOutlined /> 新建接口</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
        <div v-show="expandedGroups.has('__default__')" class="group-items">
          <div
            v-for="item in ungrouped"
            :key="item.id"
            :class="['interface-item', { active: store.currentInterface.id === item.id }]"
            @click="selectItem(item)"
          >
            <span :class="['method-tag', `method-${(item.method || 'GET').toLowerCase()}`]">
              {{ item.method || 'GET' }}
            </span>
            <template v-if="editingId === item.id">
              <input
                ref="nameInputRef"
                v-model="editingName"
                class="name-input"
                @keydown.enter="saveName(item)"
                @keydown.escape="cancelEdit"
                @blur="saveName(item)"
                @click.stop
              />
            </template>
            <template v-else>
              <span class="item-name" :title="item.name" @dblclick.stop="startEdit(item)">{{ item.name }}</span>
            </template>
            <a-button type="text" size="small" class="action-btn" @click.stop="handleCopyLink(item)">
              <CopyOutlined />
            </a-button>
            <a-button type="text" danger size="small" class="action-btn" @click.stop="handleDelete(item)">
              <DeleteOutlined />
            </a-button>
          </div>
          <div v-if="!ungrouped.length" class="group-empty">暂无接口</div>
        </div>
      </div>

      <!-- 各分组（从 store.groups 驱动，空分组也显示） -->
      <div v-for="group in allGroups" :key="group.id" class="group-section">
        <div class="group-header">
          <div class="group-toggle" @click="toggleGroup(group.id)">
            <RightOutlined :class="{ rotated: expandedGroups.has(group.id) }" />
            <span class="group-name">{{ group.name }}</span>
            <span class="group-count">{{ getGroupItems(group.id).length }}</span>
          </div>
          <a-dropdown :trigger="['click']">
            <span class="group-more" @click.stop>…</span>
            <template #overlay>
              <a-menu @click="({ key }) => onGroupMenuClick(key, group)">
                <a-menu-item key="newInterface"><PlusOutlined /> 新建接口</a-menu-item>
                <a-menu-item key="rename"><EditOutlined /> 重命名</a-menu-item>
                <a-menu-item key="delete" class="menu-danger"><DeleteOutlined /> 删除分组</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
        <div v-show="expandedGroups.has(group.id)" class="group-items">
          <div
            v-for="item in getGroupItems(group.id)"
            :key="item.id"
            :class="['interface-item', { active: store.currentInterface.id === item.id }]"
            @click="selectItem(item)"
          >
            <span :class="['method-tag', `method-${(item.method || 'GET').toLowerCase()}`]">
              {{ item.method || 'GET' }}
            </span>
            <template v-if="editingId === item.id">
              <input
                ref="nameInputRef"
                v-model="editingName"
                class="name-input"
                @keydown.enter="saveName(item)"
                @keydown.escape="cancelEdit"
                @blur="saveName(item)"
                @click.stop
              />
            </template>
            <template v-else>
              <span class="item-name" :title="item.name" @dblclick.stop="startEdit(item)">{{ item.name }}</span>
            </template>
            <a-button type="text" size="small" class="action-btn" @click.stop="handleCopyLink(item)">
              <CopyOutlined />
            </a-button>
            <a-button type="text" danger size="small" class="action-btn" @click.stop="handleDelete(item)">
              <DeleteOutlined />
            </a-button>
          </div>
          <div v-if="!getGroupItems(group.id).length" class="group-empty">暂无接口</div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="!store.interfaces.length && !store.groups.length" class="empty-hint">
        暂无接口，点击上方导入
      </div>
    </div>

    </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted, h } from 'vue'
import { SearchOutlined, RightOutlined, DeleteOutlined, PlusOutlined, EditOutlined, CopyOutlined } from '@ant-design/icons-vue'
import { Modal, message } from 'ant-design-vue'
import { useDebugStore } from '../../stores/debug'
import { debugApi } from '../../api/debug'

const store = useDebugStore()
const searchText = ref('')
const expandedGroups = ref(new Set(['__default__']))
const renameValue = ref('')

// 内联编辑状态
const editingId = ref(null)
const editingName = ref('')
const nameInputRef = ref(null)

// 从 store.groups 驱动分组列表
const allGroups = computed(() => store.groups || [])

// 按分组 ID 归类接口
const interfacesByGroup = computed(() => {
  const map = {}
  for (const item of store.interfaces) {
    const gid = item.group
    if (gid) {
      if (!map[gid]) map[gid] = []
      map[gid].push(item)
    }
  }
  return map
})

function getGroupItems(groupId) {
  return interfacesByGroup.value[groupId] || []
}

// 未分组的接口
const ungrouped = computed(() => {
  return store.interfaces.filter(item => !item.group)
})

function toggleGroup(key) {
  const s = new Set(expandedGroups.value)
  if (s.has(key)) {
    s.delete(key)
  } else {
    s.add(key)
  }
  expandedGroups.value = s
}

function selectItem(item) {
  store.setCurrentInterface(item)
}

// ---- 接口名称内联编辑 ----

function startEdit(item) {
  editingId.value = item.id
  editingName.value = item.name
  nextTick(() => {
    const inputs = nameInputRef.value
    const input = Array.isArray(inputs) ? inputs[0] : inputs
    if (input) {
      input.focus()
      input.select()
    }
  })
}

function cancelEdit() {
  editingId.value = null
  editingName.value = ''
}

async function saveName(item) {
  if (editingId.value !== item.id) return // 防重复 blur
  const newName = editingName.value.trim()
  if (!newName || newName === item.name) {
    cancelEdit()
    return
  }
  try {
    await debugApi.patchInterface(item.id, { name: newName })
    item.name = newName
    // 如果当前正在编辑的就是这个接口，也同步 debug store
    if (store.currentInterface.id === item.id) {
      store.currentInterface.name = newName
    }
    // 通知链路编辑器同步接口名称
    window.dispatchEvent(new CustomEvent('interface-updated', {
      detail: { id: item.id, name: newName },
    }))
    message.success('接口名称已更新')
  } catch {
    message.error('名称修改失败')
  }
  cancelEdit()
}

function onDefaultGroupMenuClick(key) {
  if (key === 'newInterface') {
    store.resetCurrent()
    store.currentInterface.group = null
  }
}

function onGroupMenuClick(key, group) {
  if (key === 'newInterface') {
    store.resetCurrent()
    store.currentInterface.group = group.id
  } else if (key === 'rename') {
    renameValue.value = group.name
    Modal.confirm({
      title: '重命名分组',
      content: () => h('input', {
        value: renameValue.value,
        class: 'ant-input',
        style: 'margin-top:8px',
        placeholder: '输入新名称',
        onInput: (e) => { renameValue.value = e.target.value },
      }),
      async onOk() {
        const name = renameValue.value.trim()
        if (!name) {
          message.warning('名称不能为空')
          return
        }
        try {
          await store.saveGroup({ id: group.id, name })
          store.fetchGroups()
          message.success('重命名成功')
        } catch {
          // 全局拦截器已处理
        }
      },
    })
  } else if (key === 'delete') {
    const items = getGroupItems(group.id)
    Modal.confirm({
      title: '删除分组',
      content: items.length
        ? `分组「${group.name}」下有 ${items.length} 个接口，删除后接口将移至默认分组，确定删除？`
        : `确定删除分组「${group.name}」吗？`,
      async onOk() {
        try {
          // 先把该分组下的接口移到默认分组
          for (const item of items) {
            await debugApi.patchInterface(item.id, { group: null })
          }
          await store.deleteGroup(group.id)
          store.fetchGroups()
          store.fetchInterfaces()
          message.success('分组已删除')
        } catch {
          // 全局拦截器已处理
        }
      },
    })
  }
}

async function handleDelete(item) {
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除接口「${item.name}」吗？`,
    async onOk() {
      await store.deleteInterface(item.id)
      if (store.currentInterface.id === item.id) {
        store.resetCurrent()
      }
      message.success('已删除')
    },
  })
}

function handleCopyLink(item) {
  const url = item.url || ''
  if (!url) {
    message.warning('该接口没有请求地址')
    return
  }
  navigator.clipboard.writeText(url).then(() => {
    message.success('链接已复制')
  }).catch(() => {
    message.error('复制失败')
  })
}

let searchTimer = null
function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    store.fetchInterfaces({ search: searchText.value })
  }, 300)
}

onMounted(() => {
  store.fetchInterfaces()
  store.fetchGroups()
  // 监听新分组创建事件，自动展开
  function onGroupCreated(e) {
    const s = new Set(expandedGroups.value)
    s.add(e.detail)
    expandedGroups.value = s
  }
  window.addEventListener('group-created', onGroupCreated)
  onUnmounted(() => {
    window.removeEventListener('group-created', onGroupCreated)
  })
})
</script>

<style scoped>
.interface-list {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.search-row {
  display: flex;
  gap: 4px;
  align-items: center;
}

.list-content {
  flex: 1;
  overflow-y: auto;
  margin-top: 8px;
}

.group-section {
  margin-bottom: 4px;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  font-size: 12px;
  font-weight: 600;
  color: #595959;
  border-radius: 4px;
  user-select: none;
}

.group-header:hover {
  background: #f5f5f5;
}

.group-header:hover .group-more {
  opacity: 1;
}

.group-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  cursor: pointer;
  min-width: 0;
}

.group-toggle .anticon {
  font-size: 10px;
  transition: transform 0.2s;
  flex-shrink: 0;
}

.group-toggle .anticon.rotated {
  transform: rotate(90deg);
}

.group-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-count {
  font-size: 11px;
  color: #8c8c8c;
  font-weight: normal;
}

.group-more {
  opacity: 0;
  font-size: 14px;
  font-weight: 700;
  color: #8c8c8c;
  padding: 0 4px;
  border-radius: 4px;
  line-height: 18px;
  flex-shrink: 0;
  transition: opacity 0.2s;
}

.group-more:hover {
  color: #1890ff;
  background: #e6f7ff;
}

.group-items {
  padding-left: 8px;
}

.group-empty {
  padding: 4px 8px 4px 28px;
  font-size: 11px;
  color: #bfbfbf;
}

.interface-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  cursor: pointer;
  border-radius: 4px;
  font-size: 12px;
  transition: background 0.2s;
}

.interface-item:hover {
  background: #e6f7ff;
}

.interface-item.active {
  background: #bae7ff;
}

.method-tag {
  font-size: 10px;
  font-weight: 700;
  padding: 0 4px;
  border-radius: 2px;
  line-height: 18px;
  flex-shrink: 0;
  min-width: 36px;
  text-align: center;
}

.method-get { background: #f6ffed; color: #52c41a; }
.method-post { background: #e6f7ff; color: #1890ff; }
.method-put { background: #fffbe6; color: #faad14; }
.method-delete { background: #fff2f0; color: #ff4d4f; }
.method-patch { background: #f9f0ff; color: #722ed1; }
.method-head, .method-options { background: #f5f5f5; color: #8c8c8c; }

.item-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #333;
  cursor: text;
}

.name-input {
  flex: 1;
  min-width: 0;
  border: 1px solid #1890ff;
  border-radius: 3px;
  padding: 1px 6px;
  font-size: 12px;
  line-height: 18px;
  outline: none;
  background: #fff;
}

.action-btn {
  opacity: 0;
  flex-shrink: 0;
}

.interface-item:hover .action-btn {
  opacity: 1;
}

.empty-hint {
  text-align: center;
  color: #bfbfbf;
  padding: 24px 0;
  font-size: 12px;
}
</style>

<style>
.menu-danger {
  color: #ff4d4f !important;
}
</style>