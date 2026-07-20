import request from '../utils/request'

export const mockApi = {
  // 获取 Mock 规则列表
  getMockRules(params) {
    return request.get('/api/debug/mock-rules/', { params })
  },
  // 获取单个接口的 Mock 规则
  getMockRuleByInterface(interfaceId) {
    return request.get('/api/debug/mock-rules/', { params: { interface_id: interfaceId } })
  },
  // 创建 Mock 规则
  createMockRule(data) {
    return request.post('/api/debug/mock-rules/', data)
  },
  // 更新 Mock 规则
  updateMockRule(id, data) {
    return request.put(`/api/debug/mock-rules/${id}/`, data)
  },
  // 部分更新 Mock 规则（如切换启用状态）
  patchMockRule(id, data) {
    return request.patch(`/api/debug/mock-rules/${id}/`, data)
  },
  // 切换启用/禁用
  toggleMockRule(id, enabled) {
    return request.patch(`/api/debug/mock-rules/${id}/`, { enabled })
  },
  // 删除 Mock 规则
  deleteMockRule(id) {
    return request.delete(`/api/debug/mock-rules/${id}/`)
  },
}
