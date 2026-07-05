import { ref, reactive } from 'vue'
import { defineStore } from 'pinia'
import { chainApi } from '../api/chain'
import { debugApi } from '../api/debug'

export const useChainStore = defineStore('chain', () => {
  // 链路列表
  const chains = ref([])
  const loading = ref(false)

  // 当前编辑的链路
  const currentChain = reactive({
    id: null,
    name: '',
    description: '',
    nodes: [],
    edges: [],
    globals: [],
    status: 'draft',
  })

  // 执行状态
  const executing = ref(false)
  const currentResult = ref(null)

  // 获取链路列表
  async function fetchChains(params = {}) {
    loading.value = true
    try {
      const data = await chainApi.getChains(params)
      chains.value = data.results || data
    } finally {
      loading.value = false
    }
  }

  // 设置当前链路
  async function setCurrentChain(chain) {
    // 列表数据可能不含完整 nodes/edges，拉取详情
    if (chain.id && (chain.nodes === undefined || chain.edges === undefined)) {
      try {
        chain = await chainApi.getChain(chain.id)
      } catch {
        // 拉取失败按已有数据填充
      }
    }
    currentChain.name = chain.name || ''
    currentChain.description = chain.description || ''
    currentChain.nodes = chain.nodes || []
    currentChain.edges = chain.edges || []
    currentChain.globals = chain.globals || []
    currentChain.status = chain.status || 'draft'
    currentChain.id = chain.id
    currentResult.value = null
    // 同步接口节点名称（接口可能已在调试页重命名）
    await syncInterfaceNames()
  }

  // 保存链路
  async function saveChain(data) {
    if (data.id) {
      return await chainApi.patchChain(data.id, data)
    }
    return await chainApi.createChain(data)
  }

  // 删除链路
  async function deleteChain(id) {
    await chainApi.deleteChain(id)
    await fetchChains()
  }

  // 执行链路
  async function executeChain(environmentId = null) {
    if (!currentChain.id) return null
    executing.value = true
    currentResult.value = null
    try {
      const data = await chainApi.executeChain(currentChain.id, environmentId)
      currentResult.value = data
      return data
    } finally {
      executing.value = false
    }
  }

  // 重置当前链路
  function resetCurrent() {
    currentChain.name = ''
    currentChain.description = ''
    currentChain.nodes = []
    currentChain.edges = []
    currentChain.globals = []
    currentChain.status = 'draft'
    currentChain.id = null
    currentResult.value = null
  }

  // 同步接口节点的名称（从后端接口表获取最新名称）
  async function syncInterfaceNames(updatedId) {
    const nodes = currentChain.nodes
    if (!nodes.length) return

    // 如果指定了单个接口 ID（从 saveInterface 触发），只更新该接口
    if (updatedId) {
      const node = nodes.find(n => n.type === 'interface' && n.data?.interface_id === updatedId)
      if (!node) return
      try {
        const detail = await debugApi.getInterface(updatedId)
        node.data.interface_name = `${detail.method} ${detail.name}`
        // 如果节点 label 还是旧名称，也同步更新
        if (node.data.label && node.data.label !== detail.name) {
          // 只在 label 和旧名称一致时自动替换（用户没手动改过 label）
          const oldName = node.data.interface_name?.replace(/^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+/, '')
          if (oldName && node.data.label === oldName) {
            node.data.label = detail.name
          }
        }
      } catch { /* ignore */ }
      return
    }

    // 批量同步：收集所有接口节点引用的 interface_id
    const interfaceIds = nodes
      .filter(n => n.type === 'interface' && n.data?.interface_id)
      .map(n => n.data.interface_id)

    if (!interfaceIds.length) return

    try {
      // 一次查询获取所有接口，构建 id→name 映射
      const data = await debugApi.getInterfaces({ limit: 200 })
      const list = data.results || data
      const nameMap = {}
      for (const itf of list) {
        nameMap[itf.id] = { name: itf.name, fullName: `${itf.method} ${itf.name}` }
      }

      for (const node of nodes) {
        if (node.type !== 'interface' || !node.data?.interface_id) continue
        const info = nameMap[node.data.interface_id]
        if (!info) continue

        // 更新 interface_name
        const oldInterfaceName = node.data.interface_name
        node.data.interface_name = info.fullName

        // 如果 label 对应旧名称，同步更新
        if (node.data.label) {
          const oldShortName = oldInterfaceName?.replace(/^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+/, '')
          if (oldShortName && node.data.label === oldShortName) {
            node.data.label = info.name
          } else if (node.data.label === oldInterfaceName) {
            node.data.label = info.fullName
          }
        }
      }
    } catch { /* ignore */ }
  }

  return {
    chains,
    loading,
    currentChain,
    executing,
    currentResult,
    fetchChains,
    setCurrentChain,
    saveChain,
    deleteChain,
    executeChain,
    resetCurrent,
    syncInterfaceNames,
  }
})