import request from '../utils/request'

export const chainApi = {
  // 链路 CRUD
  getChains(params) {
    return request.get('/api/debug/chains/', { params })
  },
  getChain(id) {
    return request.get(`/api/debug/chains/${id}/`)
  },
  createChain(data) {
    return request.post('/api/debug/chains/', data)
  },
  updateChain(id, data) {
    return request.put(`/api/debug/chains/${id}/`, data)
  },
  patchChain(id, data) {
    return request.patch(`/api/debug/chains/${id}/`, data)
  },
  deleteChain(id) {
    return request.delete(`/api/debug/chains/${id}/`)
  },

  // 执行链路
  executeChain(id, environmentId = null) {
    const data = {}
    if (environmentId) {
      data.environment_id = environmentId
    }
    return request.post(`/api/debug/chains/${id}/execute/`, data, {
      timeout: 300000, // 链路可能较长，5分钟超时
    })
  },

  // 链路执行结果
  getChainResults(params) {
    return request.get('/api/debug/chain-results/', { params })
  },
  getChainResult(id) {
    return request.get(`/api/debug/chain-results/${id}/`)
  },
}