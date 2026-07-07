import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useUserStore } from '../stores/user'

// Mock authApi module
const mockLogin = vi.fn()
const mockGetProfile = vi.fn()
const mockLogout = vi.fn()

vi.mock('../api/auth', () => ({
  authApi: {
    login: (...args) => mockLogin(...args),
    getProfile: (...args) => mockGetProfile(...args),
    logout: (...args) => mockLogout(...args),
  },
}))

describe('User Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('初始状态应该是未登录', () => {
    const store = useUserStore()
    expect(store.isLoggedIn).toBe(false)
    expect(store.token).toBe('')
    expect(store.userInfo).toBeNull()
  })

  it('登录成功后应保存token和用户信息', async () => {
    const mockResponse = {
      access: 'test-access-token',
      refresh: 'test-refresh-token',
      user: {
        id: 1,
        username: 'admin',
        email: 'admin@test.com',
      },
    }
    mockLogin.mockResolvedValue(mockResponse)

    const store = useUserStore()
    await store.login('admin', 'admin123')

    expect(store.isLoggedIn).toBe(true)
    expect(store.token).toBe('test-access-token')
    expect(store.userInfo.username).toBe('admin')
    expect(localStorage.getItem('access_token')).toBe('test-access-token')
  })

  it('登出后应清除所有状态', () => {
    const store = useUserStore()
    store.token = 'some-token'
    store.userInfo = { username: 'test' }
    localStorage.setItem('access_token', 'some-token')

    store.logout()

    expect(store.isLoggedIn).toBe(false)
    expect(store.token).toBe('')
    expect(store.userInfo).toBeNull()
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('fetchProfile 应更新用户信息', async () => {
    const mockProfile = {
      id: 1,
      username: 'admin',
      email: 'admin@test.com',
    }
    mockGetProfile.mockResolvedValue(mockProfile)

    const store = useUserStore()
    store.token = 'some-token'
    await store.fetchProfile()

    expect(store.userInfo.username).toBe('admin')
    expect(store.userInfo.email).toBe('admin@test.com')
  })

  it('登录后应存储 refresh token', async () => {
    const mockResponse = {
      access: 'access-abc',
      refresh: 'refresh-xyz',
      user: { id: 1, username: 'admin' },
    }
    mockLogin.mockResolvedValue(mockResponse)

    const store = useUserStore()
    await store.login('admin', 'admin123')

    expect(store.refreshToken).toBe('refresh-xyz')
    expect(localStorage.getItem('refresh_token')).toBe('refresh-xyz')
  })
})