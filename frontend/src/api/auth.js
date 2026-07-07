import request from '../utils/request'

export const authApi = {
  login(username, password) {
    return request.post('/api/auth/login/', { username, password })
  },

  register(data) {
    return request.post('/api/auth/register/', data)
  },

  logout(refreshToken) {
    return request.post('/api/auth/logout/', { refresh: refreshToken })
  },

  getProfile() {
    return request.get('/api/auth/profile/')
  },

  updateProfile(data) {
    return request.put('/api/auth/profile/', data)
  },

  changePassword(oldPassword, newPassword) {
    return request.post('/api/auth/change-password/', {
      old_password: oldPassword,
      new_password: newPassword,
    })
  },
}