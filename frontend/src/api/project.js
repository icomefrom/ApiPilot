import request from '../utils/request'

export const projectApi = {
  getProjects(params) {
    return request.get('/api/debug/projects/', { params })
  },
  getProject(id) {
    return request.get(`/api/debug/projects/${id}/`)
  },
  createProject(data) {
    return request.post('/api/debug/projects/', data)
  },
  updateProject(id, data) {
    return request.put(`/api/debug/projects/${id}/`, data)
  },
  deleteProject(id) {
    return request.delete(`/api/debug/projects/${id}/`)
  },
  getMembers(id) {
    return request.get(`/api/debug/projects/${id}/members/`)
  },
  inviteMember(id, data) {
    return request.post(`/api/debug/projects/${id}/members/invite/`, data)
  },
  updateMemberRole(id, memberId, role) {
    return request.patch(`/api/debug/projects/${id}/members/${memberId}/role/`, { role })
  },
  removeMember(id, memberId) {
    return request.delete(`/api/debug/projects/${id}/members/${memberId}/`)
  },
}
