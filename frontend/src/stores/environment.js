import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { environmentApi } from '../api/environment'

export const useEnvironmentStore = defineStore('environment', () => {
  // 环境列表
  const environments = ref([])
  // 当前选中的环境 ID
  const activeEnvironmentId = ref(null)
  const loading = ref(false)

  // 当前激活环境的变量（格式: {key: value}）
  const activeEnvVars = computed(() => {
    if (!activeEnvironmentId.value) return {}
    const env = environments.value.find(e => e.id === activeEnvironmentId.value)
    if (!env || !env.variables) return {}
    // variables 可能是数组 [{key, value}] 或对象 {key: value}
    if (Array.isArray(env.variables)) {
      const result = {}
      for (const item of env.variables) {
        if (item.key) {
          result[item.key] = item.value ?? ''
        }
      }
      return result
    }
    return env.variables
  })

  // 当前激活环境的名称
  const activeEnvName = computed(() => {
    if (!activeEnvironmentId.value) return '无环境'
    const env = environments.value.find(e => e.id === activeEnvironmentId.value)
    return env ? env.name : '无环境'
  })

  // 获取环境列表
  async function fetchEnvironments() {
    loading.value = true
    try {
      const data = await environmentApi.getEnvironments()
      environments.value = data.results || data
    } finally {
      loading.value = false
    }
  }

  // 选择环境
  function setActiveEnvironment(id) {
    activeEnvironmentId.value = id
    // 持久化选择
    if (id) {
      localStorage.setItem('active_environment_id', id)
    } else {
      localStorage.removeItem('active_environment_id')
    }
  }

  // 恢复环境选择
  function restoreActiveEnvironment() {
    const savedId = localStorage.getItem('active_environment_id')
    if (savedId) {
      const id = parseInt(savedId, 10)
      if (environments.value.some(e => e.id === id)) {
        activeEnvironmentId.value = id
      } else {
        localStorage.removeItem('active_environment_id')
      }
    }
  }

  // 保存环境
  async function saveEnvironment(data) {
    if (data.id) {
      return await environmentApi.updateEnvironment(data.id, data)
    }
    return await environmentApi.createEnvironment(data)
  }

  // 删除环境
  async function deleteEnvironment(id) {
    await environmentApi.deleteEnvironment(id)
    if (activeEnvironmentId.value === id) {
      setActiveEnvironment(null)
    }
    await fetchEnvironments()
  }

  return {
    environments,
    activeEnvironmentId,
    activeEnvVars,
    activeEnvName,
    loading,
    fetchEnvironments,
    setActiveEnvironment,
    restoreActiveEnvironment,
    saveEnvironment,
    deleteEnvironment,
  }
})