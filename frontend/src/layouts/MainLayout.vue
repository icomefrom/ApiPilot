<template>
  <a-layout style="min-height: 100vh">
    <a-layout-sider v-model:collapsed="collapsed" collapsible>
      <div class="logo">
        <h2 v-if="!collapsed">缺陷猎手</h2>
        <h2 v-else>BS</h2>
      </div>
      <a-menu
        v-model:selectedKeys="selectedKeys"
        theme="dark"
        mode="inline"
        @click="handleMenuClick"
      >
        <a-menu-item
          v-for="menu in menus"
          :key="menu.path"
        >
          <component :is="menu.icon" />
          <span>{{ menu.title }}</span>
        </a-menu-item>
      </a-menu>
    </a-layout-sider>

    <a-layout>
      <a-layout-header class="header">
        <div class="header-left">
          <a-breadcrumb>
            <a-breadcrumb-item>
              <router-link to="/">首页</router-link>
            </a-breadcrumb-item>
            <a-breadcrumb-item v-if="currentRoute?.meta?.title">
              {{ currentRoute.meta.title }}
            </a-breadcrumb-item>
          </a-breadcrumb>
        </div>
        <div class="header-right">
          <div class="project-switcher">
            <a-select
              v-model:value="projectStore.activeProjectId"
              placeholder="选择项目"
              style="width: 160px"
              size="small"
              :loading="projectStore.loading"
              @change="handleProjectChange"
            >
              <a-select-option v-for="project in projectStore.projects" :key="project.id" :value="project.id">
                <span class="project-option">
                  <span class="project-option-name">{{ project.name }}</span>
                  <DeleteOutlined
                    v-if="project.role === 'owner' && !isDefaultProject(project)"
                    class="project-option-delete"
                    title="删除项目"
                    @click.stop="handleDeleteProject(project)"
                  />
                </span>
              </a-select-option>
            </a-select>
            <a-button type="link" size="small" @click="openCreateProject" title="新建项目">
              <PlusOutlined />
            </a-button>
            <a-button type="link" size="small" :disabled="!projectStore.activeProjectId" @click="openMemberManager" title="项目成员">
              <TeamOutlined />
            </a-button>
          </div>

          <!-- 环境切换 -->
          <div class="env-switcher">
            <a-select
              v-model:value="envStore.activeEnvironmentId"
              placeholder="选择环境"
              style="width: 140px"
              size="small"
              :allowClear="true"
              @change="handleEnvChange"
            >
              <a-select-option v-for="env in envStore.environments" :key="env.id" :value="env.id">
                {{ env.name }}
              </a-select-option>
            </a-select>
            <a-button type="link" size="small" @click="openEnvManager">
              <SettingOutlined />
            </a-button>
          </div>

          <a-dropdown>
            <a class="user-info" @click.prevent>
              <a-avatar :size="28" style="background-color: #1890ff">
                {{ userStore.userInfo?.username?.charAt(0)?.toUpperCase() }}
              </a-avatar>
              <span class="username">{{ userStore.userInfo?.username }}</span>
            </a>
            <template #overlay>
              <a-menu>
                <a-menu-item @click="$router.push('/profile')">
                  <ProfileOutlined /> 个人信息
                </a-menu-item>
                <a-menu-divider />
                <a-menu-item @click="handleLogout">
                  <LogoutOutlined /> 退出登录
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>

      <a-layout-content class="content">
        <router-view />
      </a-layout-content>
    </a-layout>

    <EnvironmentManager ref="envManagerRef" @close="onEnvManagerClose" />

    <a-modal
      v-model:open="memberModalVisible"
      title="项目成员"
      :footer="null"
      :width="720"
      @cancel="resetInviteForm"
    >
      <div class="member-panel">
        <div class="invite-row" v-if="projectStore.canManage">
          <a-input
            v-model:value="inviteForm.user"
            placeholder="用户名或邮箱"
            style="flex: 1"
          />
          <a-select v-model:value="inviteForm.role" style="width: 120px">
            <a-select-option value="owner">Owner</a-select-option>
            <a-select-option value="admin">Admin</a-select-option>
            <a-select-option value="editor">Editor</a-select-option>
            <a-select-option value="viewer">Viewer</a-select-option>
          </a-select>
          <a-button type="primary" :loading="memberSubmitting" @click="handleInviteMember">邀请</a-button>
        </div>

        <a-table
          size="small"
          row-key="id"
          :loading="projectStore.membersLoading"
          :pagination="false"
          :data-source="projectStore.members"
        >
          <a-table-column title="用户" data-index="username">
            <template #default="{ record }">
              <div class="member-user">
                <span>{{ record.username }}</span>
                <small>{{ record.email || '无邮箱' }}</small>
              </div>
            </template>
          </a-table-column>
          <a-table-column title="角色" data-index="role" width="150">
            <template #default="{ record }">
              <a-select
                v-if="projectStore.canManage"
                :value="record.role"
                size="small"
                style="width: 120px"
                @change="role => handleRoleChange(record, role)"
              >
                <a-select-option value="owner">Owner</a-select-option>
                <a-select-option value="admin">Admin</a-select-option>
                <a-select-option value="editor">Editor</a-select-option>
                <a-select-option value="viewer">Viewer</a-select-option>
              </a-select>
              <a-tag v-else>{{ roleLabel(record.role) }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="加入时间" data-index="joined_at" width="180">
            <template #default="{ record }">{{ formatDate(record.joined_at) }}</template>
          </a-table-column>
          <a-table-column v-if="projectStore.canManage" title="操作" width="90">
            <template #default="{ record }">
              <a-button type="link" danger size="small" @click="handleRemoveMember(record)">移除</a-button>
            </template>
          </a-table-column>
        </a-table>
      </div>
    </a-modal>
  </a-layout>
</template>

<script setup>
import { ref, computed, onMounted, h } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  ProfileOutlined,
  LogoutOutlined,
  ApiOutlined,
  ApartmentOutlined,
  SettingOutlined,
  PlusOutlined,
  TeamOutlined,
  DeleteOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import { Modal, message } from 'ant-design-vue'
import { useUserStore } from '../stores/user'
import { useEnvironmentStore } from '../stores/environment'
import { useProjectStore } from '../stores/project'
import { authApi } from '../api/auth'
import EnvironmentManager from '../views/debug/EnvironmentManager.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const envStore = useEnvironmentStore()
const projectStore = useProjectStore()
const collapsed = ref(false)
const envManagerRef = ref(null)
const memberModalVisible = ref(false)
const memberSubmitting = ref(false)
const inviteForm = ref({ user: '', role: 'viewer' })

const menus = [
  { path: '/debug', title: '接口测试', icon: ApiOutlined },
  { path: '/chain-test', title: '链路测试', icon: ApartmentOutlined },
  { path: '/agent-planner', title: 'Agent 编排', icon: ThunderboltOutlined },
]

const selectedKeys = computed(() => [route.path])

const currentRoute = computed(() => route)

onMounted(async () => {
  if (userStore.isLoggedIn && !userStore.userInfo) {
    await userStore.fetchProfile()
  }
  await projectStore.fetchProjects()
  // 加载环境列表并恢复选择
  await envStore.fetchEnvironments()
  envStore.restoreActiveEnvironment()
})

function handleMenuClick({ key }) {
  router.push(key)
}

function roleLabel(role) {
  const labels = { owner: 'Owner', admin: 'Admin', editor: 'Editor', viewer: 'Viewer' }
  return labels[role] || role
}

function formatDate(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function resetInviteForm() {
  inviteForm.value = { user: '', role: 'viewer' }
}

async function openMemberManager() {
  if (!projectStore.activeProjectId) return
  memberModalVisible.value = true
  await projectStore.fetchMembers(projectStore.activeProjectId)
}

async function handleInviteMember() {
  const user = inviteForm.value.user.trim()
  if (!user) {
    message.warning('请输入用户名或邮箱')
    return
  }
  memberSubmitting.value = true
  try {
    await projectStore.inviteMember(projectStore.activeProjectId, {
      user,
      role: inviteForm.value.role,
    })
    resetInviteForm()
    message.success('成员已加入项目')
  } finally {
    memberSubmitting.value = false
  }
}

async function handleRoleChange(member, role) {
  if (member.role === role) return
  await projectStore.updateMemberRole(projectStore.activeProjectId, member.id, role)
  message.success('角色已更新')
}

function handleRemoveMember(member) {
  Modal.confirm({
    title: '移除成员',
    content: `确定要移除 ${member.username} 吗？`,
    async onOk() {
      await projectStore.removeMember(projectStore.activeProjectId, member.id)
      message.success('成员已移除')
    },
  })
}

function isDefaultProject(project) {
  return project?.name === '默认项目' && [
    '系统自动创建的默认项目',
    '迁移已有个人数据时自动创建的项目',
  ].includes(project?.description || '')
}

function handleDeleteProject(project) {
  if (!project) return
  if (isDefaultProject(project)) {
    message.warning('默认项目不能删除')
    return
  }
  Modal.confirm({
    title: '删除项目',
    content: `确定要删除项目「${project.name}」吗？该操作会删除项目下的接口、环境、链路和执行记录。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await projectStore.deleteProject(project.id)
      envStore.setActiveEnvironment(null)
      await envStore.fetchEnvironments()
      window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: projectStore.activeProjectId } }))
      message.success('项目已删除')
    },
  })
}

function handleProjectChange(value) {
  projectStore.setActiveProject(value)
  envStore.setActiveEnvironment(null)
  envStore.fetchEnvironments()
  window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: value } }))
}

function openCreateProject() {
  let projectName = ''
  Modal.confirm({
    title: '新建项目',
    content: () => h('input', {
      class: 'ant-input',
      placeholder: '项目名称',
      onInput: (event) => { projectName = event.target.value },
    }),
    async onOk() {
      const name = projectName.trim()
      if (!name) {
        message.warning('请输入项目名称')
        return Promise.reject(new Error('empty project name'))
      }
      await projectStore.createProject({ name })
      await envStore.fetchEnvironments()
      window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: projectStore.activeProjectId } }))
    },
  })
}

function handleEnvChange(value) {
  envStore.setActiveEnvironment(value)
}

function openEnvManager() {
  envManagerRef.value?.open()
}

function onEnvManagerClose() {
  // 刷新环境列表
  envStore.fetchEnvironments()
}

function handleLogout() {
  Modal.confirm({
    title: '确认退出',
    content: '确定要退出登录吗？',
    async onOk() {
      try {
        await authApi.logout(userStore.refreshToken)
      } catch (e) {
        // 忽略登出错误
      }
      userStore.logout()
      router.push('/login')
    },
  })
}
</script>

<style scoped>
.logo {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.logo h2 {
  margin: 0;
  color: #fff;
  font-size: 18px;
  white-space: nowrap;
}

.header {
  background: #fff;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

.header-left {
  flex: 1;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.project-switcher,
.env-switcher {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-right: 8px;
}

.project-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
}

.project-option-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-option-delete {
  flex-shrink: 0;
  color: #ff4d4f;
  opacity: 0.8;
}

.project-option-delete:hover {
  opacity: 1;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #333;
  cursor: pointer;
}

.username {
  font-size: 14px;
}

.member-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.invite-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.member-user {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}

.member-user small {
  color: #8c8c8c;
}

.content {
  margin: 24px;
  padding: 24px;
  background: #fff;
  border-radius: 4px;
  min-height: 280px;
}
</style>