import axios from 'axios'
import { message } from 'ant-design-vue'
import { useUserStore } from '../stores/user'
import { useProjectStore } from '../stores/project'
import router from '../router'
import { t } from '../i18n'

const request = axios.create({
  baseURL: '',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器
request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    try {
      const projectStore = useProjectStore()
      if (projectStore.activeProjectId) {
        config.headers['X-Project-Id'] = projectStore.activeProjectId
      }
    } catch {
      const projectId = localStorage.getItem('active_project_id')
      if (projectId) {
        config.headers['X-Project-Id'] = projectId
      }
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器
request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const { response } = error

    if (response) {
      switch (response.status) {
        case 401:
          message.error(t('登录已过期，请重新登录'))
          const userStore = useUserStore()
          userStore.logout()
          router.push({ name: 'Login' })
          break
        case 403:
          message.error(t('没有操作权限'))
          break
        case 404:
          message.error(t('请求的资源不存在'))
          break
        case 400:
          const detail = response.data?.detail || response.data?.message || t('请求参数错误')
          // 处理 DRF 的字段验证错误
          if (typeof response.data === 'object' && !response.data.detail) {
            const errors = Object.values(response.data).flat().join('; ')
            message.error(errors || t('请求参数错误'))
          } else {
            message.error(detail)
          }
          break
        default:
          message.error(response.data?.detail || t('服务器错误'))
      }
    } else {
      message.error(t('网络连接失败'))
    }

    return Promise.reject(error)
  }
)

export default request
