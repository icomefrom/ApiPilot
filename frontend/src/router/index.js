import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '../stores/user'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/Register.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('../layouts/MainLayout.vue'),
    redirect: '/debug',
    children: [
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('../views/Profile.vue'),
        meta: { title: '个人信息', icon: 'ProfileOutlined' },
      },
      {
        path: 'debug',
        name: 'ApiDebug',
        component: () => import('../views/debug/ApiDebug.vue'),
        meta: { title: '接口测试', icon: 'ApiOutlined' },
      },
      {
        path: 'chain-test',
        name: 'ChainTest',
        component: () => import('../views/chain/ChainTest.vue'),
        meta: { title: '链路测试', icon: 'ApartmentOutlined' },
      },
      {
        path: 'agent-planner',
        name: 'AgentPlanner',
        component: () => import('../views/agent/AgentPlanner.vue'),
        meta: { title: 'Agent 编排', icon: 'ThunderboltOutlined' },
      },
    ],
  },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('../views/403.vue'),
    meta: { public: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const userStore = useUserStore()

  // 公开页面直接放行
  if (to.meta.public) {
    if (to.name === 'Login' && userStore.token) {
      next({ path: '/' })
      return
    }
    if (to.name === 'Register' && userStore.token) {
      next({ path: '/' })
      return
    }
    next()
    return
  }

  // 未登录跳转登录
  if (!userStore.token) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
    return
  }

  next()
})

export default router