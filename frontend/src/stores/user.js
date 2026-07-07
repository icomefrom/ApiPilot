import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '../api/auth'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('access_token') || '')
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')
  const userInfo = ref(null)

  const isLoggedIn = computed(() => !!token.value)

  async function login(username, password) {
    const res = await authApi.login(username, password)
    token.value = res.access
    refreshToken.value = res.refresh
    userInfo.value = res.user
    localStorage.setItem('access_token', res.access)
    localStorage.setItem('refresh_token', res.refresh)
  }

  async function fetchProfile() {
    const res = await authApi.getProfile()
    userInfo.value = res
  }

  function logout() {
    token.value = ''
    refreshToken.value = ''
    userInfo.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  return {
    token, refreshToken, userInfo,
    isLoggedIn,
    login, fetchProfile, logout,
  }
})