import { ref, reactive } from 'vue'
import { defineStore } from 'pinia'
import { debugApi } from '../api/debug'

export const useDebugStore = defineStore('debug', () => {
  // 接口列表
  const interfaces = ref([])
  const groups = ref([])
  const loading = ref(false)

  // 当前编辑的接口
  const currentInterface = reactive({
    id: null,
    name: '',
    protocol: 'http',
    method: 'GET',
    url: '',
    headers: {},
    query_params: {},
    body_type: 'none',
    body: '',
    ws_message: '',
    rpc_method: '',
    rpc_service: '',
    group: null,
    description: '',
    assertions: [],
  })

  // 调试结果
  const currentResult = ref(null)
  const executing = ref(false)

  // 获取接口列表
  async function fetchInterfaces(params = {}) {
    loading.value = true
    try {
      const data = await debugApi.getInterfaces(params)
      interfaces.value = data.results || data
    } finally {
      loading.value = false
    }
  }

  // 获取分组列表
  async function fetchGroups() {
    try {
      const data = await debugApi.getGroups()
      groups.value = data.results || data
    } catch {
      groups.value = []
    }
  }

  // 保存分组
  async function saveGroup(data) {
    if (data.id) {
      return await debugApi.updateGroup(data.id, data)
    }
    return await debugApi.createGroup(data)
  }

  // 删除分组
  async function deleteGroup(id) {
    await debugApi.deleteGroup(id)
  }

  // 保存接口
  async function saveInterface(data) {
    let result
    if (data.id) {
      result = await debugApi.updateInterface(data.id, data)
      // 通知链路编辑器同步接口名称
      window.dispatchEvent(new CustomEvent('interface-updated', {
        detail: { id: data.id, name: data.name },
      }))
    } else {
      result = await debugApi.createInterface(data)
    }
    return result
  }

  // 删除接口
  async function deleteInterface(id) {
    await debugApi.deleteInterface(id)
    await fetchInterfaces()
  }

  // 解析 cURL
  async function parseCurl(curlCommand) {
    return await debugApi.parseCurl(curlCommand)
  }

  // 执行调试
  async function executeInterface(itf, environmentId = null) {
    executing.value = true
    currentResult.value = null
    try {
      let data
      if (itf.id) {
        data = await debugApi.executeSaved(itf.id, itf.timeout, environmentId)
      } else {
        // 只传后端 DebugExecuteSerializer 需要的字段，避免多余字段导致校验失败
        const payload = {
          protocol: itf.protocol || 'http',
          method: itf.method || 'GET',
          url: itf.url,
          headers: itf.headers || {},
          query_params: itf.query_params || {},
          body_type: itf.body_type || 'none',
          body: itf.body || '',
          ws_message: itf.ws_message || '',
          rpc_method: itf.rpc_method || '',
          rpc_service: itf.rpc_service || '',
          timeout: itf.timeout || 30,
          assertions: itf.assertions || [],
        }
        if (environmentId) {
          payload.environment_id = environmentId
        }
        data = await debugApi.executeAdhoc(payload)
      }
      currentResult.value = data
      return data
    } catch (e) {
      // 请求失败时也展示错误结果，而非空白
      const errMsg = e?.response?.data?.detail || e?.response?.data?.message || e?.message || '请求失败'
      currentResult.value = {
        status: 'failed',
        status_code: null,
        response_body: null,
        response_headers: {},
        elapsed_ms: null,
        error_message: errMsg,
      }
      throw e
    } finally {
      executing.value = false
    }
  }

  // 重置当前接口
  function resetCurrent() {
    currentInterface.name = ''
    currentInterface.protocol = 'http'
    currentInterface.method = 'GET'
    currentInterface.url = ''
    currentInterface.headers = {}
    currentInterface.query_params = {}
    currentInterface.body_type = 'none'
    currentInterface.body = ''
    currentInterface.ws_message = ''
    currentInterface.rpc_method = ''
    currentInterface.rpc_service = ''
    currentInterface.group = null
    currentInterface.description = ''
    currentInterface.assertions = []
    currentInterface.id = null
    currentResult.value = null
  }

  // 从接口数据填充当前接口（支持列表摘要或完整详情）
  async function setCurrentInterface(itf) {
    // 列表数据不含 assertions，需拉取完整详情
    if (itf.id && itf.assertions === undefined) {
      try {
        const full = await debugApi.getInterface(itf.id)
        itf = full
      } catch {
        // 拉取失败时按已有数据填充，assertions 默认为空
      }
    }
    // 先赋值所有数据字段（含 assertions），再赋值 id
    // 这样 id watch 触发时 assertions 已经是最新的
    currentInterface.name = itf.name
    currentInterface.protocol = itf.protocol
    currentInterface.method = itf.method
    currentInterface.url = itf.url
    currentInterface.headers = itf.headers || {}
    currentInterface.query_params = itf.query_params || {}
    currentInterface.body_type = itf.body_type || 'none'
    currentInterface.body = itf.body || ''
    currentInterface.ws_message = itf.ws_message || ''
    currentInterface.rpc_method = itf.rpc_method || ''
    currentInterface.rpc_service = itf.rpc_service || ''
    currentInterface.group = itf.group
    currentInterface.description = itf.description || ''
    currentInterface.assertions = itf.assertions || []
    currentInterface.id = itf.id
    // 加载该接口最近一次执行结果
    currentResult.value = null
    if (itf.id) {
      try {
        const res = await debugApi.getResults({ interface_id: itf.id, limit: 1 })
        const results = res.results || res
        if (results.length) {
          currentResult.value = results[0]
        }
      } catch {
        // 加载失败不阻塞
      }
    }
  }

  // 从 cURL 解析结果填充
  function fillFromCurl(parsed) {
    currentInterface.protocol = 'http'
    currentInterface.method = parsed.method || 'GET'
    currentInterface.url = parsed.url || ''
    currentInterface.headers = parsed.headers || {}
    currentInterface.query_params = parsed.query_params || {}
    currentInterface.body_type = parsed.body_type || 'none'
    currentInterface.body = parsed.body || ''
    currentInterface.name = `${parsed.method} ${parsed.url || ''}`.substring(0, 200)
  }

  // 从 Postman 导入结果批量创建
  async function importFromPostman(data) {
    return await debugApi.importPostman(data)
  }

  return {
    interfaces,
    groups,
    loading,
    currentInterface,
    currentResult,
    executing,
    fetchInterfaces,
    fetchGroups,
    saveGroup,
    deleteGroup,
    saveInterface,
    deleteInterface,
    parseCurl,
    executeInterface,
    resetCurrent,
    setCurrentInterface,
    fillFromCurl,
    importFromPostman,
  }
})