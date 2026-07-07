import request from '../utils/request'

export const environmentApi = {
  getEnvironments(params) {
    return request.get('/api/debug/environments/', { params })
  },
  getEnvironment(id) {
    return request.get(`/api/debug/environments/${id}/`)
  },
  createEnvironment(data) {
    return request.post('/api/debug/environments/', data)
  },
  updateEnvironment(id, data) {
    return request.put(`/api/debug/environments/${id}/`, data)
  },
  deleteEnvironment(id) {
    return request.delete(`/api/debug/environments/${id}/`)
  },
}