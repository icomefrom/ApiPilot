import { ref } from 'vue'
import { defineStore } from 'pinia'
import { mockApi } from '../api/mock'

export const useMockStore = defineStore('mock', () => {
  // interfaceId → mockRule 映射
  const mockRules = ref(new Map())
  const loading = ref(false)

  // 加载指定接口的 Mock 规则
  async function loadMockRule(interfaceId) {
    if (!interfaceId) return null
    loading.value = true
    try {
      const res = await mockApi.getMockRuleByInterface(interfaceId)
      const rules = res.results || res
      if (rules.length) {
        mockRules.value.set(interfaceId, rules[0])
        return rules[0]
      } else {
        mockRules.value.delete(interfaceId)
        return null
      }
    } catch {
      return mockRules.value.get(interfaceId) || null
    } finally {
      loading.value = false
    }
  }

  // 保存 Mock 规则（创建或更新）
  async function saveMockRule(data) {
    let result
    if (data.id) {
      result = await mockApi.updateMockRule(data.id, data)
    } else {
      result = await mockApi.createMockRule(data)
    }
    mockRules.value.set(result.interface, result)
    return result
  }

  // 切换启用状态
  async function toggleMock(interfaceId) {
    const rule = mockRules.value.get(interfaceId)
    if (!rule) return null
    const updated = await mockApi.toggleMockRule(rule.id, !rule.enabled)
    mockRules.value.set(interfaceId, updated)
    return updated
  }

  // 删除 Mock 规则
  async function deleteMockRule(interfaceId) {
    const rule = mockRules.value.get(interfaceId)
    if (!rule) return
    await mockApi.deleteMockRule(rule.id)
    mockRules.value.delete(interfaceId)
  }

  // 检查接口是否启用 Mock
  function isMocked(interfaceId) {
    const rule = mockRules.value.get(interfaceId)
    return rule?.enabled === true
  }

  // 获取接口的 Mock 规则
  function getMockRule(interfaceId) {
    return mockRules.value.get(interfaceId) || null
  }

  // 清除缓存
  function clearRule(interfaceId) {
    mockRules.value.delete(interfaceId)
  }

  return {
    mockRules,
    loading,
    loadMockRule,
    saveMockRule,
    toggleMock,
    deleteMockRule,
    isMocked,
    getMockRule,
    clearRule,
  }
})
