import request from '../utils/request'

export const debugApi = {
  // 接口 CRUD
  getInterfaces(params) {
    return request.get('/api/debug/interfaces/', { params })
  },
  getInterface(id) {
    return request.get(`/api/debug/interfaces/${id}/`)
  },
  createInterface(data) {
    return request.post('/api/debug/interfaces/', data)
  },
  updateInterface(id, data) {
    return request.put(`/api/debug/interfaces/${id}/`, data)
  },
  patchInterface(id, data) {
    return request.patch(`/api/debug/interfaces/${id}/`, data)
  },
  deleteInterface(id) {
    return request.delete(`/api/debug/interfaces/${id}/`)
  },

  // cURL 解析
  parseCurl(curlCommand) {
    return request.post('/api/debug/interfaces/parse-curl/', { curl_command: curlCommand })
  },

  // 调试执行（timeout 需覆盖后端执行耗时，额外加 10s 缓冲）
  executeSaved(id, timeout = 30, environmentId = null) {
    const data = {}
    if (environmentId) {
      data.environment_id = environmentId
    }
    return request.post(`/api/debug/interfaces/${id}/execute/`, data, {
      timeout: (timeout + 10) * 1000,
    })
  },
  executeAdhoc(data) {
    const timeout = data.timeout || 30
    return request.post('/api/debug/interfaces/execute/', data, {
      timeout: (timeout + 10) * 1000,
    })
  },

  // Postman Collection 导入
  importPostman(collection) {
    return request.post('/api/debug/interfaces/import-postman/', { collection }, {
      timeout: 60000,
    })
  },

  // 分组 CRUD
  getGroups(params) {
    return request.get('/api/debug/groups/', { params })
  },
  createGroup(data) {
    return request.post('/api/debug/groups/', data)
  },
  updateGroup(id, data) {
    return request.put(`/api/debug/groups/${id}/`, data)
  },
  deleteGroup(id) {
    return request.delete(`/api/debug/groups/${id}/`)
  },

  // 调试历史
  getResults(params) {
    return request.get('/api/debug/results/', { params })
  },
  getResult(id) {
    return request.get(`/api/debug/results/${id}/`)
  },

  // 脚本断言执行
  runAssertScript(data) {
    const timeout = ((data.timeout || 10) + 5) * 1000
    return request.post('/api/debug/interfaces/run-script/', data, { timeout })
  },
}